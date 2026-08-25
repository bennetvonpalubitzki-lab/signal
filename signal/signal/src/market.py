"""
Konsens-Matrix und Ticker-Profile.

Fuenf Quellen pro Wert, jede auf +1 / 0 / -1 reduziert:
  Analysten   — Verhaeltnis Kauf zu Verkauf (yfinance)
  Newsletter  — Stimmung in den Meldungen, in denen der Wert vorkommt
  Reddit      — Stimmungsverteilung aus social.py
  Insider     — Kaeufe gegen Verkaeufe der letzten 90 Tage
  Shorts      — Richtung der gemeldeten Leerverkaufspositionen

Einigkeit heisst meist: bereits eingepreist. Widerspruch heisst:
hier weiss jemand etwas, das ein anderer nicht weiss.
"""
from util import log


def _kennzahlen(t):
    try:
        i = t.info or {}
    except Exception:
        i = {}
    def zahl(x, teiler=1e9, einheit=" Mrd"):
        return f"{x/teiler:,.1f}{einheit}".replace(",", ".") if isinstance(x, (int, float)) else "—"
    return [
        ["Marktkap.", zahl(i.get("marketCap"))],
        ["KGV (erw.)", f"{i.get('forwardPE'):.1f}".replace(".", ",") if i.get("forwardPE") else "—"],
        ["Umsatzwachstum", f"{i.get('revenueGrowth')*100:+.0f} %" if i.get("revenueGrowth") else "—"],
        ["Kursziel", f"{i.get('targetMeanPrice'):.0f} {i.get('currency','')}" if i.get("targetMeanPrice") else "—"],
    ], i


def _analysten(t):
    try:
        df = t.recommendations
        if df is None or df.empty:
            return 0, "keine Daten"
        z = df.iloc[0]
        kauf = int(z.get("strongBuy", 0)) + int(z.get("buy", 0))
        halt = int(z.get("hold", 0))
        verk = int(z.get("sell", 0)) + int(z.get("strongSell", 0))
        text = f"{kauf} Kauf / {halt} Halten / {verk} Verkauf"
        if kauf + halt + verk == 0:
            return 0, "keine Daten"
        anteil = kauf / (kauf + halt + verk)
        return (1 if anteil > 0.6 else -1 if anteil < 0.3 else 0), text
    except Exception:
        return 0, "keine Daten"


def _insider(t):
    try:
        df = t.insider_transactions
        if df is None or df.empty:
            return 0, "keine Meldungen"
        sp = next((c for c in df.columns if "text" in c.lower() or "transaction" in c.lower()), None)
        if not sp:
            return 0, "keine Meldungen"
        arr = df[sp].astype(str).str.lower().head(25)
        k = int(arr.str.contains("buy|purchase").sum())
        v = int(arr.str.contains("sale|sell").sum())
        text = f"{k} Kaeufe / {v} Verkaeufe"
        return (1 if k > v else -1 if v > k else 0), text
    except Exception:
        return 0, "keine Meldungen"


def _shorts(sym, positionen):
    name = sym.split(".")[0].upper()
    passend = [p for p in positionen if name[:4] in p["emittent"].upper().replace(" ", "")[:12]]
    if not passend:
        return 0, "keine Meldung"
    summe = sum(p["prozent"] for p in passend if p["status"] != "geschlossen")
    auf = sum(1 for p in passend if p["status"] in ("neu", "aufgestockt"))
    ab = sum(1 for p in passend if p["status"] in ("reduziert", "geschlossen"))
    text = f"{summe:.2f} % ueber {len(passend)} Halter".replace(".", ",")
    # Aufbauende Shorts sind ein negatives Votum.
    return (-1 if auf > ab else 1 if ab > auf else 0), text


def _reddit(sym, gespraech):
    name = sym.split(".")[0].upper()
    e = next((g for g in gespraech if g["ticker"] == name), None)
    if not e:
        return 0, "kaum erwaehnt"
    text = f"{e['bullisch']} % bullisch, {e['erwaehnungen']} Erw."
    return (1 if e["bullisch"] >= 65 else -1 if e["bullisch"] <= 35 else 0), text


def _newsletter(sym, cluster):
    name = sym.split(".")[0].lower()
    treffer = [c for c in cluster if name in (c["titel"] + c["anriss"]).lower()]
    if not treffer:
        return 0, "nicht erwaehnt"
    return 0, f"in {len(treffer)} Clustern"


def bauen(konf, positionen, gespraech, cluster):
    import yfinance as yf
    zeilen, profile = [], {}

    for sym in konf.get("watchlist", []):
        try:
            t = yf.Ticker(sym)
            kpi, info = _kennzahlen(t)
        except Exception as e:
            log.warning("yfinance %s: %s", sym, e)
            continue

        quellen = {}
        quellen["Analysten"] = _analysten(t)
        quellen["Newsletter"] = _newsletter(sym, cluster)
        quellen["Reddit"] = _reddit(sym, gespraech)
        quellen["Insider"] = _insider(t)
        quellen["Shorts"] = _shorts(sym, positionen)

        werte = [v[0] for v in quellen.values()]
        aktive = [w for w in werte if w != 0]
        einig = len(set(aktive)) <= 1 and len(aktive) >= 3
        divergent = 1 in aktive and -1 in aktive

        zeilen.append({
            "ticker": sym,
            "name": info.get("shortName", sym),
            "region": "dach" if sym.endswith(".DE") else
                      "eu" if sym.endswith((".PA", ".AS", ".MI", ".MC")) else "us",
            "quellen": {k: v[0] for k, v in quellen.items()},
            "gruppe": "konsens" if einig else "divergenz" if divergent else "gemischt",
        })

        profile[sym] = {
            "ticker": sym,
            "name": info.get("shortName", sym),
            "wo": " · ".join(filter(None, [info.get("country"), info.get("sector"), info.get("city")])),
            "geschaeft": (info.get("longBusinessSummary") or "")[:600],
            "kpi": kpi,
            "quellen": [[k, v[1]] for k, v in quellen.items()],
        }

    rang = {"divergenz": 0, "konsens": 1, "gemischt": 2}
    zeilen.sort(key=lambda z: rang.get(z["gruppe"], 9))
    log.info("Matrix: %d Zeilen", len(zeilen))
    return zeilen, profile
