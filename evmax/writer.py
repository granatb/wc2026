"""Prose generation for evmax articles — tiered: cache → LLM → template.

Public API
----------
article_prose(article, round_no, entries, columns,
              cache_dir="data/articles", use_llm=True, subject=None,
              cache_name=None, unit="Round") -> dict
    Returns {"headline", "standfirst", "body_html", "body_md", "bottom_line", "source"}
    where source is "cache" | "llm" | "template". body_md is the content-only
    Markdown twin of body_html (used for the agent-facing .md article pages).
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

# ---------------------------------------------------------------------------
# FPL templates.
#
# Four FPL slugs (captains, wildcard, defenders, efficiency) share a name with a
# World Cup slug whose prose is pinned by tests, so the FPL versions live in their
# own table rather than overwriting entries in _TEMPLATES. _template_prose picks
# the table on `unit`.
#
# These are the --no-llm output for a real published page, so they are written as
# copy, not as slot-filling: house style is floor and ceiling in the same breath,
# whole-number percentages, prices as "5.9m", and no raw dict keys on the page.
# Everything interpolated into body HTML goes through html.escape (headline,
# standfirst and bottom_line are escaped by render.py instead — escaping them here
# too would double-encode).
#
# Superlatives ("the best on the board", "tops the table") are gated on the
# subject actually being entries[0]. The build de-duplicates lead players across
# articles, so the subject is NOT always the top-ranked row, and a template that
# assumes otherwise publishes a false claim next to a table that contradicts it.
# ---------------------------------------------------------------------------

_POS_WORD = {"GK": "goalkeeper", "DEF": "defender", "MID": "midfielder",
             "FWD": "forward"}


def _esc(v) -> str:
    return html.escape(str(v))


def _pos_word(entry) -> str:
    return _POS_WORD.get(entry.get("position"), "player")


def _num(entry, key, default=0.0) -> float:
    """A numeric field as a float, tolerating None and missing keys."""
    try:
        v = entry.get(key)
        return default if v is None else float(v)
    except (TypeError, ValueError):
        return default


def _a(v) -> str:
    """"a" or "an" in front of a rendered number — 8.10 and 11.21 are spoken
    "an eight" and "an eleven", and "a 8.10 ceiling" is the kind of thing that
    makes a page read like a mail merge."""
    intpart = str(v).lstrip("£").split(".")[0]
    return "an" if intpart.startswith("8") or intpart in ("11", "18") else "a"


def _and_join(items) -> str:
    """"ARS", "ARS and NFO", "ARS, NFO and LIV"."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _fpl_pct(v) -> str:
    """A 0-1 probability as a whole-number percentage."""
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(v)


def _fpl_is_top(entries, lead, key) -> bool:
    """Whether the subject really does hold the best value of `key` in the pool.

    Checked against the data rather than against rank order: the ranking column and
    the column the superlative is about are the same in every FPL article, but a
    superlative is a factual claim and it should be reading the numbers the table
    prints, not trusting a sort that happened upstream.
    """
    if not entries:
        return False
    return _num(lead, key) >= max(_num(x, key) for x in entries)


def _fpl_runner_up(entries, subj):
    """The best-ranked entry that is not the subject, or None if there is no other.

    Scans from the top rather than taking entries[1] because the subject is not
    always entries[0] — so this row is "the alternative", never "the next one down".
    """
    for x in entries:
        if x.get("name") != subj:
            return x
    return None


def _fpl_ceiling_clause(entry) -> str:
    """"a 10.26 ceiling — his 85th-percentile score across the simulations —".

    The closing dash is part of the clause: every caller continues the sentence
    afterwards, and an unclosed aside swallows whatever follows it.
    """
    c = _fmt_pts(entry.get("ceiling", 0))
    return (f"{_a(c)} {c} ceiling — his 85th-percentile score across the "
            f"simulations —")


# --- captains --------------------------------------------------------------

def _fpl_captains_headline(e, r, subj):
    return f"{subj} takes the armband in Gameweek {r}"


def _fpl_captains_standfirst(e, r, subj):
    lead = _subject_entry(e, subj)
    other = _fpl_runner_up(e, subj)
    ev = _fmt_pts(lead.get("captain_ev", 0))
    ceil = _fmt_pts(lead.get("ceiling", 0))
    verb = ("leads on captain EV at" if _fpl_is_top(e, lead, "captain_ev")
            else "is the armband call at")
    line = f"{subj} {verb} {ev}, with {_a(ceil)} {ceil} ceiling underneath it"
    if other is not None:
        return (line + f" and {other['name']} "
                f"({_fmt_pts(other.get('captain_ev', 0))}) the alternative.")
    return line + "."


