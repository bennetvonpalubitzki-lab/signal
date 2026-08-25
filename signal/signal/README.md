# SIGNAL

Ein Makro-Cockpit, das sich selbst aktualisiert. Läuft ohne Server, ohne Datenbank und ohne laufende Kosten.

Morgens um 6:30 kommt ein kurzes Briefing per Telegram. Das Dashboard aktualisiert sich alle drei Stunden still im Hintergrund und ist da, wenn du hinschaust.

---

## Wie es funktioniert

GitHub startet nach Zeitplan ein Python-Skript. Das sammelt Feeds, Makrodaten, Leerverkaufsregister, Reddit und Analystendaten, rechnet daraus die Regime-Werte und die Konsens-Matrix, schreibt das Ergebnis als `docs/data.json` zurück ins Repository und schickt dir das Briefing. Das Dashboard ist eine statische Seite, die diese Datei liest.

Weil jeder Lauf ins Repository schreibt, entsteht nebenbei ein Archiv. Besonders wertvoll beim Leerverkaufsregister: die Register zeigen nur den Ist-Zustand, und wer unter 0,5 % fällt, verschwindet daraus. Deine täglichen Schnappschüsse ergeben nach einigen Monaten eine Zeitreihe, die es öffentlich nirgends gibt.

---

## Was du brauchst

| | Pflicht? | Kosten | Dauer |
|---|---|---|---|
| GitHub-Konto | ja | 0 € | 3 Min |
| FRED-Schlüssel (Makrodaten) | ja | 0 € | 3 Min |
| Telegram-Bot | für das Briefing | 0 € | 3 Min |
| Groq-Schlüssel (Sprachmodell) | nein | 0 € | 3 Min |
| Reddit-Zugang | nein | 0 € | 4 Min |

Ohne Sprachmodell fehlen nur Verdichtung, Wirkungsketten, Gegenthese und die Bull/Bear-Absätze. Regime-Werte, Kalender, Register, Matrix, Kennzahlen und Gesprächslage laufen unverändert.

---

## Einrichtung

### 1 · Repository anlegen

