"""Prose generation for evmax articles — tiered: cache → LLM → template.

Public API
----------
article_prose(article, round_no, entries, columns,
              cache_dir="data/articles", use_llm=True) -> dict
    Returns {"headline", "standfirst", "body_html", "body_md", "bottom_line", "source"}
    where source is "cache" | "llm" | "template". body_md is the content-only
    Markdown twin of body_html (used for the agent-facing .md article pages).
"""

from __future__ import annotations

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


def _html_to_md(html_text: str) -> str:
    """Convert the small HTML subset _md_to_html produces back to Markdown.

    Supported (best-effort, content fidelity over formatting):
      <h2>x</h2>                     -> ## x
      <blockquote><p>x</p></blockquote> -> > x
      <b>x</b> / <strong>x</strong>  -> **x**
      <p>x</p>                       -> paragraph, blank-line separated
    Any other tags are stripped; entities are unescaped.
    """
    text = html_text

    def _blockquote_sub(m):
        inner = m.group(1)
        inner = re.sub(r"</?p>", "", inner).strip()
        return f"> {inner}"

    text = re.sub(r"<blockquote>\s*(.*?)\s*</blockquote>", _blockquote_sub,
                 text, flags=re.DOTALL)
    text = re.sub(r"<h2>(.*?)</h2>", r"## \1", text, flags=re.DOTALL)
    text = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<p>(.*?)</p>", r"\1", text, flags=re.DOTALL)
    # Strip any remaining tags defensively
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # Normalise blank lines between blocks
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n\n".join(lines)


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
    body_md_raw = "\n".join(rest_lines).strip()
    body_html = _md_to_html(body_md_raw)

    # Extract bottom_line from the <strong>Bottom line:</strong> paragraph if present
    if not bottom_line_text:
        m = re.search(r"<strong>Bottom line:</strong>\s*(.*?)</p>", body_html)
        if m:
            bottom_line_text = html.unescape(m.group(1)).strip()

    return {
        "headline": headline,
        "standfirst": standfirst,
        "body_html": body_html,
        "body_md": body_md_raw,
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
            f"attacking returns on top of clean-sheet potential — the best of both worlds.</p></blockquote>\n"
            + f"<p>That {_fmt_pts(_subject_entry(e, subj)['x_points'])} is the safe floor; the model's "
            f"ceiling has {html.escape(subj)} at {_fmt_pts(_subject_entry(e, subj)['ceiling'])} if the clean "
            f"sheet holds and a goal or assist arrives on top.</p>"
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
            f"get the best attackers from the biggest mismatches.</p></blockquote>\n"
            + f"<p>{_fmt_pts(_subject_entry(e, subj)['x_points'])} is the projected floor; if the "
            f"goals flow the way the model expects, {html.escape(subj)}'s ceiling stretches to "
            f"{_fmt_pts(_subject_entry(e, subj)['ceiling'])}.</p>"
        ),
        "bottom_line": lambda e, r, subj: (
            f"Bring in {subj} before the deadline — "
            f"{_fmt_pts(_subject_entry(e, subj)['x_points'])} xPts from the blowout fixture."
        ),
    },
}

def _pct(v) -> str:
    return f"{(v or 0.0) * 100:.0f}%"


# --- distributions prose (spec 2026-08-26, P1) -------------------------------
# Hand-written rather than assembled from the generic table, because the whole
# point of the page is that a mean hides something and the prose has to be the
# thing that says so.

# The independence caveat is a PUBLISHING RULE, not a stylistic choice: the
# beats_top column is computed by treating two players' distributions as
# independent (evmax.fpl_articles.beats), and two attackers in the same match
# plainly are not. Any template rendering that column must carry this sentence
# — the spec makes stating the approximation a condition of shipping the page.
_INDEPENDENCE_CAVEAT = (
    "That comparison treats the two players as independent of each other. "
    "They are not: two attackers in the same match rise and fall together, "
    "and our simulation knows it even though this figure does not. Read it as "
    "the size of the gap, not as a settled number.")


