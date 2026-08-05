"""Growth measurement: Cloudflare zone analytics."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from core.growth import cloudflare


class TestCloudflareParse(unittest.TestCase):
    RESPONSE = {
        "data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": [
            {"dimensions": {"clientRequestPath": "/fpl/gw1/captains/",
                            "clientRefererHost": "www.reddit.com"},
             "count": 412},
            {"dimensions": {"clientRequestPath": "/fpl/gw1/captains/",
                            "clientRefererHost": "www.google.com"},
             "count": 190},
            {"dimensions": {"clientRequestPath": "/", "clientRefererHost": ""},
             "count": 88},
        ]}]}}
    }

    def test_requests_by_path_sums_across_referrers(self):
        out = cloudflare.parse(self.RESPONSE)
        self.assertEqual(out["by_path"]["/fpl/gw1/captains/"], 602)
        self.assertEqual(out["by_path"]["/"], 88)

    def test_requests_by_referrer(self):
        out = cloudflare.parse(self.RESPONSE)
        self.assertEqual(out["by_referrer"]["www.reddit.com"], 412)

    def test_empty_referrer_is_direct_not_a_blank_key(self):
        """A blank referrer host is direct traffic; a report printing an empty
        string as a traffic source is unreadable."""
        self.assertEqual(cloudflare.parse(self.RESPONSE)["by_referrer"]["direct"], 88)

    def test_total(self):
        self.assertEqual(cloudflare.parse(self.RESPONSE)["total"], 690)

    def test_a_graphql_error_response_parses_as_none(self):
        """Cloudflare returns HTTP 200 with an `errors` key on a bad query, so a
        status check alone would read a failure as success."""
        self.assertIsNone(cloudflare.parse({"errors": [{"message": "nope"}]}))

    def test_an_empty_zone_list_is_not_a_crash(self):
        out = cloudflare.parse({"data": {"viewer": {"zones": []}}})
        self.assertEqual(out["total"], 0)
        self.assertEqual(out["by_path"], {})

    def test_a_malformed_response_parses_as_none(self):
        self.assertIsNone(cloudflare.parse({}))
        self.assertIsNone(cloudflare.parse(None))


class TestCloudflareConfigured(unittest.TestCase):
    def test_not_configured_without_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cloudflare.configured())

    def test_not_configured_with_only_a_token(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t"}, clear=True):
            self.assertFalse(cloudflare.configured())

    def test_configured_with_both_values(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t",
                                          "CLOUDFLARE_ZONE_ID": "z"}, clear=True):
            self.assertTrue(cloudflare.configured())

    def test_fetch_returns_none_when_unconfigured(self):
        """The contract: never raise on a missing credential."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(cloudflare.fetch("2026-08-01", "2026-08-04"))

    def test_fetch_returns_none_on_a_network_error(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t",
                                          "CLOUDFLARE_ZONE_ID": "z"}, clear=True):
            with mock.patch.object(cloudflare, "_post",
                                   side_effect=OSError("no route to host")):
                self.assertIsNone(cloudflare.fetch("2026-08-01", "2026-08-04"))

    def test_the_token_never_appears_in_the_returned_data(self):
        """Reports get read and pasted; a credential must not ride along."""
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "SECRET123",
                                          "CLOUDFLARE_ZONE_ID": "z"}, clear=True):
            with mock.patch.object(cloudflare, "_post",
                                   return_value=TestCloudflareParse.RESPONSE):
                out = cloudflare.fetch("2026-08-01", "2026-08-04")
        self.assertNotIn("SECRET123", repr(out))


if __name__ == "__main__":
    unittest.main()
