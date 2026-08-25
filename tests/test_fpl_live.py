"""Phase 4c: live gameweek grading — offline, synthetic payloads only.

Payloads are shaped exactly like the real API:
  event live:  {"elements": [{"id": N, "stats": {"minutes": M, "total_points": P}}]}
  fixtures:    [{"team_h": id, "team_a": id, "finished": bool,
                 "finished_provisional": bool, "kickoff_time": iso}]
No test in this file touches the network or data/.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from core import fpl_api, fpl_live

_POS_TO_TYPE = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}


def _entry(name, pos, starter=True, bench_order=None, cap=False, vice=False):
    return {"name": name, "position": pos, "is_starter": starter,
            "bench_order": bench_order, "is_captain": cap, "is_vice": vice}


def _state(squad, aliases=None):
    state = {"team_name": "Test XI", "strategy": "model", "squad": squad}
    if aliases is not None:
        state["aliases"] = aliases
    return state


def _squad_352(captain="M1", vice="F1"):
    """A legal 3-5-2 with one-club-per-player synthetic names."""
    squad = [
        _entry("G1", "GK"),
        _entry("D1", "DEF"), _entry("D2", "DEF"), _entry("D3", "DEF"),
        _entry("M1", "MID"), _entry("M2", "MID"), _entry("M3", "MID"),
        _entry("M4", "MID"), _entry("M5", "MID"),
        _entry("F1", "FWD"), _entry("F2", "FWD"),
        _entry("G2", "GK", starter=False, bench_order=1),
        _entry("D4", "DEF", starter=False, bench_order=2),
        _entry("F3", "FWD", starter=False, bench_order=3),
        _entry("D5", "DEF", starter=False, bench_order=4),
    ]
    for e in squad:
        e["is_captain"] = e["name"] == captain
        e["is_vice"] = e["name"] == vice
    return squad


def _boot(squad, rename=None):
    """A bootstrap whose elements mirror the squad, one club per player.

    rename: {state_name: bootstrap web_name} — the drifted-name scenario.
    element ids and team ids are both 1-based squad indices, so tests can
    address a player's club by his position in the squad list.
    """
    rename = rename or {}
    elements, teams = [], []
    for i, e in enumerate(squad, 1):
        teams.append({"id": i, "short_name": f"T{i:02d}"})
        elements.append({"id": i, "web_name": rename.get(e["name"], e["name"]),
                         "team": i, "element_type": _POS_TO_TYPE[e["position"]]})
    return {"teams": teams, "elements": elements}


def _live(points):
    """{state-squad index (1-based): (minutes, total_points)} -> live payload."""
    return {"elements": [
        {"id": eid, "stats": {"minutes": m, "total_points": p}}
        for eid, (m, p) in points.items()]}


def _fixtures(squad, unfinished_teams=(), blank_teams=()):
    """One finished fixture per club (vs. a dummy opponent id 999), except:
    unfinished_teams get an in-progress fixture, blank_teams get none."""
    out = []
    for i in range(1, len(squad) + 1):
        if i in blank_teams:
            continue
        done = i not in unfinished_teams
        out.append({"team_h": i, "team_a": 999, "finished": done,
                    "finished_provisional": done,
                    "kickoff_time": "2026-08-22T14:00:00Z"})
    return out


def _grade(squad, points, unfinished=(), blank=(), aliases=None, rename=None):
    state = _state(squad, aliases=aliases)
    boot = _boot(squad, rename=rename)
    live = _live(points)
    fx = _fixtures(squad, unfinished_teams=unfinished, blank_teams=blank)
    return fpl_live.grade_squad(state, live, fx, boot)


def _row(result, name):
    return next(r for r in result["rows"] if r["name"] == name)


class TestGradeSquadBasics(unittest.TestCase):
    def test_all_played_all_finished(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[5] = (90, 6)                      # M1, the captain
        result = _grade(squad, points)
        # 10 others * 2 + captain 6 * 2 = 32; bench multiplies by 0
        self.assertEqual(result["total_so_far"], 32)
        self.assertEqual(result["players_pending"], 0)
        self.assertEqual(result["autosubs_applied"], [])
        self.assertEqual(result["captain_effective"], "M1")
        self.assertEqual(_row(result, "M1")["multiplier"], 2)
        self.assertEqual(_row(result, "M1")["points"], 6)   # raw, not doubled
        for bench_name in ("G2", "D4", "F3", "D5"):
            self.assertEqual(_row(result, bench_name)["multiplier"], 0)
            self.assertEqual(_row(result, bench_name)["status"], "played")

    def test_total_is_checkable_from_the_rows_alone(self):
        squad = _squad_352()
        points = {i: (90, 3) for i in range(1, 16)}
        result = _grade(squad, points, unfinished=(2, 12))
        self.assertEqual(result["total_so_far"],
                         sum(r["points"] * r["multiplier"]
                             for r in result["rows"]))

    def test_rows_come_in_presentation_order(self):
        squad = _squad_352()
        result = _grade(squad, {i: (90, 2) for i in range(1, 16)})
        names = [r["name"] for r in result["rows"]]
        self.assertEqual(names[:11], [e["name"] for e in squad if e["is_starter"]])
        self.assertEqual(names[11:], ["G2", "D4", "F3", "D5"])  # bench order

    def test_missing_live_element_counts_as_zero(self):
        """A player absent from the live feed (early-season quirk) is 0/0,
        not a crash."""
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        del points[2]                            # D1 vanishes from the feed
        result = _grade(squad, points, unfinished=(2,))
        self.assertEqual(_row(result, "D1")["status"], "pending")
        self.assertEqual(_row(result, "D1")["points"], 0)


class TestPending(unittest.TestCase):
    def test_unfinished_club_zero_minutes_is_pending(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[2] = (0, 0)                       # D1 yet to appear
        result = _grade(squad, points, unfinished=(2,))
        row = _row(result, "D1")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["multiplier"], 1)   # still fielded
        self.assertEqual(row["note"], "to play")
        self.assertEqual(result["players_pending"], 1)
        self.assertEqual(result["autosubs_applied"], [])

    def test_pending_captain_keeps_the_armband(self):
        squad = _squad_352(captain="M1", vice="F1")
        points = {i: (90, 2) for i in range(1, 16)}
        points[5] = (0, 0)                       # captain M1, match in progress
        result = _grade(squad, points, unfinished=(5,))
        self.assertEqual(result["captain_effective"], "M1")
        self.assertEqual(_row(result, "M1")["multiplier"], 2)
        self.assertEqual(result["players_pending"], 1)

    def test_played_player_in_unfinished_match_already_counts(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[2] = (37, 1)                      # D1 on the pitch right now
        result = _grade(squad, points, unfinished=(2,))
        self.assertEqual(_row(result, "D1")["status"], "played")
        self.assertEqual(result["players_pending"], 0)
        self.assertEqual(result["total_so_far"], 2 * 9 + 2 * 2 + 1)


class TestAutosubs(unittest.TestCase):
    def test_dnp_forward_takes_first_bench_outfielder_in_order(self):
        """3-5-2 minus a FWD can legally take the bench DEF (4-5-1), and bench
        order — not position matching — decides who comes in."""
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[11] = (0, 0)                      # F2 DNP, club finished
        points[13] = (60, 5)                     # D4, bench_order 2
        points[14] = (60, 3)                     # F3, bench_order 3
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "F2", "in": "D4"}])
        self.assertEqual(_row(result, "D4")["status"], "autosub_in")
        self.assertEqual(_row(result, "D4")["multiplier"], 1)
        self.assertEqual(_row(result, "F2")["status"], "blank")
        self.assertEqual(_row(result, "F2")["multiplier"], 0)
        self.assertIn("D4 comes in", _row(result, "F2")["note"])
        self.assertIn("in for F2", _row(result, "D4")["note"])

    def test_formation_legality_skips_an_illegal_candidate(self):
        """With only 3 DEF fielded, a DNP defender cannot be covered by the
        bench FWD (2 DEF is illegal) — the sub walks on to the bench DEF."""
        squad = _squad_352()
        # make bench_order 2 the FWD and bench_order 3 the DEF
        for e in squad:
            if e["name"] == "F3":
                e["bench_order"] = 2
            elif e["name"] == "D4":
                e["bench_order"] = 3
        points = {i: (90, 2) for i in range(1, 16)}
        points[2] = (0, 0)                       # D1 DNP
        points[13] = (60, 5)                     # D4 played
        points[14] = (60, 9)                     # F3 played, earlier in order
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "D1", "in": "D4"}])

    def test_gk_swaps_gk_only(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[1] = (0, 0)                       # G1 DNP
        points[12] = (0, 0)                      # bench GK did not play either
        points[13] = (90, 8)                     # bench DEF played — must NOT come in
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"], [])
        self.assertEqual(_row(result, "G1")["status"], "blank")

    def test_gk_autosub_fires_when_the_backup_played(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[1] = (0, 0)                       # G1 DNP
        points[12] = (90, 6)                     # G2 played
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "G1", "in": "G2"}])
        self.assertEqual(_row(result, "G2")["status"], "autosub_in")

    def test_pending_bench_candidate_is_skipped_not_awaited(self):
        """Mid-gameweek semantics: a bench player who has not played yet is
        passed over for the next one who has; the next rebuild self-corrects."""
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[11] = (0, 0)                      # F2 DNP, club finished
        points[13] = (0, 0)                      # D4 (bench 2) still to play
        points[14] = (45, 4)                     # F3 (bench 3) played
        result = _grade(squad, points, unfinished=(13,))
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "F2", "in": "F3"}])
        self.assertEqual(_row(result, "D4")["status"], "pending")
        self.assertEqual(_row(result, "D4")["multiplier"], 0)

    def test_no_autosub_while_the_starter_might_still_play(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[11] = (0, 0)                      # F2 0 minutes, match unfinished
        points[14] = (45, 4)                     # bench F3 already played
        result = _grade(squad, points, unfinished=(11,))
        self.assertEqual(result["autosubs_applied"], [])
        self.assertEqual(_row(result, "F2")["status"], "pending")

    def test_blank_club_starter_is_autosub_eligible(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[11] = (0, 0)                      # F2's club has no fixture at all
        points[13] = (60, 5)                     # D4 played
        result = _grade(squad, points, blank=(11,))
        row = _row(result, "F2")
        self.assertEqual(row["status"], "blank")
        self.assertIn("D4 comes in", row["note"])
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "F2", "in": "D4"}])

    def test_blank_club_bench_player_notes_the_blank(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[13] = (0, 0)
        result = _grade(squad, points, blank=(13,))
        row = _row(result, "D4")
        self.assertEqual(row["status"], "blank")
        self.assertEqual(row["note"], "no fixture this gameweek")

    def test_two_dnp_starters_consume_the_bench_in_order(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        points[10] = (0, 0)                      # F1 DNP (also the vice)
        points[11] = (0, 0)                      # F2 DNP
        points[13] = (60, 5)                     # D4 (bench 2) played
        points[14] = (60, 3)                     # F3 (bench 3) played
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "F1", "in": "D4"},
                          {"out": "F2", "in": "F3"}])


class TestArmband(unittest.TestCase):
    def test_captain_blank_falls_to_vice(self):
        squad = _squad_352(captain="M1", vice="F1")
        points = {i: (90, 2) for i in range(1, 16)}
        points[5] = (0, 0)                       # captain M1 DNP, club done
        points[10] = (90, 7)                     # vice F1 played
        result = _grade(squad, points)
        self.assertEqual(result["captain_effective"], "F1")
        self.assertEqual(_row(result, "F1")["multiplier"], 2)
        self.assertIn("inherits the armband", _row(result, "F1")["note"])
        self.assertIn("armband passes to F1", _row(result, "M1")["note"])
        # 9 others * 2 + vice 7 * 2 + D4 in for the blanked captain * 2 = 34
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "M1", "in": "D4"}])
        self.assertEqual(result["total_so_far"], 34)

    def test_vice_blank_too_means_nobody_doubles(self):
        squad = _squad_352(captain="M1", vice="F1")
        points = {i: (90, 2) for i in range(1, 16)}
        points[5] = (0, 0)
        points[10] = (0, 0)
        result = _grade(squad, points)
        self.assertIsNone(result["captain_effective"])
        self.assertNotIn(2, [r["multiplier"] for r in result["rows"]])

    def test_autosubbed_captain_hands_the_armband_to_the_vice_not_the_sub(self):
        squad = _squad_352(captain="M1", vice="F1")
        points = {i: (90, 2) for i in range(1, 16)}
        points[5] = (0, 0)                       # captain DNP
        points[13] = (60, 5)                     # D4 comes in for him
        result = _grade(squad, points)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "M1", "in": "D4"}])
        self.assertEqual(result["captain_effective"], "F1")
        self.assertEqual(_row(result, "D4")["multiplier"], 1)
        self.assertEqual(_row(result, "F1")["multiplier"], 2)


class TestNameResolution(unittest.TestCase):
    def test_unresolved_names_fail_loudly_listing_every_one(self):
        squad = _squad_352()
        boot = _boot(squad, rename={"D1": "Somebody", "M3": "SomebodyElse"})
        with self.assertRaises(ValueError) as ctx:
            fpl_live.grade_squad(_state(squad), _live({}), _fixtures(squad), boot)
        msg = str(ctx.exception)
        self.assertIn("'D1'", msg)
        self.assertIn("'M3'", msg)
        self.assertIn("aliases", msg)

    def test_alias_lookup_resolves_a_renamed_player(self):
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        result = _grade(squad, points, aliases={"M5": "I.M5"},
                        rename={"M5": "I.M5"})
        row = _row(result, "M5")                 # row keeps the STATE name
        self.assertEqual(row["status"], "played")
        self.assertEqual(row["points"], 2)

    def test_exact_name_wins_over_the_alias(self):
        """An alias must never redirect a name that still resolves."""
        squad = _squad_352()
        points = {i: (90, 2) for i in range(1, 16)}
        result = _grade(squad, points, aliases={"M5": "D1"})
        self.assertEqual(_row(result, "M5")["points"], 2)

    def test_alias_pointing_nowhere_still_fails_loudly(self):
        squad = _squad_352()
        boot = _boot(squad, rename={"M5": "Renamed"})
        state = _state(squad, aliases={"M5": "WrongGuess"})
        with self.assertRaises(ValueError) as ctx:
            fpl_live.grade_squad(state, _live({}), _fixtures(squad), boot)
        self.assertIn("'M5'", str(ctx.exception))
        self.assertIn("'WrongGuess'", str(ctx.exception))

    def test_shared_web_name_disambiguated_by_position(self):
        squad = _squad_352()
        boot = _boot(squad)
        # a second, unrelated "D1" who plays MID
        boot["elements"].append({"id": 99, "web_name": "D1", "team": 3,
                                 "element_type": _POS_TO_TYPE["MID"]})
        points = {i: (90, 2) for i in range(1, 16)}
        result = fpl_live.grade_squad(_state(squad), _live(points),
                                      _fixtures(squad), boot)
        self.assertEqual(_row(result, "D1")["points"], 2)

    def test_still_ambiguous_name_is_an_error_not_a_guess(self):
        squad = _squad_352()
        boot = _boot(squad)
        boot["elements"].append({"id": 99, "web_name": "D1", "team": 3,
                                 "element_type": _POS_TO_TYPE["DEF"]})
        with self.assertRaises(ValueError) as ctx:
            fpl_live.grade_squad(_state(squad), _live({}), _fixtures(squad), boot)
        self.assertIn("ambiguous", str(ctx.exception))


class TestReferenceTruthGW1(unittest.TestCase):
    """The published Model XI graded on a synthetic GW1: 42 on the pitch, then
    Watkins (0 minutes, club finished) is covered by N.Williams — the FIRST
    bench outfielder in the PUBLISHED bench order, legal at 4-5-1 — for 44.
    A same-position shortcut (Calvert-Lewin) would give 43 and is wrong."""

    _XI_POINTS = {"Raya": 3, "Virgil": 4, "Senesi": 2, "Tarkowski": 6,
                  "B.Fernandes": 6, "Ndiaye": 2, "Gibbs-White": 5,
                  "E.Le Fée": 2, "Szoboszlai": 4, "Thiago": 2, "Watkins": 0}
    _BENCH_POINTS = {"Sánchez": 1, "N.Williams": 2, "Calvert-Lewin": 1,
                     "Shaw": 1}

    def _published_state(self):
        # The GW1 state as published, frozen as a fixture — the live state
        # file mutates weekly (lineups, transfers) and must not move this
        # reference truth.
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "fixtures", "gw1_state_model.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_published_model_state_grades_to_44(self):
        state = self._published_state()
        squad = state["squad"]
        boot = _boot(squad)
        points = {}
        for i, e in enumerate(squad, 1):
            pts = {**self._XI_POINTS, **self._BENCH_POINTS}[e["name"]]
            minutes = 0 if e["name"] == "Watkins" else 90
            points[i] = (minutes, pts)
        result = fpl_live.grade_squad(state, _live(points), _fixtures(squad),
                                      boot)
        self.assertEqual(result["autosubs_applied"],
                         [{"out": "Watkins", "in": "N.Williams"}])
        self.assertEqual(result["captain_effective"], "B.Fernandes")
        self.assertEqual(result["total_so_far"], 44)
        self.assertEqual(result["players_pending"], 0)


class TestAnyFixtureStarted(unittest.TestCase):
    _NOW = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)

    def test_nothing_started(self):
        fx = [{"team_h": 1, "team_a": 2, "finished": False,
               "finished_provisional": False,
               "kickoff_time": "2026-08-22T16:30:00Z"}]
        self.assertFalse(fpl_live.any_fixture_started(fx, now=self._NOW))

    def test_kickoff_in_the_past_counts(self):
        fx = [{"team_h": 1, "team_a": 2, "finished": False,
               "finished_provisional": False,
               "kickoff_time": "2026-08-22T14:00:00Z"}]
        self.assertTrue(fpl_live.any_fixture_started(fx, now=self._NOW))

    def test_feed_flags_win_over_the_clock(self):
        for flag in ("started", "finished", "finished_provisional"):
            fx = [{"team_h": 1, "team_a": 2,
                   "kickoff_time": "2026-08-22T20:00:00Z", flag: True}]
            with self.subTest(flag=flag):
                self.assertTrue(fpl_live.any_fixture_started(fx, now=self._NOW))

    def test_empty_or_missing_fixture_list(self):
        self.assertFalse(fpl_live.any_fixture_started([], now=self._NOW))
        self.assertFalse(fpl_live.any_fixture_started(None, now=self._NOW))


class TestLiveCache(unittest.TestCase):
    def test_refresh_overwrites_and_read_returns_the_latest(self):
        squad = _squad_352()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                first = fpl_live.refresh_live(
                    1,
                    fetch_live_fn=lambda gw: _live({1: (10, 1)}),
                    fetch_fixtures_fn=lambda gw: _fixtures(squad),
                    now=datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc))
                second = fpl_live.refresh_live(
                    1,
                    fetch_live_fn=lambda gw: _live({1: (90, 7)}),
                    fetch_fixtures_fn=lambda gw: _fixtures(squad),
                    now=datetime(2026, 8, 22, 17, 0, tzinfo=timezone.utc))
                cached = fpl_live.read_live_cache(1)
                self.assertEqual(cached, second)
                self.assertNotEqual(cached["fetched_at"], first["fetched_at"])
                self.assertEqual(
                    cached["live"]["elements"][0]["stats"]["total_points"], 7)
                self.assertTrue(os.path.exists(
                    os.path.join(tmp, "live_gw1.json")))

    def test_read_returns_none_when_never_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self.assertIsNone(fpl_live.read_live_cache(3))


if __name__ == "__main__":
    unittest.main()
