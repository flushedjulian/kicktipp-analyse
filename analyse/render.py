"""Erzeugt die HTML-Seite."""

from datetime import timezone
from html import escape
from zoneinfo import ZoneInfo

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
    return f"""
    <div class="bar" role="img" aria-label="Heimsieg {_pct(ph)}, Unentschieden {_pct(pd)}, Auswärtssieg {_pct(pa)}">
      <span class="seg h" style="width:{ph * 100:.1f}%"></span><span class="seg d" style="width:{pd * 100:.1f}%"></span><span class="seg a" style="width:{pa * 100:.1f}%"></span>
    </div>
    <div class="bar-legend"><span><i class="dot h"></i>{escape(home.short)} {_pct(ph)}</span><span><i class="dot d"></i>Remis {_pct(pd)}</span><span><i class="dot a"></i>{escape(away.short)} {_pct(pa)}</span></div>"""


def _market_note(g):
    mk = g["market"]
    if not mk:
        return ""
    mh, md, ma = g["model_probs"]
    diff = mh - mk["p_home"]
    if abs(diff) < 0.08:
        txt = "Modell und Wettquoten sind sich weitgehend einig."
    elif diff > 0:
        txt = f"Das Modell sieht {escape(g['home'].short)} stärker als die Buchmacher ({_pct(mh)} statt {_pct(mk['p_home'])}). Evtl. Ausfälle oder Rotation prüfen."
    else:
        txt = f"Die Buchmacher sehen {escape(g['home'].short)} stärker als das Modell ({_pct(mk['p_home'])} statt {_pct(mh)})."
    return f'<p class="note">📊 {txt} <span class="muted">(Quoten aus {mk["n_books"]} Wettanbietern)</span></p>'


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
    draw_hint = '<p class="note">⚖️ Remis-Tipp: Beide Teams liegen sehr eng beieinander.</p>' if th == ta else ""
    best_ev = g["evs"][0][1]
    alts = [_tip(t) for t, ev in g["evs"][1:] if best_ev - ev < 0.03]
    alt_hint = f'<p class="alt">Praktisch genauso gut: {", ".join(alts)}</p>' if alts and not g["locked"] else ""

    return f"""
<article class="card" id="spiel-{idx}">
  <details>
    <summary>
      <div class="when">{_when(m.kickoff_local)}</div>
      <div class="matchup">
        <span class="t home"><span class="nm">{escape(home.short)}</span> {_logo(home)}</span>
        <span class="tipbox conf-{level}">{_tip(g["tip"])}{lock}</span>
        <span class="t away">{_logo(away)} <span class="nm">{escape(away.short)}</span></span>
      </div>
      {_prob_bar(g["probs"], home, away)}
      {alt_hint}
      <div class="summary-foot"><span class="badge conf-{level}">{label}</span><span class="more">Details</span></div>
    </summary>
    <div class="details">
      {draw_hint}
      <div class="grid2">
        <section>
          <h3>Erwartete Tore</h3>
          <p class="big">{_fmt(lh, 2)} : {_fmt(la, 2)}</p>
          <h3>Wahrscheinlichste Ergebnisse</h3>
          <div class="results">{likely}</div>
        </section>
        <section>
          <h3>Welcher Tipp bringt am meisten?</h3>
          <table class="ev"><thead><tr><th>Tipp</th><th>Ø Punkte</th></tr></thead><tbody>{evs}</tbody></table>
        </section>
      </div>
      {_market_note(g)}
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
            f'<a class="ov-row" href="#spiel-{i}"><span class="muted ov-when">{_when(g["match"].kickoff_local)}</span>'
            f'<span class="ov-h">{escape(g["home"].short)}</span><span class="tipbox small conf-{level}">{_tip(g["tip"])}</span>'
            f'<span class="ov-a">{escape(g["away"].short)}</span></a>'
        )
    return "".join(rows)


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


def page(season, matchday, games, teams, table, history, generated, has_odds):
    first = min(g["match"].kickoff_local for g in games)
    last = max(g["match"].kickoff_local for g in games)
    gen = generated.astimezone(BERLIN)
    odds_hint = "" if has_odds else '<p class="note warn">Ohne Wettquoten berechnet – nur eigenes Modell.</p>'
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
    {odds_hint}
  </header>

  <section class="panel">
    <h2>Alle Tipps auf einen Blick</h2>
    <div class="overview">{_overview(games)}</div>
    <p class="legend"><span class="badge conf-hoch">Klare Sache</span><span class="badge conf-mittel">Leichter Favorit</span><span class="badge conf-niedrig">Offenes Spiel</span></p>
  </section>

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
      <li><b>Wettquoten:</b> Wenn verfügbar, fließen die Quoten mehrerer Wettanbieter mit ein (65 %). Sie enthalten Infos zu Verletzungen und Aufstellungen.</li>
      <li><b>Ergebnis-Wahrscheinlichkeiten:</b> Aus den erwarteten Toren wird für jedes Ergebnis (0:0, 1:0, 2:1 …) eine Wahrscheinlichkeit berechnet.</li>
      <li><b>Bester Tipp:</b> Für jeden möglichen Tipp werden die durchschnittlich zu erwartenden Kicktipp-Punkte (4/3/2) berechnet. Empfohlen wird der Tipp mit dem höchsten Wert. Das ist nicht immer das wahrscheinlichste Ergebnis.</li>
    </ol>
    <p class="muted">Getestet an den Saisons 24/25 und 25/26: ca. 1,3 Punkte pro Spiel und die richtige Tendenz in etwa jedem zweiten Spiel. Zum Vergleich: Immer „2:1 Heimsieg“ bringt ca. 1,07 Punkte. Fußball bleibt Fußball. 🍀</p>
    <p class="muted small-text">Daten: OpenLigaDB, Understat{", The Odds API" if has_odds else ""}.</p>
  </section>
</main>
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
