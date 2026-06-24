"""wc2026 — local Streamlit dashboard over the decision engine.

Run:  streamlit run app.py

Single source of truth for player data is data/players.json, edited ONLY on the Players
tab; every other tab reads from it. Wraps the Python engine directly (no API).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config
from core import engine_events as engine, fixtures, espn, research, odds_math
from core import players as pdb, fifa_api, holdet_api
from games import holdet_common as hc
from games.fifa.model import (expected_points as fifa_xpts, ceiling_points as fifa_ceil_pts,
                              scouting_ev as fifa_scout_ev)
from games.malspillet import model as mal

st.set_page_config(page_title="wc2026", page_icon="⚽", layout="wide")

GAMES = ["fifa", "holdet_gold", "holdet_yolo", "holdet_free"]
LABELS = {"fifa": "FIFA (Granat65)", "holdet_gold": "Holdet GOLD",
          "holdet_yolo": "Holdet YOLO", "holdet_free": "Holdet FREE"}


def ev_label(game):
    """YOLO ranks on the P85 ceiling, the rest on mean EV — label accordingly."""
    return "ceiling" if config.GAMES.get(game, {}).get("objective") == "ceiling" else "EV"


# ----------------------------------------------------------------- io helpers
def load_state(game):
    return json.load(open(f"{ROOT}/games/{game}/state.json", encoding="utf-8"))


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def save_json(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


RESULTS = f"{ROOT}/data/results.json"


def canon(name):
    r = pdb.resolve(name)
    return r["name"] if r else name


def total_so_far(game, results):
    """Cumulative actual points/increase per (canonical) player across all rounds."""
    out = {}
    for _rk, games in results.items():
        for pn, d in games.get(game, {}).get("players", {}).items():
            out[pn] = out.get(pn, 0) + (d.get("pts") or d.get("increase") or 0)
    return out


def lookup(rec, table):
    """EV/growth tables are keyed by the engine's (short) names = our aliases."""
    if not rec:
        return None
    for n in [rec.get("name")] + list(rec.get("aliases", [])):
        if n and n in table:
            return table[n]
    return None


@st.cache_data(show_spinner="Simulating…")
def run_sim(rnd, sims, w):
    players, _ = engine.simulate_round(
        rnd, sims=sims, market_rates=espn.load_player_rates(rnd),
        research=research.load_entries("players", rnd), research_weight=w)
    means = engine.event_means(players)
    ceil = {n: fifa_ceil_pts(means[n], players[n].goal_samples) for n in means}
    scout = {n: fifa_scout_ev(means[n], players[n].goal_samples) for n in means}
    return means, ceil, scout


@st.cache_data(show_spinner="Computing growth…")
def holdet_growth(rnd, sims, w):
    return hc.growth_tables(rnd, sims, {"research_weight": w, "ceiling_percentile": 0.85})


@st.cache_data
def team_info(rnd):
    ctx = hc.team_context(rnd)
    info = {}
    for f in fixtures.by_round(rnd):
        cached = espn.load_match_odds(f.match_id)
        src = "odds" if cached and cached.get("lam_home") is not None else "priors"
        for team, opp in ((f.home, f.away), (f.away, f.home)):
            if team in ctx:
                lf, la, pW, pD, pL = ctx[team]
                info[team] = {"opp": opp, "lfor": lf, "lagainst": la, "pW": pW,
                              "pD": pD, "pL": pL, "src": src, "ko": f.kickoff}
    return info


def why(team, info):
    t = info.get(team)
    if not t:
        return "no fixture this round"
    tag = "🔥 blowout" if t["lfor"] >= 2.3 and t["lagainst"] < 0.8 else (
        "⚠️ tough/close" if t["pW"] < 0.45 else "ok")
    return (f"vs {t['opp']} · xG {t['lfor']:.2f}–{t['lagainst']:.2f} · "
            f"W{t['pW']:.0%}/D{t['pD']:.0%}/L{t['pL']:.0%} · {t['src']} · {tag}")


