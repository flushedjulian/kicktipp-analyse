"""Erzeugt die HTML-Seite (Gestaltung angelehnt an TippBase)."""

import json
from html import escape
from zoneinfo import ZoneInfo

from . import model

BERLIN = ZoneInfo("Europe/Berlin")
WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONAT = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _when(dt):
    return f"{WOCHENTAG[dt.weekday()]} {dt:%d.%m.} · {dt:%H:%M}"


def _when_short(dt):
    return f"{WOCHENTAG[dt.weekday()]} {dt:%H:%M}"


def _date_range(first, last):
    if first.date() == last.date():
        return f"{first.day}. {MONAT[first.month - 1]}"
    if first.month == last.month:
        return f"{first.day}.–{last.day}. {MONAT[first.month - 1]}"
    return f"{first.day}. {MONAT[first.month - 1][:3]}. – {last.day}. {MONAT[last.month - 1][:3]}."


def _pct(p):
    return f"{round(p * 100)} %"


def _tip(t):
    return f"{t[0]}:{t[1]}"


def _score(t):
    return f'{t[0]}<span class="sep">:</span>{t[1]}'


def _logo(team, size):
    return (f'<img class="crest" src="{escape(team.icon)}" alt="" width="{size}" height="{size}" '
            f'loading="lazy" referrerpolicy="no-referrer" onerror="this.style.visibility=\'hidden\'">')


CONFIDENCE = {"hoch": "Klarer Favorit", "mittel": "Leichter Favorit", "niedrig": "Offenes Spiel"}


def _confidence(g):
    ph, pd, pa = g["probs"]
    th, ta = g["tip"]
    p = ph if th > ta else pd if th == ta else pa
    level = "hoch" if p >= 0.62 else "mittel" if p >= 0.45 else "niedrig"
    return level, CONFIDENCE[level]


def _badge_text(g, level):
    th, ta = g["tip"]
    if level == "niedrig" or th == ta:
        return "Offenes Spiel"
    team = g["home"].short if th > ta else g["away"].short
    return f"{team} {'klarer' if level == 'hoch' else 'leichter'} Favorit"


def _fmt(x, d=1):
    return "–" if x is None else f"{x:.{d}f}".replace(".", ",")


def _avg(form, key):
    vals = [f[key] for f in form if f[key] is not None]
    return sum(vals) / len(vals) if vals else None


def _form_chips(form, teams):
    if not form:
        return '<span class="dim">–</span>'
    out = []
    for f in reversed(form):  # ältestes links
        where = "H" if f["heim"] else "A"
        title = f'{f["datum"]:%d.%m.%y} {where} {teams[f["gegner"]].short} {f["tore"]}:{f["gegen"]}'
        out.append(f'<span class="chip {f["res"]}" title="{escape(title)}">{f["res"]}</span>')
    return "".join(out)


def _bar(probs, home, away):
    ph, pd, pa = probs
    return f"""<div class="bar" role="img" aria-label="Heimsieg {_pct(ph)}, Unentschieden {_pct(pd)}, Auswärtssieg {_pct(pa)}">
        <span class="seg h" style="width:{ph * 100:.1f}%"></span><span class="seg d" style="width:{pd * 100:.1f}%"></span><span class="seg a" style="width:{pa * 100:.1f}%"></span>
      </div>
      <div class="bar-legend"><span>{escape(home.short)} {_pct(ph)}</span><span>Remis {_pct(pd)}</span><span>{escape(away.short)} {_pct(pa)}</span></div>"""


def _alt_text(g):
    if g["locked"]:
        return ""
    best = g["evs"][0][1]
    alts = [_tip(t) for t, ev in g["evs"][1:] if best - ev < 0.03]
    return "Alternativ " + ", ".join(alts) if alts else ""