def _distributions_body(e: list) -> str:
    """The lead candidate's spread, the head-to-head, then floor vs ceiling."""
    top = e[0]
    lead = (
        f"<p>{html.escape(top['name'])} "
        f"({html.escape(top.get('team', ''))}) projects "
        f"{_fmt_pts(top.get('captain_ev'))} with the armband. Behind that one "
        f"number: his floor is {top.get('p10')} points in the worst tenth of "
        f"simulations, his single most likely score is {top.get('mode')}, and "
        f"his ceiling is {top.get('p90')} in the best tenth. He reaches double "
        f"figures in {_pct(top.get('p_haul'))} of simulations and returns two "
        f"points or fewer in {_pct(top.get('p_blank'))}.</p>")

    rival = ""
    if len(e) > 1:
        second = e[1]
        beat = second.get("beats_top")
        rival = (
            f"<p>{html.escape(second['name'])} is the alternative at "
            f"{_fmt_pts(second.get('captain_ev'))} captained, on a floor of "
            f"{second.get('p10')} and a ceiling of {second.get('p90')}.")
        if beat is not None:
            rival += (f" He outscores {html.escape(top['name'])} in "
                      f"{_pct(beat)} of simulated gameweeks. "
                      + _INDEPENDENCE_CAVEAT)
        rival += "</p>"
    else:
        # One candidate and no head-to-head still needs the caveat on record:
        # the table's beats column is empty here, so say what it would mean.
        rival = (f"<p>Only one candidate cleared the bar this week, so there "
                 f"is no head-to-head to report. Where we do compare two "
                 f"players, we treat their weeks as independent of each "
                 f"other, which is an approximation.</p>")

    shape = ""
    if len(e) > 1:
        floor_pick = max(e, key=lambda x: (x.get("p10") or 0, x.get("median") or 0))
        ceil_pick = max(e, key=lambda x: (x.get("p90") or 0, x.get("p_haul") or 0))
        safe = max(e, key=lambda x: -(x.get("p_blank") or 0.0))
        if floor_pick["name"] == ceil_pick["name"]:
            shape = (f"<p>{html.escape(floor_pick['name'])} holds both ends of "
                     f"the board this week: the highest floor "
                     f"({floor_pick.get('p10')}) and the highest ceiling "
                     f"({ceil_pick.get('p90')}). That is unusual, and it is "
                     f"the case for taking him.</p>")
        else:
            shape = (f"<p>The floor and the ceiling belong to different "
                     f"players. {html.escape(floor_pick['name'])} has the "
                     f"highest floor at {floor_pick.get('p10')} points, so he "
                     f"is the pick if a bad week would cost you rank. "
                     f"{html.escape(ceil_pick['name'])} has the highest "
                     f"ceiling at {ceil_pick.get('p90')}, so he is the pick if "
                     f"you need to make ground. "
                     f"{html.escape(safe['name'])} blanks least often, in "
                     f"{_pct(safe.get('p_blank'))} of simulations.</p>")
    return lead + rival + shape


def _distributions_bottom_line(e: list) -> str:
    top = e[0]
    if len(e) > 1:
        ceil_pick = max(e, key=lambda x: (x.get("p90") or 0, x.get("p_haul") or 0))
        if ceil_pick["name"] != top["name"]:
            return (f"Captain {top['name']} on the average. Captain "
                    f"{ceil_pick['name']} if you need the ceiling — "
                    f"{ceil_pick.get('p90')} points in the best tenth of "
                    f"simulations against {top.get('p90')}.")
    return (f"Captain {top['name']} — {_pct(top.get('p_haul'))} of simulations "
            f"reach double figures, against a "
            f"{_pct(top.get('p_blank'))} chance of two points or fewer.")


def _is_double_gameweek(entry) -> bool:
    """True when this player's club has more than one fixture this gameweek.

    Guards the defenders prose: bonus/defcon/cs_points are per-MATCH means
    while x_points is a per-WEEK total (games/fpl/model._derive_row), so
    framing them as components of the total is only true for a single
    fixture. A missing count reads as single — the build stamps the real
    count from the match summaries, and 0 (a blank) has nothing to double.
    TODO(pre-first-DGW): retire with the per-sim column rework (review
    2026-08-19, finding 7)."""
    return (entry.get("fixtures") or 0) > 1


def _captain_vice_kickoff_sentence(e: list) -> str:
    """The vice-timing sentence for the captains template.

    kickoff_order is a dense rank over distinct kickoff instants (see
    fpl_articles.captains), so equality means the two candidates genuinely
    kick off together — usually the same match — and neither "first" nor
    "later" is a true claim. Missing orders compare equal on purpose: with no
    kickoff data the prose must not invent a timing edge either way.
    """
    first, second = e[0].get("kickoff_order"), e[1].get("kickoff_order")
    if first is None or second is None or first == second:
        return ("He kicks off at the same time, so as vice he is pure "
                "insurance against a late scratch.")
    if second < first:
        return "He kicks off first, so he is the safer vice."
    return ("He kicks off later, so he works as a vice only if your "
            "captain's match is already done.")


