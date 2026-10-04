"""Erzeugt die HTML-Seite."""

import json
from html import escape
from zoneinfo import ZoneInfo

from . import model

BERLIN = ZoneInfo("Europe/Berlin")
WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _when(dt):
    return f"{WOCHENTAG[dt.weekday()]} {dt:%d.%m. %H:%M}"


def _pct(p):
    return f"{round(p * 100)} %"


def _tip(t):
    return f"{t[0]}:{t[1]}"


def _logo(team, size=28):
    return f'<img class="logo" src="{escape(team.icon)}" alt="" width="{size}" height="{size}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'


def _confidence(g):
    ph, pd, pa = g["probs"]
    th, ta = g["tip"]
    p = ph if th > ta else pd if th == ta else pa
    if p >= 0.62:
        return "hoch", "Klare Sache"
    if p >= 0.45:
        return "mittel", "Leichter Favorit"
    return "niedrig", "Offenes Spiel"


def _form_chips(form, teams):
    if not form:
        return '<span class="muted">keine Daten</span>'
    out = []
    for f in reversed(form):  # ältestes links
        opp = teams[f["gegner"]].short
        where = "H" if f["heim"] else "A"
        title = f'{f["datum"]:%d.%m.%y} {where} vs {opp}: {f["tore"]}:{f["gegen"]}'
        out.append(f'<span class="chip {f["res"]}" title="{escape(title)}">{f["res"]}</span>')
    return "".join(out)


def _avg(form, key):
    vals = [f[key] for f in form if f[key] is not None]
    return sum(vals) / len(vals) if vals else None


def _fmt(x, d=1):
    return "–" if x is None else f"{x:.{d}f}".replace(".", ",")


def _prob_bar(probs, home, away):
    ph, pd, pa = probs
    return f"""<div class="js-bar">
    <div class="bar" role="img" aria-label="Heimsieg {_pct(ph)}, Unentschieden {_pct(pd)}, Auswärtssieg {_pct(pa)}">
      <span class="seg h" style="width:{ph * 100:.1f}%"></span><span class="seg d" style="width:{pd * 100:.1f}%"></span><span class="seg a" style="width:{pa * 100:.1f}%"></span>
    </div>
    <div class="bar-legend"><span><i class="dot h"></i>{escape(home.short)} {_pct(ph)}</span><span><i class="dot d"></i>Remis {_pct(pd)}</span><span><i class="dot a"></i>{escape(away.short)} {_pct(pa)}</span></div></div>"""


