"""
Regime-Anzeigen: Perzentilrang mehrerer Zeitreihen gegen die Historie.

Kein Modell, keine Gewichtung nach Gefuehl — jede Komponente wird
gefragt: wo stehst du im Vergleich zu dir selbst in den letzten
N Jahren? Der Mittelwert ist der Score.

Wichtig beim Delta: Reihen haben unterschiedliche Frequenzen. Ein
taeglicher Kurs und die woechentlichen Arbeitslosenantraege duerfen
nicht beide "sieben Werte zurueck" verglichen werden, sonst schaut man
bei der einen Reihe eine Woche und bei der anderen fast zwei Monate
in die Vergangenheit. Deshalb wird ueber das Datum gesucht.
"""
import datetime as dt
from util import env, get, perzentil, log

FRED = "https://api.stlouisfed.org/fred/series/observations"


def _fred(serie, jahre):
    """Gibt [(datum, wert), ...] zurueck."""
    key = env("FRED_API_KEY")
    if not key:
        return []
    start = (dt.date.today() - dt.timedelta(days=365 * jahre)).isoformat()
    r = get(FRED, params={"series_id": serie, "api_key": key, "file_type": "json",
                          "observation_start": start})
    if not r:
        return []
    reihe = []
    for o in r.json().get("observations", []):
        try:
            reihe.append((dt.date.fromisoformat(o["date"]), float(o["value"])))
        except (ValueError, KeyError):
            continue
    if not reihe:
        log.warning("FRED %s: keine verwertbaren Werte", serie)
    return reihe


def _yf(symbol, jahre):
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period=f"{jahre}y", interval="1d")
        if h.empty:
            log.warning("yfinance %s: leere Antwort", symbol)
            return []
        return [(i.date(), float(v)) for i, v in h["Close"].dropna().items()]
    except Exception as e:
        log.warning("yfinance %s: %s", symbol, e)
        return []


def _ecb(schluessel, jahre):
    """EZB Data Portal. Schluesselform: DATENSATZ.REST.DES.SCHLUESSELS"""
    teile = schluessel.split(".", 1)
    if len(teile) != 2:
        return []
    start = (dt.date.today() - dt.timedelta(days=365 * jahre)).isoformat()
    r = get(f"https://data-api.ecb.europa.eu/service/data/{teile[0]}/{teile[1]}",
            params={"startPeriod": start, "format": "csvdata"})
    if not r:
        return []
    zeilen = r.text.splitlines()
    if len(zeilen) < 2:
        return []
    kopf = [s.strip().strip('"') for s in zeilen[0].split(",")]
    try:
        i_zeit = kopf.index("TIME_PERIOD")
        i_wert = kopf.index("OBS_VALUE")
    except ValueError:
        return []
    reihe = []
    for z in zeilen[1:]:
        f = [s.strip().strip('"') for s in z.split(",")]
        try:
            d = f[i_zeit]
            d = d if len(d) == 10 else d + "-01" if len(d) == 7 else None
            reihe.append((dt.date.fromisoformat(d), float(f[i_wert])))
        except Exception:
            continue
    return reihe


def _reihe(quelle, jahre):
    if "fred" in quelle:
        return _fred(quelle["fred"], jahre)
    if "yf" in quelle:
        return _yf(quelle["yf"], jahre)
    if "ecb" in quelle:
        return _ecb(quelle["ecb"], jahre)
    return []


def _stand_vor(reihe, tage=7):
    """Index des juengsten Werts, der mindestens `tage` alt ist."""
    grenze = reihe[-1][0] - dt.timedelta(days=tage)
    for i in range(len(reihe) - 1, -1, -1):
        if reihe[i][0] <= grenze:
            return i
    return None


def _score(quellen, jahre):
    jetzt, davor = [], []
    for q in quellen:
        reihe = _reihe(q, jahre)
        if len(reihe) < 20:
            continue
        inv = q.get("invert", False)
        werte = [v for _, v in reihe]
        jetzt.append(perzentil(werte, invert=inv))

        i = _stand_vor(reihe, 7)
        # Nur vergleichen, wenn es seither ueberhaupt neue Werte gab.
        # Bei Monatsreihen bleibt das Delta sonst kuenstlich in Bewegung.
        if i is not None and i < len(reihe) - 1:
            davor.append(perzentil(werte[:i + 1], invert=inv))
        elif i is not None:
            davor.append(perzentil(werte, invert=inv))

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
            else:
                log.warning("Regime %s/%s: keine verwertbaren Reihen", name, region)
        if not anzeige["spuren"]:
            continue
        if "us" in anzeige["spuren"] and "eur" in anzeige["spuren"]:
            anzeige["differenz"] = abs(anzeige["spuren"]["us"]["wert"]
                                       - anzeige["spuren"]["eur"]["wert"])
        raus.append(anzeige)
        log.info("Regime %s: %s", name, anzeige["spuren"])
    return raus
