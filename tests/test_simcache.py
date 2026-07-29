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
