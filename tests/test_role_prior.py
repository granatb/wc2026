"""The role prior (owner decision 2026-09-08): last season's start rate decays
away as this season's matches arrive, and this season's matches are weighted by
recency. Skill rates are untouched -- this is minutes only."""
import unittest

from core import fpl_api, fpl_priors


def _player(**kw):
    base = {"id": 9001, "name": "Mover", "team": "LIV", "position": "FWD",
            "price": 9.1, "status": "a", "chance_of_playing": None, "news": "",
            "minutes": 243, "starts": 3}
    base.update(kw)
    return base


def _rows(starts_by_round):
    return [{"round": r, "total_points": 2, "minutes": 90 if s else 0, "starts": s}
            for r, s in sorted(starts_by_round.items())]


class RolePriorDecayTest(unittest.TestCase):
    isak_history = {"9001": {"starts": 8, "minutes": 694}}   # 8 of 38 last season

    def test_three_starts_beat_a_fringe_last_season(self):
        # The Isak case: 27% under the old blend, despite 90/90/63.
        with fpl_priors.preseason_rates_override(self.isak_history):
            sp, mins = fpl_priors.minutes_model(_player(), 3, _rows({1: 1, 2: 1, 3: 1}))
        self.assertGreater(sp, 0.85)
        self.assertGreater(mins, 75)

    def test_aggregates_alone_give_the_same_direction(self):
        # No per-game rows: the season aggregate stands in, still decisive.
        with fpl_priors.preseason_rates_override(self.isak_history):
            sp, _ = fpl_priors.minutes_model(_player(), 3, None)
        self.assertGreater(sp, 0.85)

    def test_history_still_anchors_gameweek_one(self):
        # One start in one match must not read as a nailed starter when last
        # season says fringe -- the promoted-forward guard survives.
        with fpl_priors.preseason_rates_override(self.isak_history):
            sp, _ = fpl_priors.minutes_model(_player(minutes=90, starts=1), 1,
                                             _rows({1: 1}))
        self.assertLess(sp, 0.7)
        self.assertGreater(sp, 0.4)

    def test_prior_weight_halves_per_match(self):
        w = [fpl_priors.ROLE_PRIOR_MATCHES * fpl_priors.ROLE_PRIOR_DECAY ** n
             for n in range(4)]
        self.assertEqual(w, [4.0, 2.0, 1.0, 0.5])


class RecencyTest(unittest.TestCase):
    def test_recent_benchings_outweigh_early_starts(self):
        # Started GW1-3, benched GW4-6: the last three decide.
        with fpl_priors.preseason_rates_override({}):
            dropped, _ = fpl_priors.minutes_model(
                _player(minutes=270, starts=3), 6,
                _rows({1: 1, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0}))
            promoted, _ = fpl_priors.minutes_model(
                _player(minutes=270, starts=3), 6,
                _rows({1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1}))
        self.assertLess(dropped, 0.35)
        self.assertGreater(promoted, 0.65)
        # Same aggregate (3 of 6) -- only the order differs.
        self.assertAlmostEqual(dropped + promoted, 1.0, delta=0.15)

    def test_missing_round_is_a_non_start(self):
        with fpl_priors.preseason_rates_override({}):
            gaps, _ = fpl_priors.minutes_model(_player(minutes=180, starts=2), 3,
                                               _rows({1: 1, 3: 1}))
            full, _ = fpl_priors.minutes_model(_player(minutes=270, starts=3), 3,
                                               _rows({1: 1, 2: 1, 3: 1}))
        self.assertLess(gaps, full)

    def test_stale_rows_fall_back_to_aggregates(self):
        # Cache reaches GW2 but three gameweeks are finished: aggregates win,
        # and a cache without `starts` is treated the same way.
        with fpl_priors.preseason_rates_override({}):
            behind, _ = fpl_priors.minutes_model(_player(), 3, _rows({1: 1, 2: 1}))
            no_starts, _ = fpl_priors.minutes_model(
                _player(), 3, [{"round": r, "total_points": 2, "minutes": 90}
                               for r in (1, 2, 3)])
            aggregate, _ = fpl_priors.minutes_model(_player(), 3, None)
        self.assertEqual(behind, aggregate)
        self.assertEqual(no_starts, aggregate)


class FormCacheStartsTest(unittest.TestCase):
    def test_rows_carry_per_gameweek_starts_and_sum_doubles(self):
        rows = fpl_api.form_rows_from_history([
            {"round": 1, "total_points": 6, "minutes": 90, "starts": 1},
            {"round": 2, "total_points": 1, "minutes": 12, "starts": 0},
            {"round": 2, "total_points": 8, "minutes": 90, "starts": 1},
        ])
        self.assertEqual([r["starts"] for r in rows], [1, 1])
        self.assertEqual(rows[1]["minutes"], 102)

    def test_cache_without_starts_is_refetched_once(self):
        calls = []
        def fetch(pid):
            calls.append(pid)
            return {"history": [{"round": 1, "total_points": 2, "minutes": 90, "starts": 1}]}
        stale = {"7": [{"round": 1, "total_points": 2, "minutes": 90}]}
        fresh = {"8": [{"round": 1, "total_points": 2, "minutes": 90, "starts": 1}]}
        from unittest import mock
        with mock.patch.object(fpl_api, "read_cache", return_value={**stale, **fresh}), \
             mock.patch.object(fpl_api, "write_cache"):
            fpl_api.fetch_form_history([{"id": 7, "minutes": 90}, {"id": 8, "minutes": 90}],
                                       1, fetch=fetch, delay=0)
        self.assertEqual(calls, [7])


if __name__ == "__main__":
    unittest.main()
