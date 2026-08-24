"""Player dossiers + the publish gate (spec D1, owner-approved 2026-08-24).

Every GW1 credibility dent was a knowledge-layer failure a mechanical check
would have caught: a wrong Sangaré, a Watkins held into a 0-minute blank while
50k managers sold him, Isak and Maguire minutes mispriced by the proxy.
"Validate every published player" existed as intent with no enforcement; this
module is the enforcement.

Pure: every function takes plain data in and returns plain data out — no I/O,
no network, no cache reads. The caller (evmax/fpl_build.dossier_gate for the
site build, manage.py for the transfer CLI) does the joins' I/O: bootstrap
players, priors' start probabilities, research notes, and the feed-snapshot
flags from core/fpl_diff.

A dossier is red iff ANY of (spec §2):
  - status != 'a'
  - start_prob < START_FLOOR and the start probability is the proxy's
    (a sourced note's override changes the source to 'note' and clears this)
  - the club changed since the last feed snapshot
  - the transfer-out z-score spiked (core/fpl_diff.outflow_spikes)
  - the name does not resolve against the bootstrap at all

The gate refuses every red dossier UNLESS a research note exists for that
player with a non-empty `sources:` list and an `updated:` date on/after the
feed snapshot's date. Refusal, not warning — there is deliberately no
--force-publish anywhere (owner decision D1).
"""

from __future__ import annotations

# The XI minutes floor (spec D6) — shared with the optimizer via
# evmax/fpl_articles.XI_START_FLOOR so the optimizer can never propose what
# this gate would refuse. Pinned here because games/ must not import the site
# layer (same reasoning as games/fpl/state.py's local rule constants).
START_FLOOR = 0.75


def build_dossier(entry: dict, prior: dict, bootstrap_player: dict | None,
                  research_note, captured_team: str | None = None,
                  outflow: bool = False) -> dict:
    """One player's dossier.

    entry:            a squad-state entry ({name, position, ...}).
    prior:            {"start_prob": float | None, "source": "proxy"|"history"}
                      — the engine's own minutes estimate and where it came
                      from. Preseason everything is 'proxy' (last season's
                      starts + price); 'history' is reserved for realized
                      in-season starts.
    bootstrap_player: the resolved core.fpl_api.parse_players row, or None
                      when the name resolves against nothing (red).
    research_note:    the core.research.ResearchEntry for this player (or
                      None). A note carrying start_prob_override becomes the
                      start probability AND its source ('note') — that is how
                      a sourced human judgment clears the proxy floor.
    captured_team:    the club the last feed snapshot had this player at, or
                      None when no snapshot knows him (first run, new player).
    outflow:          True when core/fpl_diff flags his transfer-out z-score.

    The two feed-derived flags arrive as arguments rather than being derived
    here because they need the previous snapshot, and this module stays pure —
    the caller reads the snapshot once and threads the flags in.
    """
    name = entry["name"]
    reasons: list = []

    if bootstrap_player is None:
        return {"name": name, "web_name": None, "status": None,
                "start_prob": None, "start_source": prior.get("source",
                                                              "proxy"),
                "club_changed": False, "name_drift": False,
                "outflow_flag": bool(outflow), "red": True,
                "reasons": [f"unresolved name — {name!r} matches nothing in "
                            f"the current bootstrap (rename? departure?)"]}

    status = bootstrap_player.get("status", "a")
    web_name = bootstrap_player.get("name")
    name_drift = web_name != name
    club_changed = (captured_team is not None
                    and bootstrap_player.get("team") != captured_team)

    override = getattr(research_note, "start_prob_override", None) \
        if research_note is not None else None
    if override is not None:
        start_prob, start_source = float(override), "note"
    else:
        start_prob = prior.get("start_prob")
        start_source = prior.get("source", "proxy")

    if status != "a":
        news = bootstrap_player.get("news") or ""
        reasons.append(f"status {status!r}"
                       + (f" ({news})" if news else " (check feed)"))
    if (start_source == "proxy" and start_prob is not None
            and start_prob < START_FLOOR):
        reasons.append(f"start probability {start_prob:.2f} < "
                       f"{START_FLOOR} on the proxy alone — no overriding "
                       f"note")
    if club_changed:
        reasons.append(f"club changed since capture: {captured_team} → "
                       f"{bootstrap_player.get('team')}")
    if outflow:
        reasons.append("transfer-out spike — the crowd is selling him; "
                       "find out what it knows")

    return {"name": name, "web_name": web_name, "status": status,
            "start_prob": start_prob, "start_source": start_source,
            "club_changed": club_changed, "name_drift": name_drift,
            "outflow_flag": bool(outflow), "red": bool(reasons),
            "reasons": reasons}