def _card(g, teams, idx):
    m, home, away = g["match"], g["home"], g["away"]
    level, label = _confidence(g)
    lh, la = g["lambdas"]

    evs = "".join(
        f'<tr{" class=best" if i == 0 else ""}><td>{_tip(t)}</td><td>{_fmt(ev, 2)}</td></tr>' for i, (t, ev) in enumerate(g["evs"])
    )
    likely = "".join(f'<span class="res">{i}:{j} <small>{_pct(p)}</small></span>' for i, j, p in g["likely"])

    def team_block(team, tab, form, venue, venue_label, scorers):
        pos = f'{tab["platz"]}. Platz · {tab["pkt"]} Punkte · {tab["tore"]}:{tab["gegen"]} Tore' if tab else "Noch keine Spiele"
        xg, xga = _avg(form, "xg"), _avg(form, "xga")
        sc = ", ".join(f"{escape(n)} ({c})" for n, c in scorers) or "–"
        return f"""
        <div class="team-block">
          <div class="team-head">{_logo(team, 22)}<div><b>{escape(team.short)}</b><span>{pos}</span></div></div>
          <dl>
            <dt>Letzte 5</dt><dd>{_form_chips(form, teams)}</dd>
            <dt>{venue_label}</dt><dd>{_form_chips(venue, teams)}</dd>
            <dt>xG letzte 5</dt><dd>{_fmt(xg)} für · {_fmt(xga)} gegen</dd>
            <dt>Torschützen</dt><dd>{sc}</dd>
          </dl>
        </div>"""

    h2h = "".join(
        f'<li><span>{escape(teams[h.home_id].short)} – {escape(teams[h.away_id].short)}</span><b>{h.home_goals}:{h.away_goals}</b><span class="dim">{h.kickoff_local:%d.%m.%y}</span></li>'
        for h in g["h2h"]
    ) or '<li class="dim">Keine Spiele in den letzten zwei Saisons</li>'

    lock = '<span class="lock" title="Angepfiffen, Tipp steht fest">🔒</span>' if g["locked"] else ""

    return f"""
<article class="card match-card" id="spiel-{idx}" data-idx="{idx}">
  <details>
    <summary>
      <div class="ctime">{_when(m.kickoff_local)}</div>
      <div class="match">
        <div class="side">{_logo(home, 40)}<span class="tname">{escape(home.short)}</span></div>
        <div class="center">
          <span class="cap">Tipp{lock}</span>
          <span class="score js-tip"><span class="js-tiptext">{_score(g["tip"])}</span></span>
          <span class="mine js-mine"{"" if g["quotes"] else " hidden"}>mit Quoten</span>
        </div>
        <div class="side">{_logo(away, 40)}<span class="tname">{escape(away.short)}</span></div>
      </div>
      <div class="js-bar">{_bar(g["probs"], home, away)}</div>
      <p class="alt js-alt">{_alt_text(g)}</p>
      <div class="card-foot">
        <span class="badge js-badge conf-{level}">{escape(_badge_text(g, level))}</span>
        <span class="more">Details</span>
      </div>
    </summary>
    <div class="details">
      <section>
        <h3>Erwartete Tore</h3>
        <p class="xg js-xg">{_fmt(lh, 2)} : {_fmt(la, 2)}</p>
      </section>
      <section>
        <h3>Wahrscheinlichste Ergebnisse</h3>
        <div class="results js-likely">{likely}</div>
      </section>
      <section>
        <h3>Erwartete Punkte je Tipp</h3>
        <table class="ev"><tbody class="js-ev">{evs}</tbody></table>
      </section>
      <section class="teams">
        {team_block(home, g["tab_home"], g["form_home"], g["venue_home"], "Heim", g["scorers_home"])}
        {team_block(away, g["tab_away"], g["form_away"], g["venue_away"], "Auswärts", g["scorers_away"])}
      </section>
      <section>
        <h3>Direkter Vergleich</h3>
        <ul class="h2h">{h2h}</ul>
      </section>
    </div>
  </details>
</article>"""


def _overview(games):
    rows = []
    for i, g in enumerate(games):
        level, _ = _confidence(g)
        rows.append(
            f'<a class="ov-row" href="#spiel-{i}" data-idx="{i}">'
            f'<span class="ov-teams"><b>{escape(g["home"].short)} – {escape(g["away"].short)}</b><span>{_when_short(g["match"].kickoff_local)}</span></span>'
            f'<span class="pill js-ov-tip conf-{level}">{_tip(g["tip"])}</span></a>'
        )
    return "".join(rows)


