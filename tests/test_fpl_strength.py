"""core/fpl_strength.py — our own strength table from market odds (task 4).

Offline: synthetic odds caches shaped like data/fpl/odds_gw{N}.json (real
market entries carry no `source`; the FDR priors carry
source: "fdr_prior_calibrated_on_gw1_market_odds") through the real fit and
the model layer's odds-selection path, in a temp DATA_DIR.
"""

from __future__ import annotations

import itertools
import json
import os
import tempfile
import unittest
from unittest import mock

import config
from core import fpl_api, fpl_strength

_BASE_H = config.BASE_GOALS * config.HOME_ADV   # league-average home lambda
_BASE_A = config.BASE_GOALS                     # league-average away lambda


def _obs(gw, home, away, lam_home, lam_away):
    return {"gw": gw, "home": home, "away": away,
            "lam_home": lam_home, "lam_away": lam_away}


def _flat_prior(teams):
    return {t: (1.0, 1.0) for t in teams}


class TestFit(unittest.TestCase):
    _TEAMS = ("MCI", "AVL", "BHA", "NEW")

    def test_persistently_high_lambdas_raise_the_attack_multiplier(self):
        """A team whose matches price ~2.6 goals both weeks (league average
        ~1.4) must come out att > 1.3. With shrinkage at k=2, one match a
        week is deliberately NOT enough to clear 1.3 — the table earns
        conviction from repetition, so the shape here is a double-gameweek
        pair per week, opponents pinned near 1.0 by their own average
        matches."""
        obs = [
            _obs(1, "MCI", "AVL", 2.6, _BASE_A),
            _obs(1, "NEW", "MCI", _BASE_H, 2.6),
            _obs(1, "BHA", "SUN", _BASE_H, _BASE_A),
            _obs(2, "MCI", "BHA", 2.6, _BASE_A),
            _obs(2, "SUN", "MCI", _BASE_H, 2.6),
            _obs(2, "AVL", "NEW", _BASE_H, _BASE_A),
        ]
        table = fpl_strength.fit(obs, current_gw=2,
                                 prior=_flat_prior(self._TEAMS + ("SUN",)))
        att_mci, _def_mci = table["MCI"]
        self.assertGreater(att_mci, 1.3)

    def test_shrinkage_pulls_a_one_observation_team_toward_the_prior(self):
        obs = [_obs(1, "MCI", "AVL", 2.7, _BASE_A)]
        table = fpl_strength.fit(obs, current_gw=1,
                                 prior=_flat_prior(("MCI", "AVL")))
        att_mci, _ = table["MCI"]
        raw_implied = 2.7 / _BASE_H          # the unshrunk multiplier
        self.assertGreater(att_mci, 1.0)     # moved off the prior...
        self.assertLess(att_mci, raw_implied)  # ...but nowhere near the raw fit

    def test_recency_weight_prefers_the_later_gameweek(self):
        """gw1 says elite attack, gw10 says blunt: the table believes gw10."""
        obs = [_obs(1, "MCI", "AVL", 2.7, _BASE_A),
               _obs(10, "MCI", "AVL", 0.9, _BASE_A)]
        table = fpl_strength.fit(obs, current_gw=10,
                                 prior=_flat_prior(("MCI", "AVL")))
        self.assertLess(table["MCI"][0], 1.0)
        # mirrored: elite later wins over blunt earlier
        obs_rev = [_obs(1, "MCI", "AVL", 0.9, _BASE_A),
                   _obs(10, "MCI", "AVL", 2.7, _BASE_A)]
        table_rev = fpl_strength.fit(obs_rev, current_gw=10,
                                     prior=_flat_prior(("MCI", "AVL")))
        self.assertGreater(table_rev["MCI"][0], 1.0)

    def test_team_without_observations_keeps_the_prior(self):
        obs = [_obs(1, "MCI", "AVL", 2.0, 1.0)]
        prior = {"MCI": (1.0, 1.0), "AVL": (1.0, 1.0), "SUN": (0.8, 1.2)}
        table = fpl_strength.fit(obs, current_gw=1, prior=prior)
        self.assertEqual(table["SUN"], (0.8, 1.2))