def _fpl_captains_body(e, r, subj):
    lead = _subject_entry(e, subj)
    other = _fpl_runner_up(e, subj)
    name = _esc(subj)
    ceiling = _num(lead, "ceiling")
    price = _fmt_price(lead.get("price", 0))

    opening = (
        f"<p>{name} is the captain pick this gameweek: "
        f"{_fmt_pts(lead.get('captain_ev', 0))} captain EV, doubled off an xPts "
        f"projection of {_fmt_pts(lead.get('x_points', 0))}, with "
        f"{_fpl_ceiling_clause(lead)} which the armband turns into "
        f"{_fmt_pts(ceiling * 2)}. He is {_a(price)} £{price}m "
        f"{_esc(_pos_word(lead))}"
    )
    if lead.get("team"):
        opening += f" at {_esc(lead['team'])}"
    if lead.get("ownership_pct") is not None:
        opening += f", owned by {_fmt_own(lead['ownership_pct'])} of the game.</p>\n"
    else:
        opening += ".</p>\n"

    quote = ("<blockquote><p>The armband is the only decision you make twice — "
             "every other pick scores once, so a captain who is merely fine costs "
             "you the week silently.</p></blockquote>\n")

    if other is None:
        return opening + quote + (
            "<p>Nobody else in the pool is close enough to argue for, which makes "
            "the vice slot a formality rather than a decision.</p>"
        )

    o_ceil = _fmt_pts(other.get("ceiling", 0))
    tail = (
        f"<p>{_esc(other['name'])} is the alternative at "
        f"{_fmt_pts(other.get('captain_ev', 0))} captain EV and {_a(o_ceil)} "
        f"{o_ceil} ceiling"
    )
    lead_ko, other_ko = lead.get("kickoff_order"), other.get("kickoff_order")
    if lead_ko is not None and other_ko is not None and other_ko < lead_ko:
        tail += (f". He also kicks off first, which is what you want from a vice: "
                 f"if {name} is a late omission, the fallback score is already on "
                 f"the board rather than still to come.</p>")
    elif lead_ko is not None and other_ko is not None and other_ko > lead_ko:
        tail += (f". He kicks off after {name} though, so as a vice he leaves you "
                 f"waiting — the safety net only resolves late in the "
                 f"gameweek.</p>")
    else:
        tail += ".</p>"
    return opening + quote + tail


def _fpl_captains_bottom_line(e, r, subj):
    lead = _subject_entry(e, subj)
    other = _fpl_runner_up(e, subj)
    ev = _fmt_pts(lead.get("captain_ev", 0))
    best = " is the best on the board" if _fpl_is_top(e, lead, "captain_ev") else ""
    line = (f"Captain {subj} — {ev} EV{best}, and "
            f"{_fmt_pts(_num(lead, 'ceiling') * 2)} if the ceiling lands.")
    if other is not None:
        line += f" Vice it with {other['name']}."
    return line


# --- wildcard --------------------------------------------------------------

def _fpl_best_value(entries):
    """Highest xPts per million. Computed here rather than read off a `value` key:
    the squad rows come from fpl_squad, which does not carry one."""
    priced = [x for x in entries if _num(x, "price") > 0]
    if not priced:
        return None
    return max(priced, key=lambda x: _num(x, "x_points") / _num(x, "price"))


def _fpl_clubs_at_cap(entries, cap=3):
    counts = {}
    for x in entries:
        team = x.get("team")
        if team:
            counts[team] = counts.get(team, 0) + 1
    return sorted(t for t, n in counts.items() if n >= cap)


def _fpl_xi_phrase(entries):
    """"a 3-4-3 projecting 61.20 xPts" — falls back to a formation-free phrase when
    the XI is short, so a partial squad does not print "a 0-1-0"."""
    xi = _wc_xi(entries)
    pts = _fmt_pts(_wc_xi_xpoints(entries))
    if len(xi) == 11:
        return f"a {_wc_formation(entries)} projecting {pts} xPts"
    return f"an XI projecting {pts} xPts"


def _fpl_bank_phrase(entries) -> str:
    """"leaves £1.7m in the bank" — the over-budget branch cannot come out of
    fpl_squad, but a published "£-15.3m in the bank" is worse than a guard."""
    left = _wc_left_over(entries)
    if left < 0:
        return f"runs £{_fmt_price(-left)}m over it"
    return f"leaves £{_fmt_price(left)}m in the bank"


def _fpl_bank_short(entries) -> str:
    left = _wc_left_over(entries)
    if left < 0:
        return f"£{_fmt_price(-left)}m over budget"
    return f"£{_fmt_price(left)}m banked"


def _fpl_wildcard_headline(e, r, subj):
    return f"The Gameweek {r} wildcard draft"


def _fpl_wildcard_standfirst(e, r, subj):
    phrase = _fpl_xi_phrase(e)
    return (f"{phrase[:1].upper()}{phrase[1:]}, inside a squad costing "
            f"£{_fmt_price(_wc_total_cost(e))}m of the £100.0m budget.")


def _fpl_wildcard_body(e, r, subj):
    bench = _wc_bench(e)
    full = len(e) == 15
    shape = (" — two goalkeepers, five defenders, five midfielders, three forwards —"
             if full else "")
    out = (
        f"<p>The draft is {_fpl_xi_phrase(e)} from the starting eleven, wrapped in "
        f"a{' legal fifteen' if full else ' squad'}{shape} that spends "
        f"£{_fmt_price(_wc_total_cost(e))}m of the £100.0m budget and "
        f"{_fpl_bank_phrase(e)}.</p>\n"
    )
    out += ("<blockquote><p>The four bench places are budget, not squad depth: "
            "every pound parked there is a pound the eleven that actually scores "
            "never gets to spend.</p></blockquote>\n")
    if bench:
        out += (
            f"<p>Which is why the bench is the cheapest legal one available — "
            f"{_and_join(_esc(b['name']) for b in bench)}, "
            f"£{_fmt_price(sum(_num(b, 'price') for b in bench))}m between them. "
            f"They exist to make the fifteen legal, not to be picked.</p>\n"
        )
    capped = _fpl_clubs_at_cap(e)
    if capped:
        out += (
            f"<p>The rule that forces the compromises is three players per club. "
            f"{_and_join(_esc(c) for c in capped)} "
            f"{'is' if len(capped) == 1 else 'are'} already at the cap, so the next "
            f"upgrade from {'that club' if len(capped) == 1 else 'those clubs'} is "
            f"unavailable at any price and the budget has to find its points "
            f"somewhere else.</p>\n"
        )
    elif len(e) >= 11:
        out += ("<p>No club is at the three-player cap in this draft, which is "
                "rarer than it sounds — the cap is usually what stops a wildcard "
                "from simply buying the best side's entire defence.</p>\n")
    else:
        out += ("<p>Three players per club is the rule that forces most of the "
                "compromises in a wildcard: the best side's defence cannot all be "
                "bought, so the budget has to find its points somewhere "
                "else.</p>\n")
    best = _fpl_best_value(e)
    priciest = _wc_priciest(e, 3)
    if priciest and len(e) >= 11:
        out += (
            "<p>The money is concentrated in "
            + _and_join(f"{_esc(p['name'])} (£{_fmt_price(p.get('price', 0))}m)"
                        for p in priciest)
            + "."
        )
        if best is not None and best not in priciest:
            rate = _num(best, "x_points") / _num(best, "price", 1.0)
            out += (f" The pick doing the most per pound is {_esc(best['name'])}, "
                    f"{_fmt_pts(rate)} xPts per million at "
                    f"£{_fmt_price(best.get('price', 0))}m.")
        out += "</p>"
    return out


