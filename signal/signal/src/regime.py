"""
Regime-Anzeigen: Perzentilrang mehrerer Zeitreihen gegen die Historie.

Kein Modell, keine Gewichtung nach Gefuehl — jede Komponente wird
gefragt: wo stehst du im Vergleich zu dir selbst in den letzten
N Jahren? Der Mittelwert ist der Score.
"""
import datetime as dt
from util import env, get, perzentil, log

FRED = "https://api.stlouisfed.org/fred/series/observations"


def _fred(serie, jahre):
    key = env("FRED_API_KEY")
    if not key:
        return []
    start = (dt.date.today() - dt.timedelta(days=365 * jahre)).isoformat()
    r = get(FRED, params={"series_id": serie, "api_key": key, "file_type": "json",
                          "observation_start": start})
    if not r:
        return []
    werte = []
    for o in r.json().get("observations", []):
        try:
            werte.append(float(o["value"]))
        except (ValueError, KeyError):
            continue
    return werte


def _yf(symbol, jahre):
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period=f"{jahre}y", interval="1d")
        return list(h["Close"].dropna()) if not h.empty else []
    except Exception as e:
        log.warning("yfinance %s: %s", symbol, e)
        return []


def _ecb(schluessel, jahre):
    start = (dt.date.today() - dt.timedelta(days=365 * jahre)).isoformat()
    r = get(f"https://data-api.ecb.europa.eu/service/data/{schluessel.split('.')[0]}/"
            f"{'.'.join(schluessel.split('.')[1:])}",
            params={"startPeriod": start, "format": "csvdata"})
    if not r:
        return []
    werte = []
    for zeile in r.text.splitlines()[1:]:
        teile = zeile.split(",")
        try:
            werte.append(float(teile[-1]))
        except (ValueError, IndexError):
            continue
    return werte


def _reihe(quelle, jahre):
    if "fred" in quelle:
        return _fred(quelle["fred"], jahre)
    if "yf" in quelle:
        return _yf(quelle["yf"], jahre)
    if "ecb" in quelle:
        return _ecb(quelle["ecb"], jahre)
    return []


def _score(quellen, jahre):
    """Score heute und vor sieben Handelstagen, damit ein Delta entsteht."""
    jetzt, davor = [], []
    for q in quellen:
        reihe = _reihe(q, jahre)
        if len(reihe) < 20:
            continue
        inv = q.get("invert", False)
        jetzt.append(perzentil(reihe, invert=inv))
        if len(reihe) > 8:
            davor.append(perzentil(reihe[:-7], invert=inv))
    jetzt = [x for x in jetzt if x is not None]
    davor = [x for x in davor if x is not None]
    if not jetzt:
        return None
    wert = round(sum(jetzt) / len(jetzt))
    delta = round(wert - sum(davor) / len(davor)) if davor else 0
    return {"wert": wert, "delta": delta}


def bauen(konf):
    jahre = konf.get("rueckblick_jahre", 5)
    raus = []
    for name, regionen in konf["regime"].items():
        anzeige = {"name": name, "fenster": f"{jahre}J", "spuren": {}}
        for region, quellen in regionen.items():
            s = _score(quellen, jahre)
            if s:
                anzeige["spuren"][region] = s
        if not anzeige["spuren"]:
            continue
        if "us" in anzeige["spuren"] and "eur" in anzeige["spuren"]:
            anzeige["differenz"] = abs(anzeige["spuren"]["us"]["wert"]
                                       - anzeige["spuren"]["eur"]["wert"])
        raus.append(anzeige)
        log.info("Regime %s: %s", name, anzeige["spuren"])
    return raus
