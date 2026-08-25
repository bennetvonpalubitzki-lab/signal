"""Gemeinsame Helfer."""
import os, json, logging, pathlib, datetime as dt
import requests, yaml

log = logging.getLogger("signal")
ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HIST = DOCS / "history"
UA = {"User-Agent": "signal-dashboard/1.0 (persoenliches Projekt)"}


def cfg():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name, default=None):
    return os.environ.get(name, default)


def heute():
    return dt.date.today()


def get(url, **kw):
    """HTTP mit Zeitlimit und Fehlertoleranz. Gibt None statt zu werfen."""
    try:
        r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 30), **kw)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("Abruf fehlgeschlagen %s — %s", url, e)
        return None


def perzentil(reihe, wert=None, invert=False):
    """Wo steht der letzte Wert im Vergleich zur Historie? 0-100."""
    reihe = [x for x in reihe if x is not None]
    if len(reihe) < 20:
        return None
    wert = reihe[-1] if wert is None else wert
    p = 100.0 * sum(1 for x in reihe if x <= wert) / len(reihe)
    return round(100.0 - p if invert else p, 1)


def json_lesen(pfad, fallback=None):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def json_schreiben(pfad, daten):
    pfad = pathlib.Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
