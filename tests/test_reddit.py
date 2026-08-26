"""core/reddit.py — the read-only official-API client, entirely offline.

Every test feeds synthetic payloads shaped like Reddit's real responses. No
network, no credentials: the module must degrade to "not configured" exactly
like core/growth's sources do, so a runbook step can skip it cleanly.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from core import reddit


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(payload):
    def _open(req, timeout=None):
        return _Resp(json.dumps(payload).encode())
    return _open


LISTING = {"data": {"children": [
    {"data": {"id": "abc123", "title": "Rate my team", "author": "u1",
              "score": 42, "num_comments": 7, "created_utc": 1.0,
              "permalink": "/r/FantasyPL/comments/abc123/rate/",
              "selftext": "body text", "subreddit": "FantasyPL"}},
    {"data": {"id": "def456", "title": "Captain thread", "author": "u2",
              "score": 5, "num_comments": 0, "created_utc": 2.0,
              "permalink": "/r/FantasyPL/comments/def456/cap/",
              "selftext": "", "subreddit": "FantasyPL"}}]}}

COMMENTS = [
    {"data": {"children": []}},
    {"data": {"children": [
        {"kind": "t1", "data": {"author": "a", "score": 9, "body": "top level",
                                "replies": {"data": {"children": [
                                    {"kind": "t1", "data": {"author": "b", "score": 3,
                                                            "body": "nested reply"}}]}}}},
        {"kind": "more", "data": {"count": 12}},
    ]}},
]


class TestConfiguration(unittest.TestCase):
    def test_unconfigured_without_credentials(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(reddit.configured())

    def test_configured_with_both_credentials(self):
        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "x",
                                            "REDDIT_CLIENT_SECRET": "y"}):
            self.assertTrue(reddit.configured())

    def test_search_returns_none_when_unconfigured(self):
        """None, never an exception: an unconfigured source must not break a
        runbook step that merely wanted to look."""
        reddit._token_cache.clear()
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(reddit.search("anything"))


class TestToken(unittest.TestCase):
    def setUp(self):
        reddit._token_cache.clear()

    def test_app_only_grant_needs_no_password(self):
        seen = {}

        def _open(req, timeout=None):
            seen["url"] = req.full_url
            seen["body"] = req.data.decode()
            seen["auth"] = req.headers.get("Authorization")
            seen["ua"] = req.headers.get("User-agent")
            return _Resp(json.dumps({"access_token": "tok",
                                     "expires_in": 3600}).encode())

        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "cid",
                                            "REDDIT_CLIENT_SECRET": "sec"}):
            self.assertEqual(reddit.token(opener=_open, now=1000.0), "tok")
        self.assertIn("grant_type=client_credentials", seen["body"])
        self.assertNotIn("password", seen["body"])
        self.assertTrue(seen["auth"].startswith("Basic "))
        self.assertIn("evmax", seen["ua"])

    def test_token_is_cached_until_near_expiry(self):
        calls = []

        def _open(req, timeout=None):
            calls.append(1)
            return _Resp(json.dumps({"access_token": "tok",
                                     "expires_in": 3600}).encode())

        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "cid",
                                            "REDDIT_CLIENT_SECRET": "sec"}):
            reddit.token(opener=_open, now=1000.0)
            reddit.token(opener=_open, now=2000.0)     # still fresh
            self.assertEqual(len(calls), 1)
            reddit.token(opener=_open, now=4600.0)     # past expiry
            self.assertEqual(len(calls), 2)


class TestParsers(unittest.TestCase):
    def test_listing_parses_to_flat_rows(self):
        rows = reddit.parse_listing(LISTING)
        self.assertEqual([r["id"] for r in rows], ["abc123", "def456"])
        self.assertEqual(rows[0]["score"], 42)
        self.assertTrue(rows[0]["permalink"].startswith("https://reddit.com/r/"))

    def test_unknown_shape_yields_no_rows(self):
        self.assertEqual(reddit.parse_listing({}), [])
        self.assertEqual(reddit.parse_listing({"data": {}}), [])

    def test_comments_flatten_and_drop_more_stubs(self):
        rows = reddit.parse_comments(COMMENTS)
        self.assertEqual([c["body"] for c in rows], ["top level", "nested reply"])

    def test_comments_tolerate_a_bad_payload(self):
        self.assertEqual(reddit.parse_comments([]), [])
        self.assertEqual(reddit.parse_comments({}), [])


class TestReadPaths(unittest.TestCase):
    def setUp(self):
        reddit._token_cache.update({"value": "tok", "expires": 1e12})

    def tearDown(self):
        reddit._token_cache.clear()

    def _run(self, fn, payload, **kw):
        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "cid",
                                            "REDDIT_CLIENT_SECRET": "sec"}), \
             mock.patch.object(reddit, "MIN_INTERVAL", 0):
            return fn(opener=_opener(payload), **kw)

    def test_search_restricts_to_the_subreddit(self):
        seen = {}

        def _open(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.headers.get("Authorization")
            return _Resp(json.dumps(LISTING).encode())

        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "cid",
                                            "REDDIT_CLIENT_SECRET": "sec"}), \
             mock.patch.object(reddit, "MIN_INTERVAL", 0):
            rows = reddit.search("watkins", subreddit="FantasyPL", opener=_open)
        self.assertEqual(len(rows), 2)
        self.assertIn("/r/FantasyPL/search", seen["url"])
        self.assertIn("restrict_sr=1", seen["url"])
        self.assertEqual(seen["auth"], "bearer tok")

    def test_hot_and_comments_read(self):
        self.assertEqual(len(self._run(reddit.hot, LISTING)), 2)
        rows = self._run(reddit.post_comments, COMMENTS, post_id="abc123")
        self.assertEqual(len(rows), 2)

    def test_http_error_degrades_to_none(self):
        import urllib.error

        def _open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)

        with mock.patch.dict("os.environ", {"REDDIT_CLIENT_ID": "cid",
                                            "REDDIT_CLIENT_SECRET": "sec"}), \
             mock.patch.object(reddit, "MIN_INTERVAL", 0):
            self.assertIsNone(reddit.search("x", opener=_open))


class TestNoWritePath(unittest.TestCase):
    """Standing owner policy: outbound Reddit activity is his, disclosed and
    manual. The module must contain no way to post, vote or message — this is
    a structural guarantee, not a convention."""

    def test_module_exposes_no_write_capability(self):
        import inspect
        src = inspect.getsource(reddit)
        for banned in ("/api/submit", "/api/comment", "/api/vote",
                       "/api/compose", "method=\"POST\"", "'POST'"):
            self.assertNotIn(banned, src)
        for name in ("submit", "comment_on", "vote", "reply", "post_to"):
            self.assertFalse(hasattr(reddit, name), f"write path found: {name}")


if __name__ == "__main__":
    unittest.main()
