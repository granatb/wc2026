"""Triple Captain (owner decision 2026-09-12, GW4 on Palmer): the chip in
play travels state -> squad article -> frozen archive -> official grade."""
import unittest
from unittest import mock

from core import fpl_live, forecast_archive
from evmax import fpl_articles
from games.fpl import state as fpl_state


def _entry(name, pos, starter=True, bench=None, cap=False, vice=False):
    return {"name": name, "position": pos, "is_starter": starter, "bench_order": bench,
            "is_captain": cap, "is_vice": vice, "bought_at": 5.0}


def _squad():
    xi = ([_entry("G1", "GK")] + [_entry(f"D{i}", "DEF") for i in range(3)]
          + [_entry("M0", "MID", cap=True), _entry("M1", "MID", vice=True),
             _entry("M2", "MID"), _entry("M3", "MID")]
          + [_entry(f"F{i}", "FWD") for i in range(3)])
    bench = [_entry("G2", "GK", False, 1), _entry("M4", "MID", False, 2),
             _entry("D3", "DEF", False, 3), _entry("D4", "DEF", False, 4)]
    return xi + bench


class MultiplierTest(unittest.TestCase):
    def test_three_under_the_chip_two_otherwise(self):
        self.assertEqual(fpl_state.captain_multiplier({}), 2)
        self.assertEqual(fpl_state.captain_multiplier({"active_chip": {"gameweek": 4, "chip": "3xc"}}), 3)
        self.assertEqual(fpl_state.captain_multiplier({"active_chip": {"gameweek": 4, "chip": "bboost"}}), 2)


class SquadMetaTest(unittest.TestCase):
    def _meta(self, chip):
        squad = _squad()
        rows = [{"name": e["name"], "position": e["position"], "team": "AAA", "x_points": 4.0}
                for e in squad]
        rows[4]["x_points"] = 8.0          # M0, the captain
        state = {"team_name": "T", "strategy": "model", "squad": squad, "active_chip": chip}
        return fpl_articles.squad_article(state, rows)

    def test_projected_total_counts_the_captain_three_times(self):
        entries, plain = self._meta(None)
        _, tripled = self._meta({"gameweek": 4, "chip": "3xc"})
        self.assertEqual(plain["projected_total"], 48.0 + 8.0)
        self.assertEqual(tripled["projected_total"], 48.0 + 16.0)
        self.assertEqual(tripled["captain_multiplier"], 3)
        self.assertEqual(tripled["active_chip"], {"gameweek": 4, "chip": "3xc"})
        self.assertIsNone(plain["active_chip"])
        self.assertTrue(all(e["captain_multiplier"] == 2 for e in entries))


class GradeTest(unittest.TestCase):
    def _grade(self, chip):
        squad = _squad()
        state = {"squad": squad, "active_chip": chip}
        ids = {e["name"]: i + 1 for i, e in enumerate(squad)}
        resolved = {n: {"id": i, "team": 1} for n, i in ids.items()}
        live = {"elements": [{"id": i, "stats": {"minutes": 90, "total_points": 2}} for i in ids.values()]}
        live["elements"][ids["M0"] - 1]["stats"]["total_points"] = 10
        fixtures = [{"team_h": 1, "team_a": 2, "finished": True}]
        boot = {"teams": [{"id": 1, "short_name": "AAA"}, {"id": 2, "short_name": "BBB"}]}
        with mock.patch.object(fpl_live, "resolve_squad", return_value=resolved):
            return fpl_live.grade_squad(state, live, fixtures, boot)

    def test_official_total_triples_the_captain(self):
        plain = self._grade(None)
        tripled = self._grade({"gameweek": 4, "chip": "3xc"})
        self.assertEqual(plain["total_so_far"], 10 * 2 + 10 * 2)
        self.assertEqual(tripled["total_so_far"], 10 * 2 + 10 * 3)
        cap = next(r for r in tripled["rows"] if r["name"] == "M0")
        self.assertEqual(cap["multiplier"], 3)
        self.assertIn("Triple Captain", cap["note"])


class ArchiveTest(unittest.TestCase):
    def test_state_from_envelope_carries_the_chip(self):
        entries = [dict(name=e["name"], team="AAA", role="XI" if e["is_starter"] else "Bench",
                        is_captain=e["is_captain"], is_vice=e["is_vice"], bench_order=e["bench_order"])
                   for e in _squad()]
        env = {"gameweek": 4, "entries": entries,
               "squad": {"team_name": "T", "active_chip": {"gameweek": 4, "chip": "3xc"}}}
        st = forecast_archive.state_from_envelope(env)
        self.assertEqual(st["active_chip"], {"gameweek": 4, "chip": "3xc"})
        self.assertEqual(fpl_state.captain_multiplier(st), 3)


class StateValidationTest(unittest.TestCase):
    def test_bad_chip_is_rejected(self):
        import json
        s = json.load(open("games/fpl/state.json"))
        from core import fpl_api
        boot = fpl_api.read_cache("bootstrap")
        if boot is None:
            self.skipTest("bootstrap cache unavailable")
        players = fpl_api.parse_players(boot)
        s["active_chip"] = {"gameweek": 4, "chip": "quadruple"}
        with self.assertRaises(ValueError):
            fpl_state.validate_state(s, players)


if __name__ == "__main__":
    unittest.main()
