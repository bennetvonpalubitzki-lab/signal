"""
Telegram: Triage, nicht Zweitdashboard.

Regel: Was mehr als eine Zeile braucht, gehoert ins Dashboard. Die
Nachricht beantwortet nur die Frage, ob du jetzt hinschauen musst.
"""
import requests
from util import env, log

API = "https://api.telegram.org/bot{}/sendMessage"
WUCHT = {"hoch": "!", "mittel": "·", "niedrig": " "}


def _senden(text):
    tok, chat = env("TELEGRAM_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        log.warning("Telegram nicht eingerichtet — Briefing wird uebersprungen")
        return False
    try:
        r = requests.post(API.format(tok), timeout=25, json={
            "chat_id": chat, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True})
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("Telegram: %s", e)
        return False


def _e(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def morgenbriefing(d, konf):
    url = konf.get("dashboard_url", "")
    z = [f"<b>SIGNAL</b> · {d['stand'][:10]}", ""]

    if d.get("synthese"):
        z += [f"<i>{_e(d['synthese']['kern'])}</i>", ""]

    # Regime nur, wenn sich etwas bewegt hat
    bewegt = [r for r in d["regime"]
              if any(abs(s["delta"]) >= 5 for s in r["spuren"].values())]
    if bewegt:
        z.append("<b>Regime</b>")
        for r in bewegt[:3]:
            teile = " · ".join(f"{k.upper()} {s['wert']} ({s['delta']:+d})"
                               for k, s in r["spuren"].items())
            z.append(f"{r['name'].capitalize()}: {teile}")
        z.append("")

    z.append("<b>Heute</b>")
    for c in d["cluster"][:3]:
        z.append(f"› {_e(c['titel'])} <i>({c['anzahl']} Q.)</i>")
    z.append("")

    heute = [t for t in d["termine"] if t["datum"] == d["stand"][:10]]
    if heute:
        z.append("<b>Ansteht</b>")
        for t in heute[:4]:
            k = f" — Konsens {_e(t['konsens'])}" if t.get("konsens") else ""
            z.append(f"{WUCHT.get(t.get('wucht'),' ')} {t.get('zeit','')} {_e(t['was'])}{k}")
        z.append("")

    neu = [p for p in d["shorts"] if p["status"] in ("neu", "geschlossen")][:4]
    if neu:
        z.append("<b>Leerverkäufe</b>")
        for p in neu:
            wort = "neu" if p["status"] == "neu" else "geschlossen"
            z.append(f"{_e(p['emittent'])} {p['prozent']:.2f} % · {_e(p['halter'][:28])} ({wort})")
        z.append("")

    div = [m for m in d["matrix"] if m["gruppe"] == "divergenz"][:2]
    if div:
        z.append("<b>Divergenz</b>")
        for m in div:
            pos = [k for k, v in m["quellen"].items() if v > 0]
            neg = [k for k, v in m["quellen"].items() if v < 0]
            z.append(f"{_e(m['ticker'])}: {'/'.join(pos)} gegen {'/'.join(neg)}")
        z.append("")

    if url:
        z.append(f'<a href="{url}">Dashboard öffnen</a>')
    return _senden("\n".join(z))


def alarm(titel, zeilen, konf):
    url = konf.get("dashboard_url", "")
    t = [f"<b>{_e(titel)}</b>", ""] + [_e(x) for x in zeilen]
    if url:
        t += ["", f'<a href="{url}">Dashboard</a>']
    return _senden("\n".join(t))
