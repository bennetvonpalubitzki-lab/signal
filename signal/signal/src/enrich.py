"""
Die einzige Stelle, an der ein Sprachmodell gebraucht wird.

Faellt es aus oder ist keiner konfiguriert, liefert jede Funktion eine
brauchbare Notloesung — das Dashboard bleibt vollstaendig, nur die
Formulierungen fehlen. Nichts hier darf den Lauf abbrechen.
"""
from llm import frage, frage_json
from util import log

SYSTEM = ("Du bist Analyst fuer Makro und Kapitalmaerkte und schreibst fuer eine "
          "einzige Leserin. Nuechtern, praezise, deutsch, keine Floskeln, keine "
          "Anlageempfehlungen. Wenn die Faktenlage duenn ist, sag das.")


def synthese(cluster, regime, konf):
    if not cluster:
        return None
    lage = "; ".join(f"{r['name']}: " + ", ".join(
        f"{k} {v['wert']} ({v['delta']:+d})" for k, v in r["spuren"].items()) for r in regime)
    schlag = "\n".join(f"- {c['titel']} ({c['anzahl']} Quellen)" for c in cluster[:10])
    p = (f"Regimewerte (Perzentil 0-100 gegen 5 Jahre):\n{lage}\n\n"
         f"Wichtigste Meldungscluster:\n{schlag}\n\n"
         "Schreibe EINEN Satz von hoechstens 20 Woertern, der die Spannung des Tages "
         "benennt — was die Meldungen gemeinsam haben, was der Markt uebersieht. "
         "Danach zwei Saetze Erlaeuterung. Antworte als JSON: "
         '{"kern": "...", "erlaeuterung": "..."}')
    a = frage_json(p, konf["llm"], SYSTEM)
    if a and a.get("kern"):
        return a
    return {"kern": cluster[0]["titel"],
            "erlaeuterung": f"{len(cluster)} Themen aus {sum(c['anzahl'] for c in cluster)} Meldungen."}


def verdichten(cluster, konf, anzahl=4):
    """Jedem Top-Cluster zwei Saetze und betroffene Bereiche geben."""
    oben = cluster[:anzahl]
    if not oben:
        return cluster
    liste = "\n".join(f"[{i}] {c['titel']} — {c['anriss'][:200]}" for i, c in enumerate(oben))
    p = (f"{liste}\n\nFasse jede Meldung in zwei Saetzen zusammen und nenne betroffene "
         "Anlagen oder Branchen mit Richtung. JSON-Liste: "
         '[{"i":0,"text":"...","positiv":["..."],"negativ":["..."]}]')
    a = frage_json(p, konf["llm"], SYSTEM)
    if a:
        for e in a:
            try:
                c = oben[int(e["i"])]
                c["text"] = e.get("text", "")
                c["positiv"] = e.get("positiv", [])[:3]
                c["negativ"] = e.get("negativ", [])[:3]
            except Exception:
                continue
    for c in cluster:
        c.setdefault("text", c["anriss"][:220])
        c.setdefault("positiv", [])
        c.setdefault("negativ", [])
    return cluster


def ketten(cluster, regime, konf):
    n = konf["llm"].get("max_ketten", 2)
    if not cluster:
        return []
    schlag = "\n".join(f"- {c['titel']}" for c in cluster[:8])
    p = (f"Aktuelle Lage:\n{schlag}\n\n"
         f"Entwickle {n} Wirkungsketten. Jede beginnt mit einem konkreten, noch nicht "
         "eingetretenen Ausloeser und fuehrt ueber direkte Folge, zweite und dritte "
         "Ordnung zu betroffenen Anlagen. Beziehe europaeische Vermoegenswerte ein, "
         "wo die Uebertragung plausibel ist. Sei konkret statt allgemein. JSON: "
         '[{"ausloeser":"...","direkt":"...","zweite":"...","dritte":"...",'
         '"positiv":["..."],"negativ":["..."],"konfidenz":"hoch|mittel|niedrig"}]')
    return frage_json(p, konf["llm"], SYSTEM) or []


def gegenthese(cluster, konf):
    if not cluster:
        return None
    p = ("\n".join(f"- {c['titel']}" for c in cluster[:8]) +
         "\n\nWas ist gerade Marktkonsens, und was ist das staerkste Argument dagegen? "
         'JSON: {"konsens":"...","gegen":"..."} — je hoechstens 40 Woerter.')
    return frage_json(p, konf["llm"], SYSTEM)


def profile(profile_dict, konf):
    """Bull- und Baer-These je Watchlist-Wert. Kennzahlen bleiben faktisch."""
    grenze = konf["llm"].get("max_profile", 8)
    for sym, p in list(profile_dict.items())[:grenze]:
        quellen = "; ".join(f"{k}: {v}" for k, v in p["quellen"])
        prompt = (f"{p['name']} ({sym}). Geschaeft: {p['geschaeft'][:400]}\n"
                  f"Quellenlage: {quellen}\n"
                  f"Kennzahlen: {p['kpi']}\n\n"
                  "Schreibe je einen Absatz von hoechstens 55 Woertern: was dafuer und "
                  "was dagegen spricht. Wenn sich die Quellen widersprechen, benenne "
                  "den Widerspruch ausdruecklich. Dazu bis zu drei anstehende "
                  'Katalysatoren. JSON: {"dafuer":"...","dagegen":"...","katalysatoren":["..."]}')
        a = frage_json(prompt, konf["llm"], SYSTEM)
        if a:
            p.update({"dafuer": a.get("dafuer", ""), "dagegen": a.get("dagegen", ""),
                      "katalysatoren": a.get("katalysatoren", [])[:3]})
    for p in profile_dict.values():
        p.setdefault("dafuer", "")
        p.setdefault("dagegen", "")
        p.setdefault("katalysatoren", [])
    return profile_dict