def _fpl_wildcard_bottom_line(e, r, subj):
    return (f"Field {_fpl_xi_phrase(e)}: £{_fmt_price(_wc_total_cost(e))}m spent, "
            f"{_fpl_bank_short(e)}, and a bench that does nothing but keep the "
            f"squad legal.")


# --- ticker ----------------------------------------------------------------

def _fpl_cs_phrase(entry) -> str:
    """Expected clean sheets in words. A single fixture reads naturally as a
    percentage; a double must not, because the figure SUMS across both games and a
    "120% chance of a clean sheet" is nonsense."""
    n = int(_num(entry, "fixtures"))
    cs = _num(entry, "exp_clean_sheets")
    if n == 0:
        return "no clean sheet to expect, because there is no fixture"
    if n == 1:
        pct = _fpl_pct(cs)
        return f"{_a(pct)} {pct} clean-sheet chance"
    return f"{_fmt_pts(cs)} expected clean sheets across {n} fixtures"


_BASIS_PHRASE = {
    "market": "priced off the betting market",
    "model": "from our own team ratings, not yet priced by the market",
    "mixed": "one fixture priced by the market, one from our own ratings",
}


def _fpl_basis_phrase(entry) -> str:
    return _BASIS_PHRASE.get(entry.get("basis"), "")


def _fpl_ticker_swings(entries) -> str:
    """The paragraph naming every club without a fixture and every club with two.
    Returns "" when the gameweek has neither — an empty paragraph saying nothing
    happened is worse than no paragraph."""
    blanks = [x for x in entries if int(_num(x, "fixtures")) == 0]
    doubles = [x for x in entries if int(_num(x, "fixtures")) > 1]
    if not blanks and not doubles:
        return ""
    parts = []
    if blanks:
        names = _and_join(_esc(x["name"]) for x in blanks)
        if len(blanks) == 1:
            parts.append(f"{names} do not play at all — a blank, and every player "
                         f"there scores nothing whatever else happens.")
        else:
            parts.append(f"{names} do not play at all — blanks, and every player at "
                         f"those clubs scores nothing whatever else happens.")
    if doubles:
        if len(doubles) == 1:
            d = doubles[0]
            parts.append(f"{_esc(d['name'])} play twice "
                         f"({_esc(d.get('opponents', ''))}) — a double, which is "
                         f"two shots at every points source rather than one.")
        else:
            parts.append(f"{_and_join(_esc(x['name']) for x in doubles)} all play "
                         f"twice — doubles, and two shots at every points source "
                         f"rather than one.")
    return "<p>" + " ".join(parts) + "</p>\n"


def _fpl_ticker_headline(e, r, subj):
    return f"{e[0]['name']} lead the Gameweek {r} ticker"


def _fpl_ticker_standfirst(e, r, subj):
    top = e[0]
    line = f"{top['name']} have {_fpl_cs_phrase(top)}"
    blanks = sum(1 for x in e if int(_num(x, "fixtures")) == 0)
    doubles = sum(1 for x in e if int(_num(x, "fixtures")) > 1)
    counts = []
    if blanks:
        counts.append(f"{blanks} blank{'s' if blanks > 1 else ''}")
    if doubles:
        counts.append(f"{doubles} double{'s' if doubles > 1 else ''}")
    if counts:
        return line + ", with " + " and ".join(counts) + " to plan around."
    return line + "."


