"""Growth measurement sources: did this event peak raise the floor?

docs/STRATEGY.md §1 models the site as an event ratchet -- traffic arrives in
peaks and every peak is meant to leave permanent residue behind. So the only
question worth reporting is peak-over-peak, which is why snapshots are committed
(core/growth/snapshot.py): the previous peak has to still exist to compare
against.

EVERY SOURCE IN THIS PACKAGE IMPLEMENTS THE SAME TWO-FUNCTION CONTRACT:

    configured() -> bool
        True when this source's credentials are present in the environment.

    fetch(since, until) -> dict | None
        Raw pull for the window, or None when not configured.

        NEVER raises on a missing credential, an auth failure or a network
        error. A growth report is diagnostics: one dead source must degrade its
        own section to "unavailable" and leave every other section intact.

That second paragraph is the load-bearing part. The three planned sources have
three unrelated auth stories (Cloudflare API token, Bing API key, Google OAuth)
and will essentially never all be configured at once; a report that dies because
Google's OAuth is not set up yet cannot be used to read Cloudflare. The whole
report must run to completion, and be worth reading, with zero credentials
present. Return None, let the report print which environment variable was
missing, and move on.

Sources are also SERVER-SIDE OR API-SIDE ONLY. /privacy/ promises readers "no
cookies, no analytics or trackers, no third-party requests" in reader-facing
text. Cloudflare's edge already logs every request, so reading it back over
their API is invisible to the browser and keeps that promise intact. Nothing in
this package may ever put anything in a visitor's browser.
"""