# FPL slug templates, keyed separately from _TEMPLATES because four FPL slugs
# (captains, wildcard, defenders, efficiency) collide with World Cup slugs whose
# prose is pinned. Selected by _template_prose when unit == "Gameweek".
# Owner decision 2026-07-30: a --no-llm build must read like a real article,
# never "Gameweek analysis: Defcon".
_FPL_TEMPLATES = {
    "captains": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the gameweek {r} captain"),
        "standfirst": lambda e, r, subj: (
            f"{_fmt_pts(e[0]['captain_ev'])} captain EV, "
            f"{_fmt_pts(e[0]['ceiling'])} ceiling — the best armband in the model."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} ({html.escape(e[0].get('team', ''))}) "
            f"projects {_fmt_pts(e[0]['captain_ev'])} captained, off "
            f"{_fmt_pts(e[0]['x_points'])} expected points, with a ceiling of "
            # the FPL ceiling is a tail mean, not a percentile — say what it is
            f"{_fmt_pts(e[0]['ceiling'])} — the average of his best 15% of "
            f"simulations.</p>"
            + (f"<p>{html.escape(e[1]['name'])} is the alternative at "
               f"{_fmt_pts(e[1]['captain_ev'])}. "
               + _captain_vice_kickoff_sentence(e)
               + "</p>" if len(e) > 1 else "")),
        "bottom_line": lambda e, r, subj: (
            f"Captain {e[0]['name']} — {_fmt_pts(e[0]['captain_ev'])} is the "
            f"highest doubled projection on the board."),
    },
    "wildcard": {
        "headline": lambda e, r, subj: (
            f"The gameweek {r} draft squad: {_wc_formation(e)}"),
        "standfirst": lambda e, r, subj: (
            f"A legal 15 for {_wc_total_cost(e):.1f}m, with an XI projecting "
            f"{_wc_xi_xpoints(e):.1f} points."),
        "body": lambda e, r, subj: (
            f"<p>The model's draft squad lines up {_wc_formation(e)} and costs "
            f"{_wc_total_cost(e):.1f}m of the 100.0m budget, leaving "
            f"{_wc_left_over(e):.1f}m in the bank. The starting XI projects "
            f"{_wc_xi_xpoints(e):.1f} points.</p>"
            f"<p>The bench is deliberately cheap — four enablers that make the 15 "
            f"legal so the spending sits in the XI. No club contributes more than "
            f"three players, which is the squad rule that most often forces a "
            f"compromise on the premium picks.</p>"),
        "bottom_line": lambda e, r, subj: (
            f"Build around this {_wc_formation(e)}: "
            f"{_wc_xi_xpoints(e):.1f} projected points for "
            f"{_wc_total_cost(e):.1f}m."),
    },
    "ticker": {
        "headline": lambda e, r, subj: (
            f"Gameweek {r} fixture ticker: {e[0]['name']} lead the clean sheets"),
        "standfirst": lambda e, r, subj: (
            f"{e[0]['name']} project {e[0]['exp_clean_sheets']:.2f} expected clean "
            f"sheets against {e[0]['opponents']}."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} top the ticker at "
            f"{e[0]['exp_clean_sheets']:.2f} expected clean sheets "
            f"({html.escape(e[0]['opponents'])}), conceding an expected "
            f"{e[0]['exp_goals_against']:.1f}. "
            f"{'These numbers are market-derived.' if e[0].get('basis') == 'market' else 'These numbers come from our own team ratings, not the betting market — treat them as the softer read.'}"
            f"</p>"
            + _fpl_ticker_blanks_doubles(e)),
        "bottom_line": lambda e, r, subj: (
            f"Target {e[0]['name']} defenders — "
            f"{e[0]['exp_clean_sheets']:.2f} expected clean sheets is the best on "
            f"the board."),
    },
    "defenders": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} leads the gameweek {r} defenders"),
        "standfirst": lambda e, r, subj: (
            f"{_fmt_pts(e[0]['x_points'])} expected points, with "
            f"{_fmt_pts(e[0].get('cs_points', 0))} of it from clean sheets alone."
            if not _is_double_gameweek(e[0]) else
            f"{_fmt_pts(e[0]['x_points'])} expected points across "
            f"{e[0]['fixtures']} fixtures this gameweek."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} "
            f"({html.escape(e[0].get('team', ''))}) projects "
            f"{_fmt_pts(e[0]['x_points'])}: "
            f"{_fmt_pts(e[0].get('cs_points', 0))} from clean sheets, "
            f"{_fmt_pts(e[0].get('defcon', 0))} from defensive contribution and "
            f"{_fmt_pts(e[0].get('bonus', 0))} from bonus. Where a defender's "
            f"points come from matters as much as the total — a clean-sheet "
            f"projection lives or dies on one fixture, while defensive "
            f"contribution pays regardless of the scoreline.</p>"
            if not _is_double_gameweek(e[0]) else
            f"<p>{html.escape(e[0]['name'])} "
            f"({html.escape(e[0].get('team', ''))}) projects "
            f"{_fmt_pts(e[0]['x_points'])} expected points across "
            f"{e[0]['fixtures']} fixtures this gameweek. His clean-sheet, "
            f"DefCon and bonus columns are per-match rates rather than shares "
            f"of that total, so read them per fixture — the doubled minutes, "
            f"not the rates, are what make a double gameweek pay.</p>"),
        "bottom_line": lambda e, r, subj: (
            f"{e[0]['name']} at {_fmt_price(e[0].get('price'))} is the defensive "
            f"pick of the gameweek."),
    },
    "efficiency": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the best value in gameweek {r}"),
        "standfirst": lambda e, r, subj: (
            f"{e[0]['value']:.2f} points per million at "
            f"{_fmt_price(e[0].get('price'))}."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} returns {e[0]['value']:.2f} points "
            f"per million — {_fmt_pts(e[0]['x_points'])} expected points at "
            f"{_fmt_price(e[0].get('price'))}.</p>"
            + _wc_efficiency_tier_paragraph(e)),
        "bottom_line": lambda e, r, subj: _wc_efficiency_tier_bottom_line(e),
    },
    "our-squad": {
        # Squad-framed (subject=None): the article is about the team we field,
        # not any one player. Owner-decided reasoning (2026-08-19): horizon EV,
        # market-implied rates, no ownership shields, captain by EV.
        "headline": lambda e, r, subj: (
            f"Our gameweek {r} squad: {_sq_captain(e).get('name', '?')} "
            f"captains a {_wc_formation(e)}"),
        "standfirst": lambda e, r, subj: (
            f"The engine's own 15 — a {_wc_formation(e)} projecting "
            f"{_fmt_pts(_sq_projected(e))} points with the captain doubled, "
            f"picked on six-gameweek horizon value, not one-week form."),
        "body": lambda e, r, subj: (
            f"<p>This is the team we actually field, and it stands or falls in "
            f"public. The engine optimises expected points over a discounted "
            f"six-gameweek horizon on market-implied scoring rates, so every "
            f"pick is a horizon bet rather than a one-fixture spike. The XI "
            f"lines up {_wc_formation(e)} and projects "
            f"{_fmt_pts(_sq_xi_total(e))} points before the armband; with "
            f"{html.escape(_sq_captain(e).get('name', '?'))} doubled that "
            f"becomes {_fmt_pts(_sq_projected(e))}.</p>\n"
            + _sq_no_haaland_quote(e)
            + f"<p>{html.escape(_sq_captain(e).get('name', '?'))} wears the "
            f"armband because he tops this squad's doubled projection at "
            f"{_fmt_pts(_sq_captain(e).get('captain_ev', 0))} — captaincy here "
            f"is expected value, never narrative. "
            f"{html.escape(_sq_vice(e).get('name', '?'))} is vice: if the "
            f"captain's match falls through, the armband moves to the "
            f"next-best number, not to a hunch.</p>\n"
            + _sq_bench_sentence(e)),
        "bottom_line": lambda e, r, subj: (
            f"{_wc_formation(e)}, {_sq_captain(e).get('name', '?')} (c), "
            f"{_sq_vice(e).get('name', '?')} vice — "
            f"{_fmt_pts(_sq_projected(e))} projected with the armband applied."),
    },
    "consensus-squad": {
        # Squad-framed (subject=None). Method statement only: mention-tally
        # across the expert corpus, majority captain, minutes from sourced
        # research notes. Never names a bookmaker, never reproduces expert text.
        "headline": lambda e, r, subj: (
            f"The consensus XI: the experts' gameweek {r} team"),
        "standfirst": lambda e, r, subj: (
            f"A mention-tally across {_sq_sources_noun(e)}, assembled into a "
            f"legal 15 — {_sq_captain(e).get('name', '?')} carries the "
            f"majority armband."),
        "body": lambda e, r, subj: (
            f"<p>This squad follows the crowd on purpose. We tally which "
            f"players the expert consensus sources keep "
            f"naming{_sq_source_count_clause(e)} keep the names most lists "
            f"agree on, and assemble "
            f"them into a quota-, budget- and club-legal 15. The captain is "
            f"the majority call, not ours: "
            f"{html.escape(_sq_captain(e).get('name', '?'))}, with "
            f"{html.escape(_sq_vice(e).get('name', '?'))} as vice.</p>\n"
            f"<blockquote><p>Its minutes come from sourced research notes "
            f"rather than our engine — where the experts assert a starter, "
            f"this squad believes them. The weekly gap between this team and "
            f"our own squad measures exactly whose information about who "
            f"actually plays is better.</p></blockquote>\n"
            f"<p>Scored on our numbers, the {_wc_formation(e)} XI projects "
            f"{_fmt_pts(_sq_xi_total(e))} points, "
            f"{_fmt_pts(_sq_projected(e))} with the captain doubled. Both "
            f"squads are published before every deadline and graded after it — "
            f"the season scoreboard settles the argument.</p>"),
        "bottom_line": lambda e, r, subj: (
            f"The crowd's 15: {_wc_formation(e)}, "
            f"{_sq_captain(e).get('name', '?')} (c) — "
            f"{_fmt_pts(_sq_projected(e))} projected on our model's numbers."),
    },
    "defcon": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the gameweek {r} DefCon banker"),
        "standfirst": lambda e, r, subj: (
            f"He clears the {e[0]['defcon_threshold']}-action threshold in "
            f"{_pct(e[0]['p_defcon'])} of simulations."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} "
            f"({html.escape(e[0].get('team', ''))}) records at least "
            f"{e[0]['defcon_threshold']} defensive actions in "
            f"{_pct(e[0]['p_defcon'])} of our simulations, worth "
            f"{_fmt_pts(e[0].get('defcon', 0))} on its own. Defensive "
            f"contribution is a threshold, not a rate: a player either clears the "
            f"count in a given match or earns nothing, which is why we quote the "
            f"hit rate rather than an average.</p>"
            + (f"<p>{html.escape(e[1]['name'])} is next at "
               f"{_pct(e[1]['p_defcon'])} against a "
               f"{e[1]['defcon_threshold']}-action threshold.</p>"
               if len(e) > 1 else "")),
        "bottom_line": lambda e, r, subj: (
            f"{e[0]['name']} is the most reliable route to the 2-point defensive "
            f"bonus — {_pct(e[0]['p_defcon'])} of simulations."),
    },
    "distributions": {
        "headline": lambda e, r, subj: (
            f"Gameweek {r} spreads: {e[0]['name']} hauls "
            f"{_pct(e[0].get('p_haul'))} of the time"),
        "standfirst": lambda e, r, subj: (
            f"Every projection on this site is the average of tens of thousands "
            f"of simulated gameweeks. This is the shape behind the average: "
            f"{e[0]['name']} blanks in {_pct(e[0].get('p_blank'))} of them and "
            f"scores double figures in {_pct(e[0].get('p_haul'))}."),
        "body": lambda e, r, subj: _distributions_body(e),
        "bottom_line": lambda e, r, subj: _distributions_bottom_line(e),
    },
}



