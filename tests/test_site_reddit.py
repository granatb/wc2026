import unittest

from evmax import reddit, render


class RedditKitTest(unittest.TestCase):
    def setUp(self):
        self.entries_map = {
            "captains": [
                {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal",
                 "captain_ev": 11.34, "ceiling": 9.1, "ownership_pct": 18.0,
                 "x_points": 5.67, "price": 9.5, "value": 0.6},
                {"rank": 2, "name": "Harry Kane", "team": "England",
                 "captain_ev": 10.80, "ceiling": 8.4, "ownership_pct": 38.6,
                 "x_points": 5.4, "price": 10.0, "value": 0.54},
                {"rank": 3, "name": "Lionel Messi", "team": "Argentina",
                 "captain_ev": 9.90, "ceiling": 8.0, "ownership_pct": 25.8,
                 "x_points": 4.95, "price": 9.0, "value": 0.55},
            ],
            "matches": [
                {"match": "France vs Germany", "home": "France", "away": "Germany",
                 "kickoff": "2026-06-27T18:00:00+00:00",
                 "exp_home_goals": 1.8, "exp_away_goals": 1.7, "exp_total": 3.5,
                 "top_scoreline": "2-1", "p_home": 0.38, "p_draw": 0.28, "p_away": 0.34,
                 "close": True},
                {"match": "Brazil vs Morocco", "home": "Brazil", "away": "Morocco",
                 "kickoff": "2026-06-27T21:00:00+00:00",
                 "exp_home_goals": 2.3, "exp_away_goals": 0.6, "exp_total": 2.9,
                 "top_scoreline": "2-0", "p_home": 0.71, "p_draw": 0.18, "p_away": 0.11,
                 "close": False},
            ],
        }
        self.prose_map = {
            "captains": {
                "headline": "Bruno Fernandes leads the armband race in Round 3",
                "standfirst": "Bruno Fernandes tops captain EV at 11.34 pts.",
                "body_html": "<p>...</p>",
                "bottom_line": "Back Bruno Fernandes.",
                "source": "template",
            },
            "matches": {
                "headline": "Round 3 match predictions",
                "standfirst": "2 fixtures simulated; 1 close game.",
                "body_html": "<p>...</p>",
                "bottom_line": "Watch France vs Germany.",
                "source": "template",
            },
        }
        self.date_str = "27 June 2026"

    def test_kit_has_disclosed_affiliation_line(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("I run evmax.ai", kit)

    def test_kit_has_top_captain_table_row(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("Bruno Fernandes", kit)
        self.assertIn("Portugal", kit)
        self.assertIn("11.34", kit)

    def test_kit_has_close_game_name(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("France vs Germany", kit)

    def test_kit_has_site_link(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn(render.SITE_URL, kit)

    def test_kit_has_etiquette_header(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("Posting etiquette", kit)

    def test_kit_has_track_record_honesty_line(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("track-record", kit.lower())

    def test_kit_has_soccer_section_with_scorelines(self):
        kit = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("r/soccer", kit)
        self.assertIn("Brazil vs Morocco", kit)

    def test_kit_is_deterministic(self):
        kit1 = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        kit2 = reddit.reddit_kit(3, self.entries_map, self.prose_map, self.date_str)
        self.assertEqual(kit1, kit2)

    def test_kit_titles_reference_round_number(self):
        kit = reddit.reddit_kit(5, self.entries_map, self.prose_map, self.date_str)
        self.assertIn("Round 5", kit)


if __name__ == "__main__":
    unittest.main()
