import json
import os
import tempfile
import unittest

from site import articles


class LoadPlayerMetaTest(unittest.TestCase):
    def _write(self, players):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"_comment": "x", "players": players}, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_maps_name_to_metadata(self):
        path = self._write([
            {"name": "Kane", "aliases": [], "team": "England", "fifa_pos": "FWD",
             "fifa_price": 11.0, "ownership": 42.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertEqual(meta["Kane"]["team"], "England")
        self.assertEqual(meta["Kane"]["position"], "FWD")
        self.assertEqual(meta["Kane"]["price"], 11.0)
        self.assertEqual(meta["Kane"]["ownership_pct"], 42.0)

    def test_aliases_also_resolve(self):
        path = self._write([
            {"name": "Bruno Fernandes", "aliases": ["B. Fernandes"], "team": "Portugal",
             "fifa_pos": "MID", "fifa_price": 9.5, "ownership": 18.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertIn("B. Fernandes", meta)
        self.assertEqual(meta["B. Fernandes"]["position"], "MID")


class BuildRowsTest(unittest.TestCase):
    def setUp(self):
        self.means = {
            "Kane": {"position": "FWD", "goals": 0.8, "assists": 0.2, "clean_sheet": 0.3,
                     "played": 1.0, "yellow": 0.1, "red": 0.0, "sot": 1.2, "saves": 0.0,
                     "conc_beyond": 0.4, "minutes": 90.0, "goal_share": 0.4, "assist_share": 0.2},
        }
        self.samples = {"Kane": [0, 1, 0, 2, 1]}
        self.meta = {"Kane": {"team": "England", "position": "FWD", "price": 11.0,
                              "ownership_pct": 42.0}}
        self.kickoffs = {"England": "2026-06-26T19:00:00+00:00"}

    def test_row_has_xpts_ceiling_captain_value_kickoff(self):
        rows = articles.build_rows(self.means, self.samples, self.meta, self.kickoffs)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["name"], "Kane")
        self.assertGreater(r["x_points"], 0)
        self.assertAlmostEqual(r["captain_ev"], 2 * r["x_points"], places=6)
        self.assertGreaterEqual(r["ceiling"], r["x_points"])  # P85 goals >= mean goals
        self.assertAlmostEqual(r["value"], r["x_points"] / 11.0, places=6)
        self.assertEqual(r["kickoff"], "2026-06-26T19:00:00+00:00")

    def test_players_without_meta_or_position_are_skipped(self):
        means = dict(self.means)
        means["Ghost"] = dict(self.means["Kane"])  # no meta entry
        rows = articles.build_rows(means, {"Kane": [0, 1], "Ghost": [0]}, self.meta, self.kickoffs)
        self.assertEqual([r["name"] for r in rows], ["Kane"])


def _row(name, pos, xp, own=20.0, price=8.0, ceiling=None):
    return {"name": name, "team": name + "land", "position": pos, "x_points": xp,
            "captain_ev": 2 * xp, "ceiling": ceiling if ceiling is not None else xp,
            "price": price, "ownership_pct": own, "value": xp / price, "kickoff": None}


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row("A", "FWD", 9.0, own=50.0, price=11.0),
            _row("B", "MID", 6.0, own=3.0, price=6.0),
            _row("C", "DEF", 4.5, own=1.0, price=4.0),
        ]

    def test_rank_captains_orders_by_captain_ev_desc_and_assigns_rank(self):
        out = articles.rank_captains(self.rows)
        self.assertEqual([r["name"] for r in out], ["A", "B", "C"])
        self.assertEqual(out[0]["rank"], 1)

    def test_rank_value_orders_by_value_desc(self):
        out = articles.rank_value(self.rows)
        # C: 4.5/4=1.125, B: 6/6=1.0, A: 9/11=0.818
        self.assertEqual([r["name"] for r in out], ["C", "B", "A"])

    def test_differentials_filter_low_owned_and_min_xpts(self):
        out = articles.differentials(self.rows)
        # own<10 AND x_points>=4.0 -> B(6.0,own3) and C(4.5,own1); A excluded (own 50)
        self.assertEqual(sorted(r["name"] for r in out), ["B", "C"])
        self.assertEqual(out[0]["x_points"], 6.0)  # sorted by xpts desc -> B first


class SelectXITest(unittest.TestCase):
    def _pool(self):
        rows = []
        rows += [_row(f"GK{i}", "GK", 5 - i * 0.1) for i in range(3)]
        rows += [_row(f"DEF{i}", "DEF", 6 - i * 0.1) for i in range(8)]
        rows += [_row(f"MID{i}", "MID", 7 - i * 0.1) for i in range(8)]
        rows += [_row(f"FWD{i}", "FWD", 8 - i * 0.1) for i in range(6)]
        return rows

    def test_returns_valid_xi(self):
        xi = articles.select_xi(self._pool(), "x_points")
        self.assertEqual(len(xi), articles.XI_SIZE)
        counts = {}
        for r in xi:
            counts[r["position"]] = counts.get(r["position"], 0) + 1
        self.assertEqual(counts["GK"], 1)
        self.assertGreaterEqual(counts["DEF"], 3)
        self.assertGreaterEqual(counts["MID"], 2)
        self.assertGreaterEqual(counts["FWD"], 1)
        for pos, mx in articles.POS_MAX.items():
            self.assertLessEqual(counts.get(pos, 0), mx)

    def test_ranks_by_the_given_key(self):
        # high-ceiling XI should sort on ceiling, not x_points
        pool = self._pool()
        pool[10]["ceiling"] = 99.0  # a DEF with huge ceiling
        xi = articles.select_xi(pool, "ceiling")
        self.assertEqual(xi[0]["ceiling"], 99.0)


class BlowoutTest(unittest.TestCase):
    def test_blowout_transfers_picks_attackers_from_highest_lambda_fixtures(self):
        # two fixtures; (Spain vs Malta) has the biggest combined lambda
        fixture_totals = {("Spain", "Malta"): 4.2, ("Iran", "Qatar"): 2.1}
        teams_in_blowout = {"Spain", "Malta"}
        rows = [
            _row("Oyarzabal", "FWD", 7.0), _row("Pedri", "MID", 5.5),
            _row("Cucurella", "DEF", 3.0),       # defender -> excluded (attackers only)
            _row("IranFwd", "FWD", 6.0),         # not in a blowout fixture
        ]
        for r in rows:
            r["team"] = {"Oyarzabal": "Spain", "Pedri": "Spain", "Cucurella": "Spain",
                         "IranFwd": "Iran"}[r["name"]]
        out = articles.blowout_transfers(rows, teams_in_blowout)
        self.assertEqual([r["name"] for r in out], ["Oyarzabal", "Pedri"])
        self.assertEqual(out[0]["rank"], 1)
