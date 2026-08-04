"""Article prompt templates for the evmax LLM prose tier."""

import json

ARTICLE_PROMPT = """\
You are a tight, data-driven fantasy football analyst writing for evmax.ai.

Article slug : {slug}
{unit:<13}: {round_no}
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
  - ceiling_ratio → do not print the raw number; if it is below 1.15, say the pick has
    "no big-haul upside" or "a safe floor, no ceiling" (this is structurally true for
    goalkeepers, who cannot score outfield-style points)
  - Whenever you cite a specific pick's projected points (xPts or captain EV) and that
    entry also carries a ceiling, PAIR the two in the same breath: floor first, ceiling
    right behind it (e.g. "projects a nailed-on 5.1 with a 9.8 ceiling if he nets").
    This is the default, not the exception — a bare projected-points figure with the
    ceiling left unsaid is a missed opportunity. The only place to skip the pairing is
    a quick list of three or more names in one sentence. Readers find the floor-vs-
    ceiling range genuinely fun; treat the gap as a story (who is safe but capped, who
    is volatile but explosive), and call out the widest gap in the data explicitly.
  - The FIRST time you cite a ceiling figure, briefly say what it means in plain words:
    it is the player's 85th-percentile outcome across the 50,000 simulations — the
    realistic best-case game, not a hard cap. One clause is enough (e.g. "a ceiling of
    9.8 — his 85th-percentile sim"), then use "ceiling" freely afterwards.
  - vor → "value over replacement" (how many more points than a typical player at the
    same position)
  - p_advance → the percentage chance that player's team survives this knockout tie to
    play again next round (only present in knockout rounds — if absent or 100, do not
    mention advancement risk at all)
  - priority_score → do not print this raw number; it is the internal ranking used to
    order the list, described in prose as "priority" or "the top move"
  - p_clean_sheet → write as a percentage, e.g. 42% chance of a clean sheet
  - exp_goals_for / exp_goals_against → "expected goals for/against" for that team's fixture
  - env → do not print the raw word; "blowout" means a high-scoring fixture worth
    targeting attackers in, "avoid" means a low-scoring fixture where forwards should be
    faded, "balanced" means neither extreme applies
  - top_def / top_gk → that team's best defender/goalkeeper pick, already formatted as
    "Name (x.x)" — quote them as-is
  - role → "XI" means the player starts in the squad's lineup; "Bench" means they are
    one of the 4 squad-filler picks. Bench players are enablers that make the 15 legal
    and cheap, not picks to sell the reader on — do not oversell their point projections
    or ceiling; the pitch to the reader is entirely about the XI and the budget logic.
  - tier → the price bracket ("Budget", "Mid", or "Premium") — quote it as-is when
    naming a per-tier recommendation.
{fpl_glossary}
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


# Field vocabulary that exists ONLY in Fantasy Premier League. It is injected for
# unit="Gameweek" and left empty otherwise: a World Cup prompt that carried DefCon
# and blank-gameweek vocabulary would invite the model to reach for concepts its
# data cannot support.
_FPL_GLOSSARY = """\
  - p_defcon → the probability that player records enough defensive actions to earn
    the 2-point defensive-contribution bonus. Write it as a percentage, e.g. 71%.
    The threshold is 10 for defenders and 12 for midfielders and forwards; the entry
    carries it as defcon_threshold. Goalkeepers are not eligible at all.
  - defcon → the POINTS that probability is worth (exactly 2 x p_defcon). Prefer the
    probability in prose; the table already prints the points.
  - cs_points → the share of a defender's or goalkeeper's projection that comes from
    clean sheets, as opposed to DefCon, bonus or attacking returns. Use it to say
    WHERE a defensive pick's points come from.
  - bonus → expected bonus points from the BPS rank-within-match model.
  - exp_clean_sheets → expected clean sheets for that club this gameweek. It SUMS
    across a double gameweek, so it can exceed 1.0 — say "1.2 expected clean sheets
    across two fixtures", never "120% chance of a clean sheet".
  - fixtures → how many matches that club plays this gameweek. 0 is a BLANK (say so
    explicitly, it is the most actionable thing on the page); 2 is a DOUBLE.
  - opponents → already formatted as "LIV (H), BUR (A)" — quote it as-is.
  - basis → "market" means that club's fixture is priced by the betting market;
    "model" means it is not yet priced and the numbers come from our own team
    ratings; "mixed" means one of each across a double. Say which, plainly, when you
    cite a ticker number — never present model-derived and market-derived numbers as
    if they carried the same confidence.
  - kickoff_order → the order this player's match kicks off among the candidates
    (1 = earliest). Relevant to the vice-captain decision, not the captain one.
  - gameweeks → the gameweeks this club's run covers, in order. Say "the next six
    gameweeks", never print the list.
  - cells → that club's fixture in each of those gameweeks, in the same order.
    Each carries `label` (already formatted, e.g. "COV (H)" — quote it as-is, and
    for a double it names both opponents), `difficulty` (FPL's own 1-5 fixture
    difficulty for that fixture; 1 is easiest, 5 hardest, and it is None when
    there is no fixture to rate), `blank` (true = the club does not play that
    week) and `double` (true = they play twice). Never print the words "cells",
    "blank": true or "difficulty" — say "a blank gameweek", "a double" and
    "fixture difficulty".
  - difficulty (on the club row) → the club's AVERAGE fixture difficulty across
    the whole window. Use it as a label, not as a ranking: over six gameweeks
    most of the league lands within a few hundredths of 3.0, so it separates
    almost nobody. The ranking is expected clean sheets.
