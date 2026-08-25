"""
Leerverkaufsregister.

Oeffentlich gemeldet wird ab 0,5 Prozent des Grundkapitals. Faellt eine
Position darunter, verschwindet sie kurz darauf aus dem aktuellen
Register — deshalb legt dieses Modul bei jedem Lauf einen Schnappschuss
unter docs/history/ ab. Aus dem Vergleich zweier Schnappschuesse
entstehen die Statusangaben neu / aufgestockt / reduziert / geschlossen.

Die Registerseiten unterscheiden sich stark und aendern gelegentlich
ihren Aufbau. Deshalb sucht dieses Modul nicht nach festen Spalten,
sondern durchsucht ALLE Tabellen einer Seite nach dem Muster
"Text, Text, Prozentzahl". Schlaegt auch das fehl, schreibt es eine
Diagnosezeile ins Protokoll, damit man ohne Raten nachbessern kann.
"""
import io, re, datetime as dt
import pandas as pd
from bs4 import BeautifulSoup
from util import get, json_lesen, json_schreiben, HIST, log

PROZENT = re.compile(r"^-?\d{1,2}[.,]\d{1,4}\s*%?$")
DATUM = re.compile(r"(\d{4}-\d{2}-\d{2})|(\d{2}[./]\d{2}[./]\d{4})")


def _zahl(s):
    s = str(s).strip().replace("%", "").replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return abs(float(s))


def _datum(s):
    m = DATUM.search(str(s))
    if not m:
        return ""
    if m.group(1):
        return m.group(1)
    t = re.split(r"[./]", m.group(2))
    return f"{t[2]}-{t[1]}-{t[0]}"


def _aus_tabellen(html, land, quelle):
    """
    Generischer Parser: nimmt jede Tabelle, in der eine Spalte durchgehend
    wie ein Prozentwert aussieht, und deutet die beiden laengsten
    Textspalten links davon als Halter und Emittent.
    """
    suppe = BeautifulSoup(html, "lxml")
    tabellen = suppe.find_all("table")
    if not tabellen:
        log.warning("%s: keine Tabelle im HTML (%d Zeichen, %d Formulare) — "
                    "Seite ist vermutlich JavaScript-getrieben",
                    quelle, len(html), len(suppe.find_all("form")))
        return []

    raus = []
    for tab in tabellen:
        zeilen = []
        for tr in tab.find_all("tr"):
            zellen = [td.get_text(" ", strip=True)
                      for td in tr.find_all(["td", "th"])]
            if len(zellen) >= 3:
                zeilen.append(zellen)
        if len(zeilen) < 2:
            continue

        breite = min(len(z) for z in zeilen)
        # Welche Spalte enthaelt in der Mehrzahl der Zeilen einen Prozentwert?
        i_pct = None
        for i in range(breite):
            treffer = sum(1 for z in zeilen[1:] if PROZENT.match(z[i].strip()))
            if treffer >= max(1, len(zeilen[1:]) * 0.6):
                i_pct = i
                break
        if i_pct is None:
            continue

        text_spalten = [i for i in range(breite) if i != i_pct]
        if len(text_spalten) < 2:
            continue
        i_h, i_e = text_spalten[0], text_spalten[1]
        i_d = text_spalten[-1] if len(text_spalten) > 2 else None

        for z in zeilen[1:]:
            try:
                pct = _zahl(z[i_pct])
            except Exception:
                continue
            if not (0.1 <= pct <= 25):
                continue
            halter, emittent = z[i_h].strip(), z[i_e].strip()
            if not halter or not emittent:
                continue
            raus.append({"land": land, "halter": halter[:70],
                         "emittent": emittent[:60], "prozent": round(pct, 2),
                         "datum": _datum(z[i_d]) if i_d is not None else ""})
        if raus:
            break

    if not raus:
        log.warning("%s: %d Tabellen gefunden, aber keine mit Prozentspalte",
                    quelle, len(tabellen))
    return raus


