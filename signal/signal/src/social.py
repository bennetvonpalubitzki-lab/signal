"""
Gespraechslage auf Reddit.

Gemessen wird Menge und Stimmungsverteilung, nicht der Ausschlag.
Die Stimmung kommt von VADER — regelbasiert, laeuft lokal, kostet
nichts. Fuer Boersenslang nicht perfekt, aber die Verteilung ueber
tausend Kommentare ist stabil genug.

Ohne Reddit-Zugangsdaten wird der oeffentliche JSON-Zugang versucht;
faellt auch der aus, bleibt der Abschnitt einfach leer.
"""
import re, collections
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from util import get, env, log
import requests

TICKER = re.compile(r"\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b")
IGNORIEREN = {"THE","AND","FOR","YOU","ALL","NOT","BUT","CEO","CFO","USA","EUR","USD",
              "ETF","IPO","GDP","FED","EZB","DAX","CPI","ATH","YOLO","DD","IMO","TLDR",
              "WSB","EPS","IRA","API","AI","LLM","OK","IT","IS","ON","IN","TO","OF"}
vader = SentimentIntensityAnalyzer()


def _token():
    cid, sec = env("REDDIT_CLIENT_ID"), env("REDDIT_SECRET")
    if not (cid and sec):
        return None
    try:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(cid, sec), data={"grant_type": "client_credentials"},
                          headers={"User-Agent": "signal/1.0"}, timeout=20)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        log.warning("Reddit-Anmeldung fehlgeschlagen: %s", e)
        return None


def _posts(sub, token):
    basis = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    kopf = {"User-Agent": "signal/1.0"}
    if token:
        kopf["Authorization"] = f"bearer {token}"
    try:
        r = requests.get(f"{basis}/r/{sub}/hot.json?limit=60", headers=kopf, timeout=25)
        r.raise_for_status()
        return [k["data"] for k in r.json()["data"]["children"]]
    except Exception as e:
        log.warning("Reddit r/%s: %s", sub, e)
        return []


def holen(konf):
    token = _token()
    treffer = collections.defaultdict(lambda: {"erw": 0, "komm": 0, "pos": 0, "neg": 0,
                                               "subs": set(), "titel": []})
    for sub in konf.get("subreddits", []):
        for p in _posts(sub, token):
            text = f"{p.get('title','')} {p.get('selftext','')[:600]}"
            gefunden = set()
            for m in TICKER.finditer(text):
                sym = m.group(1) or m.group(2)
                if sym and sym not in IGNORIEREN and len(sym) >= 2:
                    gefunden.add(sym)
            if not gefunden:
                continue
            s = vader.polarity_scores(text)["compound"]
            for sym in gefunden:
                d = treffer[sym]
                d["erw"] += 1
                d["komm"] += p.get("num_comments", 0)
                d["subs"].add(sub)
                if s >= 0.05:
                    d["pos"] += 1
                elif s <= -0.05:
                    d["neg"] += 1
                if len(d["titel"]) < 3:
                    d["titel"].append(p.get("title", "")[:140])

    raus = []
    for sym, d in treffer.items():
        if d["erw"] < 3:
            continue
        gesamt = max(d["pos"] + d["neg"], 1)
        raus.append({
            "ticker": sym,
            "erwaehnungen": d["erw"],
            "kommentare": d["komm"],
            "bullisch": round(100 * d["pos"] / gesamt),
            "baerisch": round(100 * d["neg"] / gesamt),
            "subs": sorted(d["subs"]),
            "beispiele": d["titel"],
            # Einseitigkeit ist selbst eine Information: 0 = Streit, 1 = Echokammer
            "einseitigkeit": round(abs(d["pos"] - d["neg"]) / gesamt, 2),
        })
    raus.sort(key=lambda x: -x["kommentare"])
    log.info("Gespraechslage: %d Ticker", len(raus))
    return raus[:12]
