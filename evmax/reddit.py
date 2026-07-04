"""Operator posting material for Reddit — NOT part of the published site.

reddit_kit() builds a markdown briefing document for whoever is manually posting
that round's evmax output to r/FantasyPL and r/soccer: suggested titles, ready
-to-paste post bodies, and etiquette reminders. It is written to data/reddit/
(gitignored, operator-only) by evmax.build — never into dist/.

Deterministic: every number comes from entries_map/prose_map passed in, formatted
the same way render._fmt formats them elsewhere on the site. No I/O, no randomness.
"""

from evmax.render import _fmt, SITE_URL


def _captain_row(rank: int, e: dict) -> str:
    name = e.get("name", "")
    team = e.get("team", "") or ""
    ev = _fmt("captain_ev", e)
    ceiling = _fmt("ceiling", e)
    owned = _fmt("ownership_pct", e)
    return f"| {rank} | {name} | {team} | {ev} | {ceiling} | {owned} |"


def _captains_table(entries: list) -> str:
    top5 = entries[:5]
    header = "| # | Player | Team | Captain EV | Ceiling | Owned% |"
    sep = "|---|---|---|---|---|---|"
    rows = [_captain_row(i + 1, e) for i, e in enumerate(top5)]
    return "\n".join([header, sep] + rows)


def _close_games(matches_entries: list) -> list:
    return [e for e in matches_entries if e.get("close")]


def _close_games_list_md(matches_entries: list) -> str:
    close = _close_games(matches_entries)
    if not close:
        return "No fixture this round is marked close — the model has clear favourites throughout."
    lines = []
    for e in close:
        match = e.get("match", "")
        p_home = (e.get("p_home") or 0.0) * 100
        p_draw = (e.get("p_draw") or 0.0) * 100
        p_away = (e.get("p_away") or 0.0) * 100
        lines.append(f"- **{match}** — {p_home:.0f}/{p_draw:.0f}/{p_away:.0f} 1X2")
    return "\n".join(lines)


def _top_scorelines_md(matches_entries: list, n: int = 5) -> str:
    ranked = sorted(matches_entries, key=lambda e: -(e.get("exp_total") or 0.0))[:n]
    lines = []
    for e in ranked:
        match = e.get("match", "")
        score = e.get("top_scoreline", "?-?")
        p_home = (e.get("p_home") or 0.0) * 100
        p_draw = (e.get("p_draw") or 0.0) * 100
        p_away = (e.get("p_away") or 0.0) * 100
        lines.append(f"- **{match}** — predicted {score} ({p_home:.0f}/{p_draw:.0f}/{p_away:.0f} 1X2)")
    return "\n".join(lines)


def _fantasypl_titles(fantasy_round: int, captains_entries: list) -> list:
    titles = [
        f"[OC] I simulated every Round {fantasy_round} match 50,000 times — "
        f"captain EV, ceilings and the traps",
        f"[OC] Round {fantasy_round} captain data from 50k Monte-Carlo sims "
        f"(EV, ceiling, ownership)",
    ]
    if captains_entries:
        top = captains_entries[0]
        titles.append(
            f"[OC] Is {top.get('name', 'the top pick')} actually the best "
            f"Round {fantasy_round} captain? The sims say yes — here's the data")
    return titles


def _soccer_titles(fantasy_round: int, matches_entries: list) -> list:
    close = _close_games(matches_entries)
    titles = []
    if close:
        titles.append(
            f"[OC] Round {fantasy_round} match predictions — {close[0].get('match', '')} "
            f"projected as the closest game (50k simulations)")
    ranked = sorted(matches_entries, key=lambda e: -(e.get("exp_total") or 0.0))
    if ranked:
        top = ranked[0]
        titles.append(
            f"[OC] {top.get('match', '')} predicted to be Round {fantasy_round}'s "
            f"highest-scoring game — full scoreline probabilities inside")
    if not titles:
        titles.append(f"[OC] Round {fantasy_round} match predictions from 50,000 simulations")
    return titles


_ETIQUETTE = """## Posting etiquette (read first)

- **90/10 rule.** Only post this if you also comment, reply, and contribute like a
  normal community member elsewhere. Don't be a link-only account.
- **Post the graphic natively as an image**, not just a link out — attach a
  screenshot of the table/chart in the post itself. Reddit downranks bare link posts.
- **Reply to comments with numbers**, not just "thanks!" — if someone asks about a
  player not in the top 5, pull their EV from the article and answer in-thread.
- **Never spam the link** across multiple threads/subs in the same sitting. One post
  per sub, per round, and only where it's genuinely on-topic.
- **Disclose the affiliation up front** (already baked into the post body below) —
  don't bury it in a comment.
"""