def assemble(state: dict, players: list, start_probs: dict, notes: dict,
             captured_teams: dict | None = None,
             outflow_ids=None) -> list:
    """Dossiers for every member of one squad state. Pure.

    players:        core.fpl_api.parse_players output (the current bootstrap).
    start_probs:    {prior name: start_prob} — priors carry DISAMBIGUATED
                    names (core.fpl_priors._disambiguate_names), so the lookup
                    escalates the same way: web_name, full_name,
                    "web_name (team)".
    notes:          {name: ResearchEntry} from core.research.load_entries —
                    looked up under the state name first, the current
                    web_name second (a note may be filed under either side of
                    a rename).
    captured_teams: {element id as str: team_short} from the previous feed
                    snapshot, or None when no snapshot exists.
    outflow_ids:    element ids (str) flagged by core/fpl_diff.outflow_spikes.

    An entry that resolves against nothing yields a RED dossier rather than
    raising: the gate's abort message listing it beats a traceback, and the
    site build's own state validation has already crashed loudly by the time
    this runs.
    """
    by_name: dict = {}
    for p in players:
        by_name.setdefault(p["name"], []).append(p)
    aliases = state.get("aliases") or {}
    captured_teams = captured_teams or {}
    outflow_ids = set(outflow_ids or ())

    def resolve(entry):
        candidates = by_name.get(entry["name"])
        if not candidates and entry["name"] in aliases:
            candidates = by_name.get(aliases[entry["name"]])
        matches = [p for p in (candidates or [])
                   if p.get("position") == entry["position"]]
        return matches[0] if len(matches) == 1 else None

    def start_prob_of(player):
        if player is None:
            return None
        for key in (player["name"],
                    player.get("full_name") or player["name"],
                    f"{player['name']} ({player.get('team')})"):
            if key in start_probs:
                return start_probs[key]
        return None

    dossiers = []
    for entry in state.get("squad", []):
        player = resolve(entry)
        note = notes.get(entry["name"])
        if note is None and player is not None:
            note = notes.get(player["name"])
        pid = str(player["id"]) if player is not None and "id" in player \
            else None
        dossiers.append(build_dossier(
            entry,
            {"start_prob": start_prob_of(player), "source": "proxy"},
            player, note,
            captured_team=captured_teams.get(pid) if pid else None,
            outflow=pid in outflow_ids if pid else False))
    return dossiers


def _note_field(note, field, default=None):
    """sources/updated off a ResearchEntry or a plain dict alike."""
    if note is None:
        return default
    if isinstance(note, dict):
        return note.get(field, default)
    return getattr(note, field, default)


def gate(dossiers: list, notes: dict,
         snapshot_date: str | None = None) -> tuple:
    """(ok, failures) — the publish gate over one squad's dossiers.

    A red dossier passes ONLY when a note exists for that player (under the
    state name or the current web_name) whose `sources` list is non-empty and
    whose `updated` date is on/after `snapshot_date` (ISO date string, from
    the feed snapshot's taken_at). With no snapshot (first ever run) the date
    requirement is waived — sources are still mandatory.

    failures carry the player name and the dossier's reasons verbatim, so the
    abort message IS the research to-do list.
    """
    failures = []
    for d in dossiers:
        if not d["red"]:
            continue
        note = notes.get(d["name"])
        if note is None and d.get("web_name"):
            note = notes.get(d["web_name"])
        sources = _note_field(note, "sources") or []
        updated = _note_field(note, "updated")
        if note is not None and sources and (
                snapshot_date is None
                or (updated is not None and str(updated) >= str(snapshot_date))):
            continue
        failures.append({"name": d["name"], "reasons": list(d["reasons"])})
    return (not failures), failures
