"""Article prompt templates for the evmax LLM prose tier."""

import json

ARTICLE_PROMPT = """\
You are a tight, data-driven fantasy football analyst writing for evmax.pages.dev.

Article slug : {slug}
Round        : {round_no}
{subject_instruction}
Below is the EXACT dataset for this article. These are the ONLY numbers and player names
you may reference. Do not invent statistics. Do not mention any player not in this list.
Every figure you cite must appear verbatim in the data below.

--- DATA ---
{entries_json}
--- END DATA ---

Refer to the data fields by these reader-friendly names (NEVER print the raw keys):
  - x_points → "xPts"            - captain_ev → "captain EV"
  - ceiling → "ceiling"          - value → "points per million" (or "value")
  - ownership_pct → write as a percentage, e.g. 1.3% (one decimal)
  - price → a player's price, e.g. 5.9m (one decimal, suffix "m")

Write a tight analytical article with:
  - A punchy headline in SENTENCE CASE (≤ 10 words, only the first word and proper
    nouns capitalised — e.g. "Amad Diallo is the Round 3 captain edge")
  - A one-line standfirst (≤ 20 words, gives the key takeaway)
  - 3–5 short paragraphs of body copy. Each paragraph should be 2–4 sentences.
    Include exactly one pull-quote paragraph formatted as: > Your pull-quote here.
    The final paragraph must start with "**Bottom line:**" and give a 1–2 sentence
    actionable recommendation grounded in the data.

Voice: confident, analytical, a little contrarian — like a sharp fantasy analyst who
trusts the model. No hype, no clichés, no exclamation marks.

Constraints:
  - Use ONLY the numbers supplied above. Cite them precisely (copy the value exactly).
  - Name ONLY players that appear in the data list.
  - Do not speculate about injuries, form, or anything not in the data.

Return STRICT JSON with exactly these keys and no others:
{{
  "headline": "<string>",
  "standfirst": "<string>",
  "body_markdown": "<string with the 3-5 paragraphs, pull-quote, and bottom line>",
  "bottom_line": "<the bottom-line sentence(s) without the '**Bottom line:**' prefix>"
}}
"""


def build_prompt(slug: str, round_no: int, entries: list, subject=None) -> str:
    """Return a filled ARTICLE_PROMPT ready to send to the API.

    subject: player name to centre prose on, or None for team-framing (best-xi / matches).
    """
    if subject is not None:
        subject_instruction = (
            f"Focus      : Center this article on {subject}. You may reference other "
            f"players in the data, but {subject} must be the main subject — lead with "
            f"their numbers and anchor the headline and recommendation on them.\n"
        )
    elif slug == "matches":
        subject_instruction = (
            "Focus      : Write about the round's fixtures as a whole. Cover expected "
            "scorelines, goals (exp_home_goals / exp_away_goals), the top_scoreline for "
            "notable games, the 1X2 probabilities (p_home/p_draw/p_away), and name the "
            "fixtures marked close=true as games to watch. Do not invent players or "
            "stats not in the data.\n"
        )
    else:
        subject_instruction = (
            "Focus      : Write about the XI as a unit (formation, balance, total xPts). "
            "Do not center on a single player; spread references across the squad.\n"
        )
    return ARTICLE_PROMPT.format(
        slug=slug,
        round_no=round_no,
        subject_instruction=subject_instruction,
        entries_json=json.dumps(entries, ensure_ascii=False, indent=2),
    )
