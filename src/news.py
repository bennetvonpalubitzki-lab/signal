"""
Meldungen einsammeln, Duplikate zusammenfassen, ranken.

Geclustert wird mit TF-IDF und agglomerativer Clusterung. Bewusst kein
neuronales Modell: das haette in einem Cron-Job eine halbe Minute
Ladezeit und mehrere hundert Megabyte gekostet, ohne bei Schlagzeilen
merklich besser zu sein.
"""
import re, hashlib, datetime as dt
import feedparser
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
from util import log



def _sauber(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def holen(konf):
    artikel, grenze = [], dt.datetime.now() - dt.timedelta(hours=36)
    for f in konf["feeds"]:
        try:
            d = feedparser.parse(f["url"])
        except Exception as e:
            log.warning("Feed %s: %s", f["name"], e)
            continue
        for e in d.entries[:40]:
            titel = _sauber(getattr(e, "title", ""))
            if not titel:
                continue
            wann = None
            if getattr(e, "published_parsed", None):
                wann = dt.datetime(*e.published_parsed[:6])
            if wann and wann < grenze:
                continue
            artikel.append({
                "titel": titel,
                "anriss": _sauber(getattr(e, "summary", ""))[:400],
                "link": getattr(e, "link", ""),
                "quelle": f["name"],
                "region": f.get("region", "global"),
                "gewicht": f.get("gewicht", 1),
                "wann": (wann or dt.datetime.now()).isoformat(timespec="minutes"),
            })
    log.info("%d Meldungen aus %d Feeds", len(artikel), len(konf["feeds"]))
    return artikel


def clustern(artikel, konf):
    if len(artikel) < 4:
        return [{"titel": a["titel"], "artikel": [a]} for a in artikel]

    # Zeichen-n-Gramme statt Woerter: faengt deutsche Komposita
    # ("Kupfer" / "Kupferpreis") und unterschiedliche Beugungen mit,
    # woran eine reine Wortzerlegung scheitert.
    texte = [a["titel"] + " " + a["anriss"][:150] for a in artikel]
    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                        min_df=1, sublinear_tf=True,
                        max_features=30000).fit_transform(texte)
    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=konf.get("cluster_schwelle", 0.86),
        metric="cosine", linkage="average").fit_predict(X.toarray())

    eimer = {}
    for a, l in zip(artikel, labels):
        eimer.setdefault(int(l), []).append(a)

    themen = [t.lower() for t in konf.get("themen", [])]
    cluster = []
    for gruppe in eimer.values():
        gruppe.sort(key=lambda a: -a["gewicht"])
        text = " ".join(a["titel"] for a in gruppe).lower()
        treffer = sum(1 for t in themen if t in text)
        # Punktzahl: wie viele unabhaengige Quellen, wie stark gewichtet,
        # und passt es zu den Themen der Konfiguration?
        quellen = len({a["quelle"] for a in gruppe})
        punkte = quellen * 2 + sum(a["gewicht"] for a in gruppe) + treffer * 4
        cluster.append({
            "id": hashlib.md5(gruppe[0]["titel"].encode()).hexdigest()[:8],
            "titel": gruppe[0]["titel"],
            "anriss": gruppe[0]["anriss"][:300],
            "region": gruppe[0]["region"],
            "quellen": sorted({a["quelle"] for a in gruppe}),
            "anzahl": len(gruppe),
            "links": [a["link"] for a in gruppe[:5]],
            "punkte": punkte,
        })
    cluster.sort(key=lambda c: -c["punkte"])
    return cluster