class TestFutureLambdas(unittest.TestCase):
    _ATT = {"MCI": 1.2, "AVL": 1.0, "BHA": 0.95, "NEW": 0.9}
    _DEF = {"MCI": 0.9, "AVL": 1.0, "BHA": 1.05, "NEW": 1.1}

    def _true_lambdas(self, home, away):
        return (_BASE_H * self._ATT[home] * self._DEF[away],
                _BASE_A * self._ATT[away] * self._DEF[home])

    def test_recomputing_a_training_match_reproduces_its_lambda(self):
        """Symmetric consistency: fit on six gameweeks generated exactly from
        the multiplicative model, then re-price a training fixture — within
        15% (shrinkage toward the flat prior costs a few percent by design)."""
        teams = list(self._ATT)
        pairings = list(itertools.permutations(teams, 2))
        obs = []
        for gw in range(1, 7):
            for home, away in (pairings[(2 * gw) % len(pairings)],
                               pairings[(2 * gw + 1) % len(pairings)]):
                lh, la = self._true_lambdas(home, away)
                obs.append(_obs(gw, home, away, lh, la))
        table = fpl_strength.fit(obs, current_gw=6, prior=_flat_prior(teams))
        true_lh, true_la = self._true_lambdas("MCI", "NEW")
        lh, la = fpl_strength.future_lambdas("MCI", "NEW", table)
        self.assertLess(abs(lh - true_lh) / true_lh, 0.15)
        self.assertLess(abs(la - true_la) / true_la, 0.15)

    def test_unknown_teams_price_at_league_average(self):
        lh, la = fpl_strength.future_lambdas("XXX", "YYY", {})
        self.assertAlmostEqual(lh, _BASE_H, places=6)
        self.assertAlmostEqual(la, _BASE_A, places=6)


class TestPriorTable(unittest.TestCase):
    def test_average_fdr_lands_near_neutral(self):
        table = fpl_strength.prior_table({"SUN": 3})
        att, dfn = table["SUN"]
        self.assertLess(abs(att - 1.0), 0.1)
        self.assertLess(abs(dfn - 1.0), 0.1)

    def test_high_fdr_means_strong_defence_and_attack(self):
        """A 5-FDR opponent concedes little (low def multiplier) and, by the
        symmetric derivation, attacks more (att = 1/def)."""
        strong = fpl_strength.prior_table({"MCI": 5})["MCI"]
        weak = fpl_strength.prior_table({"SUN": 2})["SUN"]
        self.assertLess(strong[1], weak[1])
        self.assertGreater(strong[0], weak[0])


def _cache(gw, entries, source=None):
    payload = {"gameweek": gw, "captured_at": "2026-08-24T10:00:00+00:00",
               "matches": entries, "unmatched": []}
    if source:
        payload["source"] = source
    return payload


def _real_entry(home, away, lh=1.6, la=1.2):
    return {"home": home, "away": away, "lam_home": lh, "lam_away": la}


def _fdr_entry(home, away, lh=1.3, la=1.2):
    return {"home": home, "away": away, "lam_home": lh, "lam_away": la,
            "source": "fdr_prior_calibrated_on_gw1_market_odds"}


