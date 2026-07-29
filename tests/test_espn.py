import json
import os
import unittest
from unittest import mock

import config
from core import espn

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestEspnScoreboard(unittest.TestCase):
    def setUp(self):
        self.raw = _load("espn_scoreboard.json")

    def test_parse_schedule_and_odds(self):
        rows = espn.parse_scoreboard(self.raw, fantasy_round=2)
        self.assertEqual(len(rows), 2)
        m = rows[0]
        self.assertEqual(m["home"], "Czechia")
        self.assertEqual(m["away"], "South Africa")
        self.assertEqual(m["fantasy_round"], 2)
        self.assertAlmostEqual(m["h2h"]["home"], 1.8)   # -125 close
        self.assertAlmostEqual(m["h2h"]["away"], 4.9)   # +390 close
        self.assertEqual(m["totals"]["line"], 2.5)
        # second match has no odds -> h2h None, engine falls back to priors
        self.assertIsNone(rows[1]["h2h"])

    def test_derive_match_dc(self):
        rows = espn.parse_scoreboard(self.raw, fantasy_round=2)
        d = espn.derive_match(rows[0])
        # Czechia favourites at home (-125) so home lambda should exceed away
        self.assertGreater(d["lam_home"], d["lam_away"])
        self.assertIn("rho", d)
        self.assertAlmostEqual(sum(d["p1x2"].values()), 1.0, places=6)

    def test_derive_match_no_odds_returns_empty(self):
        rows = espn.parse_scoreboard(self.raw, fantasy_round=2)
        self.assertEqual(espn.derive_match(rows[1]), {})

    def test_derive_match_respects_devig_method_config(self):
        # config.DEVIG_METHOD picks the de-vig at the 1X2-to-lambda step. Shin/power
        # give the favourite (Czechia, -125 home) MORE fair probability than
        # proportional, which should pull lam_home up relative to the default.
        rows = espn.parse_scoreboard(self.raw, fantasy_round=2)
        with mock.patch.object(config, "DEVIG_METHOD", "proportional"):
            d_prop = espn.derive_match(rows[0])
        with mock.patch.object(config, "DEVIG_METHOD", "shin"):
            d_shin = espn.derive_match(rows[0])
        self.assertGreater(d_shin["p1x2"]["home"], d_prop["p1x2"]["home"])


class TestMatchdays(unittest.TestCase):
    def test_assign_group_matchdays_by_chronology(self):
        # A 4-team group (A,B,C,D): each team's k-th match is matchday k.
        rows = [
            {"match_id": "m1", "home": "A", "away": "B", "kickoff_utc": "2026-06-12T18:00Z"},
            {"match_id": "m2", "home": "C", "away": "D", "kickoff_utc": "2026-06-12T21:00Z"},
            {"match_id": "m3", "home": "A", "away": "C", "kickoff_utc": "2026-06-18T18:00Z"},
            {"match_id": "m4", "home": "B", "away": "D", "kickoff_utc": "2026-06-18T21:00Z"},
            {"match_id": "m5", "home": "A", "away": "D", "kickoff_utc": "2026-06-24T18:00Z"},
            {"match_id": "m6", "home": "B", "away": "C", "kickoff_utc": "2026-06-24T21:00Z"},
        ]
        tagged = {r["match_id"]: r["fantasy_round"] for r in espn.assign_group_matchdays(rows)}
        self.assertEqual(tagged["m1"], 1)
        self.assertEqual(tagged["m3"], 2)  # A's & C's 2nd game
        self.assertEqual(tagged["m5"], 3)
        # no team appears twice in any single matchday
        for md in (1, 2, 3):
            teams = [t for r in rows if r["fantasy_round"] == md for t in (r["home"], r["away"])]
            self.assertEqual(len(teams), len(set(teams)))


class TestClosingOddsPreserved(unittest.TestCase):
    """Once ESPN drops live odds, a refresh must not erase the closing line."""

    def setUp(self):
        self.mid = "TEST_CLOSE_PRESERVE"
        self.path = os.path.join(espn.ODDS_CACHE, f"{self.mid}.json")

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_no_odds_pull_keeps_prior_line_and_updates_result(self):
        espn.save_match_odds(self.mid, {"home": "A", "away": "B", "lam_home": 1.8,
                                        "lam_away": 0.8, "rho": -0.05, "status": "scheduled"})
        # later refresh: ESPN no longer prices the (now complete) match
        merged = espn.save_match_odds(self.mid, {"home": "A", "away": "B",
                                                 "status": "complete", "hs": 3, "as": 0})
        self.assertEqual(merged["lam_home"], 1.8)        # closing line preserved
        self.assertEqual(merged["lam_away"], 0.8)
        self.assertEqual(merged["odds_status"], "closing")
        self.assertEqual(merged["status"], "complete")   # result still updated
        self.assertEqual(merged["hs"], 3)

    def test_no_odds_pull_keeps_raw_markets_too(self):
        """The RAW h2h/totals/p1x2 must survive the post-kickoff odds-less refresh —
        an explicit h2h=None in the fresh pull previously clobbered the cached line
        (destroying the R1-R3 odds history the backtests depend on)."""
        h2h = {"home": 2.1, "draw": 3.4, "away": 3.6}
        totals = {"line": 2.5, "over": 1.9, "under": 1.9}
        espn.save_match_odds(self.mid, {"home": "A", "away": "B", "lam_home": 1.5,
                                        "lam_away": 1.1, "rho": -0.05,
                                        "h2h": h2h, "totals": totals,
                                        "p1x2": [0.45, 0.28, 0.27],
                                        "status": "scheduled"})
        merged = espn.save_match_odds(self.mid, {"home": "A", "away": "B",
                                                 "h2h": None, "totals": None,
                                                 "status": "complete", "hs": 1, "as": 1})
        self.assertEqual(merged["h2h"], h2h)             # raw closing markets preserved
        self.assertEqual(merged["totals"], totals)
        self.assertEqual(merged["p1x2"], [0.45, 0.28, 0.27])


class TestEspnProps(unittest.TestCase):
    def test_parse_and_goal_weights_prefers_anytime(self):
        parsed = espn.parse_propbets(_load("espn_propbets.json"))
        self.assertIn("anytime goalscorer", parsed)
        self.assertIn("first goalscorer", parsed)
        names = {
            "http://x/athletes/212330?lang=en": "Patrik Schick",
            "http://x/athletes/257336?lang=en": "Tomas Chory",
        }
        weights = espn.goal_weights(parsed, names)
        # anytime market preferred; Schick (+160) a higher rate than Chory (+215)
        self.assertIn("Patrik Schick", weights)
        self.assertGreater(weights["Patrik Schick"], weights["Tomas Chory"])


class TestLeagueParameterisation(unittest.TestCase):
    def test_default_league_is_the_world_cup(self):
        self.assertEqual(espn.league_slug(), "fifa.world")

    def test_scoreboard_url_follows_the_configured_league(self):
        with mock.patch.object(config, "ESPN_LEAGUE", "eng.1"):
            self.assertIn("/soccer/eng.1/scoreboard", espn.scoreboard_url())

    def test_core_url_follows_the_configured_league(self):
        with mock.patch.object(config, "ESPN_LEAGUE", "eng.1"):
            self.assertIn("/leagues/eng.1", espn.core_url())

    def test_world_cup_urls_unchanged_by_default(self):
        self.assertIn("/soccer/fifa.world/scoreboard", espn.scoreboard_url())


if __name__ == "__main__":
    unittest.main()