def _odds_panel(games):
    rows = []
    for i, g in enumerate(games):
        h, a = escape(g["home"].short), escape(g["away"].short)
        dis = " disabled" if g["locked"] else ""
        fields = "".join(
            f'<input type="text" inputmode="decimal" enterkeyhint="next" autocomplete="off" class="odd" data-k="{k}" '
            f'placeholder="{ph}" aria-label="Quote {lbl}"{dis}>'
            for (k, lbl), ph in zip((("1", f"Sieg {h}"), ("X", "Unentschieden"), ("2", f"Sieg {a}")),
                                    [_fmt(q, 2) for q in g["quotes"]] if g["quotes"] else ("1", "X", "2"))
        )
        state = "angepfiffen" if g["locked"] else "automatisch" if g["quotes"] else ""
        rows.append(f'<div class="odds-row" data-idx="{i}"><span class="odds-match">{h} – {a}</span>{fields}<span class="odds-state">{state}</span></div>')
    return f"""
  <details class="card odds" id="quoten">
    <summary><span class="odds-title">Quoten</span><span class="more">{_odds_summary(games)}</span></summary>
    <p class="odds-help">1&nbsp;=&nbsp;Heimsieg, X&nbsp;=&nbsp;Unentschieden, 2&nbsp;=&nbsp;Auswärtssieg. Die Quoten werden automatisch eingerechnet, sobald sie verfügbar sind (meist ab Donnerstag oder Freitag) und stehen dann grau in den Feldern. Wer früher tippen will, kann sie hier selbst eintragen. Eigene Quoten bleiben auf diesem Gerät gespeichert.</p>
    <div class="odds-head"><span></span><span>1</span><span>X</span><span>2</span><span></span></div>
    {"".join(rows)}
    <button type="button" class="linkbtn js-clear">Alle Quoten löschen</button>
  </details>"""


def _odds_status(games):
    n = sum(1 for g in games if g["quotes"])
    if n == len(games):
        return "Quoten eingerechnet"
    if n:
        return f"Quoten für {n} von {len(games)} Spielen"
    return "Quoten folgen, meist Do/Fr"


def _odds_summary(games):
    n = sum(1 for g in games if g["quotes"])
    return f"{n}/{len(games)} automatisch" if n else "selbst eintragen"


def _history(history):
    if not history:
        return '<div class="card empty">Noch keine Spiele ausgewertet.</div>'
    total = sum(h["punkte"] for h in history)
    n = sum(h["spiele"] for h in history)
    rows = []
    for h in reversed(history):
        detail = "".join(
            f'<li><span>{escape(d["heim"])} – {escape(d["gast"])}</span><span class="dim">{_tip(d["tipp"])} → {_tip(d["ergebnis"])}</span><b class="p{d["punkte"]}">+{d["punkte"]}</b></li>'
            for d in h["details"]
        )
        rows.append(
            f'<details class="hist"><summary><span>{h["spieltag"]}. Spieltag</span><span><b>{h["punkte"]}</b> <span class="dim">Pkt.</span></span></summary>'
            f'<ul class="hist-list">{detail}</ul></details>'
        )
    return f"""
    <div class="stats">
      <div class="statcard"><div class="v">{total}</div><div class="l">Punkte</div></div>
      <div class="statcard"><div class="v">{_fmt(total / n, 2)}</div><div class="l">pro Spiel</div></div>
      <div class="statcard"><div class="v">{n}</div><div class="l">Spiele</div></div>
    </div>
    <div class="card list">{"".join(rows)}</div>"""


def _script(games, season):
    data = [dict(id=g["match"].match_id, lam=[round(x, 4) for x in g["model_l"]],
                 auto=[round(x, 4) for x in g["lambdas"]] if g["quotes"] else None, locked=g["locked"], tip=list(g["tip"]),
                 home=g["home"].short, away=g["away"].short)
            for g in games]
    cfg = dict(rho=model.DC_RHO, maxGoals=model.MAX_GOALS, w=model.MARKET_WEIGHT,
               pts=[model.POINTS_EXACT, model.POINTS_DIFF, model.POINTS_TENDENCY], season=season, labels=CONFIDENCE)
    return f"<script>const GAMES={json.dumps(data, ensure_ascii=False)};const CFG={json.dumps(cfg, ensure_ascii=False)};\n{JS}</script>"