# ---------------------------------------------------------------------------
# squad-slug template helpers -- entries are squad_article's 15 (XI in state
# order + bench in bench_order), each carrying role / is_captain / is_vice.
# ---------------------------------------------------------------------------

def _sq_xi(entries):
    xi = [e for e in entries if e.get("role") == "XI"]
    return xi if xi else entries[:11]


def _sq_bench(entries):
    bench = [e for e in entries if e.get("role") == "Bench"]
    return bench if bench else entries[11:]


def _sq_captain(entries):
    xi = _sq_xi(entries)
    return next((e for e in xi if e.get("is_captain")), xi[0] if xi else {})


def _sq_vice(entries):
    xi = _sq_xi(entries)
    return next((e for e in xi if e.get("is_vice")), {})


def _sq_xi_total(entries):
    return round(sum(e.get("x_points") or 0.0 for e in _sq_xi(entries)), 2)


def _sq_projected(entries):
    """XI total with the captain counted twice — the number the duel strip and
    both squad articles headline."""
    cap = _sq_captain(entries)
    return round(_sq_xi_total(entries) + (cap.get("x_points") or 0.0), 2)


def _sq_bench_sentence(entries) -> str:
    bench = _sq_bench(entries)
    if not bench:
        return ""
    names = ", ".join(f"{i}. {html.escape(b.get('name', '?'))}"
                      for i, b in enumerate(bench, 1))
    return (f"<p>The bench, in order: {names}. It is deliberately thin — the "
            f"first name is the backup keeper, and the spend sits in the XI "
            f"where the points are.</p>")


