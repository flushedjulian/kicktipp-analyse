# Kicktipp-Analyse ⚽

Erstellt vor jedem Bundesliga-Spieltag automatisch eine Webseite mit Tipp-Empfehlungen für Kicktipp (Punktesystem 4/3/2).

## So funktioniert's

1. **Daten:** Ergebnisse der aktuellen und letzten Saison (OpenLigaDB), Expected Goals pro Spiel (Understat) und Wettquoten (football-data.co.uk, `fixtures.csv`, meist ab Donnerstag/Freitag verfügbar).
2. **Teamstärke:** Gewichtete Poisson-Regression aus Angriff, Abwehr und Heimvorteil. Neuere Spiele zählen mehr (Halbwertszeit 150 Tage), xG zählt zu 80 %, echte Tore zu 20 %. Aufsteiger starten etwas schwächer.
3. **Wettquoten:** Aus den 1X2-Durchschnittsquoten werden Torerwartungen zurückgerechnet und zu 65 % beigemischt. Einmal geholte Quoten werden in `data/predictions/` gespeichert, weil football-data.co.uk Spiele nach dem Anpfiff aus der Liste nimmt. Auf der Webseite lassen sich Quoten zusätzlich von Hand eintragen oder überschreiben (nur im Browser des Geräts gespeichert).
4. **Bester Tipp:** Aus den Torerwartungen ergibt sich für jedes Ergebnis eine Wahrscheinlichkeit (Poisson mit Dixon-Coles-Korrektur). Empfohlen wird der Tipp mit den meisten erwarteten Kicktipp-Punkten.

GitHub Actions lässt das jeden Tag um ca. 7 und 18 Uhr laufen ([.github/workflows/analyse.yml](.github/workflows/analyse.yml)). Die Seite liegt in `docs/` und wird über GitHub Pages veröffentlicht. Tipps für Spiele, die schon angepfiffen wurden, werden eingefroren und unten auf der Seite ausgewertet.

## Lokal ausführen

Keine Zusatzpakete nötig, nur Python 3.10+.

```bash
python3 -m analyse.main      # Analyse für den nächsten Spieltag → docs/index.html
python3 backtest.py          # Modell an den letzten zwei Saisons testen
python3 backtest.py --tune   # Parameter durchprobieren
```

## Backtest (Stand Oktober 2026)

| Saison | Ø Punkte/Spiel | Tendenz richtig | „Immer 2:1 Heim“ |
|---|---|---|---|
| 2024/25 | 1,23 | 50 % | 0,97 |
| 2025/26 | 1,40 | 55 % | 1,16 |

(nur eigenes Modell, ohne Wettquoten. Mit den Quoten von football-data.co.uk zu 65 % beigemischt: 394 bzw. 432 Punkte über die ganze Saison)

## Einstellungen

Alle Modell-Parameter stehen oben in [analyse/model.py](analyse/model.py). Das Punktesystem ist dort ebenfalls einstellbar (`POINTS_EXACT`, `POINTS_DIFF`, `POINTS_TENDENCY`).