def page(season, matchday, games, teams, table, history, generated):
    first = min(g["match"].kickoff_local for g in games)
    last = max(g["match"].kickoff_local for g in games)
    gen = generated.astimezone(BERLIN)
    cards = "".join(_card(g, teams, i) for i, g in enumerate(games))
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Kicktipp · {matchday}. Spieltag</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<style>{CSS}</style>
</head>
<body>
<main>
  <header class="top">
    <p class="eyebrow">Bundesliga {season}/{(season + 1) % 100:02d}</p>
    <h1>{matchday}. Spieltag</h1>
    <div class="meta">
      <span class="meta-date">{_date_range(first, last)}</span>
      <span class="meta-stand">Stand {gen:%d.%m.}, {gen:%H:%M} Uhr<br>{_odds_status(games)}</span>
    </div>
  </header>

  <h2 class="sectionhead">Tipps</h2>
  <div class="card list">{_overview(games)}</div>
  <div class="legend"><span><i class="dot conf-hoch"></i>Klarer Favorit</span><span><i class="dot conf-mittel"></i>Leichter Favorit</span><span><i class="dot conf-niedrig"></i>Offenes Spiel</span></div>

  {_odds_panel(games)}

  <h2 class="sectionhead">Spiele</h2>
  {cards}

  <h2 class="sectionhead">Bilanz</h2>
  {_history(history)}

  <h2 class="sectionhead">So wird gerechnet</h2>
  <div class="card about">
    <ul>
      <li>Angriffs- und Abwehrstärke jedes Teams aus dieser und der letzten Saison, neuere Spiele zählen mehr</li>
      <li>Grundlage sind vor allem die xG-Werte (Qualität der Torchancen), nicht nur die Tore</li>
      <li>Wettquoten zählen zu 65 % mit (automatisch von football-data.co.uk, meist ab Do/Fr)</li>
      <li>Empfohlen wird der Tipp mit den meisten erwarteten Punkten (4/3/2)</li>
    </ul>
    <p class="dim">Daten: OpenLigaDB, Understat, football-data.co.uk</p>
  </div>
</main>
{_script(games, season)}
</body>
</html>"""


CSS = """
:root{
  --bg:#fff;--card:#fff;--text:#000;--text2:#8e8e93;--text3:#aeaeb2;
  --sep:rgba(60,60,67,.09);--border:rgba(17,24,39,.06);
  --shadow:0 1px 2px rgba(16,24,40,.04),0 10px 26px -12px rgba(16,24,40,.13);
  --accent:#0f766e;--accent-soft:rgba(13,148,136,.12);--accent-line:rgba(13,148,136,.4);
  --green:#1f9d47;--green-soft:rgba(48,209,88,.13);--green-line:rgba(48,209,88,.5);
  --blue:#0a6fd6;--blue-soft:rgba(10,132,255,.13);--blue-line:rgba(10,132,255,.5);
  --gray-soft:rgba(120,120,128,.12);--gray-line:rgba(120,120,128,.4);
  --red:#ff453a;--field:#f2f2f7;--radius:20px;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#000;--card:#1c1c1e;--text:#fff;--text2:#98989f;--text3:#636366;
    --sep:rgba(255,255,255,.07);--border:rgba(255,255,255,.07);
    --shadow:0 1px 2px rgba(0,0,0,.4),0 14px 30px -14px rgba(0,0,0,.6);
    --accent:#2dd4bf;--accent-soft:rgba(45,212,191,.18);--accent-line:rgba(45,212,191,.45);
    --green:#30d158;--blue:#4c9dff;--blue-soft:rgba(76,157,255,.16);--blue-line:rgba(76,157,255,.5);
    --gray-line:rgba(170,170,175,.3);--field:#2c2c2e;
  }
}
:root[data-theme="dark"]{
  --bg:#000;--card:#1c1c1e;--text:#fff;--text2:#98989f;--text3:#636366;
  --sep:rgba(255,255,255,.07);--border:rgba(255,255,255,.07);
  --shadow:0 1px 2px rgba(0,0,0,.4),0 14px 30px -14px rgba(0,0,0,.6);
  --accent:#2dd4bf;--accent-soft:rgba(45,212,191,.18);--accent-line:rgba(45,212,191,.45);
  --green:#30d158;--blue:#4c9dff;--blue-soft:rgba(76,157,255,.16);--blue-line:rgba(76,157,255,.5);
  --gray-line:rgba(170,170,175,.3);--field:#2c2c2e;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%}
main{max-width:480px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 20px) 16px calc(env(safe-area-inset-bottom) + 48px)}
p{margin:0}
.dim{color:var(--text2)}

/* Kopf */
.top{padding:0 4px 6px}
.eyebrow{font-size:13px;font-weight:700;color:var(--accent);letter-spacing:.01em}
h1{font-size:34px;font-weight:700;letter-spacing:-.02em;margin:2px 0 10px;line-height:1.1}
.meta{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.meta-date{font-size:15px;font-weight:600;color:var(--text);background:var(--card);border:1px solid var(--border);
  box-shadow:var(--shadow);padding:6px 12px;border-radius:20px}
.meta-stand{font-size:12px;color:var(--text2);text-align:right;line-height:1.4}

.sectionhead{font-size:13px;font-weight:600;color:var(--text2);margin:24px 4px 8px}

/* Karten */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:12px}
.card.list{padding:0 16px;overflow:hidden}
summary{list-style:none;cursor:pointer}
summary::-webkit-details-marker{display:none}
.more{font-size:13px;font-weight:600;color:var(--text2);white-space:nowrap}
.more::after{content:"";display:inline-block;width:6px;height:6px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;
  transform:rotate(45deg);margin:0 2px 3px 7px;transition:transform .15s}