def _sq_no_haaland_quote(entries) -> str:
    """The model squad's standing conviction, stated only while it is TRUE —
    the gameweek Haaland enters the squad, this paragraph must vanish on its
    own rather than contradict the team sheet above it.

    The closing sentence points at the OTHER squad, so it renders only when
    the consensus squad actually owns Haaland — the build stamps
    `consensus_owns_haaland` on these entries because only it holds both
    squads (review 2026-08-19, finding 5). No flag means no claim: the prose
    never asserts what it cannot check."""
    if any(e.get("name") == "Haaland" for e in entries):
        return ""
    quote = ("No Haaland, by conviction rather than oversight. "
             "At his price the model wants the budget spread across three "
             "lines, and we do not pay a premium for an ownership shield.")
    if any(e.get("consensus_owns_haaland") for e in entries):
        quote += (" If the crowd is right about him, the consensus XI on "
                  "this site owns him and will collect the evidence.")
    return f"<blockquote><p>{quote}</p></blockquote>\n"


# Reader-facing number words for the consensus corpus size. Prose says "seven
# expert sources", not "7 expert sources"; anything past twelve falls back to
# the numeral rather than inventing "twenty-three".
_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
              7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
              12: "twelve"}


def _sq_source_count(entries):
    """The consensus corpus size squad_article stamped on the entries, or None.
    Derived from the state file, never hardcoded — a GW2 tally over nine
    sources must not publish a template's 'seven'."""
    for e in entries:
        n = e.get("source_count")
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return n
    return None


