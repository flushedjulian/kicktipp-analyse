"""Daten holen: Spielplan/Ergebnisse (OpenLigaDB), xG (Understat), Wettquoten (The Odds API)."""

import difflib
import gzip
import json
import os
import ssl
import unicodedata
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
    home_xg: float | None = None
    away_xg: float | None = None
    scorers: list = field(default_factory=list)  # (team_id, name, is_own_goal)


@dataclass
class Team:
    team_id: int
    name: str
    short: str
    icon: str


def _parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_season(season, teams):
    """Alle Spiele einer Bundesliga-Saison von OpenLigaDB. Füllt `teams` nebenbei."""
    raw = _get_json(f"https://api.openligadb.de/getmatchdata/bl1/{season}")
    matches = []
    for m in raw:
        for t in (m["team1"], m["team2"]):
            teams.setdefault(t["teamId"], Team(t["teamId"], t["teamName"], t["shortName"], t["teamIconUrl"]))
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


def attach_understat_xg(season, matches, teams):
    """Hängt xG-Werte von Understat an die Spiele. Teams werden über gemeinsame Anstoßzeiten zugeordnet,
    damit keine Namensliste gepflegt werden muss. Gibt die Anzahl zugeordneter Spiele zurück."""
    try:
        data = _get_json(
            f"https://understat.com/getLeagueData/Bundesliga/{season}",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    except Exception as e:  # xG ist ein Bonus – ohne geht es auch
        print(f"Understat {season} nicht erreichbar: {e}")
        return 0

    by_day = defaultdict(list)
    for m in matches:
        if m.finished:
            by_day[m.kickoff_utc.date()].append(m)

    n = 0
    for g in data["dates"]:
        if not g["isResult"]:
            continue
        day = datetime.strptime(g["datetime"], "%Y-%m-%d %H:%M:%S").date()
        candidates = by_day.get(day, [])
        if not candidates:
            continue
        best = max(candidates, key=lambda m: _similar(g["h"]["title"], teams[m.home_id].name) + _similar(g["a"]["title"], teams[m.away_id].name))
        score = _similar(g["h"]["title"], teams[best.home_id].name) + _similar(g["a"]["title"], teams[best.away_id].name)
        if score >= 1.0:
            best.home_xg, best.away_xg = float(g["xG"]["h"]), float(g["xG"]["a"])
            n += 1
    return n


# ---------------------------------------------------------------- Wettquoten

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


def load_odds(fixtures, teams):
    """Holt 1X2- und Über/Unter-Quoten (The Odds API) und rechnet sie in faire Wahrscheinlichkeiten um.
    Rückgabe: {match_id: {"p_home","p_draw","p_away","p_over25"(optional),"n_books"}}"""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        print("Kein ODDS_API_KEY gesetzt – Analyse ohne Wettquoten.")
        return {}
    url = (
        "https://api.the-odds-api.com/v4/sports/soccer_germany_bundesliga/odds"
        f"?apiKey={key}&regions=eu&markets=h2h,totals&oddsFormat=decimal"
    )
    try:
        events = _get_json(url)
    except Exception as e:
        print(f"Wettquoten nicht abrufbar: {e}")
        return {}

    result = {}
    for m in fixtures:
        home, away = teams[m.home_id].name, teams[m.away_id].name
        best, best_score = None, 0.0
        for ev in events:
            if abs(_parse_utc(ev["commence_time"]) - m.kickoff_utc) > timedelta(hours=3):
                continue
            score = _similar(ev["home_team"], home) + _similar(ev["away_team"], away)
            if score > best_score:
                best, best_score = ev, score
        if not best or best_score < 1.2:
            continue

        h2h, over = [], []
        for bm in best.get("bookmakers", []):
            for mk in bm.get("markets", []):
                outs = mk.get("outcomes", [])
                if mk["key"] == "h2h" and len(outs) == 3:
                    price = {o["name"]: o["price"] for o in outs}
                    try:
                        inv = [1 / price[best["home_team"]], 1 / price["Draw"], 1 / price[best["away_team"]]]
                    except KeyError:
                        continue
                    total = sum(inv)
                    h2h.append([x / total for x in inv])
                elif mk["key"] == "totals":
                    by_name = {o["name"]: o for o in outs if o.get("point") == 2.5}
                    if "Over" in by_name and "Under" in by_name:
                        io, iu = 1 / by_name["Over"]["price"], 1 / by_name["Under"]["price"]
                        over.append(io / (io + iu))
        if not h2h:
            continue
        avg = [sum(x[i] for x in h2h) / len(h2h) for i in range(3)]
        entry = {"p_home": avg[0], "p_draw": avg[1], "p_away": avg[2], "n_books": len(h2h)}
        if over:
            entry["p_over25"] = sum(over) / len(over)
        result[m.match_id] = entry
    print(f"Wettquoten für {len(result)}/{len(fixtures)} Spiele gefunden.")
    return result
