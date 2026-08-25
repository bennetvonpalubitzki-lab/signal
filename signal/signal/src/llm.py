"""
Anbieterunabhaengiger Zugang zum Sprachmodell.

Es gibt genau eine Funktion nach aussen: frage(). Welcher Anbieter
antwortet, steht in config.yaml. Fehlt der Schluessel oder faellt der
Dienst aus, gibt frage() None zurueck — das Skript laeuft dann ohne
Verdichtung und ohne Wirkungsketten weiter, statt abzubrechen.
"""
import json, re
from util import env, get, log
import requests

ENDPUNKTE = {
    "groq":       ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions",   "OPENROUTER_API_KEY"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/models", "GEMINI_API_KEY"),
    "anthropic":  ("https://api.anthropic.com/v1/messages",           "ANTHROPIC_API_KEY"),
}


def frage(prompt, konf, system=None, max_tokens=1200):
    anbieter = (konf.get("anbieter") or "keiner").lower()
    if anbieter == "keiner":
        return None
    if anbieter not in ENDPUNKTE:
        log.warning("Unbekannter LLM-Anbieter: %s", anbieter)
        return None

    url, key_name = ENDPUNKTE[anbieter]
    key = env(key_name)
    if not key:
        log.warning("%s nicht gesetzt — Sprachmodell wird uebersprungen", key_name)
        return None

    modell = konf.get("modell")
    try:
        if anbieter == "gemini":
            r = requests.post(
                f"{url}/{modell}:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": (system + "\n\n" if system else "") + prompt}]}]},
                timeout=90)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]

        if anbieter == "anthropic":
            r = requests.post(url, timeout=90,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": modell, "max_tokens": max_tokens,
                      "system": system or "",
                      "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json()["content"])

        # groq und openrouter sprechen beide das OpenAI-Format
        nachrichten = ([{"role": "system", "content": system}] if system else []) \
                      + [{"role": "user", "content": prompt}]
        r = requests.post(url, timeout=90,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": modell, "messages": nachrichten,
                  "max_tokens": max_tokens, "temperature": 0.3})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        log.warning("Sprachmodell nicht erreichbar (%s): %s", anbieter, e)
        return None


def frage_json(prompt, konf, system=None):
    """Wie frage(), erwartet aber JSON zurueck und raeumt Codezaeune weg."""
    roh = frage(prompt, konf, system=system)
    if not roh:
        return None
    roh = re.sub(r"^```(?:json)?|```$", "", roh.strip(), flags=re.M).strip()
    try:
        return json.loads(roh)
    except Exception:
        # Manche Modelle schreiben noch einen Satz davor. Groesste Klammer suchen.
        m = re.search(r"[\[{].*[\]}]", roh, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        log.warning("Antwort war kein gueltiges JSON")
        return None
