#!/usr/bin/env python3
"""
SIGNAL — Hauptlauf.

  python src/run.py            normaler Lauf, kein Briefing
  python src/run.py --brief    zusaetzlich Morgenbriefing senden
  python src/run.py --dry      nichts senden, nichts committen

Jeder Schritt ist gekapselt: faellt eine Quelle aus, laeuft der Rest
weiter und der Abschnitt bleibt leer. Ein kaputter Feed darf nie das
ganze Dashboard kosten.
"""
import sys, logging, datetime as dt
import util, regime, news, shorts, social, market, events, enrich, brief

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("signal")


def sicher(name, fn, fallback):
    try:
        return fn()
    except Exception as e:
        log.error("%s fehlgeschlagen: %s", name, e)
        return fallback


def main():
    args = set(sys.argv[1:])
    trocken = "--dry" in args
    konf = util.cfg()

    log.info("=== SIGNAL %s ===", dt.datetime.now().isoformat(timespec="minutes"))

    reg      = sicher("Regime",     lambda: regime.bauen(konf), [])
    artikel  = sicher("Feeds",      lambda: news.holen(konf), [])
    cluster  = sicher("Clusterung", lambda: news.clustern(artikel, konf), [])
    roh      = sicher("Register",   lambda: shorts.holen(konf), [])
    pos, ereignisse = sicher("Registervergleich",
                             lambda: shorts.vergleichen(roh, konf.get("watchlist", [])),
                             ([], []))
    gespraech = sicher("Reddit",    lambda: social.holen(konf), [])
    termine   = sicher("Kalender",  lambda: events.holen(konf), [])
    matrix, profile = sicher("Matrix",
                             lambda: market.bauen(konf, pos, gespraech, cluster),
                             ([], {}))

    # --- Sprachmodell: alles hier ist optional --------------------------
    cluster = sicher("Verdichtung", lambda: enrich.verdichten(cluster, konf), cluster)
    synth   = sicher("Synthese",    lambda: enrich.synthese(cluster, reg, konf), None)
    kette   = sicher("Ketten",      lambda: enrich.ketten(cluster, reg, konf), [])
    gegen   = sicher("Gegenthese",  lambda: enrich.gegenthese(cluster, konf), None)
    profile = sicher("Profile",     lambda: enrich.profile(profile, konf), profile)

    daten = {
        "stand": dt.datetime.now().isoformat(timespec="minutes"),
        "lauf": dt.datetime.now().strftime("%Y%m%d%H"),
        "synthese": synth,
        "regime": reg,
        "cluster": cluster[:8],
        "ketten": kette,
        "gegenthese": gegen,
        "matrix": matrix,
        "profile": profile,
        "shorts": pos[:30],
        "shorts_kennzahlen": shorts.kennzahlen(pos),
        "gespraech": gespraech,
        "termine": termine,
        "meldungen_gesamt": len(artikel),
        "llm_aktiv": bool(synth and kette),
    }

    if not trocken:
        util.json_schreiben(util.DOCS / "data.json", daten)
        log.info("data.json geschrieben — %d Cluster, %d Shortpositionen",
                 len(cluster), len(pos))

        if "--brief" in args:
            brief.morgenbriefing(daten, konf)

        # --- Alarme, bewusst sparsam -----------------------------------
        schwellen = konf.get("alarme", {})
        wl = {s.split(".")[0].upper() for s in konf.get("watchlist", [])}

        sprung = [r for r in reg if any(abs(s["delta"]) >= schwellen.get("regime_sprung", 10)
                                        for s in r["spuren"].values())]
        if sprung and "--brief" not in args:
            brief.alarm("Regime-Sprung",
                        [f"{r['name']}: " + ", ".join(f"{k.upper()} {s['wert']} ({s['delta']:+d})"
                         for k, s in r["spuren"].items()) for r in sprung], konf)

        if schwellen.get("neue_shortposition"):
            relevant = [e for e in ereignisse
                        if any(w[:4] in e["emittent"].upper() for w in wl)]
            if relevant:
                brief.alarm("Leerverkauf auf Watchlist",
                            [f"{e['emittent']} {e['prozent']:.2f} % — {e['halter'][:32]} ({e['status']})"
                             for e in relevant[:5]], konf)

    log.info("=== fertig ===")


if __name__ == "__main__":
    main()