def _write(tmp, name, payload):
    with open(os.path.join(tmp, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def _row(match_id, home, away):
    return {"match_id": match_id, "home": home, "away": away,
            "kickoff_utc": "2026-09-05T14:00:00Z", "fantasy_round": 3,
            "stage": "GW"}


class TestObservations(unittest.TestCase):
    def test_reads_only_real_market_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                _write(tmp, "odds_gw1",
                       _cache(1, {"a": _real_entry("MCI", "AVL")}))
                _write(tmp, "odds_gw2",
                       _cache(2, {"b": _fdr_entry("AVL", "MCI")}))
                obs = fpl_strength.observations(before_gw=10)
                self.assertEqual([o["gw"] for o in obs], [1])
                self.assertEqual(fpl_strength.real_gw_count(10), 1)


class TestModelLayerOddsSelection(unittest.TestCase):
    """games/fpl/model.gameweek_odds — the cache-consuming path (task 4):
    the strength table re-prices absent/fdr-sourced FUTURE entries once >=2
    real gameweeks exist; the FDR prior stays the zero-data fallback; a
    priced current gameweek always wins."""

    _ROWS = [_row("fpl-3-1", "MCI", "AVL"), _row("fpl-3-2", "BHA", "NEW")]

    def _seed(self, tmp, real_gws):
        entries = {1: {"a": _real_entry("MCI", "AVL", 2.2, 0.9),
                       "b": _real_entry("BHA", "NEW", 1.4, 1.3)},
                   2: {"c": _real_entry("NEW", "MCI", 1.1, 2.1),
                       "d": _real_entry("AVL", "BHA", 1.5, 1.2)}}
        for gw in real_gws:
            _write(tmp, f"odds_gw{gw}", _cache(gw, entries[gw]))

    def test_with_two_real_gameweeks_the_strength_table_prices_gw3(self):
        from games.fpl import model as fpl_model
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._seed(tmp, (1, 2))
                _write(tmp, "odds_gw3",
                       _cache(3, {"fpl-3-1": _fdr_entry("MCI", "AVL"),
                                  "fpl-3-2": _fdr_entry("BHA", "NEW")},
                              source="fdr_prior_calibrated_on_gw1_market_odds"))
                odds = fpl_model.gameweek_odds(3, self._ROWS)
        for match_id in ("fpl-3-1", "fpl-3-2"):
            entry = odds["matches"][match_id]
            self.assertEqual(entry["source"], "strength_table_v1")
            self.assertIsNotNone(entry["lam_home"])
        # MCI priced ~2.1-2.2 across both real weeks: clearly above average
        self.assertGreater(odds["matches"]["fpl-3-1"]["lam_home"], _BASE_H)

    def test_with_one_real_gameweek_the_fdr_prior_stays(self):
        from games.fpl import model as fpl_model
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._seed(tmp, (1,))
                _write(tmp, "odds_gw3",
                       _cache(3, {"fpl-3-1": _fdr_entry("MCI", "AVL"),
                                  "fpl-3-2": _fdr_entry("BHA", "NEW")},
                              source="fdr_prior_calibrated_on_gw1_market_odds"))
                odds = fpl_model.gameweek_odds(3, self._ROWS)
        for match_id in ("fpl-3-1", "fpl-3-2"):
            self.assertTrue(odds["matches"][match_id]["source"]
                            .startswith("fdr_prior"))

    def test_current_gameweek_real_odds_always_win(self):
        from games.fpl import model as fpl_model
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._seed(tmp, (1, 2))
                _write(tmp, "odds_gw3",
                       _cache(3, {"fpl-3-1": _real_entry("MCI", "AVL",
                                                         1.9, 1.0),
                                  "fpl-3-2": _real_entry("BHA", "NEW",
                                                         1.4, 1.3)}))
                odds = fpl_model.gameweek_odds(3, self._ROWS)
        entry = odds["matches"]["fpl-3-1"]
        self.assertEqual(entry["lam_home"], 1.9)
        self.assertNotIn("source", entry)

    def test_absent_cache_with_failed_fetch_prices_from_the_table(self):
        from games.fpl import model as fpl_model

        def _boom(_gw, _rows):
            raise OSError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._seed(tmp, (1, 2))
                odds = fpl_model.gameweek_odds(3, self._ROWS, fetch=_boom)
        self.assertEqual(odds["matches"]["fpl-3-1"]["source"],
                         "strength_table_v1")


if __name__ == "__main__":
    unittest.main()
