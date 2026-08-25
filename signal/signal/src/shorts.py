"""
Leerverkaufsregister.

Oeffentlich gemeldet wird ab 0,5 Prozent des Grundkapitals. Faellt eine
Position darunter, verschwindet sie kurz darauf aus dem aktuellen
Register — deshalb legt dieses Modul bei jedem Lauf einen Schnappschuss
unter docs/history/ ab. Aus dem Vergleich zweier Schnappschuesse
entstehen die Statusangaben neu / aufgestockt / reduziert / geschlossen.

Die Registerseiten aendern gelegentlich ihr Format. Faellt eine Quelle
aus, laeuft der Rest weiter und im Actions-Protokoll steht der Grund.
"""
import io, datetime as dt
import pandas as pd
from bs4 import BeautifulSoup
from util import get, json_lesen, json_schreiben, HIST, log


def _fca(url):
    r = get(url)
    if not r:
        return []
    try:
        df = pd.read_excel(io.BytesIO(r.content), sheet_name=0)
    except Exception as e:
        log.warning("FCA-Datei nicht lesbar: %s", e)
        return []
    sp = {c.lower(): c for c in df.columns}
    def s(*kandidaten):
        for k in kandidaten:
            for low, orig in sp.items():
                if k in low:
                    return orig
        return None
    c_h, c_e, c_p, c_d = s("holder","position holder"), s("issuer","name of the share"), s("net short"), s("date")
    if not all([c_h, c_e, c_p]):
        return []
    raus = []
    for _, z in df.iterrows():
        try:
            raus.append({"land": "UK", "halter": str(z[c_h]).strip(),
                         "emittent": str(z[c_e]).strip(),
                         "prozent": round(float(z[c_p]), 2),
                         "datum": str(z[c_d])[:10] if c_d else ""})
        except Exception:
            continue
    return raus


def _afm(url):
    r = get(url)
    if not r:
        return []
    tab = BeautifulSoup(r.text, "lxml").find("table")
    if not tab:
        log.warning("AFM: keine Tabelle gefunden — Seitenaufbau hat sich geaendert")
        return []
    raus = []
    for tr in tab.find_all("tr")[1:]:
        td = [t.get_text(strip=True) for t in tr.find_all("td")]
        if len(td) < 3:
            continue
        try:
            raus.append({"land": "NL", "halter": td[0], "emittent": td[1],
                         "prozent": round(float(td[2].replace("%","").replace(",",".")), 2),
                         "datum": td[3][:10] if len(td) > 3 else ""})
        except Exception:
            continue
    return raus


def _bundesanzeiger(url):
    """
    Der Bundesanzeiger liefert die Tabelle serverseitig. Sollte sich das
    aendern, faellt diese Quelle sauber aus, ohne den Lauf zu stoppen.
    """
    r = get(url)
    if not r:
        return []
    tab = BeautifulSoup(r.text, "lxml").find("table")
    if not tab:
        log.warning("Bundesanzeiger: keine Tabelle — bitte Adresse in config.yaml pruefen")
        return []
    raus = []
    for tr in tab.find_all("tr")[1:]:
        td = [t.get_text(strip=True) for t in tr.find_all("td")]
        if len(td) < 4:
            continue
        try:
            raus.append({"land": "DE", "halter": td[0], "emittent": td[1],
                         "prozent": round(float(td[2].replace(",", ".").replace("%","")), 2),
                         "datum": td[3][:10]})
        except Exception:
            continue
    return raus


def holen(konf):
    reg = konf.get("register", {})
    alle = []
    for name, fn in (("fca", _fca), ("afm", _afm), ("bundesanzeiger", _bundesanzeiger)):
        if reg.get(name):
            teil = fn(reg[name])
            log.info("Register %s: %d Positionen", name, len(teil))
            alle += teil
    return alle


def vergleichen(aktuell, watchlist):
    """Schnappschuss ablegen und gegen den letzten vergleichen."""
    heute = dt.date.today().isoformat()
    json_schreiben(HIST / f"shorts-{heute}.json", aktuell)

    vorher = None
    for datei in sorted(HIST.glob("shorts-*.json"), reverse=True):
        if datei.stem != f"shorts-{heute}":
            vorher = json_lesen(datei, [])
            break
    if vorher is None:
        # Erster Lauf: alles ist neu, aber das waere unbrauchbares Rauschen.
        for p in aktuell:
            p["status"] = "bestand"
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

    # Was gestern da war und heute fehlt, wurde unter 0,5 % abgebaut.
    jetzt = {schl(p) for p in aktuell}
    for k, wert in alt.items():
        if k not in jetzt:
            geschlossen = {"halter": k[0], "emittent": k[1], "prozent": wert,
                           "zuvor": wert, "status": "geschlossen",
                           "datum": heute, "land": ""}
            aktuell.append(geschlossen)
            ereignisse.append(geschlossen)

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
