"""Prose generation for evmax articles — tiered: cache → LLM → template.

Public API
----------
article_prose(article, round_no, entries, columns,
              cache_dir="data/articles", use_llm=True) -> dict
    Returns {"headline", "standfirst", "body_html", "bottom_line", "source"}
    where source is "cache" | "llm" | "template".
"""

import html
import json
import os
import re

# ---------------------------------------------------------------------------
# Optional anthropic import — guarded so the module works without the SDK.
# ---------------------------------------------------------------------------
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None
    _ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tiny Markdown → HTML converter (paragraphs, h2, blockquote only).
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    """Convert a small subset of Markdown to HTML.

    Supported:
      ## Heading  → <h2>
      > Quote     → <blockquote><p>…</p></blockquote>
      blank line  → paragraph boundary
    """
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            blocks.append("\n".join(current).strip())
            current.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
        else:
            current.append(line)
    flush()

    out_parts: list[str] = []
    for block in blocks:
        first_line = block.split("\n")[0].strip()
        if first_line.startswith("## "):
            heading = html.escape(first_line[3:].strip())
            out_parts.append(f"<h2>{heading}</h2>")
        elif first_line.startswith("> "):
            # Multi-line blockquote
            content_lines = []
            for l in block.split("\n"):
                if l.strip().startswith("> "):
                    content_lines.append(html.escape(l.strip()[2:]))
                else:
                    content_lines.append(html.escape(l.strip()))
            out_parts.append(
                f"<blockquote><p>{' '.join(content_lines)}</p></blockquote>"
            )
        else:
            # Preserve inline bold markers but escape the rest
            inner = html.escape(block)
            # Restore **…** as <strong>
            inner = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", inner)
            out_parts.append(f"<p>{inner}</p>")

    return "\n".join(out_parts)


# ---------------------------------------------------------------------------
# Cache tier: parse a .md file into prose dict.
# ---------------------------------------------------------------------------

