# Kicktipp-Analyse ⚽

Erstellt vor jedem Bundesliga-Spieltag automatisch eine Webseite mit Tipp-Empfehlungen für Kicktipp (Punktesystem 4/3/2).

## So funktioniert's

1. **Daten:** Ergebnisse der aktuellen und letzten Saison (OpenLigaDB) und Wettquoten (football-data.co.uk, `fixtures.csv`, meist ab Donnerstag/Freitag verfügbar).
2. **Teamstärke:** Gewichtete Poisson-Regression aus Angriff, Abwehr und Heimvorteil auf Basis der Tore. Neuere Spiele zählen mehr (Halbwertszeit 150 Tage). Aufsteiger starten etwas schwächer.
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

Getippt wurde jeweils vor dem Spieltag, nur mit den bis dahin bekannten Ergebnissen.

| Saison | Spiele | Nur Modell | Mit Quoten (65 %) | „Immer 2:1 Heim“ |
|---|---|---|---|---|
| 2024/25 | 306 | 376 | 394 | 299 |
| 2025/26 | 306 | 433 | 437 | 352 |

Quoten für den Backtest: historische Durchschnittsquoten von football-data.co.uk.

## Einstellungen

Alle Modell-Parameter stehen oben in [analyse/model.py](analyse/model.py). Das Punktesystem ist dort ebenfalls einstellbar (`POINTS_EXACT`, `POINTS_DIFF`, `POINTS_TENDENCY`).

## Datenquellen

Nur Quellen, die ausdrücklich zur freien Nutzung gedacht sind: [OpenLigaDB](https://www.openligadb.de) (Community-Projekt) und [football-data.co.uk](https://www.football-data.co.uk) („My data is free“). Die Seite ist per `noindex` von Suchmaschinen ausgenommen.