"""


def build_prompt(slug: str, round_no: int, entries: list, subject=None,
                 unit: str = "Round", chips=None) -> str:
    """Return a filled ARTICLE_PROMPT ready to send to the API.

    subject: player name to centre prose on, or None for team-framing
             (best-xi / wildcard / matches / fixtures / ticker).
    unit:    the reader-facing word for the period — "Round" for the World Cup,
             "Gameweek" for FPL. It also gates the FPL field glossary.
    chips:   bootstrap-static's chip windows, or None. Read only by the squad
             article, and only so the model is never told to write about playing
             a chip that is illegal that gameweek. None means "not available" —
             see fpl_articles.chip_available; the model must not be handed a
             permission the feed did not give.
    """
    from evmax.fpl_articles import chip_available
    if subject is not None and slug == "transfers":
        subject_instruction = (
            f"Focus      : Center this article on {subject}, the top-ranked transfer "
            f"priority. Explain the ranking logic: it is NOT raw expected points — it is "
            f"value over a replacement-level player at the same position (vor), boosted "
            f"when the player's team is likely to survive this knockout tie (p_advance) "
            f"and discounted when it's a coin flip, because a great pick on an eliminated "
            f"team is a wasted transfer. Frame this as practical advice for managers with "
            f"a limited number of transfers: which move to prioritize first, and which "
            f"second if they have another available.\n"
        )
    elif subject is not None and slug == "efficiency":
        subject_instruction = (
            f"Focus      : Center this article on {subject}, the overall value leader "
            f"(highest xPts per million). Every entry also carries a `tier` field — "
            f"\"Budget\" (under £5.5m), \"Mid\" (£5.5m-£8.0m), or \"Premium\" (over £8.0m). "
            f"After covering {subject}, recommend the single best-value pick IN EACH "
            f"tier present in the data (the entry with the highest `value` for that "
            f"tier) — a reader building on any budget should come away knowing the best "
            f"cheap pick, the best mid-price pick, and the best premium pick, grounded "
            f"only in the numbers supplied.\n"
        )
    elif slug == "defcon":
        subject_instruction = (
            "Focus      : Rank players by how reliably they earn the 2-point "
            "defensive-contribution bonus (p_defcon). This is a THRESHOLD, not a "
            "rate — a player either clears his position's action count in a given "
            "match or he does not — so frame it as 'hits the threshold in X% of "
            "simulations', never as an average number of actions. Name the best "
            "defender and the best midfielder separately: their thresholds differ "
            "(10 vs 12), so they are not competing for the same slot.\n"
        )
    elif slug == "ticker":
        subject_instruction = (
            "Focus      : Cover the gameweek club by club — who has the best "
            "clean-sheet odds (exp_clean_sheets), which fixtures are worth "
            "targeting attackers in (env=\"blowout\"), which to fade "
            "(env=\"avoid\"). Call out every club with fixtures=0 (a BLANK) and "
            "every club with fixtures=2 (a DOUBLE) explicitly and early — those "
            "are the two facts that change a manager's week. State the `basis` "
            "for any number you cite.\n"
        )
    elif slug == "runs":
        subject_instruction = (
            "Focus      : This is a PLANNING view over the next six gameweeks, not "
            "a preview of one. FPL gives a manager one free transfer a gameweek "
            "(bankable to five, any extra costing -4), so a squad changes slowly "
            "and managers buy into fixture RUNS, not single fixtures — say this "
            "out loud early, it is why the article exists. Name the best run on "
            "the board and the worst, and quote each club's own sequence of "
            "fixtures from its `cells` labels. Then do the thing this piece is "
            "for: call out any club whose NEXT fixture and whose RUN disagree — an "
            "easy opener followed by a hard stretch is a trap, because the "
            "transfer that buys the opener is still in the squad when the run "
            "turns, and a hard opener in front of an easy stretch is a side worth "
            "waiting a week for. Call out every blank gameweek and every double "
            "inside the window explicitly. Rank on expected clean sheets, NOT on "
            "average fixture difficulty. Finally, state the provenance plainly: "
            "the betting market does not price fixtures five weeks out, so the "
            "later gameweeks are derived from our own team ratings rather than "
            "from the market — check each club's `basis` and never present a "
            "model-derived number as a priced one.\n"
        )
    elif subject is not None:
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
    elif slug == "fixtures":
        subject_instruction = (
            "Focus      : Cover clean-sheet probabilities per team (p_clean_sheet), "
            "which games to target attackers in (env=\"blowout\" fixtures), and which "
            "low-scoring games to AVOID forwards from (env=\"avoid\" fixtures). Use only "
            "the supplied numbers — do not invent teams, players, or stats not in the "
            "data. You may cite top_def/top_gk as the best defensive picks for a "
            "high-clean-sheet team.\n"
        )
    elif slug == "wildcard":
        # The framing is set by the CHIP WINDOW, not by the gameweek number. The
        # wildcard runs GW2-19 and GW20-38, so gameweek 1 has no rebuild
        # available at all — and a model told to write about "playing your
        # wildcard" there will happily do it.
        if chip_available("wildcard", round_no, chips):
            framing = (
                "Focus      : This is a full 15-man wildcard/rebuild squad "
                "(role=\"XI\" for the 11 starters, role=\"Bench\" for the 4 "
                "squad-fillers), not a single-player pick. The wildcard chip IS "
                "playable this gameweek, so the squad can be rebuilt from scratch "
                "at no transfer cost — frame it that way.\n"
            )
        else:
            framing = (
                "Focus      : This is a full 15-man squad (role=\"XI\" for the 11 "
                "starters, role=\"Bench\" for the 4 squad-fillers), not a "
                "single-player pick. CRITICAL: the wildcard chip CANNOT be played "
                "this gameweek — its windows are Gameweeks 2-19 and 20-38 — and "
                "neither can the free hit. NEVER tell the reader to play, use, "
                "activate or save a wildcard, and never call this a wildcard "
                "squad, a rebuild or a reset. It is the squad they START the "
                "season in. Say early that there is no chip to undo it with: the "
                "only way out is one free transfer a gameweek (bankable to five, "
                "every extra costing -4 points), which is exactly why these "
                "fifteen are chosen on the next six gameweeks' fixtures rather "
                "than on this one Saturday.\n"
            )
        subject_instruction = framing + (
            "This article is ALSO the site's \"best XI\" piece, so open by naming the "
            "strongest starting XI explicitly — its formation and combined xPts total — "
            "before moving on to the budget and bench discussion. Then cover: the total "
            "squad cost vs the 100.0m budget, and the bench philosophy — the bench is "
            "deliberately the cheapest legal set of players (2 GK / 5 DEF / 5 MID / 3 FWD "
            "total across the 15), so all the spending power sits in the XI. Name the "
            "2-3 priciest picks and call out the single best value pick (highest xPts per "
            "million). Do not oversell the Bench players' own point projections — they "
            "are there to make the squad legal and cheap, not to score.\n"
        )
    else:
        subject_instruction = (
            "Focus      : Write about the XI as a unit (formation, balance, total xPts). "
            "Do not center on a single player; spread references across the squad.\n"
        )
    return ARTICLE_PROMPT.format(
        slug=slug,
        unit=unit,
        round_no=round_no,
        fpl_glossary=_FPL_GLOSSARY if unit == "Gameweek" else "",
        subject_instruction=subject_instruction,
        entries_json=json.dumps(entries, ensure_ascii=False, indent=2),
    )