Auf [github.com](https://github.com) ein Konto erstellen, dann oben rechts auf **+ → New repository**.

- Name: `signal`
- **Public** wählen. Bei öffentlichen Repositories sind die Actions-Minuten unbegrenzt, bei privaten hast du 2.000 im Monat — es würde auch so reichen, aber öffentlich ist sorgenfreier. Deine Schlüssel liegen in den Secrets und sind nie sichtbar.
- Haken bei **Add a README file**
- **Create repository**

### 2 · Dateien hochladen

Entpacke `signal.zip`. Im Repository auf **Add file → Upload files**, dann alle Ordner und Dateien in das Feld ziehen. Unten auf **Commit changes**.

Wichtig: Der Ordner `.github` beginnt mit einem Punkt und wird von manchen Dateimanagern versteckt. Wenn er fehlt, läuft nichts automatisch. Unter macOS blendest du versteckte Dateien mit `Cmd + Shift + .` ein, unter Windows über Ansicht → Ausgeblendete Elemente.

### 3 · FRED-Schlüssel holen

FRED ist die Datenbank der US-Notenbank von St. Louis und liefert die Zeitreihen für die Regime-Werte sowie die Termine der US-Statistikbehörden.

Auf `fred.stlouisfed.org/docs/api/api_key.html` ein Konto anlegen und einen Schlüssel anfordern. Kommt sofort, keine Freischaltung nötig.

### 4 · Telegram-Bot anlegen

In Telegram nach **@BotFather** suchen und anschreiben:

1. `/newbot` senden
2. Namen vergeben, dann einen Benutzernamen der auf `bot` endet
3. BotFather antwortet mit einem Token — das ist dein `TELEGRAM_TOKEN`

Jetzt brauchst du noch deine Chat-ID: **deinen neuen Bot anschreiben** (irgendetwas, z. B. „hallo" — ohne das kann er dir nicht antworten), dann im Browser öffnen:

```
https://api.telegram.org/botDEIN_TOKEN/getUpdates
```

In der Antwort steht `"chat":{"id":123456789` — diese Zahl ist deine `TELEGRAM_CHAT_ID`.

### 5 · Sprachmodell (optional, aber empfohlen)

Auf `console.groq.com` anmelden und einen API-Schlüssel erstellen. Groq hat ein dauerhaft kostenloses Kontingent, das für rund 40 Aufrufe pro Lauf locker reicht.

Andere Anbieter gehen genauso — in `config.yaml` unter `llm:` den `anbieter` auf `gemini`, `openrouter` oder `anthropic` stellen und den passenden Schlüssel als Secret hinterlegen. Die Limits ändern sich häufig; deshalb ist der Anbieter eine Konfigurationszeile und keine Codeänderung.

### 6 · Reddit (optional)

Ohne Zugangsdaten wird der öffentliche Zugang versucht, der oft gedrosselt wird. Mit Zugangsdaten ist es zuverlässig:

`reddit.com/prefs/apps` → **create another app** → Typ **script** → redirect uri `http://localhost:8080`. Danach steht die Client-ID klein unter dem App-Namen, das Secret daneben.

### 7 · Schlüssel im Repository hinterlegen

Im Repository: **Settings → Secrets and variables → Actions → New repository secret**. Für jeden einzeln:

| Name | Wert |
|---|---|
| `FRED_API_KEY` | aus Schritt 3 |
| `TELEGRAM_TOKEN` | aus Schritt 4 |
| `TELEGRAM_CHAT_ID` | aus Schritt 4 |
| `GROQ_API_KEY` | aus Schritt 5, optional |
| `REDDIT_CLIENT_ID` | aus Schritt 6, optional |
| `REDDIT_SECRET` | aus Schritt 6, optional |

Secrets sind nach dem Speichern auch für dich nicht mehr lesbar. Das ist so gewollt.

### 8 · Dashboard freischalten

**Settings → Pages**. Bei *Source* **Deploy from a branch** wählen, Branch `main`, Ordner `/docs`, **Save**.

Nach ein paar Minuten liegt deine Seite unter:

```
https://DEIN-BENUTZERNAME.github.io/signal/
```

Diese Adresse trägst du in `config.yaml` bei `dashboard_url` ein, damit das Briefing richtig verlinkt. Zum Bearbeiten im Repository auf `config.yaml` klicken, dann auf das Stiftsymbol.

### 9 · Ersten Lauf starten

Reiter **Actions → signal → Run workflow → Run workflow**. Der Lauf dauert zwei bis vier Minuten. Klick ihn an, um live zuzuschauen — dort siehst du auch, welche Quelle wie viele Datensätze geliefert hat.

Danach das Dashboard aufrufen. Steht dort noch „Noch keine Daten", ist der Lauf entweder nicht durch oder GitHub Pages braucht noch eine Minute.

Beim ersten Lauf ist das Leerverkaufsregister als „Bestand" markiert und die Kennzahlen sind leer — es gibt noch nichts zu vergleichen. Ab dem zweiten Tag erscheinen Statusangaben, nach einigen Wochen wird der Abschnitt aussagekräftig.

---

## Im Alltag

**Watchlist ändern:** in `config.yaml` unter `watchlist`. Schreibweise wie bei Yahoo Finance — `.DE` für XETRA, `.PA` für Paris, `.AS` für Amsterdam, ohne Zusatz für US-Börsen. Diese Werte bekommen ein Profil und lösen Alarme aus.

**Feeds ergänzen:** unter `feeds` eine Zeile anfügen. Fast jeder Substack hat einen Feed unter `/feed`. `gewicht: 3` stuft eine Quelle im Ranking hoch.

**Termine nachtragen:** unter `termine`. US-Veröffentlichungen holt FRED automatisch; EZB-Sitzungen, OPEC-Treffen und ifo trägst du einmal im Quartal nach.

**Alarme:** unter `alarme`. Die Schwellen sind bewusst hoch. Wenn du drei Wochen keinen Alarm bekommst und das Gefühl hast, etwas verpasst zu haben, senke `regime_sprung` auf 7.

**Zeiten ändern:** in `.github/workflows/signal.yml`. Die Cron-Angaben stehen in UTC — im Sommer eine Stunde weniger als bei uns, im Winter zwei.

---

## Wenn etwas nicht geht

**Ein Abschnitt bleibt leer.** So ist es gebaut: fällt eine Quelle aus, läuft der Rest weiter. Unter Actions → letzter Lauf steht die Ursache im Klartext.

**Das Leerverkaufsregister ist leer.** Das ist der wahrscheinlichste Fall. Die Registerseiten ändern gelegentlich ihren Aufbau, und dann findet der Scraper die Tabelle nicht mehr. Im Log steht dann etwa „Bundesanzeiger: keine Tabelle". Schick mir die Zeile aus dem Log, dann passe ich den Scraper an — das ist ein Zehnzeiler.

**Der Workflow läuft nicht von selbst.** Bei Repositories ohne Aktivität pausiert GitHub geplante Läufe nach 60 Tagen. Ein manueller Start reicht, um sie wieder zu aktivieren.

**Kein Telegram-Briefing.** Prüfe, ob du den Bot mindestens einmal angeschrieben hast. Ohne das darf er dir nichts senden.

**Der geplante Lauf startet zu spät.** GitHub verschiebt Cron-Jobs bei Last um bis zu 15 Minuten. Nicht änderbar, aber unkritisch.

---

## Was fehlt

Zwei Dinge aus unserem Konzept sind noch nicht drin, weil sie am besten funktionieren, wenn du das System ein paar Wochen benutzt hast:

**Das Journal** — ein Feld pro Tag für deine eigene Einschätzung, das dir nach acht Wochen zeigt, wo du systematisch danebenlagst. Braucht eine Eingabemöglichkeit und damit einen kleinen Umweg über GitHub Issues als Speicher.

**Der Abschnitt „Verändert"** — Spread-Bewegungen, COT-Positionierung, Kurvenform. Die Datenquellen sind alle in `regime.py` schon angebunden, es fehlt nur die Auswertung auf Veränderung statt Niveau.

Sag Bescheid, wenn eines davon dran sein soll.

---

*Die Regime-Werte sind Perzentilränge gegen die eigene Historie, keine Prognosen. Verdichtungen, Wirkungsketten und Ticker-Einschätzungen sind maschinell erzeugte Hypothesen — sie sind dafür da, geprüft zu werden. Keine Anlageberatung.*