# ----------------------------------------------------------------- sidebar
st.sidebar.title("⚽ wc2026")
rnd = int(st.sidebar.number_input("Round", 1, 8, 2))
sims = st.sidebar.select_slider("Monte Carlo sims", [5000, 10000, 20000, 50000], 20000)
if st.sidebar.button("🔄 Refresh ESPN odds"):
    try:
        import manage
        manage.refresh(rnd)
        st.cache_data.clear()
        st.sidebar.success("Refreshed.")
    except Exception as e:
        st.sidebar.error(f"Refresh failed: {e}")
if st.sidebar.button("🔄 Sync players (FIFA + Holdet APIs)"):
    try:
        import build_players
        from core import ratings
        n = build_players.build()
        ratings.clear_prior_cache()   # rebuild derived priors from the fresh board
        st.cache_data.clear()
        st.sidebar.success(f"Synced {n} players from the APIs.")
    except Exception as e:
        st.sidebar.error(f"Sync failed: {e}")
page = st.sidebar.radio("View", ["Dashboard", "Players", "Planner", "FIFA", "Holdet GOLD",
                                 "Holdet YOLO", "Holdet FREE", "Målspillet",
                                 "Schedule & Odds", "News"])
st.sidebar.caption("Edit prices only on the **Players** tab. Tunables: config.py")


# ----------------------------------------------------------------- shared compute
def game_rows(game, info):
    """Return (state, rows, captain, total). Rows carry EV + this-round actual (FIFA
    auto-fetched, Holdet from results.json) so actuals live in the squad table."""
    state = load_state(game)
    is_holdet = game != "fifa"
    if is_holdet:
        mean, ceil = holdet_growth(rnd, sims, config.weight(game))
    else:
        means, fifa_ceil, fifa_scout = run_sim(rnd, sims, config.weight("fifa"))
    rows = []
    for p in state["squad"]:
        rec = pdb.resolve(p["name"]) or {"name": p["name"], "aliases": []}
        team = p.get("team")
        t = info.get(team, {})
        played = fifa_api.team_match_status(team, rnd) == "complete"
        if is_holdet:
            ev = lookup(rec, mean) or 0
            cv = lookup(rec, ceil) or 0
            row = {"player": p["name"], "pos": p["position"],
                   "EV": round(ev), "ceiling": round(cv),
                   "actual": holdet_api.growth(p["name"], rnd, p["position"]),
                   "played": played, "C": p.get("is_captain", False),
                   "why": why(team, info)}
            if game == "holdet_yolo":   # anti-chalk: fade ownership into a leverage score
                own = pdb.holdet_ownership(p["name"]) or 0.0
                row["own%"] = own
                row["lev"] = round(cv * (1 - config.YOLO_FADE * own / 100.0))
            rows.append(row)
        else:
            pos = (rec.get("fifa_pos") if rec else None) or p["position"]
            e = lookup(rec, means)
            cl = lookup(rec, fifa_ceil)
            bonus = (lookup(rec, fifa_scout) or 0) if (pdb.ownership(p["name"]) or 99) < 5 else 0
            xp = (fifa_xpts(e) if e else 0.0) + bonus
            rows.append({"player": p["name"], "pos": p["position"], "EV": round(xp, 2),
                         "ceiling": round(cl + bonus, 2) if cl is not None else None,
                         "actual": fifa_api.round_points(p["name"], rnd, pos),
                         "total": fifa_api.total_points(p["name"], pos),
                         "KO": t["ko"].strftime("%m-%d %H:%M") if t.get("ko") else None,
                         "status": fifa_api.match_status(p["name"], pos)[0], "played": played,
                         "start": p.get("is_starter", False),
                         "C": p.get("is_captain", False), "why": why(team, info)})
    key = ("lev" if game == "holdet_yolo"
           else "ceiling" if (is_holdet and config.GAMES[game]["objective"] == "ceiling")
           else "EV")
    rows.sort(key=lambda r: -(r.get(key) or r["EV"]))
    cap = max(rows, key=lambda r: r.get(key) or r["EV"])["player"] if rows else None
    total = sum(r["EV"] for r in rows if r.get("start", True))
    has_ceiling = any(r.get("ceiling") is not None for r in rows)
    total_ceil = (sum((r.get("ceiling") or 0) for r in rows if r.get("start", True))
                  if has_ceiling else None)
    return state, rows, cap, total, total_ceil