def _card(g, teams, idx):
    m, home, away = g["match"], g["home"], g["away"]
    level, label = _confidence(g)
    th, ta = g["tip"]
    lh, la = g["lambdas"]

    evs = "".join(
        f'<tr{" class=best" if i == 0 else ""}><td>{_tip(t)}</td><td>{_fmt(ev, 2)}</td></tr>' for i, (t, ev) in enumerate(g["evs"])
    )
    likely = "".join(f'<span class="res">{i}:{j} <small>{_pct(p)}</small></span>' for i, j, p in g["likely"])

    def team_block(team, tab, form, venue, venue_label, scorers):
        pos = f'{tab["platz"]}. Platz · {tab["pkt"]} Pkt · {tab["tore"]}:{tab["gegen"]} Tore' if tab else "noch keine Spiele"
        xg, xga = _avg(form, "xg"), _avg(form, "xga")
        sc = ", ".join(f"{escape(n)} ({c})" for n, c in scorers) or "–"
        return f"""
        <div class="team-col">
          <h4>{_logo(team, 20)} {escape(team.short)}</h4>
          <p class="muted">{pos}</p>
          <dl>
            <dt>Letzte 5</dt><dd>{_form_chips(form, teams)}</dd>
            <dt>{venue_label}</dt><dd>{_form_chips(venue, teams)}</dd>
            <dt>xG letzte 5</dt><dd>{_fmt(xg)} erzeugt · {_fmt(xga)} zugelassen</dd>
            <dt>Torjäger</dt><dd>{sc}</dd>
          </dl>
        </div>"""

    h2h = "".join(
        f'<li><span class="muted">{h.kickoff_local:%d.%m.%y}</span> {escape(teams[h.home_id].short)} – {escape(teams[h.away_id].short)} <b>{h.home_goals}:{h.away_goals}</b></li>'
        for h in g["h2h"]
    ) or '<li class="muted">Keine Duelle in den letzten zwei Spielzeiten.</li>'

    lock = '<span class="lock" title="Spiel läuft oder ist vorbei – Tipp eingefroren">🔒</span>' if g["locked"] else ""
    draw_hint = '<p class="note js-draw"' + ("" if th == ta else " hidden") + '>⚖️ Remis-Tipp: Beide Teams liegen sehr eng beieinander.</p>'
    best_ev = g["evs"][0][1]
    alts = [_tip(t) for t, ev in g["evs"][1:] if best_ev - ev < 0.03]
    alt_hint = f'<p class="alt js-alt">{"Praktisch genauso gut: " + ", ".join(alts) if alts and not g["locked"] else ""}</p>'

    return f"""
<article class="card" id="spiel-{idx}" data-idx="{idx}">
  <details>
    <summary>
      <div class="when">{_when(m.kickoff_local)}</div>
      <div class="matchup">
        <span class="t home"><span class="nm">{escape(home.short)}</span> {_logo(home)}</span>
        <span class="tipbox js-tip conf-{level}"><span class="js-tiptext">{_tip(g["tip"])}</span>{lock}</span>
        <span class="t away">{_logo(away)} <span class="nm">{escape(away.short)}</span></span>
      </div>
      {_prob_bar(g["probs"], home, away)}
      {alt_hint}
      <p class="mine js-mine" hidden>✍️ mit deinen Quoten berechnet</p>
      <div class="summary-foot"><span class="badge js-badge conf-{level}">{label}</span><span class="more">Details</span></div>
    </summary>
    <div class="details">
      {draw_hint}
      <div class="grid2">
        <section>
          <h3>Erwartete Tore</h3>
          <p class="big js-xg">{_fmt(lh, 2)} : {_fmt(la, 2)}</p>
          <h3>Wahrscheinlichste Ergebnisse</h3>
          <div class="results js-likely">{likely}</div>
        </section>
        <section>
          <h3>Welcher Tipp bringt am meisten?</h3>
          <table class="ev"><thead><tr><th>Tipp</th><th>Ø Punkte</th></tr></thead><tbody class="js-ev">{evs}</tbody></table>
        </section>
      </div>
      <div class="grid2 teams">
        {team_block(home, g["tab_home"], g["form_home"], g["venue_home"], "Heimspiele", g["scorers_home"])}
        {team_block(away, g["tab_away"], g["form_away"], g["venue_away"], "Auswärtsspiele", g["scorers_away"])}
      </div>
      <h3>Direkter Vergleich</h3>
      <ul class="h2h">{h2h}</ul>
    </div>
  </details>
</article>"""


def _overview(games):
    rows = []
    for i, g in enumerate(games):
        level, _ = _confidence(g)
        rows.append(
            f'<a class="ov-row" href="#spiel-{i}" data-idx="{i}"><span class="muted ov-when">{_when(g["match"].kickoff_local)}</span>'
            f'<span class="ov-h">{escape(g["home"].short)}</span><span class="tipbox small js-ov-tip conf-{level}">{_tip(g["tip"])}</span>'
            f'<span class="ov-a">{escape(g["away"].short)}</span></a>'
        )
    return "".join(rows)


