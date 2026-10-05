"""Daten holen: Spielplan/Ergebnisse (OpenLigaDB) und Wettquoten (football-data.co.uk)."""

import difflib
import gzip
import json
import os
import ssl
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

USER_AGENT = "Mozilla/5.0 (Kicktipp-Analyse)"

_SSL = ssl.create_default_context()
if os.path.exists("/etc/ssl/cert.pem"):  # macOS-Python von python.org bringt sonst keine Zertifikate mit
    _SSL.load_verify_locations("/etc/ssl/cert.pem")


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw)


@dataclass
class Match:
    match_id: int
    season: int
    matchday: int
    kickoff_utc: datetime
    kickoff_local: datetime
    home_id: int
    away_id: int
    finished: bool
    home_goals: int | None = None
    away_goals: int | None = None
    scorers: list = field(default_factory=list)  # (team_id, name, is_own_goal)


@dataclass
class Team:
    team_id: int
    name: str
    short: str
    icon: str


# Logos, deren Link in OpenLigaDB nicht mehr funktioniert (Team-ID → Ersatz von Wikimedia)
LOGO_FIX = {
    6: "https://upload.wikimedia.org/wikipedia/de/f/f7/Bayer_Leverkusen_Logo.svg",  # Leverkusen
}


def _parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_season(season, teams):
    """Alle Spiele einer Bundesliga-Saison von OpenLigaDB. Füllt `teams` nebenbei."""
    raw = _get_json(f"https://api.openligadb.de/getmatchdata/bl1/{season}")
    matches = []
    for m in raw:
        for t in (m["team1"], m["team2"]):
            icon = LOGO_FIX.get(t["teamId"], t["teamIconUrl"])
            teams.setdefault(t["teamId"], Team(t["teamId"], t["teamName"], t["shortName"], icon))
        match = Match(
            match_id=m["matchID"],
            season=season,
            matchday=m["group"]["groupOrderID"],
            kickoff_utc=_parse_utc(m["matchDateTimeUTC"]),
            kickoff_local=datetime.fromisoformat(m["matchDateTime"]),
            home_id=m["team1"]["teamId"],
            away_id=m["team2"]["teamId"],
            finished=m["matchIsFinished"],
        )
        final = [r for r in m["matchResults"] if r["resultTypeID"] == 2]
        if match.finished and final:
            match.home_goals = final[0]["pointsTeam1"]
            match.away_goals = final[0]["pointsTeam2"]
            for g in m.get("goals") or []:
                if g.get("goalGetterName"):
                    match.scorers.append((g.get("scoringTeamId"), g["goalGetterName"], g.get("isOwnGoal", False)))
        elif match.finished:
            match.finished = False  # Ergebnis fehlt noch
        matches.append(match)
    return matches



# ---------------------------------------------------------------- Teamnamen vergleichen

_ALIASES = {"munich": "munchen", "cologne": "koln", "mgladbach": "monchengladbach", "leverkusen": "leverkusen"}
_NOISE = {"fc", "sc", "sv", "vfb", "vfl", "tsg", "fsv", "bv", "1", "04", "05", "07", "1846", "1899", "borussia", "bayer", "rb", "1."}


def _norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace(".", " ").replace("-", " ")
    words = [_ALIASES.get(w, w) for w in s.split()]
    words = [w for w in words if w not in _NOISE] or words
    return " ".join(words)


def _similar(a, b):
    a, b = _norm(a), _norm(b)
    if a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()



# ---------------------------------------------------------------- Wettquoten (football-data.co.uk)

def load_fd_odds(fixtures, teams):
    """Durchschnittsquoten (1X2) für anstehende Spiele aus football-data.co.uk/fixtures.csv.
    Die Datei enthält immer nur die Spiele der nächsten Tage und wird etwa zweimal pro Woche aktualisiert.
    Rückgabe: {match_id: [quote_1, quote_x, quote_2]}"""
    import csv
    import io

    try:
        req = urllib.request.Request("https://www.football-data.co.uk/fixtures.csv", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except Exception as e:  # Quoten sind ein Bonus – ohne geht es auch
        print(f"football-data.co.uk nicht erreichbar: {e}")
        return {}

    odds = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("Div") != "D1":
            continue
        try:
            day = datetime.strptime(r["Date"], "%d/%m/%Y").date()
        except (KeyError, ValueError):
            continue
        quotes = None
        for prefix in ("Avg", "B365"):  # Durchschnitt aller Anbieter, sonst Bet365
            try:
                q = [float(r[f"{prefix}{k}"]) for k in ("H", "D", "A")]
            except (KeyError, ValueError):
                continue
            if all(x > 1 for x in q):
                quotes = q
                break
        if not quotes:
            continue
        candidates = [m for m in fixtures if abs((m.kickoff_local.date() - day).days) <= 1]
        if not candidates:
            continue
        score = lambda m: _similar(r["HomeTeam"], teams[m.home_id].name) + _similar(r["AwayTeam"], teams[m.away_id].name)
        best = max(candidates, key=score)
        if score(best) >= 1.2:
            odds[best.match_id] = quotes
    print(f"Quoten von football-data.co.uk für {len(odds)}/{len(fixtures)} Spiele gefunden.")
    return odds