def news_link(name):
    surname = name.split()[-1].lower()
    for it in load_json(f"{ROOT}/data/news.json", {"items": []})["items"]:
        if surname in (it["title"] + " " + it["summary"]).lower():
            return it["url"]
    return None


@st.cache_data
def _research_entries():
    return research.load_entries("players")


def research_ref(name):
    """First source URL from this player's research note, if any."""
    for ent in _research_entries().values():
        if ent.sources and pdb.name_match(name, ent.name):
            return ent.sources[0]
    return None


def research_feed():
    """Research notes as news-style items — each carries its own source URL."""
    import glob as _glob
    items = []
    for path in _glob.glob(f"{ROOT}/research/players/*.md"):
        if os.path.basename(path).startswith("_"):
            continue
        meta, body = research.parse_frontmatter(open(path, encoding="utf-8").read())
        if not meta.get("name"):
            continue
        src = (meta.get("sources") or [None])[0]
        items.append({"title": f"{meta['name']} — {meta.get('status', 'note')}",
                      "url": src or "", "source": "research note",
                      "date": str(meta.get("updated") or ""),
                      "summary": " ".join(body.split()),
                      "tags": [meta.get("status") or "note", "research"]})
    return sorted(items, key=lambda x: x["date"], reverse=True)


def needs_attention(info):
    flags = []
    for game in GAMES:
        for p in load_state(game)["squad"]:
            status = (pdb.resolve(p["name"]) or {}).get("status")
            team = p.get("team")
            link = research_ref(p["name"]) or news_link(p["name"])
            ref = f" — [source]({link})" if link else ""
            if status in ("out", "suspended"):
                flags.append(f"🔴 **{p['name']}** ({LABELS[game]}) — {status}{ref}")
            elif status in ("doubtful", "rotation_risk"):
                flags.append(f"🟠 {p['name']} ({LABELS[game]}) — {status}{ref}")
            if team and team not in info:
                flags.append(f"⚪ {p['name']} ({LABELS[game]}) — no fixture this round")
    return flags


def our_players_in(match):
    out = []
    for g in GAMES:
        for p in load_state(g)["squad"]:
            tm = p.get("team")
            if tm and (fifa_api.same_team(tm, match["home"])
                       or fifa_api.same_team(tm, match["away"])):
                out.append(p["name"])
    return sorted(set(out))


def fixture_coverage():
    """This round's fixtures ranked by the favourite's xG, with how many of our players
    (across all squads) sit on that favourite — so an uncovered blowout is obvious."""
    owned = [(LABELS[g], pl["name"], pl.get("team"))
             for g in GAMES for pl in load_state(g)["squad"]]
    rows = []
    for f in fixtures.by_round(rnd):
        c = espn.load_match_odds(f.match_id) or {}
        if c.get("lam_home") is not None:
            lh, la, src = c["lam_home"], c["lam_away"], "odds"
        else:
            lh, la = f.lambdas(); src = "priors"
        fav, favlam = (f.home, lh) if lh >= la else (f.away, la)
        on_fav = sorted({n for _g, n, t in owned if t == fav})
        rows.append({"fav_lam": favlam, "match": f"{f.home} v {f.away}", "fav": fav,
                     "own": len(on_fav), "who": ", ".join(on_fav) or "—", "src": src})
    rows.sort(key=lambda r: -r["fav_lam"])
    return rows