def _sq_sources_noun(entries) -> str:
    """"seven expert sources" when the count is known, else a phrase that
    claims no number at all."""
    n = _sq_source_count(entries)
    if n is None:
        return "the expert consensus sources"
    return f"{_NUM_WORDS.get(n, str(n))} expert sources"


def _sq_source_count_clause(entries) -> str:
    """The parenthetical count in the consensus body, or a plain comma when
    the data carries no count to quote."""
    n = _sq_source_count(entries)
    if n is None:
        return ","
    return f" — {_NUM_WORDS.get(n, str(n))} of them this gameweek —"


def _fpl_ticker_blanks_doubles(entries: list) -> str:
    """A paragraph naming the gameweek's blanks and doubles, or "" if there are
    none. These are the two facts that change a manager's week, so they are never
    left to the reader to spot in the table."""
    blanks = [e["name"] for e in entries if e.get("fixtures") == 0]
    doubles = [e["name"] for e in entries if (e.get("fixtures") or 0) > 1]
    parts = []
    if doubles:
        parts.append(f"{', '.join(doubles)} play twice — a double gameweek, and "
                     f"the single biggest edge available")
    if blanks:
        parts.append(f"{', '.join(blanks)} have a blank gameweek and score nothing")
    if not parts:
        return ""
    # NOT str.capitalize(): that lowercases everything after the first character,
    # turning club codes ("EVE") into nonsense ("Eve"). The sentence already
    # starts with a club name, so only ensure the first character is upper.
    text = "; ".join(parts)
    return "<p>" + html.escape(text[0].upper() + text[1:]) + ".</p>"