def _odds_panel(games):
    rows = []
    for i, g in enumerate(games):
        h, a = escape(g["home"].short), escape(g["away"].short)
        dis = " disabled" if g["locked"] else ""
        fields = "".join(
            f'<input type="text" inputmode="decimal" enterkeyhint="next" autocomplete="off" class="odd" data-k="{k}" '
            f'placeholder="{k}" aria-label="Quote {lbl}"{dis}>'
            for k, lbl in (("1", f"Sieg {h}"), ("X", "Unentschieden"), ("2", f"Sieg {a}"))
        )
        state = "angepfiffen" if g["locked"] else ""
        rows.append(f'<div class="odds-row" data-idx="{i}"><span class="odds-match">{h} – {a}</span>{fields}<span class="odds-state">{state}</span></div>')
    return f"""
  <details class="panel odds" id="quoten">
    <summary><h2>Quoten eintragen <span class="muted opt">optional</span></h2><span class="more">öffnen</span></summary>
    <p class="muted small-text">Quoten für Heimsieg (1), Unentschieden (X) und Auswärtssieg (2) eintragen, z.&nbsp;B. aus Kicktipp oder von einer Wettseite. Sobald alle drei Felder eines Spiels ausgefüllt sind, werden Tipp und Wahrscheinlichkeiten neu berechnet. Die Quoten bleiben auf diesem Gerät gespeichert.</p>
    <div class="odds-head"><span></span><span>1</span><span>X</span><span>2</span><span></span></div>
    {"".join(rows)}
    <button type="button" class="linkbtn js-clear">Alle Quoten löschen</button>
  </details>"""


def _script(games, season):
    data = [dict(id=g["match"].match_id, lam=[round(x, 4) for x in g["lambdas"]], locked=g["locked"], tip=list(g["tip"]),
                 home=g["home"].short, away=g["away"].short) for g in games]
    cfg = dict(rho=model.DC_RHO, maxGoals=model.MAX_GOALS, w=model.MARKET_WEIGHT,
               pts=[model.POINTS_EXACT, model.POINTS_DIFF, model.POINTS_TENDENCY], season=season)
    return f"<script>const GAMES={json.dumps(data, ensure_ascii=False)};const CFG={json.dumps(cfg)};\n{JS}</script>"


def _history(history):
    if not history:
        return '<p class="muted">Sobald die ersten Spiele mit Empfehlung gespielt sind, steht hier, wie viele Punkte die Tipps gebracht hätten.</p>'
    total = sum(h["punkte"] for h in history)
    n = sum(h["spiele"] for h in history)
    rows = []
    for h in reversed(history):
        detail = " · ".join(
            f'{escape(d["heim"])}–{escape(d["gast"])} {_tip(d["tipp"])} → {_tip(d["ergebnis"])} <b class="p{d["punkte"]}">+{d["punkte"]}</b>'
            for d in h["details"]
        )
        rows.append(
            f'<details class="hist"><summary><span>{h["spieltag"]}. Spieltag</span><span><b>{h["punkte"]}</b> Punkte '
            f'<span class="muted">aus {h["spiele"]} Spielen</span></span></summary><p class="small-text">{detail}</p></details>'
        )
    return (
        f'<p class="hist-total"><b>{total}</b> Punkte aus {n} Spielen · Ø {_fmt(total / n, 2)} pro Spiel</p>' + "".join(rows)
    )