def _fpl_ticker_body(e, r, subj):
    top = e[0]
    # The runner-up must actually have a fixture: a club that blanks can still sort
    # second on a short list, and "next best for a clean sheet" is meaningless for a
    # side that is not playing.
    other = next((x for x in e[1:] if int(_num(x, "fixtures")) > 0), None)
    basis = _fpl_basis_phrase(top)
    out = (
        f"<p>{_esc(top['name'])} head the ticker with {_fpl_cs_phrase(top)} against "
        f"{_esc(top.get('opponents', ''))}, conceding "
        f"{_fmt_pts(top.get('exp_goals_against', 0))} expected goals"
    )
    out += f" — {basis}.</p>\n" if basis else ".</p>\n"
    if other is not None:
        o_basis = _fpl_basis_phrase(other)
        out += (
            f"<p>{_esc(other['name'])} are the other side worth buying into: "
            f"{_fpl_cs_phrase(other)} against "
            f"{_esc(other.get('opponents', ''))}"
            + (f" — {o_basis}" if o_basis else "")
            + ".</p>\n"
        )
    out += _fpl_ticker_swings(e)
    blowouts = [x for x in e if x.get("env") == "blowout"]
    avoids = [x for x in e if x.get("env") == "avoid"]
    if blowouts:
        names = _and_join(_esc(b["name"]) for b in blowouts[:3])
        verb = ("are in the highest-scoring fixture on the board"
                if len(blowouts[:3]) == 1
                else "are in the highest-scoring fixtures on the board")
        out += (f"<blockquote><p>Goals go where the goals are: {names} {verb}, and "
                f"that is where an attacking punt is worth "
                f"taking.</p></blockquote>\n")
    else:
        out += ("<blockquote><p>No fixture on this board projects the goal total "
                "that makes chasing an attacker worthwhile — which makes the clean "
                "sheets, not the punts, where the edge is this "
                "gameweek.</p></blockquote>\n")
    if avoids:
        names = _and_join(_esc(a["name"]) for a in avoids[:3])
        out += (f"<p>Fade forwards at {names} — the model has "
                f"{'that game' if len(avoids[:3]) == 1 else 'those games'} "
                f"low-scoring at both ends.</p>")
    return out


def _fpl_ticker_bottom_line(e, r, subj):
    top = e[0]
    line = f"Buy the {top['name']} defence — {_fpl_cs_phrase(top)} is the best on offer"
    basis = _fpl_basis_phrase(top)
    line += f", {basis}." if basis else "."
    blanks = [x["name"] for x in e if int(_num(x, "fixtures")) == 0]
    doubles = [x["name"] for x in e if int(_num(x, "fixtures")) > 1]
    if blanks:
        line += f" Check your squad for {_and_join(blanks)} before the deadline."
    if doubles:
        line += f" {_and_join(doubles)} play twice."
    return line


# --- defenders -------------------------------------------------------------

def _fpl_defenders_headline(e, r, subj):
    return f"{subj} is the defence to own in Gameweek {r}"


def _fpl_defenders_standfirst(e, r, subj):
    lead = _subject_entry(e, subj)
    ceil = _fmt_pts(lead.get("ceiling", 0))
    return (f"{subj} projects {_fmt_pts(lead.get('x_points', 0))} xPts with "
            f"{_a(ceil)} {ceil} ceiling, {_fmt_pts(lead.get('cs_points', 0))} of it "
            f"from clean sheets.")


def _fpl_defenders_body(e, r, subj):
    lead = _subject_entry(e, subj)
    name = _esc(subj)
    xp = _num(lead, "x_points")
    cs, dc, bon = (_num(lead, "cs_points"), _num(lead, "defcon"),
                   _num(lead, "bonus"))
    rest = xp - cs - dc - bon
    is_gk = lead.get("position") == "GK"
    verb = ("tops the defensive board at" if _fpl_is_top(e, lead, "x_points")
            else "is the defensive pick at")

    out = (
        f"<p>{name} {verb} {_fmt_pts(xp)} xPts and {_fpl_ceiling_clause(lead)} for "
        f"£{_fmt_price(lead.get('price', 0))}m"
    )
    out += f" at {_esc(lead['team'])}.</p>\n" if lead.get("team") else ".</p>\n"

    split = [f"{_fmt_pts(cs)} from clean sheets"]
    if is_gk:
        split.append("nothing from defensive contributions, which goalkeepers are "
                     "not eligible for")
    elif dc:
        split.append(f"{_fmt_pts(dc)} from defensive contributions")
    if bon:
        split.append(f"{_fmt_pts(bon)} from bonus")
    tail = (f", and the remaining {_fmt_pts(rest)} from appearances and attacking "
            f"returns" if rest > 0.05 else "")
    out += (f"<p>Where those points come from matters as much as the total: "
            f"{', '.join(split)}{tail}.</p>\n")

    out += ("<blockquote><p>A clean sheet is one fixture's worth of luck — one "
            "deflection and the whole line is worth nothing. Defensive "
            "contributions pay whatever the scoreline does, which is why a "
            "projection built on them is the steadier one.</p></blockquote>\n")

    other = _fpl_runner_up(e, subj)
    if other is not None:
        out += (
            f"<p>{_esc(other['name'])} is the alternative at "
            f"{_fmt_pts(other.get('x_points', 0))} xPts for "
            f"£{_fmt_price(other.get('price', 0))}m, "
            f"{_fmt_pts(other.get('cs_points', 0))} of it from clean sheets"
            + (" — and as a goalkeeper he earns no defensive contributions at all."
               if other.get("position") == "GK" else ".")
            + "</p>"
        )
    return out


def _fpl_defenders_bottom_line(e, r, subj):
    lead = _subject_entry(e, subj)
    return (f"Start {subj} — {_fmt_pts(lead.get('x_points', 0))} xPts at "
            f"£{_fmt_price(lead.get('price', 0))}m, of which "
            f"{_fmt_pts(lead.get('cs_points', 0))} rides on the clean sheet and the "
            f"rest arrives whatever the score.")


# --- efficiency ------------------------------------------------------------

def _fpl_efficiency_headline(e, r, subj):
    return f"{subj} is the best value in Gameweek {r}"


def _fpl_efficiency_standfirst(e, r, subj):
    lead = _subject_entry(e, subj)
    return (f"{subj} returns {_fmt_pts(lead.get('value', 0))} xPts per million — "
            f"{_fmt_pts(lead.get('x_points', 0))} xPts at "
            f"£{_fmt_price(lead.get('price', 0))}m.")


