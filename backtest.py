"""Testet das Modell auf vergangenen Saisons: Was hätte es vor jedem Spieltag getippt, wie viele Punkte wären es gewesen?

Aufruf:  python3 backtest.py            (Saisons 2024 und 2025)
         python3 backtest.py --tune     (probiert Parameter-Kombinationen durch)
"""

import itertools
import math
import sys

from analyse import data, model

SEASONS = [2024, 2025]


def load(season, cache={}):
    if season not in cache:
        teams = {}
        prev = data.load_season(season - 1, teams)
        cur = data.load_season(season, teams)
        data.attach_understat_xg(season - 1, prev, teams)
        data.attach_understat_xg(season, cur, teams)
        cache[season] = (prev, cur)
    return cache[season]


def run(season, start_md=3):
    prev, cur = load(season)
    all_matches = prev + cur
    team_ids = {m.home_id for m in cur} | {m.away_id for m in cur}
    promoted = team_ids - {m.home_id for m in prev}
    pts = base = n = hits = exact = 0
    logloss = 0.0
    for md in range(start_md, 35):
        games = [m for m in cur if m.matchday == md and m.finished]
        if not games:
            continue
        as_of = min(m.kickoff_utc for m in games)
        r = model.fit_ratings(all_matches, as_of, team_ids, promoted)
        for m in games:
            mat = model.score_matrix(*r.expected_goals(m.home_id, m.away_id))
            tip = model.expected_points(mat)[0][0]
            res = (m.home_goals, m.away_goals)
            p = model.kicktipp_points(tip, res)
            pts += p
            base += model.kicktipp_points((2, 1), res)
            hits += p > 0
            exact += p == 4
            ph, pd, pa = model.outcome_probs(mat)
            real = ph if res[0] > res[1] else pd if res[0] == res[1] else pa
            logloss -= math.log(real)
            n += 1
    return dict(n=n, ppg=pts / n, base=base / n, tendency=hits / n, exact=exact / n, logloss=logloss / n)


def report():
    for s in SEASONS:
        r = run(s)
        print(
            f"Saison {s}/{s + 1 - 2000}: {r['n']} Spiele | Modell {r['ppg']:.2f} Pkt/Spiel "
            f"(≈{r['ppg'] * 306:.0f} pro Saison) | immer 2:1 Heim: {r['base']:.2f} | "
            f"Tendenz richtig {r['tendency']:.0%} | exakt {r['exact']:.0%} | LogLoss {r['logloss']:.3f}"
        )


def tune():
    grid = {
        "HALF_LIFE_DAYS": [90, 150, 250],
        "XG_WEIGHT": [0.0, 0.4, 0.6, 0.8],
        "PRIOR_STRENGTH": [2.0, 4.0, 8.0],
    }
    results = []
    for combo in itertools.product(*grid.values()):
        for k, v in zip(grid, combo):
            setattr(model, k, v)
        rs = [run(s) for s in SEASONS]
        ll = sum(r["logloss"] for r in rs) / len(rs)
        ppg = sum(r["ppg"] for r in rs) / len(rs)
        results.append((ll, ppg, combo))
        print(dict(zip(grid, combo)), f"LogLoss {ll:.4f}  Pkt/Spiel {ppg:.3f}", flush=True)
    results.sort()
    print("\nBeste nach LogLoss:")
    for ll, ppg, combo in results[:5]:
        print(dict(zip(grid, combo)), f"{ll:.4f}  {ppg:.3f}")


if __name__ == "__main__":
    tune() if "--tune" in sys.argv else report()