# ----------------------------------------------------------------- pages
def page_dashboard():
    st.header(f"Dashboard — Round {rnd}")
    cu1, cu2 = st.columns([1, 3])
    if cu1.button("🔄 Update all live data", type="primary"):
        try:
            fifa_api.refresh()
            holdet_api.refresh(rounds=(rnd,))
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Update failed: {e}")
    cu2.caption("Pulls latest FIFA results/points + Holdet growth (live ~15s feeds), "
                "then re-renders. Use after matches finish.")
    info = team_info(rnd)

    # Top strip: last 4 results + next 4 fixtures (with our players), from FIFA feed.
    fx = [m for m in fifa_api.fixtures() if m.get("date")]
    done = sorted([m for m in fx if m["status"] == "complete"], key=lambda m: m["date"])[-4:]
    nxt = sorted([m for m in fx if m["status"] in ("scheduled", "playing")],
                 key=lambda m: m["date"])[:4]
    s1, s2 = st.columns(2)
    with s1.container(border=True):
        st.subheader("⏪ Last 4 results")
        for m in reversed(done):
            st.write(f"{m['date'][5:10]}  **{m['home']} {m['hs']}–{m['as']} {m['away']}**")
        if not done:
            st.caption("Refresh FIFA data (sidebar / FIFA tab).")
    with s2.container(border=True):
        st.subheader("⏩ Next 4 — your players")
        for m in nxt:
            ours = our_players_in(m)
            st.write(f"{m['date'][5:16].replace('T',' ')}  {m['home']} v {m['away']}"
                     + (f" · 👤 {', '.join(ours)}" if ours else ""))
        if not nxt:
            st.caption("Refresh FIFA data.")

    with st.container(border=True):
        st.subheader("⚠️ Needs attention")
        flags = needs_attention(info)
        for f in flags:
            st.markdown("- " + f)
        if not flags:
            st.success("Nothing flagged across your squads.")

    with st.container(border=True):
        st.subheader("🎯 Fixture coverage — are we in the blowouts?")
        cov = fixture_coverage()
        gaps = [r for r in cov if r["fav_lam"] >= 2.0 and r["own"] == 0]
        if gaps:
            st.warning("⚠️ Uncovered blowout(s): "
                       + "  ·  ".join(f"{r['match']} (λ{r['fav_lam']:.2f})" for r in gaps))
        else:
            st.success("Every λ≥2.0 blowout has at least one of our players.")
        st.dataframe([{"fav λ": round(r["fav_lam"], 2), "match": r["match"],
                       "favourite": r["fav"], "ours": r["own"], "who": r["who"]}
                      for r in cov], width="stretch", hide_index=True)
        st.caption("This round's fixtures by favourite xG. Cover the top blowouts before "
                   "deepening an already-covered team. 'ours' = player-slots on the favourite "
                   "across all squads. 'priors' rows have no live odds.")

    # Read-only EV vs actual, 4 game tables (actuals entered on the game tabs).
    cards = st.columns(2)
    for i, game in enumerate(GAMES):
        state, rows, cap, total, total_ceil = game_rows(game, info)
        unit = "pts" if game == "fifa" else "kr"
        pl = [r for r in rows if r.get("played") and r.get("start", True)]
        ev_p = sum(r["EV"] for r in pl)
        act_p = sum((r["actual"] or 0) for r in pl)
        is_ceil_game = total_ceil is not None
        n = len(pl)
        ceil_p = sum((r.get("ceiling") or 0) for r in pl)
        with cards[i % 2].container(border=True):
            st.subheader(LABELS[game])
            st.caption(f"© {state.get('captain') or cap}")
            evc, cec = f"EV ({unit})", f"Ceiling ({unit})"
            summ_src = [("Round (proj)", total, total_ceil),
                        (f"So far ({n} played)", ev_p if pl else None, ceil_p if pl else None),
                        (f"Actual ({n} played)", act_p if pl else None, act_p if pl else None)]
            summ = []
            for lbl, evv, cev in summ_src:
                d = {"": lbl, evc: f"{evv:,.0f}" if evv is not None else "—"}
                if is_ceil_game:
                    d[cec] = f"{cev:,.0f}" if cev is not None else "—"
                summ.append(d)
            st.dataframe(summ, width="stretch", hide_index=True)
            if pl:
                st.metric(f"Actual vs EV ({unit})", f"{act_p:,.0f}",
                          f"{act_p - ev_p:+,.0f}")
            dcols = ["player", "EV"] + (["ceiling"] if is_ceil_game else []) + ["actual"]
            st.dataframe([{k: r[k] for k in dcols} for r in rows],
                         width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("📰 Latest news")
        curated = load_json(f"{ROOT}/data/news.json", {"items": []})["items"]
        latest = sorted(curated + research_feed(),
                        key=lambda it: it.get("date", ""), reverse=True)
        for it in latest[:6]:
            url = it.get("url", "")
            title = it["title"]
            line = f"- `{it['date']}` [{title}]({url}) · *{it['source']}*" if url else f"- `{it['date']}` {title} · *{it['source']}*"
            st.markdown(line)


def page_players():
    st.header("Players — single source of truth")
    st.caption("The only editable tab. Edit FIFA/Holdet prices, ownership, status → Save. "
               "EV columns are computed live for players the model knows.")
    info = team_info(rnd)
    means, _ = run_sim(rnd, sims, config.weight("fifa"))
    mean_g, _ = holdet_growth(rnd, sims, config.weight("holdet_gold"))
    recs = pdb.load()
    teams = ["(all)"] + sorted({r["team"] for r in recs if r.get("team")})
    pick = st.selectbox("Filter team", teams)
    view = [r for r in recs if pick == "(all)" or r.get("team") == pick]
    rows = []
    for r in view:
        rows.append({"name": r["name"], "team": r.get("team"),
                     "fifa_pos": r.get("fifa_pos"), "holdet_pos": r.get("holdet_pos"),
                     "fifa_price": r.get("fifa_price"), "holdet_price": r.get("holdet_price"),
                     "own%": r.get("ownership"), "status": r.get("status"),
                     "fifa_xPts": round(fifa_xpts(lookup(r, means)), 2) if lookup(r, means) else None,
                     "holdet_growth": round(lookup(r, mean_g)) if lookup(r, mean_g) else None,
                     "matchup": why(r.get("team"), info)})
    edited = st.data_editor(
        rows, width="stretch", hide_index=True, key="players_editor",
        disabled=["name", "team", "fifa_pos", "holdet_pos", "fifa_xPts",
                  "holdet_growth", "matchup"])
    if st.button("💾 Save player edits"):
        by = {e["name"]: e for e in edited}
        for r in recs:
            e = by.get(r["name"])
            if not e:
                continue
            r["fifa_price"] = e["fifa_price"]
            r["holdet_price"] = e["holdet_price"]
            r["ownership"] = e["own%"]
            r["status"] = e["status"] or None
        pdb.save(recs)
        st.cache_data.clear()
        st.success("Saved to data/players.json.")


def fifa_live(state):
    """Live-subs helper: refresh button + blank flags (only when the match is complete)."""
    if st.button("⬇️ Refresh FIFA Fantasy data (live)"):
        try:
            fifa_api.refresh()
            st.cache_data.clear()
            st.success("Fetched live FIFA data.")
        except Exception as e:
            st.error(f"Fetch failed: {e}")
    blanks = []
    for p in state["squad"]:
        if not p.get("is_starter"):
            continue
        rec = pdb.resolve(p["name"]) or {}
        pos = (rec.get("fifa_pos") if rec else None) or p["position"]
        rp = fifa_api.round_points(p["name"], rnd, pos)
        if rp == 0 and fifa_api.team_match_status(p.get("team"), rnd) == "complete":
            blanks.append(p["name"])
    if blanks:
        bench = [p["name"] for p in state["squad"] if not p.get("is_starter")]
        st.warning(f"🔁 Blanked (match complete, 0 pts): **{', '.join(blanks)}** — "
                   f"auto-subs cover from the bench ({', '.join(bench)}); manual sub only "
                   "to swap in a bench player whose match hasn't kicked off.")
    st.caption("FIFA points/status auto-fetched from play.fifa.com (~15s live). "
               "`actual` + `KO` + `status` are in the squad table above.")


def holdet_actuals(game, state):
    st.subheader("📊 Pre-round price · model EV · actual growth (auto from holdet API)")
    if st.button("⬇️ Refresh Holdet data (live)", key=f"hr_{game}"):
        try:
            holdet_api.refresh(rounds=(rnd,))
            st.cache_data.clear()
            st.success("Fetched live Holdet data.")
        except Exception as e:
            st.error(f"Fetch failed: {e}")
    mean, _ = holdet_growth(rnd, sims, config.weight(game))
    info = team_info(rnd)
    now = datetime.now(timezone.utc)
    rows, played = [], []
    for p in state["squad"]:
        rec = pdb.resolve(p["name"]) or {}
        ev = lookup(rec, mean)
        actual = holdet_api.growth(p["name"], rnd, p["position"])
        ko = info.get(p.get("team"), {}).get("ko")
        has_played = bool(ko and ko < now)
        rows.append({"player": p["name"], "pre_price": rec.get("holdet_price"),
                     "model_EV": round(ev) if ev else None, "actual_growth": actual,
                     "played": "✓" if has_played else ""})
        if has_played and ev is not None and actual is not None:
            played.append((ev, actual))
    st.dataframe(rows, width="stretch", hide_index=True)
    if played:
        ms = sum(e for e, _ in played)
        ac = sum(a for _, a in played)
        st.metric(f"Model vs actual — {len(played)} played", f"{ac:,.0f}",
                  f"{ac - ms:+,.0f} vs model {ms:,.0f}")
    else:
        st.caption("Model-vs-actual appears once players' matches have been played.")


def page_game(game):
    st.header(LABELS[game])
    info = team_info(rnd)
    state, rows, cap, total, total_ceil = game_rows(game, info)
    unit = "pts" if game == "fifa" else "kr"
    a, b, c = st.columns(3)
    a.metric("Captain", state.get("captain") or cap)
    b.metric(f"EV ({unit})", f"{total:,.0f}")
    if total_ceil is not None:
        c.metric(f"Ceiling ({unit})", f"{total_ceil:,.0f}")
    render_pitch(rows, game)
    st.dataframe(rows, width="stretch", hide_index=True)

    st.subheader("🔀 Probe a change")
    names = [p["name"] for p in state["squad"]]
    out = st.selectbox("OUT", names, key=f"out_{game}")
    if game == "fifa":
        means, _, _ = run_sim(rnd, sims, config.weight("fifa"))
        cands = sorted(n for n in means if n not in set(names))
        inp = st.selectbox("IN", cands, key=f"in_{game}")
        d = fifa_xpts(means[inp]) - (fifa_xpts(means[out]) if out in means else 0)
        st.metric("xPts delta", f"{d:+.2f}", "upgrade" if d > 0 else "downgrade")
    else:
        mean, _ = holdet_growth(rnd, sims, config.weight(game))
        owned = set(names)
        cands = sorted(r["name"] for r in pdb.load()
                       if r.get("holdet_price") and r["name"] not in owned)
        inp = st.selectbox("IN", cands, key=f"in_{game}")
        rec = pdb.resolve(inp)
        g_in = lookup(rec, mean) if rec else None
        price = rec.get("holdet_price") if rec else None
        if g_in is None or not price:
            st.info("No model growth/price for this player.")
        else:
            delta = g_in - (lookup(pdb.resolve(out) or {}, mean) or 0)
            fee = 0.01 * price
            x, y, z = st.columns(3)
            x.metric("Growth Δ", f"{delta:,.0f} kr")
            y.metric("Fee", f"{fee:,.0f} kr")
            z.metric("Net", f"{delta - fee:,.0f} kr", "✅ DO" if delta - fee > 0 else "❌ NO")

    if game == "fifa":
        fifa_live(state)
    else:
        holdet_actuals(game, state)


def mal_points(sh, sa, ah, aa):
    """Målspillet 1+1+1 points for a submitted (sh-sa) vs actual (ah-aa). None if no result."""
    if ah is None or aa is None:
        return None
    so = (sh > sa) - (sh < sa)
    ao = (ah > aa) - (ah < aa)
    return int(sh == ah) + int(sa == aa) + int(so == ao)


def page_malspillet():
    st.header("Målspillet")
    fx = sorted(fixtures.by_round(rnd), key=lambda f: f.kickoff)
    if not fx:
        st.warning("No fixtures — Refresh ESPN odds.")
        return
    rows = []
    for f in fx:
        lh, la, rho = mal.match_dc_params(f)
        hg, ag, ev = mal.optimal_pick(odds_math.score_matrix_dc(lh, la, rho))
        ah, aa, _ = fifa_api.actual_score(f.home, f.away)
        rows.append({"KO": f.kickoff.strftime("%m-%d %H:%M"), "match": f"{f.home} v {f.away}",
                     "submit": f"{hg}-{ag}", "E[pts]": round(ev, 3),
                     "actual": f"{ah}-{aa}" if ah is not None else None,
                     "pts": mal_points(hg, ag, ah, aa), "_ev": ev})
    best = max(rows, key=lambda r: r["_ev"])
    st.subheader("🏆 Top 3 bets")
    st.table([{k: r[k] for k in ("match", "submit", "E[pts]")}
              for r in sorted(rows, key=lambda r: -r["_ev"])[:3]])
    st.info(f"⭐ Bamse → **{best['match']} {best['submit']}** "
            f"(E {best['E[pts]']} → {2*best['E[pts]']:.2f})")
    tot_ev = sum(r["_ev"] for r in rows) + best["_ev"]  # bamse doubles the top match's EV
    played = [r for r in rows if r["pts"] is not None]
    tot_act = sum(r["pts"] for r in played) + (best["pts"] or 0 if best["pts"] is not None else 0)
    a, b = st.columns(2)
    a.metric("Total EV (round, incl. Bamse)", f"{tot_ev:.1f}")
    b.metric("Total actual pts", f"{tot_act}" if played else "—",
             help="Auto from FIFA results; includes Bamse double on the top match.")
    st.dataframe([{k: r[k] for k in ("KO", "match", "submit", "E[pts]", "actual", "pts")}
                  for r in rows], width="stretch", hide_index=True)
    st.caption("Actual scorelines + points auto-fetched from the FIFA results feed (1+1+1).")


def page_schedule():
    st.header("Schedule & scraped odds")
    fx = sorted(fixtures.by_round(rnd), key=lambda f: f.kickoff)
    if not fx:
        st.warning("No fixtures — Refresh ESPN odds.")
        return
    rows = []
    for f in fx:
        c = espn.load_match_odds(f.match_id)
        lh, la, rho = mal.match_dc_params(f)
        pH, pD, pA = odds_math.outcome_from_matrix(odds_math.score_matrix_dc(lh, la, rho))
        rows.append({"KO": f.kickoff.strftime("%m-%d %H:%M"), "match": f"{f.home} v {f.away}",
                     "λ_home": lh, "λ_away": la, "ρ": rho, "H": round(pH, 2),
                     "D": round(pD, 2), "A": round(pA, 2),
                     "src": "odds" if c and c.get("lam_home") is not None else "priors"})
    st.dataframe(rows, width="stretch", hide_index=True)


def page_news():
    st.header("📰 News & expert feed")
    curated = load_json(f"{ROOT}/data/news.json", {"items": []})["items"]
    items = sorted(curated + research_feed(),
                   key=lambda it: it.get("date", ""), reverse=True)
    tags = sorted({t for it in items for t in it.get("tags", [])})
    pick = st.multiselect("Filter tags", tags, default=[])
    for it in items:
        if pick and not set(pick) & set(it["tags"]):
            continue
        with st.container(border=True):
            st.markdown(f"**[{it['title']}]({it['url']})**  ·  *{it['source']}* · {it['date']}")
            st.caption(it["summary"] + "  —  `" + "` `".join(it["tags"]) + "`")


def render_pitch(rows, game):
    """XI on a pitch (FWD top → GK bottom). Starters only for FIFA; all 11 for Holdet."""
    starters = [r for r in rows if r.get("start", True)]
    bypos = {"FWD": [], "MID": [], "DEF": [], "GK": []}
    for r in starters:
        bypos.get(r["pos"], bypos["MID"]).append(r)

    def card(r):
        cap = " ©" if r.get("C") else ""
        act = f" · {r['actual']}" if r.get("actual") is not None else ""
        return (f"<div style='background:#fff;border-radius:8px;padding:5px 9px;margin:5px;"
                f"text-align:center;min-width:74px;font-size:12px;color:#111'>"
                f"<b>{r['player'].split()[-1]}</b>{cap}<br>"
                f"<span style='color:#137333'>{r['EV']}</span>"
                f"<span style='color:#888'>{act}</span></div>")
    body = "".join(
        f"<div style='display:flex;justify-content:center;flex-wrap:wrap'>"
        f"{''.join(card(r) for r in bypos[p])}</div>" for p in ("FWD", "MID", "DEF", "GK"))
    components.html(
        f"<div style='background:linear-gradient(#2e7d32,#1b5e20);padding:14px;"
        f"border-radius:12px;font-family:sans-serif'>{body}</div>", height=300)


def page_planner():
    st.header("🔀 Transfer planner")
    game = st.selectbox("Game", GAMES, format_func=lambda g: LABELS[g])
    state = load_state(game)
    is_holdet = game != "fifa"
    names = [p["name"] for p in state["squad"]]
    if is_holdet:
        mean, ceil = holdet_growth(rnd, sims, config.weight(game))
        price = lambda n: (pdb.resolve(n) or {}).get("holdet_price") or 0
        if game == "holdet_yolo":   # rank trades by anti-chalk leverage (ceiling × fade)
            ev = lambda n: (lookup(pdb.resolve(n) or {}, ceil) or 0) * (
                1 - config.YOLO_FADE * (pdb.holdet_ownership(n) or 0.0) / 100.0)
        else:                        # GOLD/FREE: mean growth, comparable across games
            ev = lambda n: lookup(pdb.resolve(n) or {}, mean) or 0
        bank, unit, feerate = state.get("cash", 0), "kr", 0.01
    else:
        means, _, _ = run_sim(rnd, sims, config.weight("fifa"))
        price = lambda n: (pdb.resolve(n) or {}).get("fifa_price") or 0
        ev = lambda n: (lambda e: fifa_xpts(e) if e else 0)(lookup(pdb.resolve(n) or {}, means))
        bank, unit, feerate = state.get("budget_remaining", 0), "$m", 0.0

    out = st.multiselect("OUT", names)
    cand = sorted(r["name"] for r in pdb.load()
                  if (r.get("holdet_price") if is_holdet else r.get("fifa_price"))
                  and r["name"] not in names)
    inp = st.multiselect("IN", cand)

    sold, bought = sum(price(n) for n in out), sum(price(n) for n in inp)
    fee = feerate * bought
    budget_after = bank + sold - bought - fee
    ev_delta = sum(ev(n) for n in inp) - sum(ev(n) for n in out) - (fee if is_holdet else 0)
    final_teams = [p.get("team") for p in state["squad"] if p["name"] not in out] + \
                  [(pdb.resolve(n) or {}).get("team") for n in inp]
    overcap = [t for t, c in Counter(t for t in final_teams if t).items() if c > 4]

    c1, c2, c3 = st.columns(3)
    feasible = budget_after >= 0 and len(inp) == len(out) and not overcap
    c1.metric(f"Budget after ({unit})",
              f"{budget_after:,.0f}" if is_holdet else f"{budget_after:,.1f}",
              "✅ ok" if budget_after >= 0 else "⚠️ over")
    c2.metric(f"Net EV/growth ({unit})",
              f"{ev_delta:,.0f}" if is_holdet else f"{ev_delta:+.2f}",
              "✅" if ev_delta > 0 else "❌")
    c3.metric("Legal", "✅" if feasible else ("nation cap" if overcap else "counts/budget"))
    if len(inp) != len(out):
        st.caption("Pick equal numbers OUT and IN.")
    if overcap:
        st.warning(f"Over 4-per-nation: {overcap}")
    if not is_holdet and len(out) > state.get("free_transfers", 99):
        st.caption(f"⚠️ {len(out)} transfers > {state.get('free_transfers')} free — point hits apply.")
    risky = [n for n in inp if (pdb.resolve(n) or {}).get("status")
             in ("out", "suspended", "doubtful", "rotation_risk", "bench")]
    if risky:
        st.warning("⚠️ Start-risk on IN picks: "
                   + ", ".join(f"{n} ({(pdb.resolve(n) or {}).get('status')})" for n in risky)
                   + " — check predicted lineups before committing.")
    st.dataframe(
        [{"move": "OUT", "player": n, "price": price(n), "EV": round(ev(n), 2),
          "status": (pdb.resolve(n) or {}).get("status")} for n in out] +
        [{"move": "IN", "player": n, "price": price(n), "EV": round(ev(n), 2),
          "status": (pdb.resolve(n) or {}).get("status")} for n in inp],
        width="stretch", hide_index=True)


PAGES = {
    "Dashboard": page_dashboard, "Players": page_players, "Planner": page_planner,
    "FIFA": lambda: page_game("fifa"),
    "Holdet GOLD": lambda: page_game("holdet_gold"),
    "Holdet YOLO": lambda: page_game("holdet_yolo"),
    "Holdet FREE": lambda: page_game("holdet_free"),
    "Målspillet": page_malspillet, "Schedule & Odds": page_schedule, "News": page_news,
}
PAGES[page]()