def _fpl_efficiency_body(e, r, subj):
    lead = _subject_entry(e, subj)
    who = _esc(subj)
    if lead.get("position"):
        who += f", a {_esc(_pos_word(lead))}"
        if lead.get("team"):
            who += f" at {_esc(lead['team'])}"
        who += ","
    verb = ("is the most efficient pick in the pool at" if _fpl_is_top(e, lead, "value")
            else "returns")
    out = (
        f"<p>{who} {verb} {_fmt_pts(lead.get('value', 0))} xPts per million: "
        f"{_fmt_pts(lead.get('x_points', 0))} xPts with "
        f"{_fpl_ceiling_clause(lead)} from a "
        f"£{_fmt_price(lead.get('price', 0))}m price tag.</p>\n"
    )
    out += ("<blockquote><p>The budget is the whole game. FPL hands every manager "
            "the same £100.0m, so points per million is not a bargain-hunter's "
            "metric — it is what decides which players the rest of the squad can "
            "afford.</p></blockquote>\n")
    tiers = _wc_efficiency_tier_paragraph(e)
    if tiers:
        out += tiers + "\n"
    other = _fpl_runner_up(e, subj)
    if other is not None:
        out += (f"<p>{_esc(other['name'])} is the other name on the list to weigh, "
                f"at {_fmt_pts(other.get('value', 0))} xPts per million for "
                f"£{_fmt_price(other.get('price', 0))}m.</p>")
    return out


def _fpl_efficiency_bottom_line(e, r, subj):
    lead = _subject_entry(e, subj)
    best = (" is the best rate in the game" if _fpl_is_top(e, lead, "value")
            else " funds the rest of the squad")
    return (f"Buy {subj} first — {_fmt_pts(lead.get('value', 0))} xPts per "
            f"million{best}." + _wc_efficiency_tier_bottom_line(e))


# --- defcon ----------------------------------------------------------------

# --- runs (the six-gameweek fixture grid) ----------------------------------

def _fpl_run_window(entries) -> int:
    """How many gameweeks the grid covers. Read off the data rather than assumed:
    a window late in the season is simply shorter (see core.fpl_horizon.window)."""
    for x in entries:
        gws = x.get("gameweeks") or []
        if gws:
            return len(gws)
    return 0


def _fpl_run_phrase(entry) -> str:
    """A club's run as a reader reads it: "COV (H), AVL (A), CHE (H)". Blanks and
    doubles are spelled out in words rather than left as grid glyphs -- an em dash
    is legible in a coloured cell and invisible in a sentence."""
    parts = []
    for cell in entry.get("cells", []):
        if cell.get("blank"):
            parts.append("blank")
        elif cell.get("double"):
            parts.append(f"{cell.get('label', '')} (double)")
        else:
            parts.append(cell.get("label", ""))
    return _esc(", ".join(p for p in parts if p))


def _fpl_run_split(entry) -> tuple:
    """(first gameweek's FDR, mean FDR of the rest) -- or (None, None) when either
    half has no rated fixture. This is the pair the divergence test compares."""
    cells = entry.get("cells", [])
    if len(cells) < 2:
        return None, None
    first = cells[0].get("difficulty")
    rest = [c["difficulty"] for c in cells[1:] if c.get("difficulty") is not None]
    if first is None or not rest:
        return None, None
    return float(first), sum(rest) / len(rest)


# How far the rest of a run has to sit from the opening fixture before the two
# count as telling different stories. One full FDR band: Arsenal open at COV (2)
# and average 3.2 across the following five, a 1.2 gap, which is exactly the
# case this article exists to catch.
_RUN_DIVERGENCE_GAP = 1.0


def _fpl_run_divergences(entries) -> list:
    """Clubs whose opening fixture and whose run disagree, widest gap first.

    Returned as (entry, first_fdr, rest_mean, "trap"|"opportunity"). A "trap"
    opens easy and gets harder -- the single most expensive mistake a
    one-gameweek ticker can walk a manager into, because one free transfer a week
    means the squad they buy on Saturday is largely the squad they still hold in
    five weeks' time. An "opportunity" is the mirror: a club that looks
    unbuyable this week and is the best run on the board once the opener is past.
    """
    out = []
    for x in entries:
        first, rest = _fpl_run_split(x)
        if first is None:
            continue
        gap = rest - first
        if gap >= _RUN_DIVERGENCE_GAP:
            out.append((x, first, rest, "trap"))
        elif -gap >= _RUN_DIVERGENCE_GAP:
            out.append((x, first, rest, "opportunity"))
    # Traps first, then opportunities, each widest gap first. The ordering is an
    # editorial judgement, not a numeric one: a trap is a mistake the
    # one-gameweek ticker actively walks a manager into and costs a transfer to
    # undo, while an opportunity is at worst a week of patience. So the widest
    # trap leads the article even when an opportunity has the larger gap.
    out.sort(key=lambda t: (t[3] != "trap", -abs(t[2] - t[1])))
    return out


_NUM_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def _num_word(n: int) -> str:
    """Small counts spelled out. "the kindest six" is prose; "the kindest 6" is a
    mail merge."""
    return _NUM_WORD.get(int(n), str(n))


