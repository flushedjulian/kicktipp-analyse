"""Erstellt die Analyse für den nächsten Bundesliga-Spieltag und schreibt die Webseite nach docs/.

Aufruf:  python3 -m analyse.main
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import data, model, render

ROOT = Path(__file__).resolve().parent.parent
PRED_DIR = ROOT / "data" / "predictions"
DOCS = ROOT / "docs"


def current_season(now):
    return now.year if now.month >= 7 else now.year - 1


def pick_matchday(matches, now):
    """Spieltag mit den meisten der nächsten anstehenden Spiele (robust gegen einzelne Nachholspiele)."""
    upcoming = sorted((m for m in matches if not m.finished and m.kickoff_utc > now - timedelta(hours=12)), key=lambda m: m.kickoff_utc)
    if not upcoming:
        return None
    return Counter(m.matchday for m in upcoming[:9]).most_common(1)[0][0]


def table(matches):
    rows = defaultdict(lambda: dict(sp=0, s=0, u=0, n=0, tore=0, gegen=0, pkt=0))
    for m in matches:
        if not m.finished:
            continue
        for tid, gf, ga in ((m.home_id, m.home_goals, m.away_goals), (m.away_id, m.away_goals, m.home_goals)):
            r = rows[tid]
            r["sp"] += 1; r["tore"] += gf; r["gegen"] += ga
            if gf > ga: r["s"] += 1; r["pkt"] += 3
            elif gf == ga: r["u"] += 1; r["pkt"] += 1
            else: r["n"] += 1
    order = sorted(rows, key=lambda t: (-rows[t]["pkt"], -(rows[t]["tore"] - rows[t]["gegen"]), -rows[t]["tore"]))
    return {t: dict(rows[t], platz=i + 1) for i, t in enumerate(order)}


def team_form(matches, tid, n=5, venue=None):
    """Letzte n Spiele eines Teams (venue: 'heim'/'auswärts'/None)."""
    games = []
    for m in sorted((m for m in matches if m.finished), key=lambda m: m.kickoff_utc, reverse=True):
        is_home = m.home_id == tid
        if not is_home and m.away_id != tid:
            continue
        if venue == "heim" and not is_home or venue == "auswärts" and is_home:
            continue
        gf, ga = (m.home_goals, m.away_goals) if is_home else (m.away_goals, m.home_goals)
        games.append(dict(gegner=m.away_id if is_home else m.home_id, heim=is_home, tore=gf, gegen=ga,
                          res="S" if gf > ga else "U" if gf == ga else "N", datum=m.kickoff_local))
        if len(games) == n:
            break
    return games


def head_to_head(matches, a, b, n=4):
    games = [m for m in matches if m.finished and {m.home_id, m.away_id} == {a, b}]
    return sorted(games, key=lambda m: m.kickoff_utc, reverse=True)[:n]


def top_scorers(matches, tid, n=2):
    c = Counter(name for m in matches for t, name, og in m.scorers if t == tid and not og)
    return c.most_common(n)


def load_predictions():
    out = {}
    for f in sorted(PRED_DIR.glob("*.json")):
        out[f.stem] = json.loads(f.read_text())
    return out


def evaluate_history(predictions, matches_by_id):
    """Wie viele Punkte hätten die Empfehlungen pro Spieltag gebracht?"""
    hist = []
    for key, pred in sorted(predictions.items()):
        rows, pts, done = [], 0, 0
        for g in pred["spiele"]:
            m = matches_by_id.get(g["match_id"])
            if not m or not m.finished:
                continue
            p = model.kicktipp_points(tuple(g["tipp"]), (m.home_goals, m.away_goals))
            pts += p; done += 1
            rows.append(dict(g, ergebnis=[m.home_goals, m.away_goals], punkte=p))
        if done:
            hist.append(dict(saison=pred["saison"], spieltag=pred["spieltag"], punkte=pts, spiele=done, details=rows))
    return hist


def main():
    now = datetime.now(timezone.utc)
    season = current_season(now)
    teams = {}
    prev = data.load_season(season - 1, teams)
    cur = data.load_season(season, teams)

    md = pick_matchday(cur, now)
    if md is None:
        print("Keine anstehenden Spiele – Saison vorbei?")
        return
    fixtures = sorted((m for m in cur if m.matchday == md), key=lambda m: (m.kickoff_utc, m.match_id))
    team_ids = {m.home_id for m in cur} | {m.away_id for m in cur}
    promoted = team_ids - {m.home_id for m in prev}
    ratings = model.fit_ratings(prev + cur, now, team_ids, promoted)
    tab = table(cur)
    all_matches = prev + cur

    # bereits gespeicherte Tipps für schon angepfiffene Spiele nicht mehr ändern
    key = f"{season}-{md:02d}"
    pred_file = PRED_DIR / f"{key}.json"
    old = {g["match_id"]: g for g in json.loads(pred_file.read_text())["spiele"]} if pred_file.exists() else {}

    # Quoten: neu geholte haben Vorrang, sonst die zuletzt gespeicherten (football-data.co.uk
    # nimmt Spiele nach dem Anpfiff aus der Liste)
    odds = {mid: g["quoten"] for mid, g in old.items() if g.get("quoten")}
    odds_since = {mid: g.get("quoten_seit") for mid, g in old.items() if g.get("quoten")}
    for mid, q in data.load_fd_odds(fixtures, teams).items():
        if q != odds.get(mid) or not odds_since.get(mid):  # neu oder geändert → Zeitpunkt merken
            odds_since[mid] = now.isoformat(timespec="minutes")
        odds[mid] = q

    games = []
    for m in fixtures:
        model_l = ratings.expected_goals(m.home_id, m.away_id)
        quotes = odds.get(m.match_id)
        if quotes:
            inv = [1 / q for q in quotes]
            market_l = model.lambdas_from_market(inv[0] / sum(inv), inv[2] / sum(inv))
            lambdas = model.blend(model_l, market_l)
        else:
            lambdas = model_l
        mat = model.score_matrix(*lambdas)
        ph, pd, pa = model.outcome_probs(mat)
        evs = model.expected_points(mat)
        tip = evs[0][0]
        locked = m.kickoff_utc <= now and m.match_id in old
        if locked:
            tip = tuple(old[m.match_id]["tipp"])
        likely = sorted(((i, j, mat[i][j]) for i in range(6) for j in range(6)), key=lambda x: -x[2])[:6]
        games.append(dict(
            match=m, home=teams[m.home_id], away=teams[m.away_id],
            tip=tip, locked=locked, evs=evs[:4], probs=(ph, pd, pa), lambdas=lambdas, likely=likely,
            model_l=model_l, quotes=quotes, quotes_since=odds_since.get(m.match_id) if quotes else None,
            tab_home=tab.get(m.home_id), tab_away=tab.get(m.away_id),
            form_home=team_form(all_matches, m.home_id), form_away=team_form(all_matches, m.away_id),
            venue_home=team_form(cur, m.home_id, venue="heim"), venue_away=team_form(cur, m.away_id, venue="auswärts"),
            h2h=head_to_head(all_matches, m.home_id, m.away_id),
            scorers_home=top_scorers(cur, m.home_id), scorers_away=top_scorers(cur, m.away_id),
        ))

    PRED_DIR.mkdir(parents=True, exist_ok=True)
    pred_file.write_text(json.dumps(dict(
        saison=season, spieltag=md, erstellt=now.isoformat(timespec="minutes"),
        spiele=[dict(match_id=g["match"].match_id, heim=g["home"].short, gast=g["away"].short, tipp=list(g["tip"]),
                     p=[round(x, 3) for x in g["probs"]], quoten=g["quotes"], quoten_seit=g["quotes_since"]) for g in games],
    ), ensure_ascii=False, indent=1))

    history = evaluate_history(load_predictions(), {m.match_id: m for m in cur + prev})
    DOCS.mkdir(exist_ok=True)
    html = render.page(season=season, matchday=md, games=games, teams=teams, table=tab, history=history,
                       generated=now)
    (DOCS / "index.html").write_text(html)
    (DOCS / f"spieltag-{key}.html").write_text(html)
    print(f"Fertig: Spieltag {md}, {len(games)} Spiele → docs/index.html")


if __name__ == "__main__":
    main()