def _fca(url):
    r = get(url)
    if not r:
        return []
    try:
        blaetter = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
    except Exception as e:
        log.warning("FCA-Datei nicht lesbar: %s", e)
        return []

    raus = []
    for name, df in blaetter.items():
        if df.empty:
            continue
        sp = {str(c).lower(): c for c in df.columns}
        def finde(*schluessel):
            for k in schluessel:
                for low, orig in sp.items():
                    if k in low:
                        return orig
            return None
        c_h = finde("position holder", "holder")
        c_e = finde("name of the share issuer", "issuer", "share")
        c_p = finde("net short position", "net short", "%")
        c_d = finde("position date", "date")
        if not all([c_h, c_e, c_p]):
            continue
        for _, z in df.iterrows():
            try:
                pct = _zahl(z[c_p])
            except Exception:
                continue
            if not (0.1 <= pct <= 25):
                continue
            raus.append({"land": "UK", "halter": str(z[c_h]).strip()[:70],
                         "emittent": str(z[c_e]).strip()[:60],
                         "prozent": round(pct, 2),
                         "datum": _datum(z[c_d]) if c_d else ""})
        if "current" in str(name).lower() and raus:
            break
    return raus


def _seite(url, land, quelle):
    r = get(url)
    if not r:
        return []
    return _aus_tabellen(r.text, land, quelle)


def holen(konf):
    reg = konf.get("register", {})
    alle = []
    aufgaben = [
        ("fca", lambda u: _fca(u)),
        ("afm", lambda u: _seite(u, "NL", "AFM")),
        ("bundesanzeiger", lambda u: _seite(u, "DE", "Bundesanzeiger")),
        ("amf", lambda u: _seite(u, "FR", "AMF")),
    ]
    for name, fn in aufgaben:
        if not reg.get(name):
            continue
        try:
            teil = fn(reg[name])
        except Exception as e:
            log.warning("Register %s: %s", name, e)
            teil = []
        log.info("Register %s: %d Positionen", name, len(teil))
        alle += teil

    if not alle:
        log.warning("Kein Register lieferte Daten. Die Statusangaben und "
                    "Kennzahlen bleiben deshalb leer.")
    return alle


def vergleichen(aktuell, watchlist):
    heute = dt.date.today().isoformat()
    json_schreiben(HIST / f"shorts-{heute}.json", aktuell)

    vorher = None
    for datei in sorted(HIST.glob("shorts-*.json"), reverse=True):
        if datei.stem != f"shorts-{heute}":
            vorher = json_lesen(datei, [])
            break
    if vorher is None:
        for p in aktuell:
            p["status"], p["zuvor"] = "bestand", None
        return aktuell, []

    schl = lambda p: (p["halter"], p["emittent"])
    alt = {schl(p): p["prozent"] for p in vorher}
    ereignisse = []

    for p in aktuell:
        k = schl(p)
        if k not in alt:
            p["status"], p["zuvor"] = "neu", None
        elif p["prozent"] > alt[k] + 0.009:
            p["status"], p["zuvor"] = "aufgestockt", alt[k]
        elif p["prozent"] < alt[k] - 0.009:
            p["status"], p["zuvor"] = "reduziert", alt[k]
        else:
            p["status"], p["zuvor"] = "bestand", alt[k]
        if p["status"] in ("neu", "aufgestockt"):
            ereignisse.append(p)

    jetzt = {schl(p) for p in aktuell}
    for k, wert in alt.items():
        if k not in jetzt:
            g = {"halter": k[0], "emittent": k[1], "prozent": wert, "zuvor": wert,
                 "status": "geschlossen", "datum": heute, "land": ""}
            aktuell.append(g)
            ereignisse.append(g)

    rang = {"neu": 0, "aufgestockt": 1, "geschlossen": 2, "reduziert": 3, "bestand": 4}
    aktuell.sort(key=lambda p: (rang.get(p["status"], 9), -p["prozent"]))
    return aktuell, ereignisse


def kennzahlen(positionen):
    if not positionen:
        return {}
    je_emittent, je_halter = {}, {}
    for p in positionen:
        if p["status"] == "geschlossen":
            continue
        je_emittent[p["emittent"]] = je_emittent.get(p["emittent"], 0) + p["prozent"]
        je_halter[p["halter"]] = je_halter.get(p["halter"], 0) + 1
    top_e = max(je_emittent.items(), key=lambda x: x[1], default=("—", 0))
    top_h = max(je_halter.items(), key=lambda x: x[1], default=("—", 0))
    return {
        "neu_diese_woche": sum(1 for p in positionen if p["status"] == "neu"),
        "meistgeshortet": {"name": top_e[0], "summe": round(top_e[1], 2)},
        "aktivster_halter": {"name": top_h[0], "anzahl": top_h[1]},
        "gesamt": len([p for p in positionen if p["status"] != "geschlossen"]),
    }