def _fpl_run_basis_note(entries) -> str:
    """The provenance sentence. Over a six-week window the honest answer is almost
    always "model": the betting market does not price a fixture five weeks out, so
    only the opening gameweek can ever be market-derived, and today not even that
    is priced. Saying so is the point of the site."""
    bases = {x.get("basis") for x in entries}
    if bases <= {"model", "—"}:
        return ("Every number on this grid comes from our own team ratings, not "
                "from the betting market — nothing in this window is priced yet. "
                "Treat the near gameweeks as firmer than the far ones: team news, "
                "form and injuries all move before week six arrives.")
    if "market" in bases and len(bases - {"—"}) > 1:
        return ("The opening gameweek is priced by the betting market; everything "
                "beyond it comes from our own team ratings. The far end of this "
                "window is a plan, not a price.")
    return ("These fixtures are priced by the betting market, which reaches a "
            "week or two out at most — the far end of the window leans on our "
            "own team ratings.")


def _fpl_runs_playing(entries) -> list:
    """Clubs with at least one fixture in the window. A side that blanks
    throughout still belongs on the grid and does not belong in a sentence about
    the best or worst run."""
    return [x for x in entries if int(_num(x, "fixtures")) > 0]


def _fpl_runs_headline(e, r, subj):
    playing = _fpl_runs_playing(e)
    lead = playing[0] if playing else e[0]
    n = _fpl_run_window(e)
    return f"{lead['name']} own the best {_num_word(n)} gameweeks from here"


def _fpl_runs_standfirst(e, r, subj):
    playing = _fpl_runs_playing(e)
    if not playing:
        return "No club has a fixture in this planning window."
    lead, tail = playing[0], playing[-1]
    n = _fpl_run_window(e)
    line = (f"{lead['name']} project {_fmt_pts(lead.get('exp_clean_sheets', 0))} "
            f"clean sheets across the next {_num_word(n)} gameweeks; "
            f"{tail['name']} project "
            f"{_fmt_pts(tail.get('exp_clean_sheets', 0))}")
    div = _fpl_run_divergences(e)
    if div:
        x, _first, _rest, kind = div[0]
        tail_clause = (f"{x['name']}'s opener flatters their run" if kind == "trap"
                       else f"{x['name']}'s opener libels their run")
        return f"{line} — and {tail_clause}."
    return line + "."


def _fpl_runs_body(e, r, subj):
    playing = _fpl_runs_playing(e)
    if not playing:
        return ("<p>No club in the league has a fixture inside this planning "
                "window, so there is no run to buy into.</p>")
    n = _fpl_run_window(e)
    lead, tail = playing[0], playing[-1]

    out = (
        f"<p>One free transfer a gameweek — bankable to five, and any extra "
        f"costs four points — means the squad you buy this week is mostly the "
        f"squad you still own {_num_word(n)} gameweeks from now. So the question "
        f"is not who plays the kindest fixture on Saturday; it is who plays the "
        f"kindest {_num_word(n)}. {_esc(lead['name'])} answer it: "
        f"{_fpl_run_phrase(lead)}, worth "
        f"{_fmt_pts(lead.get('exp_clean_sheets', 0))} expected clean sheets "
        f"across the window.</p>\n"
    )

    out += (
        f"<p>The other end of the grid is {_esc(tail['name'])}: "
        f"{_fpl_run_phrase(tail)}, and "
        f"{_fmt_pts(tail.get('exp_clean_sheets', 0))} expected clean sheets to "
        f"show for it. That is the floor and the ceiling of this window in one "
        f"breath — same number of gameweeks, "
        f"{_fmt_pts(_num(lead, 'exp_clean_sheets') - _num(tail, 'exp_clean_sheets'))} "
        f"clean sheets between them.</p>\n"
    )

    div = _fpl_run_divergences(e)
    if div:
        x, first, rest, kind = div[0]
        behind = _num_word(len(x.get("cells", [])) - 1)
        if kind == "trap" and x is lead:
            # The awkward case, and the one this article was built for: the club
            # with the best run is ALSO the club whose opener is doing the most
            # work. Saying "avoid them" would be false -- they top the window on
            # the numbers -- so the honest line is that the ranking survives the
            # longer view and the MARGIN does not. Both halves are computed from
            # this article's own rows, never from the one-gameweek ticker.
            out += (
                f"<blockquote><p>{_esc(x['name'])} are the awkward case. They top "
                f"this grid on the aggregate — and their opener rates {first:.0f} "
                f"on the difficulty scale while the {behind} fixtures behind it "
                f"average {rest:.1f}. One kind Saturday, then an ordinary "
                f"month.</p></blockquote>\n"
            )
            runner = playing[1] if len(playing) > 1 else None
            if runner is not None and _num(runner, "exp_clean_sheets") > 0:
                margin = (_num(lead, "exp_clean_sheets")
                          / _num(runner, "exp_clean_sheets") - 1) * 100
                out += (
                    f"<p>{_esc(x['name'])} run {_fpl_run_phrase(x)}. Across the "
                    f"window they lead {_esc(runner['name'])} by {margin:.0f}% on "
                    f"expected clean sheets — a real lead, and a thin one. A "
                    f"ticker that stops at Saturday prices that opening fixture "
                    f"as though it repeats {_num_word(n)} times; the row above "
                    f"says it does not.</p>\n"
                )
            else:
                out += (f"<p>{_esc(x['name'])} run {_fpl_run_phrase(x)}. A ticker "
                        f"that stops at Saturday prices the opener as though it "
                        f"repeats {_num_word(n)} times; the row above says it "
                        f"does not.</p>\n")
        elif kind == "trap":
            out += (
                f"<blockquote><p>{_esc(x['name'])} are the trap. Their opener "
                f"rates {first:.0f} on the difficulty scale and the {behind} "
                f"fixtures behind it average {rest:.1f} — a one-week pop, bought "
                f"with a transfer you will still be living with when the run "
                f"turns.</p></blockquote>\n"
            )
            out += (
                f"<p>{_esc(x['name'])} run {_fpl_run_phrase(x)}. A ticker that "
                f"stops at Saturday ranks them near the top of the board; the "
                f"grid above says the fixture doing that work does not come "
                f"back.</p>\n"
            )
        else:
            out += (
                f"<blockquote><p>{_esc(x['name'])} are the inverse. Their opener "
                f"rates {first:.0f} and the {behind} behind it average "
                f"{rest:.1f} — a side a one-gameweek ticker tells you to avoid, "
                f"and a run worth waiting one week to buy.</p></blockquote>\n"
            )
            out += (
                f"<p>{_esc(x['name'])} run {_fpl_run_phrase(x)}. A ticker that "
                f"stops at Saturday buries them; the grid above says the hard "
                f"fixture is the one that does not come back.</p>\n"
            )
        if len(div) > 1:
            others = _and_join(_esc(o[0]["name"]) for o in div[1:4])
            out += (f"<p>{others} split the same way — near fixture and run "
                    f"pointing in opposite directions. Check the row, not the "
                    f"first cell.</p>\n")
    else:
        out += ("<blockquote><p>No club on this grid opens meaningfully out of "
                "step with its own run, which is the rare week when a "
                "one-gameweek ticker and a six-week one give the same "
                "answer.</p></blockquote>\n")

    blanks = [x for x in e if any(c.get("blank") for c in x.get("cells", []))]
    doubles = [x for x in e if any(c.get("double") for c in x.get("cells", []))]
    swings = []
    if blanks:
        swings.append(f"{_and_join(_esc(x['name']) for x in blanks[:6])} "
                      f"{'has' if len(blanks) == 1 else 'have'} a blank inside "
                      f"the window — a gameweek those players score nothing at "
                      f"all")
    if doubles:
        swings.append(f"{_and_join(_esc(x['name']) for x in doubles[:6])} "
                      f"{'has' if len(doubles) == 1 else 'have'} a double — two "
                      f"shots at every points source in one week")
    if swings:
        out += "<p>" + "; ".join(swings) + ".</p>\n"
    else:
        out += ("<p>No blank and no double falls inside this window, so every "
                "club on the grid plays exactly once a week — the runs are the "
                "whole story.</p>\n")

    out += f"<p>{_fpl_run_basis_note(e)}</p>"
    return out


