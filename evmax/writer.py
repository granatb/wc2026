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
    body_lines: list[str] = []

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


def _fmt_ev(v) -> str:
    """Format captain_ev (shown in body text) to 1 decimal."""
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Template tier: deterministic per-article prose.
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "captains": {
        "headline": lambda e: f"{e[0]['name']} leads the armband race in Round {e[0].get('round_no', '')}",
        "standfirst": lambda e: (
            f"{e[0]['name']} tops captain EV at {_fmt_ev(e[0]['captain_ev'])} pts"
            + (f", ahead of {e[1]['name']} ({_fmt_ev(e[1]['captain_ev'])})." if len(e) > 1 else ".")
        ),
        "body": lambda e: (
            f"<p>{html.escape(e[0]['name'])} is the standout captain option this round, "
            f"posting a captain EV of {_fmt_pts(e[0]['captain_ev'])} pts and an xPts of "
            f"{_fmt_pts(e[0]['x_points'])}. "
            + (f"{html.escape(e[1]['name'])} is a credible alternative at "
               f"{_fmt_pts(e[1]['captain_ev'])} EV." if len(e) > 1 else "")
            + "</p>\n"
            + (f"<blockquote><p>{html.escape(e[0]['name'])}'s ownership sits at "
               f"{_fmt_own(e[0]['ownership_pct'])}, making them a high-upside, "
               f"manageable captaincy.</p></blockquote>\n" if e[0].get('ownership_pct') is not None else "")
            + f"<p>With a ceiling of {_fmt_pts(e[0]['ceiling'])}, the upside justifies "
            f"the pick. Priced at £{_fmt_price(e[0]['price'])}m, {html.escape(e[0]['name'])} "
            f"offers value at {_fmt_pts(e[0].get('value', 0))} xPts/£.</p>"
        ),
        "bottom_line": lambda e: (
            f"Back {e[0]['name']} — {_fmt_pts(e[0]['captain_ev'])} captain EV is the best "
            f"available this round."
        ),
    },
    "best-xi": {
        "headline": lambda e: f"The optimal Fantasy XI for Round {e[0].get('round_no', '')}",
        "standfirst": lambda e: (
            f"{e[0]['name']} leads the best XI at {_fmt_pts(e[0]['x_points'])} xPts."
        ),
        "body": lambda e: (
            f"<p>The highest-expected-points XI this round is anchored by "
            f"{html.escape(e[0]['name'])} ({_fmt_pts(e[0]['x_points'])} xPts, "
            f"£{_fmt_price(e[0]['price'])}m)"
            + (f" and {html.escape(e[1]['name'])} ({_fmt_pts(e[1]['x_points'])} xPts)."
               if len(e) > 1 else ".")
            + "</p>\n"
            + (f"<blockquote><p>{html.escape(e[0]['name'])}'s ceiling of "
               f"{_fmt_pts(e[0]['ceiling'])} makes them the must-have pick.</p></blockquote>"
               if e[0].get('ceiling') is not None else "")
        ),
        "bottom_line": lambda e: (
            f"Start {e[0]['name']} — the {_fmt_pts(e[0]['x_points'])} xPts projection "
            f"is the highest in the XI."
        ),
    },
    "differentials": {
        "headline": lambda e: f"Differential gems: low-owned, high-upside picks for Round {e[0].get('round_no', '')}",
        "standfirst": lambda e: (
            f"{e[0]['name']} tops the differential list at {_fmt_own(e[0]['ownership_pct'])} ownership "
            f"and {_fmt_pts(e[0]['x_points'])} xPts."
        ),
        "body": lambda e: (
            f"<p>{html.escape(e[0]['name'])} is the standout differential this round — "
            f"owned by just {_fmt_own(e[0]['ownership_pct'])} of managers while projecting "
            f"{_fmt_pts(e[0]['x_points'])} xPts"
            + (f" ahead of {html.escape(e[1]['name'])} ({_fmt_own(e[1]['ownership_pct'])}, "
               f"{_fmt_pts(e[1]['x_points'])} xPts)." if len(e) > 1 else ".")
            + "</p>\n"
            + f"<blockquote><p>The biggest rank-gain opportunity comes from punting on "
            f"{html.escape(e[0]['name'])} while the field ignores them.</p></blockquote>"
        ),
        "bottom_line": lambda e: (
            f"{e[0]['name']} at {_fmt_own(e[0]['ownership_pct'])} ownership is the best "
            f"way to differentiate your team this round."
        ),
    },
    "efficiency": {
        "headline": lambda e: f"Best value picks: EV per £ this round",
        "standfirst": lambda e: (
            f"{e[0]['name']} leads on value at {_fmt_pts(e[0].get('value', 0))} xPts/£."
        ),
        "body": lambda e: (
            f"<p>{html.escape(e[0]['name'])} tops the efficiency table at "
            f"{_fmt_pts(e[0].get('value', 0))} xPts/£ — "
            f"{_fmt_pts(e[0]['x_points'])} xPts from a £{_fmt_price(e[0]['price'])}m price tag"
            + (f", beating {html.escape(e[1]['name'])} ({_fmt_pts(e[1].get('value', 0))} xPts/£)."
               if len(e) > 1 else ".")
            + "</p>\n"
            + f"<blockquote><p>Value picks compound over a tournament — "
            f"a 0.1 xPts/£ edge across 11 players adds up fast.</p></blockquote>"
        ),
        "bottom_line": lambda e: (
            f"Prioritise {e[0]['name']} — {_fmt_pts(e[0].get('value', 0))} xPts/£ is the best "
            f"efficiency in the pool."
        ),
    },
    "high-ceiling-xi": {
        "headline": lambda e: f"High-ceiling XI: chase the big haul this round",
        "standfirst": lambda e: (
            f"{e[0]['name']} leads ceiling at {_fmt_pts(e[0]['ceiling'])} pts."
        ),
        "body": lambda e: (
            f"<p>For managers chasing a big week, {html.escape(e[0]['name'])} offers the "
            f"highest ceiling at {_fmt_pts(e[0]['ceiling'])} pts while projecting "
            f"{_fmt_pts(e[0]['x_points'])} xPts"
            + (f". {html.escape(e[1]['name'])} follows with a {_fmt_pts(e[1]['ceiling'])} ceiling."
               if len(e) > 1 else ".")
            + "</p>\n"
            + f"<blockquote><p>The high-ceiling XI is built for rank-jumps — "
            f"accept the variance, target the upside.</p></blockquote>"
        ),
        "bottom_line": lambda e: (
            f"Back {e[0]['name']} for ceiling — {_fmt_pts(e[0]['ceiling'])} best-case "
            f"is the round's highest projection."
        ),
    },
    "blowout-transfers": {
        "headline": lambda e: f"Blowout fixture targets: attackers to buy now",
        "standfirst": lambda e: (
            f"{e[0]['name']} is the top transfer target at {_fmt_pts(e[0]['x_points'])} xPts "
            f"from a blowout fixture."
        ),
        "body": lambda e: (
            f"<p>With the blowout fixture incoming, {html.escape(e[0]['name'])} "
            f"({_fmt_pts(e[0]['x_points'])} xPts, £{_fmt_price(e[0]['price'])}m) is the "
            f"priority transfer"
            + (f" alongside {html.escape(e[1]['name'])} ({_fmt_pts(e[1]['x_points'])} xPts)."
               if len(e) > 1 else ".")
            + "</p>\n"
            + f"<blockquote><p>Fixtures drive points at a World Cup — "
            f"get the best attackers from the biggest mismatches.</p></blockquote>"
        ),
        "bottom_line": lambda e: (
            f"Bring in {e[0]['name']} before the deadline — "
            f"{_fmt_pts(e[0]['x_points'])} xPts from the blowout fixture."
        ),
    },
}

