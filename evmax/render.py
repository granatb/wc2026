"""Pure emitters for the evmax static site (HTML/SVG/JSON/text). No I/O."""

SITE_URL = "https://evmax.pages.dev"
METHODOLOGY = ("Market odds (de-vigged) → Dixon-Coles scorelines → 50k Monte-Carlo "
               "simulations, scored on the official FIFA World Cup Fantasy points table.")


def article_json(competition, fantasy_round, article, title, generated_at, sims, entries):
    return {
        "competition": competition,
        "round": fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": METHODOLOGY,
        "entries": entries,
        "source": SITE_URL,
        "license": "Attribution requested: evmax",
    }


def summary_sentence(article, entries):
    if not entries:
        return "No qualifying players this round."
    top = entries[0]
    name, team = top["name"], top.get("team", "")
    if article == "captains":
        return (f"Captain {name} ({team}): {top['captain_ev']:.1f} expected points — "
                f"the highest captain EV in this round.")
    if article == "differentials":
        return (f"{name} ({team}) is the standout differential: {top['x_points']:.1f} xPts "
                f"at just {top['ownership_pct']:.1f}% ownership.")
    if article == "best-value-xi":
        return (f"{name} ({team}) leads on value: {top['x_points']:.1f} xPts for "
                f"{top['price']:.1f}m.")
    if article == "high-ceiling-xi":
        return (f"{name} ({team}) has the highest ceiling: up to {top['ceiling']:.1f} points.")
    if article == "blowout-transfers":
        return (f"{name} ({team}) is the top attacker in this round's most lopsided fixtures "
                f"at {top['x_points']:.1f} xPts.")
    return f"{name} ({team}) tops the list at {top['x_points']:.1f} expected points."