details[open]>summary .more::after{transform:rotate(-135deg);margin:0 2px -1px 7px;vertical-align:middle}

/* Übersicht */
.ov-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-top:.5px solid var(--sep);color:inherit;text-decoration:none}
.ov-row:first-child{border-top:0}
.ov-teams{display:flex;flex-direction:column;min-width:0}
.ov-teams b{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-teams span{font-size:12px;color:var(--text2);margin-top:1px}
.pill{flex:none;min-width:54px;text-align:center;font-size:15px;font-weight:800;font-variant-numeric:tabular-nums;padding:5px 12px;border-radius:20px;border:1.5px solid}
.ov-row.has-mine .pill{box-shadow:0 0 0 3px var(--accent-soft)}
.conf-hoch.pill,.conf-hoch.badge{color:var(--green);background:var(--green-soft);border-color:var(--green-line)}
.conf-mittel.pill,.conf-mittel.badge{color:var(--blue);background:var(--blue-soft);border-color:var(--blue-line)}
.conf-niedrig.pill,.conf-niedrig.badge{color:var(--text2);background:var(--gray-soft);border-color:var(--gray-line)}
.legend{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;font-size:12px;color:var(--text2);margin:2px 0 14px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;border:1.5px solid}
.dot.conf-hoch{background:var(--green-soft);border-color:var(--green)}
.dot.conf-mittel{background:var(--blue-soft);border-color:var(--blue)}
.dot.conf-niedrig{background:var(--gray-soft);border-color:var(--text3)}

/* Spielkarte */
.match-card>details>summary{padding:15px}
.ctime{text-align:center;font-size:13px;color:var(--text2);font-weight:500;margin-bottom:12px}
.match{display:flex;align-items:center;gap:8px}
.side{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;min-width:0}
.crest{object-fit:contain;flex:none}
.tname{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.center{flex-shrink:0;min-width:96px;display:flex;flex-direction:column;align-items:center}
.cap{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.06em}
.lock{font-size:10px;margin-left:3px}
.score{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.15}
.score .sep{color:var(--text3);margin:0 5px;font-weight:600}
.mine{font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent-line);padding:1px 8px;border-radius:20px;margin-top:3px}
.mine[hidden]{display:none}
.bar{display:flex;height:6px;border-radius:99px;overflow:hidden;margin-top:14px;background:var(--sep);gap:2px}
.seg{border-radius:99px}
.seg.h{background:var(--accent)}.seg.d{background:var(--text3)}.seg.a{background:var(--blue)}
.bar-legend{display:flex;justify-content:space-between;gap:8px;font-size:12px;font-weight:600;margin-top:5px;font-variant-numeric:tabular-nums}
.bar-legend span{white-space:nowrap}
.bar-legend span:nth-child(1){color:var(--accent)}
.bar-legend span:nth-child(2){color:var(--text2);font-weight:500}
.bar-legend span:nth-child(3){color:var(--blue)}
.card-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px}
.badge{font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;border:1.5px solid;white-space:nowrap}
.alt{text-align:center;font-size:12px;color:var(--text2);margin:8px 0 0}
.alt:empty{display:none}

