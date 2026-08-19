"""core/fpl_odds.py — ESPN eng.1 match odds onto FPL gameweek fixtures.

Offline: every test feeds synthetic payloads shaped like the live ESPN response
(captured 2026-08-19) through the real parse/derive path. No network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import fpl_api, fpl_odds

# The 20 FPL club short names for 2026/27, from bootstrap-static (read 2026-08-19).
FPL_CLUBS_2026_27 = {
    "ARS", "AVL", "BHA", "BOU", "BRE", "CHE", "COV", "CRY", "EVE", "FUL",
    "HUL", "IPS", "LEE", "LIV", "MCI", "MUN", "NEW", "NFO", "SUN", "TOT",
}


def espn_event(event_id, home, away, kickoff, ml_home, ml_draw, ml_away,
               over_under=2.5):
    """One ESPN scoreboard event, the shape parse_scoreboard consumes."""
    def side(name, home_away):
        return {"homeAway": home_away, "team": {"displayName": name}}

    def price(american):
        return {"close": {"odds": american}}

    return {
        "id": event_id,
        "date": kickoff,
        "competitions": [{
            "competitors": [side(home, "home"), side(away, "away")],
            "status": {"type": {"name": "STATUS_SCHEDULED"}},
            "odds": [{
                "provider": {"name": "DraftKings"},
                "moneyline": {"home": price(ml_home), "away": price(ml_away)},
                "drawOdds": price(ml_draw),
                "overUnder": over_under,
                "total": {"over": price("-115"), "under": price("-105")},
            }],
        }],
    }


def fpl_row(match_id, home, away, kickoff):
    return {"match_id": match_id, "home": home, "away": away,
            "kickoff_utc": kickoff, "fantasy_round": 1, "stage": "GW"}


# Hull v Man United, real GW1 closing shape captured 2026-08-19: away heavy
# favourite. Used by several tests below.
HULL_MUN_RAW = {"events": [espn_event(
    "401879322", "Hull City", "Manchester United",
    "2026-08-22T11:30:00Z", "+700", "+400", "-260")]}
HULL_MUN_FPL_ROW = fpl_row("fpl-1-1", "HUL", "MUN", "2026-08-22T11:30:00Z")


class TestMappingCoversTheLeague(unittest.TestCase):
    def test_every_fpl_club_is_reachable(self):
        self.assertEqual(set(fpl_odds.ESPN_TO_FPL.values()), FPL_CLUBS_2026_27)

    def test_no_duplicate_targets(self):
        self.assertEqual(len(fpl_odds.ESPN_TO_FPL),
                         len(set(fpl_odds.ESPN_TO_FPL.values())))


class TestGwDates(unittest.TestCase):
    def test_unique_sorted_utc_dates(self):
        rows = [fpl_row("a", "ARS", "COV", "2026-08-21T19:00:00Z"),
                fpl_row("b", "HUL", "MUN", "2026-08-22T11:30:00Z"),
                fpl_row("c", "EVE", "CRY", "2026-08-22T14:00:00Z"),
                fpl_row("d", "FUL", "CHE", "2026-08-24T19:00:00Z")]
        self.assertEqual(fpl_odds.gw_dates(rows),
                         ["20260821", "20260822", "20260824"])


class TestMatchEspn(unittest.TestCase):
    def test_pairs_by_mapped_clubs(self):
        from core import espn
        espn_rows = espn.parse_scoreboard(HULL_MUN_RAW, 1)
        matched, unmatched = fpl_odds.match_espn(espn_rows, [HULL_MUN_FPL_ROW])
        self.assertIn("fpl-1-1", matched)
        self.assertEqual(unmatched, [])

    def test_unknown_espn_team_raises(self):
        raw = {"events": [espn_event("x", "Wrexham", "Arsenal",
                                     "2026-08-22T14:00:00Z",
                                     "+900", "+500", "-400")]}
        from core import espn
        espn_rows = espn.parse_scoreboard(raw, 1)
        with self.assertRaises(ValueError):
            fpl_odds.match_espn(
                espn_rows, [fpl_row("y", "ARS", "COV", "2026-08-22T14:00:00Z")])

    def test_fixture_espn_lacks_goes_to_unmatched(self):
        matched, unmatched = fpl_odds.match_espn([], [HULL_MUN_FPL_ROW])
        self.assertEqual(matched, {})
        self.assertEqual(unmatched, [HULL_MUN_FPL_ROW])


class TestFetchGwOdds(unittest.TestCase):
    def test_derives_lambdas_keyed_by_fpl_match_id(self):
        fetch = mock.Mock(return_value=HULL_MUN_RAW)
        out = fpl_odds.fetch_gw_odds(1, [HULL_MUN_FPL_ROW],
                                     fetch=fetch, write=False)
        fetch.assert_called_once_with("20260822", league="eng.1")
        entry = out["matches"]["fpl-1-1"]
        # Away side is a -260 favourite: its lambda must clearly exceed home's.
        self.assertGreater(entry["lam_away"], entry["lam_home"])
        self.assertGreater(entry["lam_away"], 1.5)
        self.assertLess(entry["lam_home"], 1.0)
        self.assertEqual(entry["home"], "HUL")
        self.assertEqual(entry["away"], "MUN")
        self.assertIn("captured_at", out)

    def test_unpriced_fixture_present_without_lambdas(self):
        raw = {"events": [espn_event("401", "Hull City", "Manchester United",
                                     "2026-08-22T11:30:00Z",
                                     None, None, None)]}
        fetch = mock.Mock(return_value=raw)
        out = fpl_odds.fetch_gw_odds(1, [HULL_MUN_FPL_ROW],
                                     fetch=fetch, write=False)
        entry = out["matches"]["fpl-1-1"]
        self.assertNotIn("lam_home", entry)

    def test_write_persists_to_gw_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                fetch = mock.Mock(return_value=HULL_MUN_RAW)
                fpl_odds.fetch_gw_odds(1, [HULL_MUN_FPL_ROW], fetch=fetch)
                self.assertTrue(os.path.exists(
                    os.path.join(tmp, "odds_gw1.json")))
                cached = fpl_odds.read_cached(1)
                self.assertIn("fpl-1-1", cached["matches"])

    def test_read_cached_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self.assertIsNone(fpl_odds.read_cached(7))


if __name__ == "__main__":
    unittest.main()