def page(season, matchday, games, teams, table, history, generated):
    first = min(g["match"].kickoff_local for g in games)
    last = max(g["match"].kickoff_local for g in games)
    gen = generated.astimezone(BERLIN)
    cards = "".join(_card(g, teams, i) for i, g in enumerate(games))
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kicktipp-Analyse · {matchday}. Spieltag</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<style>{CSS}</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Bundesliga {season}/{(season + 1) % 100:02d}</p>
    <h1>{matchday}. Spieltag</h1>
    <p class="muted">{_when(first)} bis {_when(last)} · aktualisiert {gen:%d.%m. %H:%M} Uhr</p>
  </header>

  <section class="panel">
    <h2>Alle Tipps auf einen Blick</h2>
    <div class="overview">{_overview(games)}</div>
    <p class="legend"><span class="badge conf-hoch">Klare Sache</span><span class="badge conf-mittel">Leichter Favorit</span><span class="badge conf-niedrig">Offenes Spiel</span></p>
    <p class="muted small-text ov-hint">💡 Mit Wettquoten werden die Tipps genauer: <a href="#quoten" class="js-open-odds">Quoten eintragen</a></p>
  </section>
{_odds_panel(games)}

  <h2 class="section-title">Spiele im Detail</h2>
  <p class="muted hint">Auf ein Spiel tippen, um die Analyse aufzuklappen.</p>
  {cards}

  <section class="panel">
    <h2>Bilanz der Empfehlungen</h2>
    {_history(history)}
  </section>

  <section class="panel about">
    <h2>So entstehen die Tipps</h2>
    <ol>
      <li><b>Teamstärke:</b> Aus allen Spielen dieser und der letzten Saison wird für jedes Team eine Angriffs- und Abwehrstärke berechnet. Neuere Spiele zählen mehr. Statt nur der Tore zählt vor allem <b>xG</b> (Expected Goals), also die Qualität der Torchancen. Das sagt die Zukunft besser voraus als das Ergebnis allein.</li>
      <li><b>Wettquoten (optional):</b> Wenn du unter „Quoten eintragen“ Quoten einträgst, fließen sie zu 65 % in die Torerwartung ein. Quoten enthalten Infos, die das Modell nicht kennt, z.&nbsp;B. Verletzungen und Aufstellungen.</li>
      <li><b>Ergebnis-Wahrscheinlichkeiten:</b> Aus den erwarteten Toren wird für jedes Ergebnis (0:0, 1:0, 2:1 …) eine Wahrscheinlichkeit berechnet.</li>
      <li><b>Bester Tipp:</b> Für jeden möglichen Tipp werden die durchschnittlich zu erwartenden Kicktipp-Punkte (4/3/2) berechnet. Empfohlen wird der Tipp mit dem höchsten Wert. Das ist nicht immer das wahrscheinlichste Ergebnis.</li>
    </ol>
    <p class="muted">Getestet an den Saisons 24/25 und 25/26: ca. 1,3 Punkte pro Spiel und die richtige Tendenz in etwa jedem zweiten Spiel. Zum Vergleich: Immer „2:1 Heimsieg“ bringt ca. 1,07 Punkte. Fußball bleibt Fußball. 🍀</p>
    <p class="muted small-text">Daten: OpenLigaDB, Understat.</p>
  </section>
