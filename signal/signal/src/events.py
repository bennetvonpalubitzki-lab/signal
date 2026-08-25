"""
Terminkalender: kommende Datenveroeffentlichungen.

FRED kennt die Termine aller US-Statistikbehoerden und gibt sie ueber
releases/dates heraus. Alles, was FRED nicht kennt — EZB-Sitzungen,
OPEC, ifo — steht handgepflegt in config.yaml.
"""
import datetime as dt
from util import env, get, log

RELEASES = "https://api.stlouisfed.org/fred/releases/dates"
WICHTIG = ["Consumer Price Index", "Employment Situation", "Gross Domestic Product",
           "Personal Income", "Producer Price", "Retail Sales", "FOMC",
           "Industrial Production", "Job Openings"]


def _fred_termine(tage=14):
    key = env("FRED_API_KEY")
    if not key:
        return []
    heute = dt.date.today()
    r = get(RELEASES, params={"api_key": key, "file_type": "json",
                              "realtime_start": heute.isoformat(),
                              "realtime_end": (heute + dt.timedelta(days=tage)).isoformat(),
                              "include_release_dates_with_no_data": "true",
                              "limit": 400})
    if not r:
        return []
    raus = []
    for d in r.json().get("release_dates", []):
        name = d.get("release_name", "")
        if not any(w.lower() in name.lower() for w in WICHTIG):
            continue
        raus.append({"datum": d["date"], "zeit": "", "region": "us",
                     "was": name, "konsens": "", "wucht": "hoch"})
    return raus


def holen(konf, tage=14):
    heute = dt.date.today()
    ende = heute + dt.timedelta(days=tage)
    manuell = []
    for t in konf.get("termine", []):
        try:
            d = dt.date.fromisoformat(t["datum"])
        except Exception:
            continue
        if heute <= d <= ende:
            manuell.append(dict(t))

    alle = manuell + _fred_termine(tage)
    # Duplikate nach Datum und Kurzname entfernen
    gesehen, raus = set(), []
    for t in sorted(alle, key=lambda x: (x["datum"], x.get("zeit", ""))):
        k = (t["datum"], t["was"][:24].lower())
        if k in gesehen:
            continue
        gesehen.add(k)
        raus.append(t)
    log.info("Kalender: %d Termine", len(raus))
    return raus[:12]
