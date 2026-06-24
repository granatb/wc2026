"""Article prompt templates for the evmax LLM prose tier."""

import json

ARTICLE_PROMPT = """\
You are a tight, data-driven fantasy football analyst writing for evmax.pages.dev.

Article slug : {slug}
Round        : {round_no}

Below is the EXACT dataset for this article. These are the ONLY numbers and player names
you may reference. Do not invent statistics. Do not mention any player not in this list.
Every figure you cite must appear verbatim in the data below.

--- DATA ---
{entries_json}
--- END DATA ---

Write a tight analytical article with:
  - A punchy headline (≤ 10 words)
  - A one-line standfirst (≤ 20 words, gives the key takeaway)
  - 3–5 short paragraphs of body copy. Each paragraph should be 2–4 sentences.
    Include exactly one pull-quote paragraph formatted as: > Your pull-quote here.
    The final paragraph must start with "**Bottom line:**" and give a 1–2 sentence
    actionable recommendation grounded in the data.

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


def build_prompt(slug: str, round_no: int, entries: list) -> str:
    """Return a filled ARTICLE_PROMPT ready to send to the API."""
    return ARTICLE_PROMPT.format(
        slug=slug,
        round_no=round_no,
        entries_json=json.dumps(entries, ensure_ascii=False, indent=2),
    )