def _parse_cache_md(path: str) -> dict:
    """Parse a cache markdown file into prose components."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    lines = text.splitlines()
    headline = ""
    standfirst = ""
    bottom_line = ""

    i = 0
    # H1 → headline
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("# "):
            headline = stripped[2:].strip()
            i += 1
            break
        i += 1

    # Skip blank lines then look for standfirst
    while i < len(lines) and not lines[i].strip():
        i += 1

    if i < len(lines) and lines[i].strip().startswith("> "):
        standfirst = lines[i].strip()[2:].strip()
        i += 1

    # Remaining lines → body (may contain **Bottom line:** paragraph)
    rest_lines = lines[i:]
    bottom_line_text = ""
    for line in rest_lines:
        m = re.match(r"\*\*Bottom line:\*\*\s*(.*)", line.strip())
        if m:
            bottom_line_text = m.group(1).strip()
    body_html = _md_to_html("\n".join(rest_lines))

    # Extract bottom_line from the <strong>Bottom line:</strong> paragraph if present
    if not bottom_line_text:
        m = re.search(r"<strong>Bottom line:</strong>\s*(.*?)</p>", body_html)
        if m:
            bottom_line_text = html.unescape(m.group(1)).strip()

    return {
        "headline": headline,
        "standfirst": standfirst,
        "body_html": body_html,
        "bottom_line": bottom_line_text,
        "source": "cache",
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_pts(v) -> str:
    """Format points / EV / ceiling to 2 decimal places."""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_own(v) -> str:
    """Format ownership to 1 decimal + %."""
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _fmt_price(v) -> str:
    """Format price to 1 decimal."""
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)


# _fmt_ev is kept as an alias so external callers don't break, but EV is
# now formatted with _fmt_pts (2 dp) everywhere inside this module.
_fmt_ev = _fmt_pts


def _fmt_vor(v) -> str:
    """Format value-over-replacement with an explicit sign, 2 decimal places."""
    try:
        return f"{float(v):+.2f}"
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Template tier: deterministic per-article prose.
# ---------------------------------------------------------------------------

def _subject_entry(entries, subject):
    """Return the entry for `subject`, or entries[0] if subject is None or not found."""
    if subject is None:
        return entries[0] if entries else {}
    for e in entries:
        if e.get("name") == subject:
            return e
    return entries[0] if entries else {}


# ---------------------------------------------------------------------------
# wildcard template helpers -- entries is the full 15 (XI + bench); these
# derive squad-level numbers from the rows themselves since the template tier
# only ever receives the flat entries list (not articles.wildcard_squad's
# separate meta dict).
# ---------------------------------------------------------------------------

def _wc_xi(entries):
    xi = [e for e in entries if e.get("role") == "XI"]
    return xi if xi else entries[:11]


def _wc_bench(entries):
    bench = [e for e in entries if e.get("role") == "Bench"]
    return bench if bench else entries[11:]


def _wc_total_cost(entries):
    return sum(e.get("price") or 0.0 for e in entries)


def _wc_xi_xpoints(entries):
    return sum(e.get("x_points") or 0.0 for e in _wc_xi(entries))


def _wc_left_over(entries, budget=100.0):
    return round(budget - _wc_total_cost(entries), 2)


def _wc_formation(entries):
    from evmax.articles import formation_of
    return formation_of(_wc_xi(entries))


def _wc_priciest(entries, n=3):
    return sorted(entries, key=lambda e: e.get("price") or 0.0, reverse=True)[:n]


def _wc_best_value(entries):
    priced = [e for e in entries if e.get("value") is not None]
    if not priced:
        return None
    return max(priced, key=lambda e: e["value"])


# ---------------------------------------------------------------------------
# efficiency() price-tier helpers -- entries carry a `tier` field (Budget/Mid/
# Premium, from articles.efficiency); these surface the best value pick WITHIN
# each tier, not just the single best overall.
# ---------------------------------------------------------------------------

_TIER_ORDER = ["Budget", "Mid", "Premium"]


def _eff_best_in_tier(entries):
    from evmax.articles import best_in_tier
    return best_in_tier(entries)


def _wc_efficiency_tier_paragraph(entries) -> str:
    by_tier = _eff_best_in_tier(entries)
    if not by_tier:
        return ""
    picks = []
    for tier in _TIER_ORDER:
        r = by_tier.get(tier)
        if r is None:
            continue
        picks.append(
            f"<b>{tier}</b>: {html.escape(r['name'])} "
            f"({_fmt_pts(r.get('value', 0))} xPts/£, £{_fmt_price(r['price'])}m)"
        )
    if not picks:
        return ""
    return f"<p>The best pick in each price bracket — {'; '.join(picks)}.</p>"


def _wc_efficiency_tier_bottom_line(entries) -> str:
    by_tier = _eff_best_in_tier(entries)
    picks = []
    for tier in _TIER_ORDER:
        r = by_tier.get(tier)
        if r is None:
            continue
        picks.append(f"{tier.lower()} — {html.escape(r['name'])}")
    if not picks:
        return ""
    return " By tier: " + ", ".join(picks) + "."


_TEMPLATES = {
    "captains": {
        "headline": lambda e, r, subj: f"{subj} leads the armband race in Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} tops captain EV at {_fmt_ev(_subject_entry(e, subj)['captain_ev'])} pts"
            + (f", ahead of {e[1]['name']} ({_fmt_ev(e[1]['captain_ev'])})."
               if len(e) > 1 and e[1]['name'] != subj else ".")
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} is the standout captain option this round, "
            f"posting a captain EV of {_fmt_pts(_subject_entry(e, subj)['captain_ev'])} pts and an xPts of "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])}. "
            + (f"{html.escape(e[1]['name'])} is a credible alternative at "
               f"{_fmt_pts(e[1]['captain_ev'])} EV." if len(e) > 1 and e[1]['name'] != subj else "")
            + "</p>\n"
            + (f"<blockquote><p>{html.escape(subj)}'s ownership sits at "
               f"{_fmt_own(_subject_entry(e, subj)['ownership_pct'])}, making them a high-upside, "
               f"manageable captaincy.</p></blockquote>\n"
               if _subject_entry(e, subj).get('ownership_pct') is not None else "")
            + f"<p>With a ceiling of {_fmt_pts(_subject_entry(e, subj)['ceiling'])}, the upside justifies "
            f"the pick. Priced at £{_fmt_price(_subject_entry(e, subj)['price'])}m, {html.escape(subj)} "
            f"offers value at {_fmt_pts(_subject_entry(e, subj).get('value', 0))} xPts/£.</p>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Back {subj} — {_fmt_pts(_subject_entry(e, subj)['captain_ev'])} captain EV is the best "
            f"available this round."
        ),
    },
    "best-xi": {
        # best-xi is always team-framed (subject=None)
        "headline": lambda e, r, subj: f"The optimal Fantasy XI for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"A {sum(x.get('x_points', 0) for x in e):.1f}-xPts XI built for Round {r}."
            if e else f"The optimal XI for Round {r}."
        ),
        "body": lambda e, r, subj: (
            (
                f"<p>The highest-expected-points XI this round totals "
                f"{sum(x.get('x_points', 0) for x in e):.1f} xPts across all positions. "
                f"{html.escape(e[0]['name'])} ({_fmt_pts(e[0]['x_points'])} xPts) "
                f"and {html.escape(e[1]['name'])} ({_fmt_pts(e[1]['x_points'])} xPts) "
                f"anchor the attacking line."
                if len(e) > 1 else
                f"<p>The optimal XI for this round projects {e[0].get('x_points', 0):.1f} xPts."
            ) + "</p>\n"
            + "<blockquote><p>Balance beats stars — a well-rounded XI from the best fixtures "
            "consistently outperforms a lopsided squad.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Field this XI — {sum(x.get('x_points', 0) for x in e):.1f} total xPts "
            f"is the model's best-fit combination for Round {r}."
        ),
    },
    "wildcard": {
        # wildcard is always team-framed (subject=None) -- the article is about
        # the 15-man squad as a unit, not any one player.
        "headline": lambda e, r, subj: f"Best XI and Wildcard draft for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"The strongest starting XI is a {_wc_formation(e)} projecting "
            f"{_fmt_pts(_wc_xi_xpoints(e))} xPts, wrapped in a {_fmt_price(_wc_total_cost(e))}m "
            f"legal 15."
            if e else f"Wildcard squad for Round {r}."
        ),
        "body": lambda e, r, subj: (
            f"<p>The strongest starting XI this round is a {_wc_formation(e)} projecting "
            f"{_fmt_pts(_wc_xi_xpoints(e))} combined xPts. Built out to a full legal 15 "
            f"— 2 goalkeepers, 5 defenders, 5 midfielders, 3 forwards — for wildcard and "
            f"rebuild managers, the squad spends "
            f"{_fmt_price(_wc_total_cost(e))}m of a 100.0m budget.</p>\n"
            + (
                f"<blockquote><p>The bench is deliberately the cheapest legal one "
                f"available — {', '.join(html.escape(b['name']) for b in _wc_bench(e))} "
                f"are enablers, not picks: their job is to exist within the rules so "
                f"every spare pound goes into the XI, not to contribute points "
                f"themselves.</p></blockquote>\n"
                if _wc_bench(e) else ""
            )
            + (
                f"<p>The most expensive picks are "
                + ", ".join(f"{html.escape(p['name'])} ({_fmt_price(p['price'])}m)"
                           for p in _wc_priciest(e, 3))
                + f". The standout value pick is "
                f"{html.escape(_wc_best_value(e)['name'])} at "
                f"{_fmt_pts(_wc_best_value(e).get('value', 0))} xPts/m "
                f"({_fmt_price(_wc_best_value(e)['price'])}m).</p>"
                if _wc_priciest(e, 1) and _wc_best_value(e) else ""
            )
        ),
        "bottom_line": lambda e, r, subj: (
            f"Field this {_wc_formation(e)} — {_fmt_pts(_wc_xi_xpoints(e))} xPts from "
            f"a {_fmt_price(_wc_total_cost(e))}m squad, with "
            f"{_fmt_price(_wc_left_over(e))}m left in the bank."
            if e else f"No wildcard squad available for Round {r}."
        ),
    },
    "defenders": {
        "headline": lambda e, r, subj: f"{subj} heads the defensive picks for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} leads defenders at {_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts"
            + (f", ahead of {e[1]['name']} ({_fmt_pts(e[1]['x_points'])})."
               if len(e) > 1 and e[1]['name'] != subj else ".")
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} tops the defensive rankings this round at "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts, "
            f"priced at £{_fmt_price(_subject_entry(e, subj)['price'])}m"
            + (f". {html.escape(e[1]['name'])} ({_fmt_pts(e[1]['x_points'])} xPts) "
               f"is the next-best option."
               if len(e) > 1 and e[1]['name'] != subj else ".")
            + "</p>\n"
            + f"<blockquote><p>Defenders from high-scoring expected fixtures offer "
            f"attacking returns on top of clean-sheet potential — the best of both worlds.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Start {subj} — {_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts "
            f"at £{_fmt_price(_subject_entry(e, subj)['price'])}m is the best defensive value this round."
        ),
    },
    "risky": {
        "headline": lambda e, r, subj: f"{subj} — the highest-ceiling punt in Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} tops the ceiling chart at {_fmt_pts(_subject_entry(e, subj)['ceiling'])} pts "
            f"with just {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} ownership."
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} carries a ceiling of {_fmt_pts(_subject_entry(e, subj)['ceiling'])} pts "
            f"— the highest boom-or-bust upside among low-owned players this round. "
            f"At just {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} ownership, a big haul here "
            f"moves the needle on the rank table.</p>\n"
            + (f"<p>{html.escape(e[1]['name'])} ({_fmt_pts(e[1]['ceiling'])} ceiling, "
               f"{_fmt_own(e[1]['ownership_pct'])} owned) is the next most tempting gamble.</p>\n"
               if len(e) > 1 and e[1]['name'] != subj else "")
            + f"<blockquote><p>Ceiling picks are leverage plays — "
            f"the expected value is lower, but the rank-jump potential is outsized.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"If you want differentiation, {subj} — {_fmt_pts(_subject_entry(e, subj)['ceiling'])} ceiling "
            f"at {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} ownership is the sharpest punt available."
        ),
    },
    "differentials": {
        "headline": lambda e, r, subj: f"Differential gems: low-owned, high-upside picks for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} tops the differential list at {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} ownership "
            f"and {_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts."
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} is the standout differential this round — "
            f"owned by just {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} of managers while projecting "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts"
            + (f" ahead of {html.escape(e[1]['name'])} ({_fmt_own(e[1]['ownership_pct'])}, "
               f"{_fmt_pts(e[1]['x_points'])} xPts)." if len(e) > 1 and e[1]['name'] != subj else ".")
            + "</p>\n"
            + f"<blockquote><p>The biggest rank-gain opportunity comes from punting on "
            f"{html.escape(subj)} while the field ignores them.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"{subj} at {_fmt_own(_subject_entry(e, subj)['ownership_pct'])} ownership is the best "
            f"way to differentiate your team this round."
        ),
    },
    "efficiency": {
        "headline": lambda e, r, subj: f"{subj} leads the value table in Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} leads on value at {_fmt_pts(_subject_entry(e, subj).get('value', 0))} xPts/£."
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} tops the efficiency table at "
            f"{_fmt_pts(_subject_entry(e, subj).get('value', 0))} xPts/£ — "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts from a £{_fmt_price(_subject_entry(e, subj)['price'])}m price tag"
            + (f", beating {html.escape(e[1]['name'])} ({_fmt_pts(e[1].get('value', 0))} xPts/£)."
               if len(e) > 1 and e[1]['name'] != subj else ".")
            + "</p>\n"
            + f"<blockquote><p>Value picks compound over a tournament — "
            f"a 0.1 xPts/£ edge across 11 players adds up fast.</p></blockquote>\n"
            + _wc_efficiency_tier_paragraph(e)
        ),
        "bottom_line": lambda e, r, subj: (
            f"Prioritise {subj} — {_fmt_pts(_subject_entry(e, subj).get('value', 0))} xPts/£ is the best "
            f"efficiency in the pool."
            + _wc_efficiency_tier_bottom_line(e)
        ),
    },
    "high-ceiling-xi": {
        "headline": lambda e, r, subj: f"High-ceiling XI: chase the big haul this round",
        "standfirst": lambda e, r, subj: (
            f"{subj} leads ceiling at {_fmt_pts(_subject_entry(e, subj)['ceiling'])} pts."
        ),
        "body": lambda e, r, subj: (
            f"<p>For managers chasing a big week, {html.escape(subj)} offers the "
            f"highest ceiling at {_fmt_pts(_subject_entry(e, subj)['ceiling'])} pts while projecting "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts"
            + (f". {html.escape(e[1]['name'])} follows with a {_fmt_pts(e[1]['ceiling'])} ceiling."
               if len(e) > 1 and e[1]['name'] != subj else ".")
            + "</p>\n"
            + f"<blockquote><p>The high-ceiling XI is built for rank-jumps — "
            f"accept the variance, target the upside.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Back {subj} for ceiling — {_fmt_pts(_subject_entry(e, subj)['ceiling'])} best-case "
            f"is the round's highest projection."
        ),
    },
    "matches": {
        "headline": lambda e, r, subj: f"Round {r} match predictions: scorelines and games to watch",
        "standfirst": lambda e, r, subj: (
            (lambda close: (
                f"{len(e)} fixtures simulated; {len(close)} close game(s) to watch: "
                + ", ".join(c["match"] for c in close[:2])
                + ("." if len(close) <= 2 else " and more.")
            ))([ c for c in e if c.get("close")])
            if e else f"Match predictions for Round {r}."
        ),
        "body": lambda e, r, subj: (
            (lambda top2, close: (
                f"<p>The model simulates {len(e)} fixtures for Round {r}. "
                + (f"The most decisive expected result is {html.escape(top2[0]['match'])} "
                   f"(predicted {html.escape(top2[0]['top_scoreline'])}, "
                   f"{top2[0]['exp_home_goals']:.2f}–{top2[0]['exp_away_goals']:.2f} xG)."
                   if top2 else "")
                + "</p>\n"
                + (f"<blockquote><p>Close games — where no outcome exceeds 45% probability — "
                   f"are the hardest to call and the most watchable: "
                   + ", ".join(html.escape(c['match']) for c in close[:3])
                   + ".</p></blockquote>\n"
                   if close else "")
                + (f"<p>{html.escape(top2[1]['match'])} is another fixture to note: "
                   f"expected {html.escape(top2[1]['top_scoreline'])} "
                   f"({top2[1]['exp_home_goals']:.2f}–{top2[1]['exp_away_goals']:.2f} xG).</p>"
                   if len(top2) > 1 else "")
            ))(
                sorted(e, key=lambda x: -x.get("exp_total", 0))[:2],
                [c for c in e if c.get("close")]
            )
        ),
        "bottom_line": lambda e, r, subj: (
            (lambda close: (
                f"Watch {close[0]['match']} — the model rates it too close to call at "
                f"{close[0]['p_home']*100:.0f}/{close[0]['p_draw']*100:.0f}/{close[0]['p_away']*100:.0f} 1X2."
                if close else
                f"No fixture is marked as close this round — the model has clear favourites across all {len(e)} games."
            ))([c for c in e if c.get("close")])
        ),
    },
    "fixtures": {
        "headline": lambda e, r, subj: f"Fixture guide: clean sheets and blowouts for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{e[0]['name']} rate highest for a clean sheet at "
            f"{e[0]['p_clean_sheet']*100:.0f}% {html.escape(e[0]['team'])}."
            if e else f"Fixture guide for Round {r}."
        ),
        "body": lambda e, r, subj: (
            (lambda blowouts, avoids: (
                f"<p>{html.escape(e[0]['name'])} carry the best clean-sheet odds this round at "
                f"{e[0]['p_clean_sheet']*100:.0f}% {html.escape(e[0]['team'])}, "
                f"conceding just {_fmt_pts(e[0]['exp_goals_against'])} expected goals."
                + (f" {html.escape(e[1]['name'])} are next at "
                   f"{e[1]['p_clean_sheet']*100:.0f}% {html.escape(e[1]['team'])}."
                   if len(e) > 1 else "")
                + "</p>\n"
                + (f"<blockquote><p>Target attackers in the blowout fixtures — "
                   + ", ".join(f"{html.escape(b['name'])} {html.escape(b['team'])}"
                               for b in blowouts[:3])
                   + f", each projecting {_fmt_pts(blowouts[0]['exp_goals_for'])}+ goals for.</p></blockquote>\n"
                   if blowouts else "")
                + (f"<p>On the other side, avoid forwards from the low-scoring games: "
                   + ", ".join(f"{html.escape(a['name'])} {html.escape(a['team'])}"
                               for a in avoids[:3])
                   + f" — total expected goals sit at or below "
                   f"{_fmt_pts(max(a['exp_goals_for'] + a['exp_goals_against'] for a in avoids))} "
                   f"in these fixtures.</p>"
                   if avoids else "")
            ))(
                [x for x in e if x.get("env") == "blowout"],
                [x for x in e if x.get("env") == "avoid"],
            )
        ),
        "bottom_line": lambda e, r, subj: (
            f"Back {e[0]['name']} for a clean sheet ({e[0]['p_clean_sheet']*100:.0f}% "
            f"{html.escape(e[0]['team'])}), target attackers in the blowouts, and fade "
            f"forwards in the low-goal fixtures."
            if e else f"No fixture data available for Round {r}."
        ),
    },
    "transfers": {
        "headline": lambda e, r, subj: f"{subj} tops the priority transfer list for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} offers {_fmt_vor(_subject_entry(e, subj)['vor'])} value over a replacement "
            f"at their position"
            + (f", with a {_fmt_own(_subject_entry(e, subj)['p_advance'])} chance of advancing "
               f"to feed a future round." if _subject_entry(e, subj).get('p_advance', 100) < 100
               else ".")
        ),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(subj)} tops the priority list at "
            f"{_fmt_vor(_subject_entry(e, subj)['vor'])} value over a replacement-level player "
            f"at their position, projecting {_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts "
            f"this round.</p>\n"
            + (f"<blockquote><p>Ranking by value alone isn't enough in a knockout: "
               f"{html.escape(subj)}'s team has a {_fmt_own(_subject_entry(e, subj)['p_advance'])} "
               f"chance of advancing, so that's weighed into the priority score — a great pick on a "
               f"team about to be eliminated is a wasted transfer.</p></blockquote>\n"
               if _subject_entry(e, subj).get('p_advance', 100) < 100 else
               "<blockquote><p>This round's transfer priorities, ranked by value over a "
               "replacement-level player at each position.</p></blockquote>\n")
            + (f"<p>{html.escape(e[1]['name'])} ({_fmt_vor(e[1]['vor'])} VOR) is the next priority "
               f"if you have a second move available.</p>"
               if len(e) > 1 and e[1]['name'] != subj else "")
        ),
        "bottom_line": lambda e, r, subj: (
            f"If you can only make one move this round, make it {subj} — "
            f"{_fmt_vor(_subject_entry(e, subj)['vor'])} value over replacement"
            + (f" from a team {_fmt_own(_subject_entry(e, subj)['p_advance'])} likely to advance."
               if _subject_entry(e, subj).get('p_advance', 100) < 100 else ".")
        ),
    },
    "blowout-transfers": {
        "headline": lambda e, r, subj: f"{subj} — top blowout target for Round {r}",
        "standfirst": lambda e, r, subj: (
            f"{subj} is the top transfer target at {_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts "
            f"from a blowout fixture."
        ),
        "body": lambda e, r, subj: (
            f"<p>With the blowout fixture incoming, {html.escape(subj)} "
            f"({_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts, £{_fmt_price(_subject_entry(e, subj)['price'])}m) is the "
            f"priority transfer"
            + (f" alongside {html.escape(e[1]['name'])} ({_fmt_pts(e[1]['x_points'])} xPts)."
               if len(e) > 1 and e[1]['name'] != subj else ".")
            + "</p>\n"
            + f"<blockquote><p>Fixtures drive points at a World Cup — "
            f"get the best attackers from the biggest mismatches.</p></blockquote>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Bring in {subj} before the deadline — "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts from the blowout fixture."
        ),
    },
}

_GENERIC_TEMPLATE = {
    "headline": lambda e, r, slug, subj: f"Round analysis: {slug.replace('-', ' ').title()}",
    "standfirst": lambda e, r, subj: (
        f"{subj or e[0]['name']} leads with {_fmt_pts(e[0]['x_points'])} xPts."
    ),
    "body": lambda e, r, subj: (
        f"<p>{html.escape(subj or e[0]['name'])} tops this list with {_fmt_pts(e[0]['x_points'])} xPts "
        f"and a captain EV of {_fmt_pts(e[0]['captain_ev'])}"
        + (f". {html.escape(e[1]['name'])} is close behind at {_fmt_pts(e[1]['x_points'])} xPts."
           if len(e) > 1 else ".")
        + "</p>"
    ),
    "bottom_line": lambda e, r, subj: (
        f"Target {subj or e[0]['name']} — {_fmt_pts(e[0]['x_points'])} xPts is the best projection available."
    ),
}


def _template_prose(article: str, entries: list, columns: list,
                    round_no: int = 0, subject=None) -> dict:
    """Build deterministic template prose from entries.

    subject: the player to centre the prose on (or None for team-framing in best-xi).
    """
    if not entries:
        return {
            "headline": f"Round analysis: {article}",
            "standfirst": "No data available.",
            "body_html": "<p>No entries available for this article.</p>",
            "bottom_line": "Check back when data is available.",
            "source": "template",
        }

    # For best-xi, wildcard, matches and fixtures (no player subject), skip
    # per-player framing
    if subject is not None:
        subj = subject
    elif article in ("best-xi", "wildcard", "matches", "fixtures"):
        subj = None
    else:
        subj = entries[0].get("name") if entries else None

    tmpl = _TEMPLATES.get(article)
    if tmpl:
        headline = tmpl["headline"](entries, round_no, subj)
        standfirst = tmpl["standfirst"](entries, round_no, subj)
        body_html = tmpl["body"](entries, round_no, subj)
        bottom_line = tmpl["bottom_line"](entries, round_no, subj)
    else:
        headline = _GENERIC_TEMPLATE["headline"](entries, round_no, article, subj)
        standfirst = _GENERIC_TEMPLATE["standfirst"](entries, round_no, subj)
        body_html = _GENERIC_TEMPLATE["body"](entries, round_no, subj)
        bottom_line = _GENERIC_TEMPLATE["bottom_line"](entries, round_no, subj)

    return {
        "headline": headline,
        "standfirst": standfirst,
        "body_html": body_html,
        "bottom_line": bottom_line,
        "source": "template",
    }


# ---------------------------------------------------------------------------
# LLM tier
# ---------------------------------------------------------------------------

def _llm_prose(article: str, round_no: int, entries: list, columns: list,
               cache_dir: str, subject=None):
    """Call the Claude API and return prose dict, or None if we should fall through."""
    if not _ANTHROPIC_AVAILABLE:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    from evmax.prompts import build_prompt

    prompt = build_prompt(article, round_no, entries, subject=subject)

    try:
        client = _anthropic.Anthropic()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
    except Exception:
        return None

    # Parse JSON response — find the JSON object even with preamble or code fences.
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None

    required_keys = {"headline", "standfirst", "body_markdown", "bottom_line"}
    if not required_keys.issubset(data.keys()):
        return None

    # --- Grounding validation (practical guardrail against gross fabrication) ---
    # Goal: reject made-up STAT figures and wholesale off-topic output, while
    # allowing natural prose (legitimate rounding, integers like "Round 3" /
    # "50,000" / "1%", country names, sentence-initial capitals). It does NOT bind
    # a number to a specific player — cross-player attribution could still pass —
    # which is acceptable because the prompt forbids it and the cache/template
    # tiers exist as backstops.
    combined_output = (
        data.get("headline", "") + " " +
        data.get("standfirst", "") + " " +
        data.get("body_markdown", "") + " " +
        data.get("bottom_line", "")
    )

    # Numbers: scrutinise only DECIMAL tokens (the shape of a fabricated stat). A
    # decimal is allowed if it is within 0.05 of some real entry value (covers
    # legitimate 1dp/2dp rounding); bare integers are allowed freely.
    real_values = [float(v) for e in entries for v in e.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
    for token in re.findall(r"\d+\.\d+", combined_output):
        val = float(token)
        if not any(abs(val - rv) <= 0.05 for rv in real_values):
            return None

    # Names: require the article's subject (passed in, or top entry) to actually appear,
    # rather than policing every capitalised word (which false-rejects country
    # names, "World Cup", sentence starts). Catches wholesale off-topic output.
    # For matches (subject=None, no "name" key), skip this check entirely.
    has_name_field = entries and "name" in entries[0]
    if subject is None and not has_name_field:
        pass  # matches article — no player name to ground on; skip check
    else:
        grounding_subject = subject if subject else (entries[0].get("name", "") if entries else "")
        if grounding_subject and not any(
            w in combined_output for w in grounding_subject.split() if len(w) > 2
        ):
            return None

    # Convert body_markdown to HTML
    body_html = _md_to_html(data["body_markdown"])

    result = {
        "headline": data["headline"],
        "standfirst": data["standfirst"],
        "body_html": body_html,
        "bottom_line": data["bottom_line"],
        "source": "llm",
    }

    # Cache the result as markdown
    try:
        cache_path = os.path.join(cache_dir, f"round-{round_no}", f"{article}.md")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            fh.write(f"# {data['headline']}\n\n")
            fh.write(f"> {data['standfirst']}\n\n")
            fh.write(data["body_markdown"])
            fh.write("\n")
    except OSError:
        pass  # Cache write failure is non-fatal

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def article_prose(
    article: str,
    round_no: int,
    entries: list,
    columns: list,
    cache_dir: str = "data/articles",
    use_llm: bool = True,
    subject=None,
) -> dict:
    """Generate prose for an article using tiered resolution: cache → LLM → template.

    Parameters
    ----------
    article   : article slug, e.g. "captains"
    round_no  : fantasy round number
    entries   : list of ranked row dicts (from articles.py)
    columns   : list of column keys to feature in prose
    cache_dir : base directory for cached markdown files
    use_llm   : whether to attempt the LLM tier (default True)
    subject   : player name to centre prose on, or None for team-framing (best-xi)

    Returns
    -------
    dict with keys: headline, standfirst, body_html, bottom_line, source
    """
    # Tier 1: cache
    cache_path = os.path.join(cache_dir, f"round-{round_no}", f"{article}.md")
    if os.path.isfile(cache_path):
        return _parse_cache_md(cache_path)

    # Tier 2: LLM (optional)
    if use_llm:
        result = _llm_prose(article, round_no, entries, columns, cache_dir, subject=subject)
        if result is not None:
            return result

    # Tier 3: template
    return _template_prose(article, entries, columns, round_no=round_no, subject=subject)