_GENERIC_TEMPLATE = {
    "headline": lambda e, r, slug, subj, unit="Round": (
        f"{unit} analysis: {slug.replace('-', ' ').title()}"),
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
                    round_no: int = 0, subject=None, unit: str = "Round") -> dict:
    """Build deterministic template prose from entries.

    subject: the player to centre the prose on (or None for team-framing in best-xi).
    unit: the reader-facing period word — selects the FPL template table when it
    is "Gameweek", because four FPL slugs share names with World Cup slugs whose
    prose must not change.
    """
    if not entries:
        body_html = "<p>No entries available for this article.</p>"
        return {
            "headline": f"{unit} analysis: {article}",
            "standfirst": "No data available.",
            "body_html": body_html,
            "body_md": _html_to_md(body_html),
            "bottom_line": "Check back when data is available.",
            "source": "template",
        }

    # For best-xi, wildcard, matches, fixtures, the FPL ticker and the two
    # published squads (no player subject), skip per-player framing
    if subject is not None:
        subj = subject
    elif article in ("best-xi", "wildcard", "matches", "fixtures", "ticker",
                     "our-squad", "consensus-squad"):
        subj = None
    else:
        subj = entries[0].get("name") if entries else None

    table = _FPL_TEMPLATES if unit == "Gameweek" else _TEMPLATES
    tmpl = table.get(article)
    if tmpl:
        headline = tmpl["headline"](entries, round_no, subj)
        standfirst = tmpl["standfirst"](entries, round_no, subj)
        body_html = tmpl["body"](entries, round_no, subj)
        bottom_line = tmpl["bottom_line"](entries, round_no, subj)
    else:
        headline = _GENERIC_TEMPLATE["headline"](entries, round_no, article, subj,
                                                 unit)
        standfirst = _GENERIC_TEMPLATE["standfirst"](entries, round_no, subj)
        body_html = _GENERIC_TEMPLATE["body"](entries, round_no, subj)
        bottom_line = _GENERIC_TEMPLATE["bottom_line"](entries, round_no, subj)

    return {
        "headline": headline,
        "standfirst": standfirst,
        "body_html": body_html,
        "body_md": _html_to_md(body_html),
        "bottom_line": bottom_line,
        "source": "template",
    }


# ---------------------------------------------------------------------------
# LLM tier
# ---------------------------------------------------------------------------

def _llm_prose(article: str, round_no: int, entries: list, columns: list,
               cache_dir: str, subject=None, cache_name: str | None = None,
               unit: str = "Round"):
    """Call the Claude API and return prose dict, or None if we should fall through.

    cache_name namespaces the write-back exactly like article_prose's read path —
    an FPL article cached under round-{n} would poison the World Cup round's
    prose (and vice versa).
    """
    if not _ANTHROPIC_AVAILABLE:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    from evmax.prompts import build_prompt

    prompt = build_prompt(article, round_no, entries, subject=subject, unit=unit)

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
        "body_md": data["body_markdown"],
        "bottom_line": data["bottom_line"],
        "source": "llm",
    }

    # Cache the result as markdown
    try:
        cache_path = os.path.join(cache_dir, cache_name or f"round-{round_no}",
                                  f"{article}.md")
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
    cache_name: str | None = None,
    unit: str = "Round",
) -> dict:
    """Generate prose for an article using tiered resolution: cache → LLM → template.

    Parameters
    ----------
    article    : article slug, e.g. "captains"
    round_no   : fantasy round number
    entries    : list of ranked row dicts (from articles.py)
    columns    : list of column keys to feature in prose
    cache_dir  : base directory for cached markdown files
    use_llm    : whether to attempt the LLM tier (default True)
    subject    : player name to centre prose on, or None for team-framing (best-xi)
    cache_name : subdirectory under cache_dir, defaulting to "round-{round_no}".
                 The FPL build passes "fpl-gw{n}" — without it, FPL gameweek 1 and
                 World Cup round 1 share a cache entry and one serves the other's
                 article.
    unit       : the reader-facing word for the period ("Round" or "Gameweek"),
                 passed through to the LLM prompt and the templates.

    Returns
    -------
    dict with keys: headline, standfirst, body_html, body_md, bottom_line, source
    """
    cache_name = cache_name or f"round-{round_no}"
    # Tier 1: cache
    cache_path = os.path.join(cache_dir, cache_name, f"{article}.md")
    if os.path.isfile(cache_path):
        return _parse_cache_md(cache_path)

    # Tier 2: LLM (optional)
    if use_llm:
        result = _llm_prose(article, round_no, entries, columns, cache_dir,
                            subject=subject, cache_name=cache_name, unit=unit)
        if result is not None:
            return result

    # Tier 3: template
    return _template_prose(article, entries, columns, round_no=round_no,
                           subject=subject, unit=unit)
