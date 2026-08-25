"""Phase 4b: the two published squad states — loader + validator."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest

from games.fpl import state as fpl_state


def _players():
    """A synthetic bootstrap pool: enough legal bodies plus deliberate traps
    (an ambiguous web_name pair, a diacritic name, an expensive premium)."""
    out = []

    def p(name, team, pos, price):
        out.append({"name": name, "team": team, "position": pos, "price": price})

    p("Keeper", "AAA", "GK", 5.0)
    p("Backup", "BBB", "GK", 4.0)
    p("Def1", "AAA", "DEF", 5.0)
    p("Def2", "BBB", "DEF", 5.0)
    p("Def3", "CCC", "DEF", 5.0)
    p("Def4", "DDD", "DEF", 4.5)
    p("Def5", "EEE", "DEF", 4.0)
    p("Mid1", "CCC", "MID", 8.0)
    p("Mid2", "DDD", "MID", 7.0)
    p("Mid3", "EEE", "MID", 6.0)
    p("Mid4", "FFF", "MID", 6.0)
    p("Groß", "GGG", "MID", 5.5)
    p("Fwd1", "FFF", "FWD", 9.0)
    p("Fwd2", "GGG", "FWD", 7.0)
    p("Fwd3", "HHH", "FWD", 6.0)
    # traps
    p("Premium", "III", "FWD", 15.5)
    p("Twin", "III", "MID", 5.0)       # same web_name, two positions:
    p("Twin", "JJJ", "DEF", 4.5)       # position disambiguates
    p("Clone", "KKK", "MID", 5.0)      # same web_name, SAME position:
    p("Clone", "LLL", "MID", 5.5)      # unresolvable
    return out


def _entry(name, pos, starter=True, bench_order=None, cap=False, vice=False):
    return {"name": name, "position": pos, "is_starter": starter,
            "bench_order": bench_order, "is_captain": cap, "is_vice": vice}


def _valid_state():
    """A legal 3-5-2: XI (1 GK, 3 DEF, 5 MID, 2 FWD) + GK/DEF/FWD/DEF bench."""
    return {
        "team_name": "Test XI",
        "strategy": "model",
        "free_transfers": 1,
        "chips_used": [],
        "squad": [
            _entry("Keeper", "GK"),
            _entry("Def1", "DEF"),
            _entry("Def2", "DEF"),
            _entry("Def3", "DEF"),
            _entry("Mid1", "MID", cap=True),
            _entry("Mid2", "MID", vice=True),
            _entry("Mid3", "MID"),
            _entry("Mid4", "MID"),
            _entry("Groß", "MID"),
            _entry("Fwd1", "FWD"),
            _entry("Fwd2", "FWD"),
            _entry("Backup", "GK", starter=False, bench_order=1),
            _entry("Def4", "DEF", starter=False, bench_order=2),
            _entry("Fwd3", "FWD", starter=False, bench_order=3),
            _entry("Def5", "DEF", starter=False, bench_order=4),
        ],
    }


class TestValidateState(unittest.TestCase):
    def setUp(self):
        self.players = _players()
        self.state = _valid_state()

    def _check(self, mutate, fragment):
        """Apply `mutate` to a fresh copy and assert ValueError names the cause."""
        state = copy.deepcopy(self.state)
        mutate(state)
        with self.assertRaises(ValueError) as ctx:
            fpl_state.validate_state(state, self.players)
        self.assertIn(fragment, str(ctx.exception))

    # --- the happy path -------------------------------------------------------

    def test_valid_state_is_enriched_with_bootstrap_team_and_price(self):
        out = fpl_state.validate_state(self.state, self.players)
        by_name = {e["name"]: e for e in out["squad"]}
        self.assertEqual(by_name["Keeper"]["team"], "AAA")
        self.assertEqual(by_name["Keeper"]["price"], 5.0)
        self.assertEqual(out["total_cost"], 87.0)
        self.assertEqual(out["team_name"], "Test XI")
        self.assertEqual(out["free_transfers"], 1)
        self.assertEqual(out["chips_used"], [])

    def test_prices_are_never_read_from_the_state_file(self):
        """A stored price is ignored: the bootstrap is the only price source."""
        self.state["squad"][0]["price"] = 99.0
        out = fpl_state.validate_state(self.state, self.players)
        self.assertEqual(out["squad"][0]["price"], 5.0)

    def test_diacritic_names_resolve_exactly(self):
        out = fpl_state.validate_state(self.state, self.players)
        self.assertIn("Groß", [e["name"] for e in out["squad"]])

    def test_shared_web_name_is_disambiguated_by_position(self):
        state = copy.deepcopy(self.state)
        state["squad"][8] = _entry("Twin", "MID")     # replaces Groß
        out = fpl_state.validate_state(state, self.players)
        twin = next(e for e in out["squad"] if e["name"] == "Twin")
        self.assertEqual(twin["team"], "III")

    def test_input_state_is_not_mutated(self):
        before = copy.deepcopy(self.state)
        fpl_state.validate_state(self.state, self.players)
        self.assertEqual(self.state, before)

    # --- every failure mode ----------------------------------------------------

    def test_unknown_strategy(self):
        self._check(lambda s: s.update(strategy="vibes"), "strategy")

    def test_missing_team_name(self):
        self._check(lambda s: s.update(team_name=""), "team_name")

    def test_wrong_squad_size(self):
        self._check(lambda s: s["squad"].pop(), "exactly 15")

    def test_missing_entry_key(self):
        self._check(lambda s: s["squad"][3].pop("bench_order"), "missing key")

    def test_duplicate_name(self):
        def mutate(s):
            s["squad"][7] = _entry("Mid1", "MID")
        self._check(mutate, "duplicate")

    def test_name_not_in_bootstrap(self):
        def mutate(s):
            s["squad"][8] = _entry("Nobody", "MID")
        self._check(mutate, "does not resolve")

    def test_diacritics_are_not_optional(self):
        """'Gross' is NOT 'Groß' — a transliterated name must fail loudly."""
        def mutate(s):
            s["squad"][8] = _entry("Gross", "MID")
        self._check(mutate, "does not resolve")

    def test_position_mismatch_against_bootstrap(self):
        def mutate(s):
            s["squad"][8] = _entry("Fwd3", "MID")
            s["squad"][13] = _entry("Groß", "MID", starter=False, bench_order=3)
        self._check(mutate, "position")

    def test_ambiguous_name_raises_instead_of_guessing(self):
        def mutate(s):
            s["squad"][8] = _entry("Clone", "MID")
        self._check(mutate, "ambiguous")

    def test_quota_violation(self):
        def mutate(s):
            s["squad"][14] = _entry("Mid4", "MID")     # 4 DEF, 6 MID
            s["squad"][7] = _entry("Twin", "MID")      # keep names unique
        self._check(mutate, "quota")

    def test_club_cap_violation(self):
        players = self.players + [
            {"name": "Def6", "team": "AAA", "position": "DEF", "price": 4.0},
            {"name": "Mid9", "team": "AAA", "position": "MID", "price": 5.0},
        ]
        state = copy.deepcopy(self.state)
        state["squad"][2] = _entry("Def6", "DEF")      # AAA x4
        state["squad"][7] = _entry("Mid9", "MID")
        with self.assertRaises(ValueError) as ctx:
            fpl_state.validate_state(state, players)
        self.assertIn("club cap", str(ctx.exception))

    def test_over_budget(self):
        # A single premium swap keeps this pool under 100, so inflate the whole
        # price list instead — the squad itself stays untouched and legal.
        players = [dict(p, price=p["price"] * 2) for p in self.players]
        with self.assertRaises(ValueError) as ctx:
            fpl_state.validate_state(self.state, players)
        self.assertIn("budget", str(ctx.exception))

    def test_wrong_starter_count(self):
        def mutate(s):
            s["squad"][11]["is_starter"] = True        # 12 starters
            s["squad"][11]["bench_order"] = None
        self._check(mutate, "11 starters")

    def test_illegal_xi_formation(self):
        def mutate(s):
            # swap a starting DEF with the bench FWD: XI becomes 2 DEF / 3 FWD
            s["squad"][3] = _entry("Def3", "DEF", starter=False, bench_order=3)
            s["squad"][13] = _entry("Fwd3", "FWD")
        self._check(mutate, "formation")

    def test_no_captain(self):
        self._check(lambda s: s["squad"][4].update(is_captain=False), "captain")

    def test_two_captains(self):
        self._check(lambda s: s["squad"][6].update(is_captain=True),
                    "exactly 1 captain")

    def test_no_vice(self):
        self._check(lambda s: s["squad"][5].update(is_vice=False), "vice")

    def test_captain_equals_vice(self):
        def mutate(s):
            s["squad"][5]["is_vice"] = False
            s["squad"][4]["is_vice"] = True
        self._check(mutate, "differ")

    def test_captain_on_the_bench(self):
        def mutate(s):
            s["squad"][4]["is_captain"] = False
            s["squad"][13]["is_captain"] = True        # bench FWD
        self._check(mutate, "starter")

    def test_starter_with_a_bench_order(self):
        self._check(lambda s: s["squad"][2].update(bench_order=2),
                    "starters must be null")

    def test_bench_order_not_one_to_four(self):
        self._check(lambda s: s["squad"][14].update(bench_order=2),
                    "bench_order")

    def test_bench_order_one_must_be_the_gk(self):
        def mutate(s):
            s["squad"][11]["bench_order"] = 2
            s["squad"][12]["bench_order"] = 1
        self._check(mutate, "backup GK")

    def test_bench_order_rejects_booleans(self):
        """bool is a subclass of int: True would otherwise pass an
        isinstance(int) check and quietly count as bench_order 1."""
        def mutate(s):
            s["squad"][11]["bench_order"] = True
        self._check(mutate, "bench_order")

    # --- free_transfers --------------------------------------------------------

    def test_free_transfers_must_be_a_non_negative_int_when_present(self):
        for bad in (-1, 1.5, "2", True, None):
            with self.subTest(bad=bad):
                self._check(lambda s, b=bad: s.update(free_transfers=b),
                            "free_transfers")

    def test_free_transfers_zero_and_banked_values_pass(self):
        for ok in (0, 5):
            with self.subTest(ok=ok):
                state = copy.deepcopy(self.state)
                state["free_transfers"] = ok
                out = fpl_state.validate_state(state, self.players)
                self.assertEqual(out["free_transfers"], ok)

    def test_absent_free_transfers_defaults_to_one(self):
        state = copy.deepcopy(self.state)
        del state["free_transfers"]
        out = fpl_state.validate_state(state, self.players)
        self.assertEqual(out["free_transfers"], 1)

    # --- source_count (the consensus corpus size, published in prose) ---------

    def test_source_count_passes_through_when_valid(self):
        state = copy.deepcopy(self.state)
        state["source_count"] = 7
        out = fpl_state.validate_state(state, self.players)
        self.assertEqual(out["source_count"], 7)

    def test_absent_source_count_stays_absent(self):
        out = fpl_state.validate_state(self.state, self.players)
        self.assertNotIn("source_count", out)

    def test_source_count_must_be_a_positive_integer(self):
        for bad in (0, -3, "7", 7.0, True, None):
            with self.subTest(bad=bad):
                self._check(lambda s, b=bad: s.update(source_count=b),
                            "source_count")

    # --- aliases (the renamed-player shim, phase 4c) ---------------------------

    def test_empty_aliases_map_is_accepted(self):
        state = copy.deepcopy(self.state)
        state["aliases"] = {}
        out = fpl_state.validate_state(state, self.players)
        self.assertEqual(out["aliases"], {})

    def test_alias_resolves_a_renamed_player(self):
        """The season renamed 'Groß' — the frozen state name must keep
        resolving via the alias against the refreshed bootstrap."""
        players = [dict(p, name="M.Groß") if p["name"] == "Groß" else p
                   for p in self.players]
        state = copy.deepcopy(self.state)
        state["aliases"] = {"Groß": "M.Groß"}
        out = fpl_state.validate_state(state, players)
        entry = next(e for e in out["squad"] if e["name"] == "Groß")
        self.assertEqual(entry["team"], "GGG")   # name stays the published claim
        self.assertEqual(entry["price"], 5.5)

    def test_exact_name_wins_over_the_alias(self):
        state = copy.deepcopy(self.state)
        state["aliases"] = {"Groß": "Mid1"}      # a bad alias must stay unused
        out = fpl_state.validate_state(state, self.players)
        entry = next(e for e in out["squad"] if e["name"] == "Groß")
        self.assertEqual(entry["team"], "GGG")

    def test_alias_pointing_nowhere_names_both_strings(self):
        players = [p for p in self.players if p["name"] != "Groß"]
        state = copy.deepcopy(self.state)
        state["aliases"] = {"Groß": "Nobody"}
        with self.assertRaises(ValueError) as ctx:
            fpl_state.validate_state(state, players)
        self.assertIn("does not resolve", str(ctx.exception))
        self.assertIn("Nobody", str(ctx.exception))

    def test_aliases_must_be_a_dict_of_non_empty_strings(self):
        for bad in (["Groß"], "Groß", {"Groß": ""}, {"": "M.Groß"},
                    {"Groß": 7}):
            with self.subTest(bad=bad):
                self._check(lambda s, b=bad: s.update(aliases=b), "aliases")

    def test_alias_key_must_name_a_squad_member(self):
        self._check(lambda s: s.update(aliases={"Haaland": "E.Haaland"}),
                    "no squad member")


class TestLoadState(unittest.TestCase):
    def test_load_squad_reads_validates_and_enriches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_valid_state(), fh, ensure_ascii=False)
            out = fpl_state.load_squad(path, _players())
            self.assertEqual(out["total_cost"], 87.0)
            self.assertEqual(out["squad"][0]["team"], "AAA")


class TestRealStateFiles(unittest.TestCase):
    """The two files the site actually publishes, against the real bootstrap.

    Uses the cached data/fpl/bootstrap.json like the end-to-end build test does
    (data/ is gitignored but present on any machine that has ever built)."""

    @classmethod
    def setUpClass(cls):
        from core import fpl_api
        boot = fpl_api.read_cache("bootstrap")
        cls.players = fpl_api.parse_players(boot) if boot else None

    def setUp(self):
        if self.players is None:
            self.skipTest("data/fpl/bootstrap.json not cached on this machine")

    def _root(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

    def test_model_state_is_legal_and_captained_by_fernandes(self):
        out = fpl_state.load_squad(
            os.path.join(self._root(), "games", "fpl", "state.json"),
            self.players)
        self.assertEqual(out["strategy"], "model")
        self.assertEqual(out["total_cost"], 100.0)
        cap = next(e for e in out["squad"] if e["is_captain"])
        vice = next(e for e in out["squad"] if e["is_vice"])
        self.assertEqual(cap["name"], "B.Fernandes")
        # vice is weekly content — assert existence, not identity
        self.assertTrue(vice["name"])
        self.assertNotIn("Haaland", [e["name"] for e in out["squad"]])

    def test_consensus_state_is_legal_and_captained_by_haaland(self):
        out = fpl_state.load_squad(
            os.path.join(self._root(), "games", "fpl", "state_consensus.json"),
            self.players)
        self.assertEqual(out["strategy"], "consensus")
        # total cost and bench composition are weekly content — assert
        # legality invariants only (the validator already enforced them)
        self.assertLessEqual(out["total_cost"], 100.0)
        cap = next(e for e in out["squad"] if e["is_captain"])
        self.assertEqual(cap["name"], "Haaland")
        bench = [e for e in out["squad"] if not e["is_starter"]]
        self.assertEqual(len(bench), 4)


if __name__ == "__main__":
    unittest.main()
