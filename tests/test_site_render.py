import json
import unittest

from evmax import render


class JsonEnvelopeTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]

    def test_envelope_has_required_fields(self):
        env = render.article_json("fifa_world_cup_fantasy", 3, "captains",
                                  "Best captain picks — Round 3",
                                  "2026-06-24T12:00:00+00:00", 50000, self.entries)
        self.assertEqual(env["competition"], "fifa_world_cup_fantasy")
        self.assertEqual(env["round"], 3)
        self.assertEqual(env["article"], "captains")
        self.assertEqual(env["sims"], 50000)
        self.assertEqual(env["entries"][0]["name"], "Bruno Fernandes")
        self.assertIn("methodology", env)
        self.assertEqual(env["source"], "https://evmax.ai")
        # must be JSON-serializable
        json.dumps(env)

    def test_summary_sentence_is_stat_dense(self):
        s = render.summary_sentence("captains", self.entries)
        self.assertIn("Bruno Fernandes", s)
        self.assertIn("11.3", s)  # captain EV, one decimal

    def test_summary_sentence_efficiency_mentions_value(self):
        entries = [{"name": "Amad Diallo", "team": "CIV", "x_points": 8.55, "price": 5.5,
                    "value": 1.55, "ownership_pct": 1.0}]
        s = render.summary_sentence("efficiency", entries)
        self.assertIn("Amad Diallo", s)
        self.assertIn("8.55", s)   # xPts
        self.assertIn("5.5", s)    # price

    def test_summary_sentence_fixtures_mentions_clean_sheet_pct(self):
        """fixtures entries have no x_points key -- summary_sentence must not fall
        through to the generic branch, which would KeyError on x_points."""
        entries = [{"name": "England", "team": "vs Senegal", "p_clean_sheet": 0.62,
                    "exp_goals_for": 2.5, "exp_goals_against": 0.3, "env": "balanced"}]
        s = render.summary_sentence("fixtures", entries)
        self.assertIn("England", s)
        self.assertIn("62%", s)

    def test_summary_sentence_wildcard_mentions_cost_and_formation(self):
        entries = (
            [{"name": f"XI{i}", "position": pos, "x_points": 5.0, "price": 6.0,
              "role": "XI"}
             for i, pos in enumerate(
                 ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"])]
            + [{"name": f"B{i}", "position": pos, "x_points": 2.0, "price": 4.0,
                "role": "Bench"}
               for i, pos in enumerate(["GK", "DEF", "DEF", "DEF"])]
        )
        s = render.summary_sentence("wildcard", entries)
        self.assertIn("3-4-3", s)
        self.assertIn("82.0", s)  # 11 XI * 6.0 + 4 bench * 4.0 price
        self.assertIn("55.0", s)  # 11 XI * 5.0 xPts

    def test_article_json_extra_fields_merged(self):
        env = render.article_json("fifa_world_cup_fantasy", 5, "wildcard",
                                  "Wildcard draft — Round 5",
                                  "2026-06-24T12:00:00+00:00", 50000, self.entries,
                                  extra_fields={"squad": {"total_cost": 99.5}})
        self.assertIn("squad", env)
        self.assertEqual(env["squad"]["total_cost"], 99.5)
        json.dumps(env)

    def test_article_json_without_extra_fields_unchanged(self):
        env = render.article_json("fifa_world_cup_fantasy", 3, "captains",
                                  "Best captain picks — Round 3",
                                  "2026-06-24T12:00:00+00:00", 50000, self.entries)
        self.assertNotIn("squad", env)


class SvgChartTest(unittest.TestCase):
    def test_svg_contains_bars_and_labels(self):
        svg = render.svg_bar_chart([("Bruno", 11.3), ("Wirtz", 10.1), ("Kane", 9.2)], "EV")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("</svg>", svg)
        self.assertEqual(svg.count("<rect"), 3)
        self.assertIn("Bruno", svg)
        self.assertIn("11.3", svg)

    def test_empty_input_is_safe(self):
        svg = render.svg_bar_chart([], "EV")
        self.assertTrue(svg.startswith("<svg"))


# ── sample data shared by HtmlTest, PitchSvgTest, EvBarTest ──────────────────

_SAMPLE_XI = [
    {"rank": 1,  "name": "Harry Kane",    "team": "ENG", "position": "FWD",
     "x_points": 9.16, "captain_ev": 18.31, "ownership_pct": 38.6},
    {"rank": 2,  "name": "Lionel Messi",  "team": "ARG", "position": "FWD",
     "x_points": 9.03, "captain_ev": 18.06, "ownership_pct": 25.8},
    {"rank": 3,  "name": "Amad Diallo",   "team": "CIV", "position": "FWD",
     "x_points": 8.55, "captain_ev": 17.10, "ownership_pct": 1.0},
    {"rank": 4,  "name": "Florian Wirtz", "team": "GER", "position": "MID",
     "x_points": 7.80, "captain_ev": 15.60, "ownership_pct": 12.0},
    {"rank": 5,  "name": "Ismael Saibari","team": "MAR", "position": "MID",
     "x_points": 7.50, "captain_ev": 15.00, "ownership_pct": 3.0},
    {"rank": 6,  "name": "Phil Foden",    "team": "ENG", "position": "MID",
     "x_points": 7.20, "captain_ev": 14.40, "ownership_pct": 18.0},
    {"rank": 7,  "name": "Jamal Musiala", "team": "GER", "position": "MID",
     "x_points": 7.00, "captain_ev": 14.00, "ownership_pct": 22.0},
    {"rank": 8,  "name": "Noussair Mazraoui", "team": "MAR", "position": "DEF",
     "x_points": 5.80, "captain_ev": 11.60, "ownership_pct": 8.0},
    {"rank": 9,  "name": "Kieran Trippier","team": "ENG", "position": "DEF",
     "x_points": 5.60, "captain_ev": 11.20, "ownership_pct": 14.0},
    {"rank": 10, "name": "David Raum",    "team": "GER", "position": "DEF",
     "x_points": 5.40, "captain_ev": 10.80, "ownership_pct": 6.0},
    {"rank": 11, "name": "Yassine Bounou","team": "MAR", "position": "GK",
     "x_points": 5.00, "captain_ev": 10.00, "ownership_pct": 11.0},
]

_SAMPLE_PROSE = {
    "headline": "Back Kane — but the brave move is Amad Diallo.",
    "standfirst": ("50,000 simulations make England's striker the safe armband. "
                   "They also flag a 1%-owned forward as the highest-leverage punt."),
    "body_html": ("<p>The model ran every Round 3 fixture 50,000 times. "
                  "<b>Harry Kane</b> comes out on top: 9.16 expected points, "
                  "or <b>18.31 as captain</b>.</p>"),
    "bottom_line": "Hold Kane if you have him.",
    "source": "template",
}


class HtmlTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]
        self.nav = [("captains", "Best captain picks"), ("best-xi", "Best World Cup Fantasy XI")]
        self.prose = {
            "headline": "Bruno Fernandes leads the captain board",
            "standfirst": "Portugal's midfielder tops this round's captain EV at 11.34.",
            "body_html": "<p>Bruno Fernandes projects <b>11.34 captain EV</b> this round.</p>",
            "bottom_line": "Captain Bruno Fernandes.",
            "source": "template",
        }
        self.viz_html = '<svg viewBox="0 0 100 40"><rect width="80" height="20" fill="#0f7a45"/></svg>'

    def test_article_page_has_head_jsonld_table_and_summary(self):
        h = render.article_page(
            round_no=3, article="captains",
            title="Best captain picks — Round 3",
            prose=self.prose,
            entries=self.entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json",
            viz_html=self.viz_html,
            generated_at="2026-06-24T12:00:00+00:00")
        self.assertIn("<!doctype html>", h.lower())
        self.assertIn("application/ld+json", h)         # JSON-LD present
        self.assertIn("Bruno Fernandes", h)
        self.assertIn("11.3", h)                         # captain EV appears in table
        self.assertIn('rel="alternate"', h)              # link to JSON
        self.assertIn("Monte-Carlo", h)                  # methodology
        # Fixed nav: Home and About links
        self.assertIn('href="/"', h)
        self.assertIn('href="/about/"', h)
        # No per-article nav links (old nav parameter removed)
        self.assertNotIn("/round/3/captains/", h.split('<nav>')[1].split('</nav>')[0])

    def test_article_page_has_article_schema_and_prose_headline(self):
        h = render.article_page(
            round_no=3, article="captains",
            title="Best captain picks — Round 3",
            prose=self.prose,
            entries=self.entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json",
            viz_html=self.viz_html,
            generated_at="2026-06-24T12:00:00+00:00",
            date_str="24 June 2026")
        self.assertIn('"Article"', h)                           # Article JSON-LD type
        self.assertIn(self.prose["headline"], h)                # prose headline rendered
        self.assertIn("datePublished", h)                       # datePublished in Article LD
        self.assertIn("2026-06-24T12:00:00+00:00", h)          # generated_at value present
        self.assertIn("24 June 2026", h)                        # date_str in byline
        self.assertNotIn("&amp;", h.split(
            '<script type="application/ld+json">')[1].split("</script>")[0])  # no double-escaping in LD

    def test_low_ceiling_captain_gets_safe_floor_chip(self):
        entries = [
            {"rank": 1, "name": "Boring Keeper", "team": "France", "position": "GK",
             "x_points": 5.16, "captain_ev": 10.32, "ceiling": 5.16,
             "ceiling_ratio": 1.0, "price": 5.0, "ownership_pct": 8.9,
             "value": 1.0, "kickoff": None},
        ]
        h = render.article_page(
            round_no=5, article="captains", title="Best captain picks — Round 5",
            prose=self.prose, entries=entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/5/captains.json", viz_html=self.viz_html)
        self.assertIn("Safe floor", h)

    def test_high_ceiling_player_has_no_safe_floor_chip(self):
        entries = [
            {"rank": 1, "name": "Boom Striker", "team": "Brazil", "position": "FWD",
             "x_points": 5.0, "captain_ev": 10.0, "ceiling": 12.0,
             "ceiling_ratio": 2.4, "price": 9.0, "ownership_pct": 30.0,
             "value": 0.55, "kickoff": None},
        ]
        h = render.article_page(
            round_no=5, article="captains", title="Best captain picks — Round 5",
            prose=self.prose, entries=entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/5/captains.json", viz_html=self.viz_html)
        self.assertNotIn("Safe floor", h)

    def test_low_advance_probability_gets_advance_risk_chip(self):
        entries = [
            {"rank": 1, "name": "Risky Pick", "team": "Coinflip FC", "position": "FWD",
             "x_points": 6.0, "priority_score": 1.2, "vor": 0.8, "p_advance": 45.0,
             "price": 7.0, "ownership_pct": 12.0, "kickoff": None},
        ]
        h = render.article_page(
            round_no=5, article="transfers", title="Priority transfers — Round 5",
            prose=self.prose, entries=entries,
            columns=["priority_score", "vor", "p_advance"],
            json_url="/api/round/5/transfers.json", viz_html=self.viz_html)
        self.assertIn("Advance risk", h)

    def test_bench_role_gets_bench_chip(self):
        entries = [
            {"rank": 1, "name": "Star Striker", "team": "Brazil", "position": "FWD",
             "x_points": 8.0, "captain_ev": 16.0, "ceiling": 10.0, "price": 12.0,
             "ownership_pct": 40.0, "value": 0.67, "role": "XI", "kickoff": None},
            {"rank": 12, "name": "Backup Keeper", "team": "Brazil", "position": "GK",
             "x_points": 3.0, "captain_ev": 6.0, "ceiling": 3.0, "price": 4.0,
             "ownership_pct": 2.0, "value": 0.75, "role": "Bench", "kickoff": None},
        ]
        h = render.article_page(
            round_no=5, article="wildcard", title="Wildcard draft — Round 5",
            prose=self.prose, entries=entries,
            columns=["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
            json_url="/api/round/5/wildcard.json", viz_html=self.viz_html)
        self.assertIn("Bench", h)
        self.assertNotIn("Bench", h.split("Star Striker")[1].split("</tr>")[0])

    def test_fixture_guide_columns_render_formatted_values(self):
        entries = [
            {"rank": 1, "name": "England", "team": "vs Senegal", "position": "—",
             "p_clean_sheet": 0.62, "exp_goals_for": 2.5, "exp_goals_against": 0.3,
             "env": "balanced", "top_def": "Trippier (5.2)", "top_gk": "Pickford (5.7)"},
        ]
        h = render.article_page(
            round_no=5, article="fixtures", title="Fixture guide — Round 5",
            prose=self.prose, entries=entries,
            columns=["p_clean_sheet", "exp_goals_against", "exp_goals_for", "top_def", "top_gk"],
            json_url="/api/round/5/fixtures.json", viz_html=self.viz_html)
        self.assertIn("62%", h)                # p_clean_sheet formatted as a percent
        self.assertIn("Trippier (5.2)", h)     # top_def passthrough
        self.assertIn("Pickford (5.7)", h)     # top_gk passthrough
        self.assertIn("CS %", h)               # column header label
        self.assertIn("Best DEF", h)
        self.assertIn("Best GK", h)

    def test_blowout_env_gets_blowout_chip(self):
        entries = [
            {"rank": 1, "name": "France", "team": "vs Panama", "position": "—",
             "p_clean_sheet": 0.55, "exp_goals_for": 2.9, "exp_goals_against": 0.4,
             "env": "blowout", "top_def": "—", "top_gk": "—"},
        ]
        h = render.article_page(
            round_no=5, article="fixtures", title="Fixture guide — Round 5",
            prose=self.prose, entries=entries,
            columns=["p_clean_sheet", "exp_goals_against", "exp_goals_for", "top_def", "top_gk"],
            json_url="/api/round/5/fixtures.json", viz_html=self.viz_html)
        self.assertIn("Blowout", h)

    def test_avoid_env_gets_fade_forwards_chip(self):
        entries = [
            {"rank": 1, "name": "Belgium", "team": "vs Iran", "position": "—",
             "p_clean_sheet": 0.5, "exp_goals_for": 1.0, "exp_goals_against": 0.8,
             "env": "avoid", "top_def": "—", "top_gk": "—"},
        ]
        h = render.article_page(
            round_no=5, article="fixtures", title="Fixture guide — Round 5",
            prose=self.prose, entries=entries,
            columns=["p_clean_sheet", "exp_goals_against", "exp_goals_for", "top_def", "top_gk"],
            json_url="/api/round/5/fixtures.json", viz_html=self.viz_html)
        self.assertIn("Low-goal", h)
        self.assertIn("fade forwards", h)

    def test_balanced_env_gets_no_env_chip(self):
        entries = [
            {"rank": 1, "name": "Japan", "team": "vs Croatia", "position": "—",
             "p_clean_sheet": 0.4, "exp_goals_for": 1.3, "exp_goals_against": 1.2,
             "env": "balanced", "top_def": "—", "top_gk": "—"},
        ]
        h = render.article_page(
            round_no=5, article="fixtures", title="Fixture guide — Round 5",
            prose=self.prose, entries=entries,
            columns=["p_clean_sheet", "exp_goals_against", "exp_goals_for", "top_def", "top_gk"],
            json_url="/api/round/5/fixtures.json", viz_html=self.viz_html)
        self.assertNotIn("Blowout", h)
        self.assertNotIn("Low-goal", h)

    def test_hub_page_links_all_articles(self):
        h = render.hub_page(round_no=3, nav=self.nav,
                            highlights={"captains": "Captain Bruno Fernandes (11.3 EV)"})
        self.assertIn("Best captain picks", h)
        self.assertIn("/round/3/captains/", h)
        self.assertIn("Captain Bruno Fernandes", h)

    def test_landing_page_featured_and_feed(self):
        feed = [
            {"slug": "best-xi", "headline": "The model's Round 3 XI",
             "teaser": "A 3-4-3 built around Kane.", "stat_value": "58.7",
             "stat_label": "total xPts"},
            {"slug": "risky", "headline": "Three low-owned forwards worth picking",
             "teaser": "Diallo leads the ceiling board.",
             "stat_value": "1.0%", "stat_label": "top pick owned"},
            {"slug": "efficiency", "headline": "Best value picks this round",
             "teaser": "Diallo at 1.45 xPts/million.",
             "stat_value": "1.45", "stat_label": "xPts / million"},
        ]
        featured = {
            "slug": "captains",
            "prose": _SAMPLE_PROSE,
            "viz_html": self.viz_html,
        }
        h = render.landing_page(round_no=3, featured=featured, feed=feed, date_str="24 June 2026")
        self.assertIn(_SAMPLE_PROSE["headline"], h)             # featured headline
        self.assertIn("Round 3 XI", h)                          # feed card 1 (apostrophe escaped)
        self.assertIn("Three low-owned forwards worth picking", h)  # feed card 2
        self.assertIn("Best value picks this round", h)         # feed card 3
        self.assertIn("/round/3/best-xi/", h)                   # feed card links
        self.assertIn("/round/3/risky/", h)
        self.assertIn("/round/3/captains/", h)                  # featured link
        self.assertIn("24 June 2026", h)                        # date_str in byline
        # Fixed nav has Home and About
        self.assertIn('href="/"', h)
        self.assertIn('href="/about/"', h)

    def test_landing_with_fixtures_uses_grid_areas_and_fold_label(self):
        fixtures = [
            {"home": "France", "away": "Paraguay", "kickoff": "2026-07-04T17:00:00+00:00",
             "p_home": 0.68, "p_draw": 0.2, "p_away": 0.12, "close": False,
             "top_scoreline": "2-0", "exp_home_goals": 2.1, "exp_away_goals": 0.4},
        ]
        featured = {"slug": "captains", "prose": _SAMPLE_PROSE, "viz_html": ""}
        h = render.landing_page(round_no=5, featured=featured, feed=[],
                                date_str="4 July 2026", fixtures=fixtures)
        self.assertIn('grid-template-areas', h)
        self.assertIn('class="feat-area"', h)
        self.assertIn('class="feed-area"', h)
        self.assertIn('id="rail-toggle"', h)
        self.assertIn('for="rail-toggle"', h)
        self.assertIn("Quick picks", h)
        # feat-area must come before rail in DOM order (featured stays first)
        self.assertLess(h.index('class="feat-area"'), h.index('id="rail-toggle"'))

    def test_landing_rail_row_shows_date_and_xg_line(self):
        fixtures = [
            {"home": "France", "away": "Paraguay", "kickoff": "2026-07-04T17:00:00+00:00",
             "p_home": 0.68, "p_draw": 0.2, "p_away": 0.12, "close": False,
             "top_scoreline": "1-1", "exp_home_goals": 1.24, "exp_away_goals": 1.07},
        ]
        featured = {"slug": "captains", "prose": _SAMPLE_PROSE, "viz_html": ""}
        h = render.landing_page(round_no=5, featured=featured, feed=[],
                                fixtures=fixtures)
        self.assertIn("4 Jul", h)
        self.assertIn("17:00", h)
        self.assertIn("xG 1.07", h)
        self.assertIn("1.24", h)
        self.assertIn("pred 1-1", h)


class ArticleFigureLayoutTest(unittest.TestCase):
    """Prose-first article layout: lede paragraph before the figure, then the
    rest of the body; every viz (except matches) wrapped in a captioned
    <figure>."""

    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": None},
        ]
        self.prose = {
            "headline": "Bruno Fernandes leads the captain board",
            "standfirst": "Portugal's midfielder tops this round's captain EV at 11.34.",
            "body_html": ("<p>First paragraph, the lede.</p>"
                          "<p>Second paragraph with more detail.</p>"),
            "bottom_line": "Captain Bruno Fernandes.",
            "source": "template",
        }
        self.viz_html = '<svg viewBox="0 0 100 40"><rect width="80" height="20"/></svg>'

    def test_lede_paragraph_renders_before_figure(self):
        h = render.article_page(
            round_no=3, article="captains", title="Best captain picks — Round 3",
            prose=self.prose, entries=self.entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json", viz_html=self.viz_html)
        lede_pos = h.index("First paragraph, the lede.")
        fig_pos = h.index('<figure class="fig">')
        rest_pos = h.index("Second paragraph with more detail.")
        self.assertLess(lede_pos, fig_pos)
        self.assertLess(fig_pos, rest_pos)

    def test_figure_has_figcaption_for_captains_metric(self):
        h = render.article_page(
            round_no=3, article="captains", title="Best captain picks — Round 3",
            prose=self.prose, entries=self.entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json", viz_html=self.viz_html)
        self.assertIn("<figcaption>", h)
        self.assertIn("Top 10 by Captain EV.", h)
        self.assertIn("Full list in the table below.", h)

    def test_pitch_article_gets_fixed_caption_and_pitch_class(self):
        h = render.article_page(
            round_no=5, article="wildcard", title="Wildcard draft — Round 5",
            prose=self.prose, entries=self.entries,
            columns=["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
            json_url="/api/round/5/wildcard.json", viz_html=self.viz_html)
        self.assertIn("The model&#x27;s optimal XI · number = projected points (xPts)", h)
        self.assertIn('class="fig fig-pitch"', h)

    def test_matches_article_has_no_figure_wrapper(self):
        h = render.article_page(
            round_no=5, article="matches", title="Match predictions — Round 5",
            prose=self.prose, entries=[], columns=[],
            json_url="/api/round/5/matches.json", viz_html=self.viz_html,
            show_table=False)
        self.assertNotIn("<figure", h)
        self.assertNotIn("<figcaption>", h)
        self.assertIn(self.viz_html, h)

    def test_no_closing_p_tag_leaves_body_unsplit(self):
        prose = dict(self.prose, body_html="<div>No paragraph tags here.</div>")
        h = render.article_page(
            round_no=3, article="captains", title="Best captain picks — Round 3",
            prose=prose, entries=self.entries, columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json", viz_html=self.viz_html)
        self.assertIn("No paragraph tags here.", h)
        # figure still renders, just with the (unsplit) body after it
        fig_pos = h.index('<figure class="fig">')
        body_pos = h.index("No paragraph tags here.")
        self.assertLess(fig_pos, body_pos)


class MatchCardStyleTest(unittest.TestCase):
    def _entry(self, **overrides):
        base = {
            "match": "France vs Paraguay", "home": "France", "away": "Paraguay",
            "kickoff": "2026-07-04T15:00:00+00:00",
            "exp_home_goals": 2.1, "exp_away_goals": 0.4, "exp_total": 2.5,
            "top_scoreline": "2-0", "p_home": 0.68, "p_draw": 0.20, "p_away": 0.12,
            "close": False,
        }
        base.update(overrides)
        return base

    def test_mx_grid_uses_260px_two_column_minmax(self):
        h = render.match_predictions_html([self._entry()])
        self.assertIn("minmax(260px,1fr)", h)

    def test_mx_score_is_22px(self):
        h = render.match_predictions_html([self._entry()])
        self.assertIn(".mx-score{font-size:22px", h)
        self.assertIn(".mx-final-score{font-size:22px", h)

    def test_games_to_watch_is_flat_line_not_nested_card(self):
        h = render.match_predictions_html([self._entry(close=True)])
        self.assertIn("Games to watch", h)
        self.assertIn('class="mx-lead"', h)
        self.assertNotIn("<h3>", h)  # no more nested-card heading


class PitchSvgTest(unittest.TestCase):
    def test_pitch_svg_returns_svg(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        self.assertTrue(svg.startswith("<svg"), "pitch_svg should return an SVG element")
        self.assertIn("</svg>", svg)

    def test_pitch_svg_contains_11_surnames(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        # Each player's last name should appear as a text node
        for entry in _SAMPLE_XI:
            surname = entry["name"].split()[-1]
            self.assertIn(surname, svg,
                          f"surname '{surname}' not found in pitch SVG")

    def test_pitch_svg_flags_captain(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        # Captain badge: red circle with "C" label
        self.assertIn(">C<", svg, "captain badge 'C' not found in pitch SVG")

    def test_pitch_label_drops_jr_suffix(self):
        # "Vinicius Jr" must label as "Vinicius", not the suffix "Jr".
        self.assertEqual(render._pitch_label("Vinicius Jr"), "Vinicius")

    def test_pitch_label_drops_other_generational_suffixes(self):
        self.assertEqual(render._pitch_label("Alexander Isaksson Sr"), "Isaksson")
        self.assertEqual(render._pitch_label("Alexander Isaksson II"), "Isaksson")
        self.assertEqual(render._pitch_label("Alexander Isaksson III"), "Isaksson")

    def test_pitch_label_short_full_name_shown_in_full(self):
        # <=11 chars: show the full name rather than truncating to one token.
        self.assertEqual(render._pitch_label("Harry Kane"), "Harry Kane")

    def test_pitch_label_long_name_falls_back_to_last_token(self):
        self.assertEqual(render._pitch_label("Kylian Mbappe Lottin"), "Lottin")

    def test_pitch_svg_labels_vinicius_jr_correctly(self):
        xi = [dict(e) for e in _SAMPLE_XI]
        xi[0] = dict(xi[0], name="Vinicius Jr")
        svg = render.pitch_svg(xi)
        self.assertIn("Vinicius", svg)
        self.assertNotIn(">Jr<", svg)

    def test_pitch_svg_xpts_inside_node_name_below(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        # The xPts text should render at a smaller y-offset from the node centre
        # than the name text (xPts inside the circle, name below it on the grass).
        self.assertIn('fill="#f2f8f4"', svg)   # name label fill (on-grass colour)
        self.assertIn('fill="#15140f"', svg)   # xPts label fill (in-node colour)


class EvBarTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"name": "Harry Kane",   "captain_ev": 18.31, "ownership_pct": 38.6},
            {"name": "Lionel Messi", "captain_ev": 18.06, "ownership_pct": 25.8},
            {"name": "Amad Diallo",  "captain_ev": 17.10, "ownership_pct": 1.0},
        ]

    def test_ev_bar_returns_svg(self):
        svg = render.ev_bar(self.entries, "captain_ev")
        self.assertTrue(svg.startswith("<svg"), "ev_bar should return an SVG element")
        self.assertIn("</svg>", svg)

    def test_ev_bar_contains_top_value(self):
        svg = render.ev_bar(self.entries, "captain_ev")
        # Top value 18.31 should appear as a label
        self.assertIn("18.31", svg)

    def test_ev_bar_empty_is_safe(self):
        svg = render.ev_bar([], "captain_ev")
        self.assertTrue(svg.startswith("<svg"))


class AgentFilesTest(unittest.TestCase):
    def setUp(self):
        self.nav = [("captains", "Best captain picks"), ("best-xi", "Best World Cup Fantasy XI")]

    def test_llms_txt_lists_articles_and_json(self):
        t = render.llms_txt(round_no=3, nav=self.nav)
        self.assertIn("evmax", t)
        self.assertIn("/round/3/captains/", t)
        self.assertIn("/api/round/3/captains.json", t)

    def test_llms_txt_mentions_markdown_twin(self):
        t = render.llms_txt(round_no=3, nav=self.nav)
        self.assertIn(".md", t)
        self.assertIn(f"{render.SITE_URL}/round/3/captains.md", t)

    def test_robots_allows_ai_bots(self):
        r = render.robots_txt()
        for bot in ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"]:
            self.assertIn(bot, r)
        self.assertIn("Sitemap:", r)

    def test_sitemap_lists_pages(self):
        x = render.sitemap_xml(round_no=3, nav=self.nav)
        self.assertIn("<urlset", x)
        self.assertIn(f"{render.SITE_URL}/round/3/captains/", x)
        self.assertIn(f"{render.SITE_URL}/about/", x)

    def test_about_page_has_expected_content(self):
        h = render.about_page()
        self.assertIn("<!doctype html>", h.lower())
        self.assertIn("evmax", h)
        self.assertIn("Monte-Carlo", h)
        self.assertIn("Dixon-Coles", h)
        self.assertIn("50,000", h)
        self.assertIn('href="/about/"', h)  # nav active on about


class NewsletterTest(unittest.TestCase):
    """Feature 1: zero-cookie, zero-JS, zero-third-party-on-load newsletter capture."""

    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]
        self.prose = {
            "headline": "Bruno Fernandes leads the captain board",
            "standfirst": "Portugal's midfielder tops this round's captain EV at 11.34.",
            "body_html": "<p>Bruno Fernandes projects <b>11.34 captain EV</b> this round.</p>",
            "bottom_line": "Captain Bruno Fernandes.",
            "source": "template",
        }
        self.viz_html = '<svg viewBox="0 0 100 40"><rect width="80" height="20" fill="#0f7a45"/></svg>'

    def test_article_page_has_newsletter_form(self):
        h = render.article_page(
            round_no=3, article="captains",
            title="Best captain picks — Round 3",
            prose=self.prose, entries=self.entries,
            columns=["captain_ev", "x_points"],
            json_url="/api/round/3/captains.json",
            viz_html=self.viz_html)
        self.assertIn(f'action="{render.NEWSLETTER_ACTION}"', h)
        self.assertIn('method="post"', h)
        self.assertIn('name="email"', h)
        # The only <script> tags on the page are the pre-existing JSON-LD blocks
        # (Dataset + Article schema.org); the newsletter feature adds none.
        scripts = h.count("<script")
        ld_json_scripts = h.count('<script type="application/ld+json">')
        self.assertEqual(scripts, ld_json_scripts)

    def test_landing_page_has_newsletter_form(self):
        feed = [
            {"slug": "best-xi", "headline": "The model's Round 3 XI",
             "teaser": "A 3-4-3 built around Kane.", "stat_value": "58.7",
             "stat_label": "total xPts"},
        ]
        featured = {"slug": "captains", "prose": _SAMPLE_PROSE, "viz_html": self.viz_html}
        h = render.landing_page(round_no=3, featured=featured, feed=feed)
        self.assertIn(f'action="{render.NEWSLETTER_ACTION}"', h)
        self.assertIn('name="email"', h)

    def test_no_script_tags_introduced_by_newsletter_box(self):
        nl = render._newsletter_html()
        self.assertNotIn("<script", nl)

    def test_privacy_page_mentions_buttondown(self):
        h = render.privacy_page()
        self.assertIn("Buttondown", h)
        self.assertIn("Newsletter", h)

    def test_privacy_page_no_script_tags(self):
        h = render.privacy_page()
        self.assertNotIn("<script", h)


class MatchPredictionsHtmlTest(unittest.TestCase):
    """Live-round scoreboard: finished fixtures show the actual score big with
    the prediction demoted underneath; upcoming fixtures render as before."""

    def _entry(self, **overrides):
        base = {
            "match": "France vs Paraguay", "home": "France", "away": "Paraguay",
            "kickoff": "2026-07-04T15:00:00+00:00",
            "exp_home_goals": 2.1, "exp_away_goals": 0.4, "exp_total": 2.5,
            "top_scoreline": "2-0", "p_home": 0.68, "p_draw": 0.20, "p_away": 0.12,
            "close": False,
        }
        base.update(overrides)
        return base

    def test_finished_fixture_shows_final_badge_and_actual_score(self):
        entry = self._entry(finished=True, final_score="3-0")
        h = render.match_predictions_html([entry])
        self.assertIn("Final", h)
        self.assertIn("3-0", h)
        self.assertIn("mx-final-score", h)

    def test_finished_fixture_shows_prediction_small_underneath(self):
        entry = self._entry(finished=True, final_score="3-0")
        h = render.match_predictions_html([entry])
        self.assertIn("predicted 2-0", h)
        self.assertIn("68%", h)

    def test_unfinished_fixture_renders_prediction_only_no_final_badge(self):
        entry = self._entry()
        h = render.match_predictions_html([entry])
        self.assertIn("2-0", h)               # predicted scoreline still shown big
        self.assertNotIn(">Final<", h)
        # no element actually uses the final-score class (CSS rule alone doesn't count)
        self.assertNotIn('class="mx-final-score"', h)

    def test_unfinished_close_fixture_still_gets_close_badge(self):
        entry = self._entry(close=True, p_home=0.3, p_draw=0.35, p_away=0.35)
        h = render.match_predictions_html([entry])
        self.assertIn("Close", h)

    def test_finished_close_fixture_gets_final_not_close_badge(self):
        """Once a fixture is finished, it's graded as Final, not flagged as a
        close pre-match call — the outcome is already known."""
        entry = self._entry(close=True, finished=True, final_score="1-1",
                            p_home=0.3, p_draw=0.35, p_away=0.35)
        h = render.match_predictions_html([entry])
        self.assertIn("Final", h)
        self.assertNotIn("Close — one to watch", h)


class UtilityAndOgTest(unittest.TestCase):
    def test_thanks_and_confirmed_pages_render_noindex(self):
        for page in (render.thanks_page(), render.confirmed_page()):
            self.assertIn("noindex", page)
            self.assertIn("evmax", page)

    def test_landing_has_og_canonical_and_org_schema(self):
        h = render.landing_page(5, {"slug": "captains", "prose": _SAMPLE_PROSE,
                                    "viz_html": ""}, [], date_str="4 July 2026")
        self.assertIn('property="og:image"', h)
        self.assertIn('rel="canonical"', h)
        self.assertIn('"Organization"', h)

    def test_article_page_has_og_and_canonical(self):
        h = render.article_page(
            round_no=5, article="captains", title="Best captain picks — Round 5",
            prose=_SAMPLE_PROSE, entries=_SAMPLE_XI[:1], columns=["captain_ev"],
            json_url="/api/round/5/captains.json", viz_html="")
        self.assertIn('property="og:title"', h)
        self.assertIn('https://evmax.ai/round/5/captains/', h)  # canonical URL
        self.assertIn("twitter:card", h)

    def test_article_page_has_markdown_alternate_link(self):
        h = render.article_page(
            round_no=5, article="captains", title="Best captain picks — Round 5",
            prose=_SAMPLE_PROSE, entries=_SAMPLE_XI[:1], columns=["captain_ev"],
            json_url="/api/round/5/captains.json", viz_html="")
        self.assertIn('rel="alternate" type="text/markdown" href="/round/5/captains.md"', h)


class ArticleMdTest(unittest.TestCase):
    """render.article_md -- the agent-facing content-only Markdown twin."""

    def setUp(self):
        self.prose = {
            "headline": "Bruno Fernandes leads the captain board",
            "standfirst": "Portugal's midfielder tops this round's captain EV at 11.34.",
            "body_html": "<p>Bruno Fernandes projects <b>11.34 captain EV</b> this round.</p>",
            "body_md": "Bruno Fernandes projects **11.34 captain EV** this round.",
            "bottom_line": "Captain Bruno Fernandes.",
            "source": "template",
        }
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6},
            {"rank": 2, "name": "Amad | Diallo", "team": "CIV", "position": "FWD",
             "x_points": 5.0, "captain_ev": 10.0, "ceiling": 8.0, "price": 5.5,
             "ownership_pct": 1.0, "value": 0.9},
        ]

    def test_article_md_has_headline_table_row_and_license_no_html(self):
        md = render.article_md(
            round_no=5, slug="captains", title="Best captain picks — Round 5",
            prose=self.prose, entries=self.entries, columns=["captain_ev", "x_points"],
            generated_at="2026-07-04T12:00:00+00:00", date_str="4 July 2026",
            canonical_path="/round/5/captains/")
        self.assertTrue(md.startswith("# Bruno Fernandes leads the captain board"))
        self.assertIn("Bruno Fernandes", md)
        self.assertIn("11.34", md)
        self.assertIn("CC BY 4.0", md)
        self.assertIn("https://evmax.ai/api/round/5/captains.json", md)
        self.assertNotIn("<p>", md)
        self.assertNotIn("<b>", md)
        self.assertNotIn("<table", md)

    def test_article_md_escapes_pipe_in_names(self):
        md = render.article_md(
            round_no=5, slug="captains", title="Best captain picks — Round 5",
            prose=self.prose, entries=self.entries, columns=["captain_ev"],
            generated_at="2026-07-04T12:00:00+00:00", date_str="4 July 2026",
            canonical_path="/round/5/captains/")
        self.assertIn("Amad \\| Diallo", md)

    def test_article_md_matches_uses_match_columns(self):
        entries = [
            {"match": "France vs Paraguay", "home": "France", "away": "Paraguay",
             "kickoff": "2026-07-04T15:00:00+00:00", "exp_home_goals": 2.1,
             "exp_away_goals": 0.4, "exp_total": 2.5, "top_scoreline": "2-0",
             "p_home": 0.68, "p_draw": 0.20, "p_away": 0.12, "close": False},
        ]
        md = render.article_md(
            round_no=5, slug="matches", title="Match predictions — Round 5",
            prose=self.prose, entries=entries, columns=[],
            generated_at="2026-07-04T12:00:00+00:00", date_str="4 July 2026",
            canonical_path="/round/5/matches/")
        self.assertIn("France vs Paraguay", md)
        self.assertIn("2-0", md)
        self.assertIn("68%", md)

    def test_article_md_caps_table_at_20_rows(self):
        entries = [
            {"rank": i + 1, "name": f"Player{i}", "team": "X", "captain_ev": 10.0 - i * 0.1}
            for i in range(30)
        ]
        md = render.article_md(
            round_no=5, slug="captains", title="t", prose=self.prose, entries=entries,
            columns=["captain_ev"], generated_at="2026-07-04T12:00:00+00:00",
            date_str="4 July 2026", canonical_path="/round/5/captains/")
        self.assertIn("Player19", md)
        self.assertNotIn("Player20", md)


if __name__ == '__main__':
    unittest.main()