def _fpl_runs_bottom_line(e, r, subj):
    playing = _fpl_runs_playing(e)
    if not playing:
        return "There is no fixture in this window to plan around."
    lead = playing[0]
    n = _fpl_run_window(e)
    div = _fpl_run_divergences(e)
    trap = next((d for d in div if d[3] == "trap"), None)
    base = (f"Buy into {lead['name']} — "
            f"{_fmt_pts(lead.get('exp_clean_sheets', 0))} expected clean sheets "
            f"over {_num_word(n)} gameweeks is the run worth spending a transfer "
            f"on")
    if trap and trap[0] is lead:
        # "Buy them, but not for the reason the one-week ticker gives you" --
        # never "avoid them", which their own aggregate contradicts.
        return (base + f", but buy it for the whole run and not the opener: the "
                f"{_num_word(len(lead.get('cells', [])) - 1)} fixtures behind it "
                f"average {trap[2]:.1f} on difficulty.")
    if trap:
        return (base + f", and do not pay for {trap[0]['name']}'s opening fixture "
                f"when the {_num_word(len(trap[0].get('cells', [])) - 1)} behind "
                f"it average {trap[2]:.1f}.")
    return base + ", not a single kind fixture."


def _fpl_defcon_bar(entry) -> str:
    """The threshold in the units the position actually counts."""
    t = int(_num(entry, "defcon_threshold"))
    if entry.get("position") == "DEF":
        return f"{t} clearances, blocks, interceptions and tackles"
    return f"{t} defensive actions"


def _fpl_defcon_short_bar(entry) -> str:
    return f"{int(_num(entry, 'defcon_threshold'))}-action bar"


def _fpl_defcon_headline(e, r, subj):
    return f"{subj} is the surest DefCon bet in Gameweek {r}"


def _fpl_defcon_standfirst(e, r, subj):
    lead = _subject_entry(e, subj)
    return (f"{subj} records {_fpl_defcon_bar(lead)} in "
            f"{_fpl_pct(lead.get('p_defcon', 0))} of simulations — "
            f"{_fmt_pts(lead.get('defcon', 0))} points before anything else "
            f"happens.")


def _fpl_defcon_body(e, r, subj):
    lead = _subject_entry(e, subj)
    name = _esc(subj)
    out = (
        f"<p>{name} hits the defensive-contribution threshold — "
        f"{_fpl_defcon_bar(lead)} for a {_esc(_pos_word(lead))} — in "
        f"{_fpl_pct(lead.get('p_defcon', 0))} of simulations. That is "
        f"{_fmt_pts(lead.get('defcon', 0))} points of the "
        f"{_fmt_pts(lead.get('x_points', 0))} xPts he projects at "
        f"£{_fmt_price(lead.get('price', 0))}m"
    )
    out += (f", playing for {_esc(lead['team'])}.</p>\n" if lead.get("team")
            else ".</p>\n")

    out += ("<blockquote><p>DefCon is a threshold, not a rate. A player either "
            "clears the count in a given match or he banks nothing for the actions "
            "he did make — which is why the number that matters is how often he "
            "gets over the line, not how busy he looks.</p></blockquote>\n")

    other = _fpl_runner_up(e, subj)
    if other is None:
        out += (f"<p>There is no second name on the board this gameweek, so the "
                f"defensive-contribution call comes down to {name} or "
                f"nothing.</p>")
        return out

    o_name = _esc(other["name"])
    o_pct = _fpl_pct(other.get("p_defcon", 0))
    if int(_num(other, "defcon_threshold")) != int(_num(lead, "defcon_threshold")):
        out += (
            f"<p>{o_name} clears his own bar in {o_pct} of simulations — a "
            f"different bar, {_fpl_defcon_bar(other)} for a "
            f"{_esc(_pos_word(other))}. The two are not competing for the same "
            f"slot, so a squad can carry both.</p>"
        )
    else:
        gap = abs(_num(lead, "p_defcon") - _num(other, "p_defcon")) * 100
        out += (
            f"<p>{o_name} clears the same {_fpl_defcon_short_bar(other)} in "
            f"{o_pct} of simulations, which makes it a straight comparison — and a "
            f"{gap:.0f}-point gap in how often the bonus actually arrives.</p>"
        )
    return out


