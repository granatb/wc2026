"""Phase 4c task 3: the consensus reset — most-owned legal template (GW2+).

Offline, synthetic payloads only. The pure builder is tested on
parse_players-shaped dicts; reset_consensus is tested through a synthetic RAW
bootstrap payload (mocked cache read) writing to a temp path — the real
games/fpl/state_consensus.json is never touched by this suite.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from unittest import mock

from games.fpl import consensus, state as fpl_state

_POS_TO_TYPE = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}


def _p(name, team, pos, price, ownership, status="a"):
    return {"name": name, "team": team, "position": pos, "price": price,
            "ownership": ownership, "status": status}


def _pool():
    """Ownership-graded pool. The most-owned legal squad is exactly
    G1,G2 / D1-D5 / M1-M5 / F1-F3 at 99.5m, XI 3-5-2, F1 (c) M1 (v)."""
    return [
        _p("G1", "T1", "GK", 5.0, 60), _p("G2", "T2", "GK", 4.5, 50),
        _p("G3", "T3", "GK", 4.0, 10),
        _p("D1", "T1", "DEF", 5.5, 70), _p("D2", "T2", "DEF", 5.0, 65),
        _p("D3", "T3", "DEF", 4.5, 60), _p("D4", "T4", "DEF", 4.5, 55),
        _p("D5", "T5", "DEF", 4.0, 50), _p("D6", "T6", "DEF", 4.0, 20),
        _p("M1", "T3", "MID", 12.0, 80), _p("M2", "T4", "MID", 8.0, 75),
        _p("M3", "T5", "MID", 7.0, 70), _p("M4", "T6", "MID", 6.5, 65),
        _p("M5", "T7", "MID", 6.0, 60), _p("M6", "T8", "MID", 5.0, 15),
        _p("F1", "T8", "FWD", 12.5, 90), _p("F2", "T7", "FWD", 8.5, 70),
        _p("F3", "T1", "FWD", 6.0, 55), _p("F4", "T2", "FWD", 5.5, 25),
    ]


def _names(state, starter=None):
    squad = state["squad"]
    if starter is not None:
        squad = [e for e in squad if e["is_starter"] == starter]
    return [e["name"] for e in squad]


class TestBuildConsensusState(unittest.TestCase):
    def test_most_owned_squad_validates_and_declares_the_wildcard(self):
        pool = _pool()
        state = consensus.build_consensus_state(pool, gameweek=2)
        out = fpl_state.validate_state(state, pool)     # legality is the gate
        self.assertEqual(out["strategy"], "consensus")
        self.assertEqual(out["team_name"], "The Consensus XI")
        self.assertEqual(out["chips_used"], ["wildcard"])
        self.assertEqual(out["total_cost"], 99.5)
        self.assertEqual(sorted(_names(state)),
                         sorted(["G1", "G2", "D1", "D2", "D3", "D4", "D5",
                                 "M1", "M2", "M3", "M4", "M5",
                                 "F1", "F2", "F3"]))

    def test_method_note_states_the_method_and_the_gameweek(self):
        state = consensus.build_consensus_state(_pool(), gameweek=2)
        self.assertIn("most-owned", state["method_note"])
        self.assertIn("gameweek 2", state["method_note"])
        self.assertIn("Wildcard", state["method_note"])
        self.assertIn("retired", state["method_note"])
        # no expert corpus any more — the prose must not claim one
        self.assertNotIn("source_count", state)

    def test_xi_is_the_most_owned_legal_formation(self):
        state = consensus.build_consensus_state(_pool(), gameweek=2)
        xi = _names(state, starter=True)
        self.assertEqual(xi, ["G1", "D1", "D2", "D3",
                              "M1", "M2", "M3", "M4", "M5", "F1", "F2"])

    def test_bench_is_backup_gk_then_outfield_by_ownership(self):
        state = consensus.build_consensus_state(_pool(), gameweek=2)
        bench = sorted((e for e in state["squad"] if not e["is_starter"]),
                       key=lambda e: e["bench_order"])
        self.assertEqual([e["name"] for e in bench], ["G2", "D4", "F3", "D5"])

    def test_captain_is_the_highest_owned_premium_vice_the_next(self):
        state = consensus.build_consensus_state(_pool(), gameweek=2)
        cap = next(e for e in state["squad"] if e["is_captain"])
        vice = next(e for e in state["squad"] if e["is_vice"])
        self.assertEqual(cap["name"], "F1")     # 12.5m, 90% — not M1 at 80%
        self.assertEqual(vice["name"], "M1")

    def test_without_premiums_the_armband_falls_to_raw_ownership(self):
        pool = [dict(p, price=min(p["price"], 9.5)) for p in _pool()]
        state = consensus.build_consensus_state(pool, gameweek=2)
        cap = next(e for e in state["squad"] if e["is_captain"])
        vice = next(e for e in state["squad"] if e["is_vice"])
        self.assertEqual(cap["name"], "F1")     # 90% owned
        self.assertEqual(vice["name"], "M1")    # 80% owned

    def test_club_cap_skips_to_the_next_most_owned(self):
        pool = _pool() + [_p("D0", "T1", "DEF", 5.0, 75)]
        state = consensus.build_consensus_state(pool, gameweek=2)
        names = _names(state)
        # T1 fills with G1 + D0 + D1; F3 (T1) must give way to F4
        self.assertIn("D0", names)
        self.assertNotIn("F3", names)
        self.assertIn("F4", names)
        fpl_state.validate_state(state, pool)

    def test_budget_repair_downgrades_the_least_ownership_per_pound(self):
        pool = [dict(p, price=13.5) if p["name"] == "M1" else p
                for p in _pool()]                # naive squad now 101.0m
        state = consensus.build_consensus_state(pool, gameweek=2)
        out = fpl_state.validate_state(state, pool)
        self.assertLessEqual(out["total_cost"], 100.0)
        self.assertNotIn("M1", _names(state))    # cheapest ownership to shed
        cap = next(e for e in state["squad"] if e["is_captain"])
        vice = next(e for e in state["squad"] if e["is_vice"])
        self.assertEqual(cap["name"], "F1")      # the one premium left
        self.assertEqual(vice["name"], "M2")     # highest-owned non-premium

    def test_transferred_out_players_are_excluded(self):
        pool = [dict(p, status="u") if p["name"] == "F1" else p
                for p in _pool()]
        state = consensus.build_consensus_state(pool, gameweek=2)
        self.assertNotIn("F1", _names(state))
        self.assertIn("F4", _names(state))       # next FWD steps in

    def test_ambiguous_names_are_never_guessed(self):
        pool = _pool() + [_p("Twin", "T5", "MID", 6.0, 99),
                          _p("Twin", "T6", "MID", 6.0, 98)]
        state = consensus.build_consensus_state(pool, gameweek=2)
        self.assertNotIn("Twin", _names(state))

    def test_one_squad_slot_per_web_name_across_positions(self):
        pool = _pool() + [_p("Solo", "T7", "DEF", 4.0, 99),
                          _p("Solo", "T8", "FWD", 5.0, 99)]
        state = consensus.build_consensus_state(pool, gameweek=2)
        self.assertEqual(_names(state).count("Solo"), 1)
        fpl_state.validate_state(state, pool)

    def test_deterministic(self):
        pool = _pool()
        self.assertEqual(consensus.build_consensus_state(pool, 2),
                         consensus.build_consensus_state(copy.deepcopy(pool), 2))

    def test_input_pool_is_not_mutated(self):
        pool = _pool()
        before = copy.deepcopy(pool)
        consensus.build_consensus_state(pool, 2)
        self.assertEqual(pool, before)

    def test_no_ownership_data_aborts(self):
        pool = [dict(p, ownership=0.0) for p in _pool()]
        with self.assertRaises(ValueError) as ctx:
            consensus.build_consensus_state(pool, 2)
        self.assertIn("ownership", str(ctx.exception))


def _raw_boot(pool):
    """The builder pool re-encoded as a RAW bootstrap payload, so the reset
    path is exercised through fpl_api.parse_players like production."""
    team_ids = {t: i for i, t in
                enumerate(sorted({p["team"] for p in pool}), 1)}
    return {
        "teams": [{"id": i, "short_name": t} for t, i in team_ids.items()],
        "elements": [
            {"id": n, "web_name": p["name"], "first_name": p["name"],
             "second_name": p["name"], "team": team_ids[p["team"]],
             "element_type": _POS_TO_TYPE[p["position"]],
             "now_cost": int(round(p["price"] * 10)),
             "selected_by_percent": str(p["ownership"]),
             "status": p["status"]}
            for n, p in enumerate(pool, 1)],
    }


class TestResetConsensus(unittest.TestCase):
    def _reset(self, boot, out_path):
        from evmax import fpl_build
        with mock.patch.object(fpl_build.fpl_api, "read_cache",
                               return_value=boot):
            return fpl_build.reset_consensus(2, out_path=out_path)

    def test_writes_a_validated_state_file_in_house_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state_consensus.json")
            self._reset(_raw_boot(_pool()), path)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            state = json.loads(text)
            self.assertEqual(state["chips_used"], ["wildcard"])
            self.assertEqual(len(state["squad"]), 15)
            # house style: one squad entry per line, diacritics unescaped
            self.assertEqual(
                sum(1 for line in text.splitlines()
                    if line.strip().startswith('{"name"')), 15)
            cap = next(e for e in state["squad"] if e["is_captain"])
            self.assertEqual(cap["name"], "F1")

    def test_missing_bootstrap_aborts_with_the_refresh_command(self):
        from evmax import fpl_build
        with mock.patch.object(fpl_build.fpl_api, "read_cache",
                               return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.reset_consensus(2, out_path="/nonexistent/x.json")
        self.assertIn("refresh", str(ctx.exception))

    def test_illegal_template_aborts_instead_of_writing(self):
        boot = _raw_boot([p for p in _pool() if p["position"] != "FWD"])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state_consensus.json")
            with self.assertRaises(SystemExit):
                self._reset(boot, path)
            self.assertFalse(os.path.exists(path))

    def test_stale_ownershipless_bootstrap_aborts(self):
        pool = [dict(p, ownership=0.0) for p in _pool()]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state_consensus.json")
            with self.assertRaises(SystemExit) as ctx:
                self._reset(_raw_boot(pool), path)
            self.assertIn("ownership", str(ctx.exception))
            self.assertFalse(os.path.exists(path))


class TestCliResetConsensus(unittest.TestCase):
    def test_reset_flag_routes_and_builds_nothing(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "fpl_build") as fake:
            with mock.patch("sys.argv",
                            ["build", "--gw", "2", "--reset-consensus"]):
                build_mod.main()
        fake.reset_consensus.assert_called_once_with(2)
        fake.build.assert_not_called()

    def test_reset_without_gw_is_an_error(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "fpl_build"):
            with mock.patch("sys.argv", ["build", "--round", "8",
                                         "--reset-consensus"]):
                with self.assertRaises(SystemExit):
                    build_mod.main()


if __name__ == "__main__":
    unittest.main()
