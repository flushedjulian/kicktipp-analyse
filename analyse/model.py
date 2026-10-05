"""Torerwartung schätzen, Ergebniswahrscheinlichkeiten berechnen und den Tipp mit den meisten erwarteten Punkten wählen."""

import math
from dataclasses import dataclass

# Parameter – per backtest.py auf vergangenen Saisons abgestimmt
HALF_LIFE_DAYS = 150     # nach so vielen Tagen zählt ein Spiel nur noch halb
PRIOR_STRENGTH = 8.0     # wie stark Teams zum Ausgangswert gezogen werden (Schutz bei wenig Daten)
PROMOTED_PRIOR = -0.20   # Aufsteiger starten etwas schwächer (log-Skala, Angriff und Abwehr)
DC_RHO = -0.06           # Dixon-Coles-Korrektur: etwas mehr 0:0 / 1:1 als reiner Poisson
MARKET_WEIGHT = 0.65     # Anteil der Wettquoten an der finalen Torerwartung (falls vorhanden)
MAX_GOALS = 10

# Kicktipp Standard
POINTS_EXACT, POINTS_DIFF, POINTS_TENDENCY = 4, 3, 2


@dataclass
class Ratings:
    mu: float
    home: float
    att: dict
    defe: dict

    def expected_goals(self, home_id, away_id):
        lh = math.exp(self.mu + self.home + self.att.get(home_id, 0) - self.defe.get(away_id, 0))
        la = math.exp(self.mu + self.att.get(away_id, 0) - self.defe.get(home_id, 0))
        return lh, la


def fit_ratings(matches, as_of, team_ids, promoted=()):
    """Gewichtete Poisson-Regression (log λ = mu + heim + angriff − abwehr) mit Zeitabklingen und Prior."""
    data = []
    for m in matches:
        if not m.finished or m.kickoff_utc >= as_of:
            continue
        age = (as_of - m.kickoff_utc).total_seconds() / 86400
        w = 0.5 ** (age / HALF_LIFE_DAYS)
        data.append((m.home_id, m.away_id, float(m.home_goals), float(m.away_goals), w))

    team_ids = set(team_ids) | {d[0] for d in data} | {d[1] for d in data}  # inkl. Absteiger der Vorsaison
    prior = {t: (PROMOTED_PRIOR if t in promoted else 0.0) for t in team_ids}
    att = dict(prior)
    defe = dict(prior)
    mu, home = math.log(1.4), 0.2
    if not data:
        return Ratings(mu, home, att, defe)

    for _ in range(60):
        sa_y = {t: 0.0 for t in team_ids}; sa_l = dict(sa_y)
        sd_y = dict(sa_y); sd_l = dict(sa_y)
        sy = sl = shy = shl = 0.0
        for h, a, yh, ya, w in data:
            lh = math.exp(mu + home + att[h] - defe[a])
            la = math.exp(mu + att[a] - defe[h])
            sa_y[h] += w * yh; sa_l[h] += w * lh
            sa_y[a] += w * ya; sa_l[a] += w * la
            sd_y[a] += w * yh; sd_l[a] += w * lh   # Abwehr von a gegen Tore von h
            sd_y[h] += w * ya; sd_l[h] += w * la
            sy += w * (yh + ya); sl += w * (lh + la)
            shy += w * yh; shl += w * lh
        # Gedämpfte Newton-Schritte je Parameter (Poisson-Log-Likelihood + quadratischer Prior)
        for t in team_ids:
            att[t] += 0.5 * (sa_y[t] - sa_l[t] - PRIOR_STRENGTH * (att[t] - prior[t])) / (sa_l[t] + PRIOR_STRENGTH)
            defe[t] += 0.5 * (sd_l[t] - sd_y[t] - PRIOR_STRENGTH * (defe[t] - prior[t])) / (sd_l[t] + PRIOR_STRENGTH)
        # Angriff und Abwehr auf Mittelwert 0 halten, das Niveau steckt in mu
        ma = sum(att.values()) / len(att)
        md = sum(defe.values()) / len(defe)
        for t in team_ids:
            att[t] -= ma
            defe[t] -= md
        mu += ma - md + 0.5 * math.log(sy / sl)
        home += 0.5 * math.log(shy / shl)
    return Ratings(mu, home, att, defe)


def score_matrix(lh, la, rho=DC_RHO):
    def pois(k, lam):
        return math.exp(-lam) * lam ** k / math.factorial(k)

    ph = [pois(k, lh) for k in range(MAX_GOALS + 1)]
    pa = [pois(k, la) for k in range(MAX_GOALS + 1)]
    mat = [[ph[i] * pa[j] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
    # Dixon-Coles-Anpassung für niedrige Ergebnisse
    mat[0][0] *= 1 - lh * la * rho
    mat[0][1] *= 1 + lh * rho
    mat[1][0] *= 1 + la * rho
    mat[1][1] *= 1 - rho
    total = sum(map(sum, mat))
    return [[p / total for p in row] for row in mat]


def outcome_probs(mat):
    n = len(mat)
    ph = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    pd = sum(mat[i][i] for i in range(n))
    return ph, pd, 1 - ph - pd


def over25(mat):
    n = len(mat)
    return sum(mat[i][j] for i in range(n) for j in range(n) if i + j > 2)


def kicktipp_points(tip, result):
    th, ta = tip
    rh, ra = result
    if th == rh and ta == ra:
        return POINTS_EXACT
    if (th > ta) - (th < ta) != (rh > ra) - (rh < ra):
        return 0
    if th - ta == rh - ra:
        return POINTS_DIFF
    return POINTS_TENDENCY


def expected_points(mat, max_tip=5):
    """Erwartete Kicktipp-Punkte für jeden möglichen Tipp, absteigend sortiert."""
    n = len(mat)
    out = []
    for th in range(max_tip + 1):
        for ta in range(max_tip + 1):
            ev = sum(mat[i][j] * kicktipp_points((th, ta), (i, j)) for i in range(n) for j in range(n))
            out.append(((th, ta), ev))
    out.sort(key=lambda x: -x[1])
    return out


def lambdas_from_market(p_home, p_away, p_over25=None):
    """Sucht die Torerwartungen, die am besten zu den Wettquoten passen (grob, dann fein)."""
    def err(lh, la):
        mat = score_matrix(lh, la)
        h, _, a = outcome_probs(mat)
        e = (h - p_home) ** 2 + (a - p_away) ** 2
        if p_over25 is not None:
            e += (over25(mat) - p_over25) ** 2
        return e

    best = min(((lh / 10, la / 10) for lh in range(2, 45) for la in range(2, 45)), key=lambda x: err(*x))
    lo_h, lo_a = best
    fine = [(lo_h + dh / 100, lo_a + da / 100) for dh in range(-10, 11) for da in range(-10, 11)]
    return min((x for x in fine if x[0] > 0.05 and x[1] > 0.05), key=lambda x: err(*x))


def blend(model_l, market_l, weight=MARKET_WEIGHT):
    return tuple(math.exp((1 - weight) * math.log(m) + weight * math.log(k)) for m, k in zip(model_l, market_l))
