# Sport w TV

Einfache polnische Sport-Übersicht für den Vater: MotoGP, Skispringen (Männer), Fußball (Spiele Polens + WM/EM/Nations League), Olympia.
Pro Termin: Uhrzeit, Ort, polnischer Sender. Läuft als statische Seite (PWA) auf GitHub Pages.

## Einrichten (einmalig)

1. **Pages aktivieren:** Repo → *Settings → Pages* → Source: *Deploy from a branch* → `main` / `/ (root)`.
2. **Fußball-Key (optional, aber nötig für Polen-Spiele):** Gratis-Konto auf api-football.com → API-Key →
   Repo → *Settings → Secrets and variables → Actions → New repository secret* → Name `API_FOOTBALL_KEY`.
3. **Ersten Lauf starten:** *Actions → „Dane — aktualizacja" → Run workflow*. Danach läuft es täglich ca. 05:10 Uhr.
4. **Aufs iPhone/Handy des Vaters:** Seite in Safari öffnen → Teilen → *Zum Home-Bildschirm*.

Die Seite liegt dann unter `https://swayzz90.github.io/Sport-TV/`.

## So funktioniert es

```
fetcher/seeds/*.yml      feste Kalender (Skispringen, MotoGP, manuelle Fußball-Termine)
fetcher/providers/       Live-Quellen (Fußball über API-Football)
fetcher/config/rules.yml Welche Sportart/Wettbewerb läuft auf welchem Sender
fetcher/config/overrides.yml  Einzelne Termine korrigieren oder ausblenden
fetcher/build.py         setzt alles zusammen -> data/events.json (nächste 14 Tage)
index.html, app.js, ...  die App; liest nur data/events.json
```

Fällt die Fußball-API aus, bleiben die Termine vom Vortag stehen (mit Hinweis). Sind die Daten älter als 2 Tage, zeigt die App ein Warnbanner.

## Pflege

- **Sender falsch?** `fetcher/config/rules.yml` ändern (gilt für alle) oder einzelnen Termin in `overrides.yml` korrigieren.
- **Neue Saison:** neue Seed-Datei in `fetcher/seeds/` anlegen (Format wie `skijumping.yml`).
- **Tests:** `python -m unittest discover -s tests -v`
- **Lokal bauen:** `pip install -r fetcher/requirements.txt && python fetcher/build.py`

## Bekannte Grenzen

- Für Polen gibt es keine verlässliche Gratis-API „Termin → Sender". Die Sender kommen deshalb aus Regeln (Senderechte ändern sich selten), nicht pro Termin aus einem Programmführer.
- MotoGP: Sessionzeiten stehen nur für Valencia 2026; für 2027 sind bisher nur die Renntage hinterlegt.
- Olympia und EM: noch kein Sender hinterlegt (App zeigt „Sprawdź program TV"), bis die Rechte geklärt sind.
- `providers/api_football.py` wurde ohne Live-Zugriff geschrieben. Beim ersten Lauf das Action-Log prüfen (Abschnitt „Termine holen").