.details{border-top:.5px solid var(--sep);padding:4px 15px 15px}
.details section{padding:12px 0;border-bottom:.5px solid var(--sep)}
.details section:last-child{border-bottom:0;padding-bottom:0}
.details h3{font-size:13px;font-weight:600;color:var(--text2);margin:0 0 8px}
.xg{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
.results{display:flex;flex-wrap:wrap;gap:6px}
.res{background:var(--field);border-radius:10px;padding:4px 10px;font-weight:700;font-size:14px;font-variant-numeric:tabular-nums}
.res small{font-weight:500;color:var(--text2);margin-left:2px}
table.ev{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:15px}
.ev td{padding:6px 0;border-top:.5px solid var(--sep)}
.ev tr:first-child td{border-top:0}
.ev td:last-child{text-align:right;color:var(--text2)}
.ev tr.best td{font-weight:700;color:var(--accent)}
.teams{display:flex;flex-direction:column;gap:16px}
.team-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.team-head div{display:flex;flex-direction:column}
.team-head b{font-size:15px}
.team-head span{font-size:12px;color:var(--text2)}
.team-block dl{display:grid;grid-template-columns:96px 1fr;gap:6px 10px;margin:0;font-size:14px;align-items:center}
.team-block dt{color:var(--text2)}
.team-block dd{margin:0}
.chip{display:inline-flex;width:20px;height:20px;align-items:center;justify-content:center;border-radius:6px;font-size:11px;font-weight:700;margin-right:3px}
.chip.S{color:var(--green);background:var(--green-soft)}
.chip.U{color:var(--text2);background:var(--gray-soft)}
.chip.N{color:var(--red);background:rgba(255,69,58,.13)}
.h2h{list-style:none;padding:0;margin:0;font-size:14px}
.h2h li{display:grid;grid-template-columns:1fr auto 70px;gap:10px;padding:5px 0}
.h2h li .dim{text-align:right;font-size:12px}
.h2h li.dim{display:block}

/* Quoten */
.odds{padding:0 16px}
.odds>summary{display:flex;justify-content:space-between;align-items:center;padding:15px 0}
.odds-title{font-size:16px;font-weight:600}
.odds-help{font-size:13px;color:var(--text2);line-height:1.45;margin-bottom:6px}
.odds-head,.odds-row{display:grid;grid-template-columns:1fr 56px 56px 56px 64px;gap:6px;align-items:center}
.odds-head{font-size:12px;color:var(--text2);font-weight:600;text-align:center;margin-top:8px}
.odds-row{padding:8px 0;border-top:.5px solid var(--sep)}
.odds-match{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.odd{width:100%;padding:8px 2px;border:1.5px solid transparent;border-radius:10px;background:var(--field);color:var(--text);font:inherit;
  font-size:16px;text-align:center;font-variant-numeric:tabular-nums;-webkit-appearance:none}
.odd::placeholder{color:var(--text3)}
.odd:focus{outline:none;border-color:var(--accent-line);background:var(--accent-soft)}
.odd.bad{border-color:var(--red)}
.odd:disabled{opacity:.4}
.odds-state{font-size:12px;color:var(--text2);text-align:right}
.odds-state.ok{color:var(--accent);font-weight:700}
.odds-state.err{color:var(--red)}
.linkbtn{background:none;border:0;padding:6px 0 16px;color:var(--accent);font:inherit;font-size:14px;font-weight:600;cursor:pointer}

/* Bilanz */
.stats{display:flex;gap:10px;margin-bottom:12px}
.statcard{flex:1;background:var(--card);border:1px solid var(--border);border-radius:18px;padding:13px 15px;box-shadow:var(--shadow)}
.statcard .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.statcard .l{font-size:12px;color:var(--text2);margin-top:2px}
.hist{border-top:.5px solid var(--sep)}
.hist:first-child{border-top:0}
.hist summary{display:flex;justify-content:space-between;padding:13px 0;font-size:15px;font-weight:600}
.hist-list{list-style:none;padding:0 0 10px;margin:0;font-size:13px}
.hist-list li{display:grid;grid-template-columns:1fr auto 30px;gap:10px;padding:4px 0}
.hist-list b{text-align:right}
.p4,.p3{color:var(--green)}.p2{color:var(--blue)}.p0{color:var(--text3)}
.empty{padding:15px 16px;font-size:14px;color:var(--text2)}

.about{padding:14px 16px;font-size:14px;line-height:1.5}
.about ul{margin:0 0 8px;padding-left:18px}
.about li{margin-bottom:4px}
.about .dim{font-size:12px}

@media (max-width:400px){
  .odds-head,.odds-row{grid-template-columns:1fr 52px 52px 52px;row-gap:4px}
  .odds-match{grid-column:1/-1}
  .odds-head span:first-child,.odds-head span:last-child{display:none}
  .odds-head span:nth-child(2){grid-column:2}
  .odds-state{grid-column:1;grid-row:2;text-align:left}
  .odds-state.err{grid-column:1/-1;grid-row:3}
  .odd[data-k="1"]{grid-column:2;grid-row:2}
  .odd[data-k="X"]{grid-column:3;grid-row:2}
  .odd[data-k="2"]{grid-column:4;grid-row:2}
}
"""

JS = r"""
(function(){
const fmt=(x,d)=>x.toFixed(d).replace('.',',');
const pct=p=>Math.round(p*100)+' %';
const tipStr=t=>t[0]+':'+t[1];
const scoreHtml=t=>t[0]+'<span class="sep">:</span>'+t[1];
const sign=x=>x>0?1:x<0?-1:0;

function scoreMatrix(lh,la){
  const n=CFG.maxGoals+1, ph=[], pa=[];
  let a=Math.exp(-lh), b=Math.exp(-la);
  for(let k=0;k<n;k++){ ph.push(a); pa.push(b); a*=lh/(k+1); b*=la/(k+1); }
  const m=[]; let tot=0;
  for(let i=0;i<n;i++){ m.push([]); for(let j=0;j<n;j++) m[i].push(ph[i]*pa[j]); }
  const r=CFG.rho;
  m[0][0]*=1-lh*la*r; m[0][1]*=1+lh*r; m[1][0]*=1+la*r; m[1][1]*=1-r;
  for(const row of m) for(const v of row) tot+=v;
  return m.map(row=>row.map(v=>v/tot));
}
function outcome(m){
  let h=0,d=0; const n=m.length;
  for(let i=0;i<n;i++) for(let j=0;j<n;j++){ if(i>j) h+=m[i][j]; else if(i===j) d+=m[i][j]; }
  return [h,d,1-h-d];
}
function points(t,r){
  if(t[0]===r[0]&&t[1]===r[1]) return CFG.pts[0];
  if(sign(t[0]-t[1])!==sign(r[0]-r[1])) return 0;
  return (t[0]-t[1]===r[0]-r[1]) ? CFG.pts[1] : CFG.pts[2];
}
function expectedPoints(m){
  const out=[], n=m.length;
  for(let th=0;th<=5;th++) for(let ta=0;ta<=5;ta++){
    let ev=0;
    for(let i=0;i<n;i++) for(let j=0;j<n;j++) ev+=m[i][j]*points([th,ta],[i,j]);
    out.push([[th,ta],ev]);
  }
  return out.sort((x,y)=>y[1]-x[1]);
}
function lambdasFromMarket(pH,pA){
  const err=(lh,la)=>{ const o=outcome(scoreMatrix(lh,la)); return (o[0]-pH)**2+(o[2]-pA)**2; };
  let best=null, be=Infinity;
  for(let x=2;x<45;x++) for(let y=2;y<45;y++){ const e=err(x/10,y/10); if(e<be){be=e;best=[x/10,y/10];} }
  const [h0,a0]=best;
  for(let dx=-10;dx<=10;dx++) for(let dy=-10;dy<=10;dy++){
    const lh=h0+dx/100, la=a0+dy/100; if(lh<=0.05||la<=0.05) continue;
    const e=err(lh,la); if(e<be){be=e;best=[lh,la];}
  }
  return best;
}
function blend(mod,mkt){ return mod.map((v,i)=>Math.exp((1-CFG.w)*Math.log(v)+CFG.w*Math.log(mkt[i]))); }
function esc(x){ const d=document.createElement('div'); d.textContent=x; return d.innerHTML; }
function badgeText(g,level,t){
  if(level==='niedrig'||t[0]===t[1]) return 'Offenes Spiel';
  return (t[0]>t[1]?g.home:g.away)+(level==='hoch'?' klarer':' leichter')+' Favorit';
}
function confidence(p,t){
  const q=t[0]>t[1]?p[0]:t[0]===t[1]?p[1]:p[2];
  const level=q>=0.62?'hoch':q>=0.45?'mittel':'niedrig';
  return [level,CFG.labels[level]];
}
function setConf(el,level){ el.classList.remove('conf-hoch','conf-mittel','conf-niedrig'); el.classList.add('conf-'+level); }

function render(idx, lam, mine){
  const g=GAMES[idx], card=document.querySelector('.match-card[data-idx="'+idx+'"]'), ov=document.querySelector('.ov-row[data-idx="'+idx+'"]');
  const m=scoreMatrix(lam[0],lam[1]), p=outcome(m), evs=expectedPoints(m).slice(0,4);
  const tip=g.locked?g.tip:evs[0][0];
  const [level,label]=confidence(p,tip);
  card.querySelector('.js-tiptext').innerHTML=scoreHtml(tip);
  const badge=card.querySelector('.js-badge'); setConf(badge,level); badge.textContent=badgeText(g,level,tip);
  card.querySelector('.js-bar').innerHTML=
    '<div class="bar" role="img" aria-label="Heimsieg '+pct(p[0])+', Unentschieden '+pct(p[1])+', Auswärtssieg '+pct(p[2])+'">'+
    '<span class="seg h" style="width:'+(p[0]*100).toFixed(1)+'%"></span><span class="seg d" style="width:'+(p[1]*100).toFixed(1)+'%"></span><span class="seg a" style="width:'+(p[2]*100).toFixed(1)+'%"></span></div>'+
    '<div class="bar-legend"><span>'+esc(g.home)+' '+pct(p[0])+'</span><span>Remis '+pct(p[1])+'</span><span>'+esc(g.away)+' '+pct(p[2])+'</span></div>';
  const alts=g.locked?[]:evs.slice(1).filter(e=>evs[0][1]-e[1]<0.03).map(e=>tipStr(e[0]));
  card.querySelector('.js-alt').textContent=alts.length?'Alternativ '+alts.join(', '):'';
  card.querySelector('.js-mine').hidden=!mine;
  card.querySelector('.js-xg').textContent=fmt(lam[0],2)+' : '+fmt(lam[1],2);
  const likely=[]; for(let i=0;i<6;i++) for(let j=0;j<6;j++) likely.push([i,j,m[i][j]]);
  likely.sort((x,y)=>y[2]-x[2]);
  card.querySelector('.js-likely').innerHTML=likely.slice(0,6).map(l=>'<span class="res">'+l[0]+':'+l[1]+' <small>'+pct(l[2])+'</small></span>').join('');
  card.querySelector('.js-ev').innerHTML=evs.map((e,i)=>'<tr'+(i===0?' class=best':'')+'><td>'+tipStr(e[0])+'</td><td>'+fmt(e[1],2)+'</td></tr>').join('');
  const ot=ov.querySelector('.js-ov-tip'); ot.textContent=tipStr(tip); setConf(ot,level);
  ov.classList.toggle('has-mine',!!mine);
  return tip;
}

const KEY=id=>'kicktipp-quoten-'+CFG.season+'-'+id;
const store={
  get(id){ try{ return JSON.parse(localStorage.getItem(KEY(id))||'null'); }catch(e){ return null; } },
  set(id,v){ try{ v?localStorage.setItem(KEY(id),JSON.stringify(v)):localStorage.removeItem(KEY(id)); }catch(e){} }
};
function parseOdd(s){
  s=(s||'').trim().replace(',','.');
  if(!s) return null;
  const v=Number(s);
  return (isFinite(v)&&v>1.0&&v<100)?v:NaN;
}
const modelState=GAMES.map(()=>true);
function update(row, save){
  const idx=+row.dataset.idx, g=GAMES[idx];
  if(g.locked) return;
  const inputs=[...row.querySelectorAll('.odd')], vals=inputs.map(i=>parseOdd(i.value)), state=row.querySelector('.odds-state');
  const bad=vals.some(v=>Number.isNaN(v));
  inputs.forEach((inp,k)=>inp.classList.toggle('bad',Number.isNaN(vals[k])));
  const complete=vals.every(v=>typeof v==='number'&&!Number.isNaN(v));
  if(save) store.set(g.id, inputs.some(i=>i.value.trim())?inputs.map(i=>i.value.trim()):null);
  if(complete){
    const inv=vals.map(v=>1/v), s=inv[0]+inv[1]+inv[2];
    const lam=blend(g.lam, lambdasFromMarket(inv[0]/s, inv[2]/s));
    const tip=render(idx, lam, true);
    state.textContent='Tipp '+tipStr(tip); state.className='odds-state ok';
    modelState[idx]=false;
  }else{
    if(!modelState[idx]){ render(idx, g.auto||g.lam, !!g.auto); modelState[idx]=true; }
    state.textContent=bad?'Quoten müssen über 1 liegen, z. B. 1,45':(g.auto?'automatisch':''); state.className='odds-state'+(bad?' err':'');
  }
}
document.querySelectorAll('.odds-row').forEach(row=>{
  const g=GAMES[+row.dataset.idx], saved=store.get(g.id), inputs=row.querySelectorAll('.odd');
  if(saved&&!g.locked){ inputs.forEach((inp,k)=>inp.value=saved[k]||''); update(row,false); }
  inputs.forEach(inp=>inp.addEventListener('input',()=>update(row,true)));
});
document.querySelector('.js-clear').addEventListener('click',()=>{
  if(!confirm('Alle eingetragenen Quoten löschen?')) return;
  document.querySelectorAll('.odds-row').forEach(row=>{ row.querySelectorAll('.odd:not(:disabled)').forEach(i=>i.value=''); update(row,true); });
});
})();
"""