def _fantasypl_body(fantasy_round: int, entries_map: dict, prose_map: dict, date_str: str) -> str:
    captains_entries = entries_map.get("captains", [])
    matches_entries = entries_map.get("matches", [])
    table = _captains_table(captains_entries)
    close_list = _close_games_list_md(matches_entries)
    top_captain = captains_entries[0] if captains_entries else {}
    top_name = top_captain.get("name", "our top pick")

    lines = [
        f"I run evmax.ai — Monte-Carlo sims on de-vigged market odds; sharing the "
        f"Round {fantasy_round} outputs.",
        "",
        f"Ran 50,000 simulations for Round {fantasy_round} ({date_str}) on the official "
        f"FIFA World Cup Fantasy scoring table. Here's the top-5 captain picks by "
        f"expected value:",
        "",
        table,
        "",
        "**Close games to watch this round:**",
        "",
        close_list,
        "",
        f"We grade every round publicly — Round 3's top captain scored 1 point, "
        f"receipts on the site (see /track-record/). Not every round is a hit; "
        f"that's the point of publishing the misses too.",
        "",
        f"**Method:** market odds (de-vigged) → Dixon-Coles scorelines → 50,000 "
        f"Monte-Carlo simulations, scored on the official FIFA World Cup Fantasy "
        f"points table.",
        "",
        f"Full breakdown with the reasoning behind {top_name} and the rest of the "
        f"round: {SITE_URL}/round/{fantasy_round}/captains/",
    ]
    return "\n".join(lines)


def _soccer_body(fantasy_round: int, entries_map: dict, date_str: str) -> str:
    matches_entries = entries_map.get("matches", [])
    scorelines = _top_scorelines_md(matches_entries)
    close_list = _close_games_list_md(matches_entries)

    lines = [
        f"I run evmax.ai — Monte-Carlo sims on de-vigged market odds; sharing the "
        f"Round {fantasy_round} match predictions.",
        "",
        f"50,000 simulations per fixture for Round {fantasy_round} ({date_str}). "
        f"Predicted scorelines and 1X2 probabilities for the highest-total-goals games:",
        "",
        scorelines,
        "",
        "**Closest games to call (no outcome above 45% probability):**",
        "",
        close_list,
        "",
        f"Method: de-vigged market odds → Dixon-Coles → 50k Monte-Carlo sims.",
        "",
        f"Full fixture-by-fixture breakdown: {SITE_URL}/round/{fantasy_round}/matches/",
    ]
    return "\n".join(lines)


def reddit_kit(fantasy_round: int, entries_map: dict, prose_map: dict, date_str: str) -> str:
    """Build the operator's Reddit posting kit for one round as a markdown document.

    entries_map: {slug: [entry, ...]} — same shape build.py assembles per round
                 (must contain "captains" and "matches" for the tables/lists here).
    prose_map:   {slug: {headline, standfirst, body_html, bottom_line, source}}
    date_str:    human-readable date, e.g. "24 June 2026" (as produced by
                 build._format_date).

    Deterministic given its inputs — no LLM calls, no randomness. Not published to
    the site; written by build.py to data/reddit/round-{N}.md (gitignored).
    """
    captains_entries = entries_map.get("captains", [])
    matches_entries = entries_map.get("matches", [])

    fpl_titles = _fantasypl_titles(fantasy_round, captains_entries)
    soc_titles = _soccer_titles(fantasy_round, matches_entries)

    fpl_body = _fantasypl_body(fantasy_round, entries_map, prose_map, date_str)
    soc_body = _soccer_body(fantasy_round, entries_map, date_str)

    parts = [
        f"# Reddit kit — Round {fantasy_round} ({date_str})",
        "",
        _ETIQUETTE,
        "## Suggested titles — r/FantasyPL",
        "",
    ]
    parts += [f"{i + 1}. {t}" for i, t in enumerate(fpl_titles)]
    parts += [
        "",
        "## Suggested titles — r/soccer",
        "",
    ]
    parts += [f"{i + 1}. {t}" for i, t in enumerate(soc_titles)]
    parts += [
        "",
        "## Post body — r/FantasyPL",
        "",
        fpl_body,
        "",
        "## Post body — r/soccer",
        "",
        soc_body,
        "",
    ]
    return "\n".join(parts) + "\n"
