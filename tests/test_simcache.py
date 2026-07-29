import os
import unittest
from unittest import mock

from core import simcache


class TestSourceFingerprint(unittest.TestCase):
    def test_fingerprint_is_stable_across_calls(self):
        self.assertEqual(simcache.source_fingerprint(), simcache.source_fingerprint())

    def test_fingerprint_is_a_hex_digest(self):
        fp = simcache.source_fingerprint()
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_fingerprint_covers_the_model_and_engine_sources(self):
        # The files whose content must invalidate the cache.
        for path in simcache.FINGERPRINT_SOURCES:
            self.assertTrue(os.path.exists(path), f"missing: {path}")
        self.assertTrue(any(p.endswith("engine_events.py")
                            for p in simcache.FINGERPRINT_SOURCES))
        self.assertTrue(any(p.endswith(os.path.join("fpl", "model.py"))
                            for p in simcache.FINGERPRINT_SOURCES))
        self.assertTrue(any(p.endswith("fpl_priors.py")
                            for p in simcache.FINGERPRINT_SOURCES))

    def test_changing_a_source_file_changes_the_fingerprint(self):
        before = simcache.source_fingerprint()
        real = simcache._read_source

        def tampered(path):
            text = real(path)
            return text + "\n# a scoring constant changed\n" if "model.py" in path else text

        with mock.patch.object(simcache, "_read_source", side_effect=tampered):
            after = simcache.source_fingerprint()
        self.assertNotEqual(before, after)

    def test_a_missing_source_file_does_not_raise(self):
        with mock.patch.object(simcache, "_read_source", side_effect=lambda p: ""):
            self.assertEqual(len(simcache.source_fingerprint()), 64)


class TestCacheKey(unittest.TestCase):
    def _inputs(self, **kw):
        base = {
            "gameweek": 1,
            "sims": 50_000,
            "seed": 12345,
            "lambdas": {"m1": (1.44, 1.35), "m2": (1.60, 1.10)},
            "priors": {"Haaland": (0.89, 0.35, 0.05, 0.0, 0.0)},
            "research": {"Haaland": "nailed"},
            "config": {"GOAL_CONCENTRATION": 1.2, "PEN_TAKER_GOAL_BONUS": 0.10},
        }
        base.update(kw)
        return base

    def test_same_inputs_give_the_same_key(self):
        self.assertEqual(simcache.cache_key(**self._inputs()),
                         simcache.cache_key(**self._inputs()))

    def test_key_is_order_independent_for_dict_inputs(self):
        a = self._inputs(priors={"A": (1.0,), "B": (2.0,)})
        b = self._inputs(priors={"B": (2.0,), "A": (1.0,)})
        self.assertEqual(simcache.cache_key(**a), simcache.cache_key(**b))

    def test_different_gameweek_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(gameweek=2)))

    def test_different_lambdas_change_the_key(self):
        other = self._inputs(lambdas={"m1": (2.10, 0.90), "m2": (1.60, 1.10)})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_priors_change_the_key(self):
        other = self._inputs(priors={"Haaland": (0.50, 0.35, 0.05, 0.0, 0.0)})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_research_changes_the_key(self):
        other = self._inputs(research={"Haaland": "doubtful"})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_sim_config_changes_the_key(self):
        other = self._inputs(config={"GOAL_CONCENTRATION": 1.6,
                                     "PEN_TAKER_GOAL_BONUS": 0.10})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_sim_count_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(sims=10_000)))

    def test_different_seed_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(seed=999)))

    def test_a_changed_model_source_changes_the_key(self):
        before = simcache.cache_key(**self._inputs())
        real = simcache._read_source

        def tampered(path):
            text = real(path)
            return text + "\n# GOAL_PTS edited\n" if "model.py" in path else text

        with mock.patch.object(simcache, "_read_source", side_effect=tampered):
            after = simcache.cache_key(**self._inputs())
        self.assertNotEqual(before, after,
                            "editing the model source MUST invalidate the cache")