</main>
{_script(games, season)}
</body>
</html>"""


CSS = """
:root{
  --bg:#f4f5f7;--card:#fff;--text:#16181d;--muted:#667085;--line:#e4e7ec;
  --home:#2f6fdb;--draw:#9aa3b2;--away:#e0663a;
  --hoch:#1f9d55;--mittel:#c98a0b;--niedrig:#8a94a6;
  --win:#1f9d55;--loss:#d64545;--accent:#2f6fdb;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0f1115;--card:#181b21;--text:#e8eaee;--muted:#98a2b3;--line:#2a2f38;
    --home:#5b8ff0;--draw:#6b7486;--away:#f08358;
    --hoch:#3fbf75;--mittel:#e0a52b;--niedrig:#7d879a;--win:#3fbf75;--loss:#ef6262;--accent:#5b8ff0;
  }
}
:root[data-theme="dark"]{
  --bg:#0f1115;--card:#181b21;--text:#e8eaee;--muted:#98a2b3;--line:#2a2f38;
  --home:#5b8ff0;--draw:#6b7486;--away:#f08358;
  --hoch:#3fbf75;--mittel:#e0a52b;--niedrig:#7d879a;--win:#3fbf75;--loss:#ef6262;--accent:#5b8ff0;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
main{max-width:760px;margin:0 auto;padding:24px 16px 64px}
header{margin-bottom:20px}
.eyebrow{margin:0;color:var(--accent);font-weight:600;font-size:14px;letter-spacing:.02em}
h1{margin:2px 0 4px;font-size:32px;line-height:1.15}
h2{font-size:20px;margin:0 0 12px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:16px 0 8px;font-weight:600}
h4{margin:0 0 2px;font-size:16px;display:flex;align-items:center;gap:6px}
p{margin:0 0 8px}
.muted{color:var(--muted)}
.small-text{font-size:13px}
.section-title{margin-top:28px;margin-bottom:2px}
.hint{font-size:14px;margin-bottom:12px}
.panel,.card{background:var(--card);border:1px solid var(--line);border-radius:14px}
.panel{padding:16px;margin:16px 0}
.card{margin:10px 0;overflow:hidden}
.logo{object-fit:contain;flex:none}
.overview{display:flex;flex-direction:column}
.ov-row{display:grid;grid-template-columns:96px 1fr auto 1fr;align-items:center;gap:8px;padding:9px 0;border-top:1px solid var(--line);color:inherit;text-decoration:none}
.ov-row:first-child{border-top:0}
.ov-when{font-size:13px}
.ov-h{text-align:right;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ov-a{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tipbox{display:inline-flex;align-items:center;gap:2px;justify-content:center;min-width:64px;padding:6px 10px;border-radius:10px;font-weight:800;font-size:22px;font-variant-numeric:tabular-nums;color:#fff;background:var(--niedrig)}
.tipbox.small{min-width:52px;font-size:17px;padding:3px 8px}
.conf-hoch.tipbox,.badge.conf-hoch{background:var(--hoch)}
.conf-mittel.tipbox,.badge.conf-mittel{background:var(--mittel)}
.conf-niedrig.tipbox,.badge.conf-niedrig{background:var(--niedrig)}
.lock{font-size:12px;margin-left:2px}
.badge{display:inline-block;color:#fff;font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px}
.legend{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 0}
summary{list-style:none;cursor:pointer;padding:14px 16px}
summary::-webkit-details-marker{display:none}
.when{font-size:13px;color:var(--muted);text-align:center;margin-bottom:6px}
.matchup{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px}
.t{display:flex;align-items:center;gap:8px;font-weight:700;font-size:17px;min-width:0}
.t.home{justify-content:flex-end;text-align:right}
.nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.bar{display:flex;height:8px;border-radius:99px;overflow:hidden;margin-top:12px;background:var(--line)}
.seg.h,.dot.h{background:var(--home)}.seg.d,.dot.d{background:var(--draw)}.seg.a,.dot.a{background:var(--away)}
.bar-legend{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-top:4px;gap:6px}
.bar-legend span{white-space:nowrap}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
.summary-foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px}
.alt{text-align:center;font-size:13px;color:var(--muted);margin:8px 0 0}
.more{font-size:13px;color:var(--accent);font-weight:600}
.more::after{content:" ▾"}
details[open] .more::after{content:" ▴"}
.details{padding:0 16px 16px;border-top:1px solid var(--line)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.big{font-size:26px;font-weight:800;margin:0;font-variant-numeric:tabular-nums}
.results{display:flex;flex-wrap:wrap;gap:6px}
.res{border:1px solid var(--line);border-radius:8px;padding:2px 8px;font-weight:700;font-variant-numeric:tabular-nums}
.res small{font-weight:400;color:var(--muted)}
table.ev{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
.ev th,.ev td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)}
.ev th{font-size:12px;color:var(--muted);font-weight:600}
.ev tr.best td{font-weight:800;color:var(--hoch)}
.note{background:var(--bg);border-radius:10px;padding:10px 12px;font-size:14px;margin:14px 0 0}
.note.warn{border-left:3px solid var(--mittel)}
.teams{margin-top:8px}
.team-col dl{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;margin:10px 0 0;font-size:14px}
.team-col dt{color:var(--muted)}
.team-col dd{margin:0}
.chip{display:inline-flex;width:20px;height:20px;align-items:center;justify-content:center;border-radius:5px;font-size:11px;font-weight:700;color:#fff;margin-right:2px}
.chip.S{background:var(--win)}.chip.U{background:var(--draw)}.chip.N{background:var(--loss)}
.h2h{list-style:none;padding:0;margin:0;font-size:14px}
.h2h li{padding:3px 0}
.hist-total{font-size:18px}
.hist{border-top:1px solid var(--line)}
.hist summary{display:flex;justify-content:space-between;padding:10px 0}
.p4{color:var(--hoch)}.p3{color:var(--hoch)}.p2{color:var(--mittel)}.p0{color:var(--loss)}
.about ol{padding-left:20px;margin:0 0 12px}
.about li{margin-bottom:8px}
@media (max-width:560px){
  .grid2{grid-template-columns:1fr;gap:0}
  .teams{gap:18px}
  .t{font-size:15px;gap:6px}
  .matchup{gap:6px}
  .t .logo{width:22px;height:22px}
  .tipbox{min-width:56px;font-size:20px}
  .ov-row{grid-template-columns:1fr auto 1fr;row-gap:0}
  .ov-when{grid-column:1/-1;text-align:center;font-size:12px}
  h1{font-size:28px}
  .bar-legend{font-size:11px}
}
"""

CSS += """
.alt:empty{display:none}
.mine{text-align:center;font-size:13px;color:var(--accent);font-weight:600;margin:6px 0 0}
.ov-hint{margin:10px 0 0}
.ov-hint a{color:var(--accent);font-weight:600}
.ov-row.has-mine .tipbox{box-shadow:0 0 0 2px var(--accent)}
.odds>summary{display:flex;justify-content:space-between;align-items:center;padding:0}
.odds>summary h2{margin:0}
.odds[open]>summary{margin-bottom:10px}
.opt{font-size:13px;font-weight:500}
.odds-head,.odds-row{display:grid;grid-template-columns:1fr 58px 58px 58px 70px;gap:6px;align-items:center}
.odds-head{font-size:12px;color:var(--muted);font-weight:600;text-align:center;margin-top:8px}
.odds-row{padding:6px 0;border-top:1px solid var(--line)}
.odds-match{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.odd{width:100%;padding:8px 4px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font:inherit;font-size:16px;text-align:center;font-variant-numeric:tabular-nums}
.odd:focus{outline:2px solid var(--accent);outline-offset:0;border-color:transparent}
.odd.bad{border-color:var(--loss)}
.odd:disabled{opacity:.45}
.odds-state{font-size:12px;color:var(--muted);text-align:right}
.odds-state.ok{color:var(--hoch);font-weight:700}
.odds-state.err{color:var(--loss)}
.linkbtn{background:none;border:0;padding:10px 0 0;color:var(--accent);font:inherit;font-size:14px;cursor:pointer}
@media (max-width:560px){
  .odds-head,.odds-row{grid-template-columns:1fr 52px 52px 52px;row-gap:4px}
  .odds-match{grid-column:1/-1}
  .odds-head span:first-child{display:none}
  .odds-head{grid-template-columns:1fr 52px 52px 52px}
  .odds-head span:nth-child(2){grid-column:2}
  .odds-head span:last-child{display:none}
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
function confidence(p,t){
  const q=t[0]>t[1]?p[0]:t[0]===t[1]?p[1]:p[2];
  return q>=0.62?['hoch','Klare Sache']:q>=0.45?['mittel','Leichter Favorit']:['niedrig','Offenes Spiel'];
}
function setConf(el,level){ el.classList.remove('conf-hoch','conf-mittel','conf-niedrig'); el.classList.add('conf-'+level); }

function render(idx, lam, mine){
  const g=GAMES[idx], card=document.querySelector('.card[data-idx="'+idx+'"]'), ov=document.querySelector('.ov-row[data-idx="'+idx+'"]');
  const m=scoreMatrix(lam[0],lam[1]), p=outcome(m), evs=expectedPoints(m).slice(0,4);
  const tip=g.locked?g.tip:evs[0][0];
  const [level,label]=confidence(p,tip);
  card.querySelector('.js-tiptext').textContent=tipStr(tip);
  setConf(card.querySelector('.js-tip'),level);
  const badge=card.querySelector('.js-badge'); setConf(badge,level); badge.textContent=label;
  card.querySelector('.js-bar').innerHTML=
    '<div class="bar" role="img" aria-label="Heimsieg '+pct(p[0])+', Unentschieden '+pct(p[1])+', Auswärtssieg '+pct(p[2])+'">'+
    '<span class="seg h" style="width:'+(p[0]*100).toFixed(1)+'%"></span><span class="seg d" style="width:'+(p[1]*100).toFixed(1)+'%"></span><span class="seg a" style="width:'+(p[2]*100).toFixed(1)+'%"></span></div>'+
    '<div class="bar-legend"><span><i class="dot h"></i>'+esc(g.home)+' '+pct(p[0])+'</span><span><i class="dot d"></i>Remis '+pct(p[1])+'</span><span><i class="dot a"></i>'+esc(g.away)+' '+pct(p[2])+'</span></div>';
  const alts=g.locked?[]:evs.slice(1).filter(e=>evs[0][1]-e[1]<0.03).map(e=>tipStr(e[0]));
  card.querySelector('.js-alt').textContent=alts.length?'Praktisch genauso gut: '+alts.join(', '):'';
  card.querySelector('.js-mine').hidden=!mine;
  card.querySelector('.js-draw').hidden=tip[0]!==tip[1];
  card.querySelector('.js-xg').textContent=fmt(lam[0],2)+' : '+fmt(lam[1],2);
  const likely=[]; for(let i=0;i<6;i++) for(let j=0;j<6;j++) likely.push([i,j,m[i][j]]);
  likely.sort((x,y)=>y[2]-x[2]);
  card.querySelector('.js-likely').innerHTML=likely.slice(0,6).map(l=>'<span class="res">'+l[0]+':'+l[1]+' <small>'+pct(l[2])+'</small></span>').join('');
  card.querySelector('.js-ev').innerHTML=evs.map((e,i)=>'<tr'+(i===0?' class=best':'')+'><td>'+tipStr(e[0])+'</td><td>'+fmt(e[1],2)+'</td></tr>').join('');
  const ot=ov.querySelector('.js-ov-tip'); ot.textContent=tipStr(tip); setConf(ot,level);
  ov.classList.toggle('has-mine',!!mine);
  return tip;
}
function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

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
  inputs.forEach((inp,k)=>inp.classList.toggle('bad',Number.isNaN(vals[k])));
  const complete=vals.every(v=>typeof v==='number'&&!Number.isNaN(v));
  if(save) store.set(g.id, inputs.some(i=>i.value.trim())?inputs.map(i=>i.value.trim()):null);
  if(complete){
    const inv=vals.map(v=>1/v), s=inv[0]+inv[1]+inv[2];
    const lam=blend(g.lam, lambdasFromMarket(inv[0]/s, inv[2]/s));
    const tip=render(idx, lam, true);
    state.textContent='✓ Tipp '+tipStr(tip); state.className='odds-state ok';
    modelState[idx]=false;
  }else{
    if(!modelState[idx]){ render(idx, g.lam, false); modelState[idx]=true; }
    state.textContent=vals.some(v=>Number.isNaN(v))?'Quoten müssen über 1 liegen, z. B. 1,45':''; state.className='odds-state'+(vals.some(v=>Number.isNaN(v))?' err':'');
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
document.querySelector('.js-open-odds').addEventListener('click',()=>{ document.getElementById('quoten').open=true; });
})();
"""
