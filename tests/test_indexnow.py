"""IndexNow — the key file in the site chrome + the post-deploy ping (task 8).

Offline: the key-file test collects write_site_chrome's output in memory; the
ping tests feed a synthetic sitemap through the real payload builder with the
HTTP call injected. No network anywhere.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from evmax import build as wc_build

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "indexnow_ping", os.path.join(_ROOT, "scripts", "indexnow_ping.py"))
indexnow_ping = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(indexnow_ping)


_SITEMAP = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://evmax.ai/</loc></url>'
            '<url><loc>https://evmax.ai/fpl/gw2/</loc></url>'
            '<url><loc>https://evmax.ai/fpl/gw2/our-squad/</loc></url>'
            '</urlset>')


class TestKeyFileInSiteChrome(unittest.TestCase):
    def test_chrome_writes_the_key_file_at_the_root(self):
        """A deploy replaces the whole tree, so EVERY section build must
        regenerate /{key}.txt — an FPL publish that dropped it would silently
        de-verify the domain for IndexNow. The track-record build is stubbed
        (tests/test_fpl_site's e2e chrome test exercises the real one)."""
        written = {}
        with mock.patch.object(wc_build.backtest, "build_track_record",
                               return_value={}), \
             mock.patch.object(wc_build.render, "track_record_page",
                               return_value="<!doctype html>"), \
             mock.patch.object(wc_build.render, "track_record_json",
                               return_value={}):
            wc_build.write_site_chrome(lambda path, text: written.update(
                {path: text}))
        key = wc_build.indexnow_key()
        self.assertRegex(key, r"^[0-9a-f]{32}$")
        self.assertEqual(written[f"/{key}.txt"], key + "\n")


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b""


class TestPing(unittest.TestCase):
    def _run(self, opener, sitemap=_SITEMAP):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "sitemap.xml"), "w",
                      encoding="utf-8") as fh:
                fh.write(sitemap)
            out = io.StringIO()
            with redirect_stdout(out):
                code = indexnow_ping.main(["--out", tmp], opener=opener)
        return code, out.getvalue()

    def test_payload_carries_every_loc_with_host_and_key(self):
        seen = {}

        def opener(request, timeout=None):
            seen["url"] = request.full_url
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response(200)

        code, text = self._run(opener)
        self.assertEqual(code, 0)
        self.assertEqual(seen["url"], indexnow_ping.ENDPOINT)
        payload = seen["payload"]
        self.assertEqual(payload["host"], "evmax.ai")
        self.assertEqual(payload["key"], indexnow_ping.load_key())
        self.assertEqual(payload["keyLocation"],
                         f"https://evmax.ai/{payload['key']}.txt")
        self.assertEqual(payload["urlList"],
                         ["https://evmax.ai/",
                          "https://evmax.ai/fpl/gw2/",
                          "https://evmax.ai/fpl/gw2/our-squad/"])
        self.assertIn("200", text)

    def test_202_also_exits_zero(self):
        code, _ = self._run(lambda req, timeout=None: _Response(202))
        self.assertEqual(code, 0)

    def test_http_error_status_exits_one(self):
        code, text = self._run(lambda req, timeout=None: _Response(422))
        self.assertEqual(code, 1)
        self.assertIn("422", text)

    def test_network_failure_exits_one_without_a_traceback(self):
        """A failed ping must never break a deploy — print and exit 1."""
        def opener(request, timeout=None):
            raise OSError("network is down")

        code, text = self._run(opener)
        self.assertEqual(code, 1)
        self.assertIn("network is down", text)

    def test_missing_sitemap_exits_one_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                code = indexnow_ping.main(
                    ["--out", tmp],
                    opener=lambda req, timeout=None: _Response(200))
        self.assertEqual(code, 1)
        self.assertIn("sitemap", out.getvalue())

    def test_url_list_is_capped_at_the_protocol_limit(self):
        urls = "".join(f"<url><loc>https://evmax.ai/p{i}/</loc></url>"
                       for i in range(3))
        with mock.patch.object(indexnow_ping, "MAX_URLS", 2):
            seen = {}

            def opener(request, timeout=None):
                seen["payload"] = json.loads(request.data.decode("utf-8"))
                return _Response(200)

            code, _ = self._run(opener, sitemap=f"<urlset>{urls}</urlset>")
        self.assertEqual(code, 0)
        self.assertEqual(len(seen["payload"]["urlList"]), 2)


if __name__ == "__main__":
    unittest.main()