_GENERIC_TEMPLATE = {
    "headline": lambda e, slug: f"Round analysis: {slug.replace('-', ' ').title()}",
    "standfirst": lambda e: (
        f"{e[0]['name']} leads with {_fmt_pts(e[0]['x_points'])} xPts."
    ),
    "body": lambda e: (
        f"<p>{html.escape(e[0]['name'])} tops this list with {_fmt_pts(e[0]['x_points'])} xPts "
        f"and a captain EV of {_fmt_pts(e[0]['captain_ev'])}"
        + (f". {html.escape(e[1]['name'])} is close behind at {_fmt_pts(e[1]['x_points'])} xPts."
           if len(e) > 1 else ".")
        + "</p>"
    ),
    "bottom_line": lambda e: (
        f"Target {e[0]['name']} — {_fmt_pts(e[0]['x_points'])} xPts is the best projection available."
    ),
}


def _template_prose(article: str, entries: list, columns: list) -> dict:
    """Build deterministic template prose from entries."""
    if not entries:
        return {
            "headline": f"Round analysis: {article}",
            "standfirst": "No data available.",
            "body_html": "<p>No entries available for this article.</p>",
            "bottom_line": "Check back when data is available.",
            "source": "template",
        }

    tmpl = _TEMPLATES.get(article)
    if tmpl:
        headline = tmpl["headline"](entries)
        standfirst = tmpl["standfirst"](entries)
        body_html = tmpl["body"](entries)
        bottom_line = tmpl["bottom_line"](entries)
    else:
        headline = _GENERIC_TEMPLATE["headline"](entries, article)
        standfirst = _GENERIC_TEMPLATE["standfirst"](entries)
        body_html = _GENERIC_TEMPLATE["body"](entries)
        bottom_line = _GENERIC_TEMPLATE["bottom_line"](entries)

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
               cache_dir: str):
    """Call the Claude API and return prose dict, or None if we should fall through."""
    if not _ANTHROPIC_AVAILABLE:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    from evmax.prompts import build_prompt

    prompt = build_prompt(article, round_no, entries)

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

    # Parse JSON response
    try:
        # Strip markdown code fences if present
        json_text = re.sub(r"^```(?:json)?\s*", "", raw)
        json_text = re.sub(r"\s*```$", "", json_text)
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return None

    required_keys = {"headline", "standfirst", "body_markdown", "bottom_line"}
    if not required_keys.issubset(data.keys()):
        return None

    # --- Grounding validation ---
    # Collect all values from entries as strings for number/name checks
    all_entry_values: set[str] = set()
    all_player_names: set[str] = set()
    for entry in entries:
        for k, v in entry.items():
            all_entry_values.add(str(v))
            if k == "name":
                all_player_names.add(str(v))
        # Also add partial numeric representations
        for k, v in entry.items():
            if isinstance(v, (int, float)):
                # Add various formatted forms
                all_entry_values.add(f"{v:.1f}")
                all_entry_values.add(f"{v:.2f}")
                all_entry_values.add(f"{v:.3f}")
                all_entry_values.add(str(int(v)) if v == int(v) else str(v))

    combined_output = (
        data.get("headline", "") + " " +
        data.get("standfirst", "") + " " +
        data.get("body_markdown", "") + " " +
        data.get("bottom_line", "")
    )

    # Check every numeric token in the output appears in entry values
    numeric_tokens = re.findall(r"\d+\.?\d*", combined_output)
    for token in numeric_tokens:
        if token not in all_entry_values:
            # Fall through to template
            return None

    # Check every player name in output is in the entries
    # Extract capitalized words (potential player names) — simple heuristic
    output_words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", combined_output)
    for word in output_words:
        # Only flag if it looks like a proper name (not article/sentence-start)
        # and is long enough to be a surname or full name
        if len(word) > 3 and word not in {
            "Round", "Bottom", "World", "Cup", "Fantasy", "The", "With", "From",
            "This", "These", "Their", "There", "While", "When", "Where", "Which",
        }:
            # Check if it matches any part of any player name
            matches = any(word in name or name in word for name in all_player_names)
            if not matches:
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
        result = _llm_prose(article, round_no, entries, columns, cache_dir)
        if result is not None:
            return result

    # Tier 3: template
    return _template_prose(article, entries, columns)