def _fpl_defcon_bottom_line(e, r, subj):
    lead = _subject_entry(e, subj)
    best = (" is the most reliable defensive-contribution source on the board, and "
            "it pays" if _fpl_is_top(e, lead, "p_defcon")
            else " pays")
    return (f"Own {subj} — clearing the {_fpl_defcon_short_bar(lead)} in "
            f"{_fpl_pct(lead.get('p_defcon', 0))} of simulations{best} whether or "
            f"not the clean sheet holds.")


_FPL_TEMPLATES = {
    "captains": {
        "headline": _fpl_captains_headline,
        "standfirst": _fpl_captains_standfirst,
        "body": _fpl_captains_body,
        "bottom_line": _fpl_captains_bottom_line,
    },
    "wildcard": {
        "headline": _fpl_wildcard_headline,
        "standfirst": _fpl_wildcard_standfirst,
        "body": _fpl_wildcard_body,
        "bottom_line": _fpl_wildcard_bottom_line,
    },
    "ticker": {
        "headline": _fpl_ticker_headline,
        "standfirst": _fpl_ticker_standfirst,
        "body": _fpl_ticker_body,
        "bottom_line": _fpl_ticker_bottom_line,
    },
    "runs": {
        "headline": _fpl_runs_headline,
        "standfirst": _fpl_runs_standfirst,
        "body": _fpl_runs_body,
        "bottom_line": _fpl_runs_bottom_line,
    },
    "defenders": {
        "headline": _fpl_defenders_headline,
        "standfirst": _fpl_defenders_standfirst,
        "body": _fpl_defenders_body,
        "bottom_line": _fpl_defenders_bottom_line,
    },
    "efficiency": {
        "headline": _fpl_efficiency_headline,
        "standfirst": _fpl_efficiency_standfirst,
        "body": _fpl_efficiency_body,
        "bottom_line": _fpl_efficiency_bottom_line,
    },
    "defcon": {
        "headline": _fpl_defcon_headline,
        "standfirst": _fpl_defcon_standfirst,
        "body": _fpl_defcon_body,
        "bottom_line": _fpl_defcon_bottom_line,
    },
}


_GENERIC_TEMPLATE = {
    "headline": lambda e, r, slug, subj, unit="Round": (
        f"{unit} analysis: {slug.replace('-', ' ').title()}"
    ),
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
    unit:    "Round" (World Cup) or "Gameweek" (FPL). It selects the template table
             as well as the reader-facing wording: four FPL slugs share a name with
             a World Cup slug, so they cannot live in the same dict.
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

    # For best-xi, wildcard, matches, fixtures and ticker (no player subject), skip
    # per-player framing — ticker's rows are clubs, so entries[0]["name"] would put
    # a three-letter club abbreviation where a player's name belongs.
    if subject is not None:
        subj = subject
    elif article in ("best-xi", "wildcard", "matches", "fixtures", "ticker",
                     "runs"):
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
               cache_dir: str, subject=None, cache_name=None, unit: str = "Round"):
    """Call the Claude API and return prose dict, or None if we should fall through."""
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
    # A 0-1 probability is asked for IN PROSE as a percentage (the FPL glossary
    # says to write p_defcon as "71%"), so its correct rendering is the stored
    # value x100 and never matches the stored value itself. Admit that form
    # explicitly. Without it this guard rejects accurate output and silently
    # disables the whole LLM tier for FPL -- which is exactly what it did until
    # 2026-08-04: every FPL article fell through to the template tier because the
    # model wrote "60.2%" for a p_defcon of 0.602.
    #
    # World Cup entries never hit this because ownership_pct and p_advance are
    # already stored on a 0-100 scale, so a percentage in prose matched directly.
    #
    # The widening is deliberately bounded, and the bound is narrower than it first
    # looks. Only STRICTLY FRACTIONAL values in (0, 1) get a percentage twin:
    # `rank: 1` is in [0, 1] but is not a probability, and admitting its twin of
    # 100 would accept a fabricated "99.99" — which is exactly what the first
    # version of this widening did, caught by
    # tests/test_site_writer.test_llm_fabricated_number_falls_to_template.
    # A probability of exactly 0 or 1 renders as the bare integer "0%"/"100%",
    # and bare integers already pass freely, so excluding them costs nothing.
    real_values += [rv * 100 for rv in real_values
                    if 0.0 < rv < 1.0 and rv != int(rv)]
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
    cache_name=None,
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
    # Tier 1: cache
    cache_path = os.path.join(cache_dir, cache_name or f"round-{round_no}",
                              f"{article}.md")
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
