"""Player cards scaffold: URL scheme, verdicts, fixture strip, payload
assembly and the HTML emitters (evmax/fpl_players.py).

All synthetic payloads — no network, no data/ dependency, and a deliberately
small player pool so the suite never pays for 563 pages here (the capped
end-to-end build in tests/test_fpl_site.py covers the real wiring)."""
from __future__ import annotations

import os
import re
import unittest

from evmax import fpl_players


class TestUrlScheme(unittest.TestCase):
    def test_slug_is_id_plus_kebab_web_name(self):
        self.assertEqual(fpl_players.slugify(233, "Haaland"), "233-haaland")
        self.assertEqual(fpl_players.slugify(58, "B.Fernandes"),
                         "58-b-fernandes")

    def test_slug_strips_diacritics_and_collapses_separators(self):
        self.assertEqual(fpl_players.slugify(7, "Sánchez"), "7-sanchez")
        self.assertEqual(fpl_players.slugify(9, "Van de Ven"), "9-van-de-ven")
        self.assertEqual(fpl_players.slugify(3, "  Ødegaard  "), "3-odegaard")

    def test_slug_survives_an_empty_web_name(self):
        self.assertEqual(fpl_players.slugify(41, ""), "41")

    def test_paths(self):
        self.assertEqual(fpl_players.page_path("233-haaland"),
                         "/fpl/players/233-haaland/")
        self.assertEqual(fpl_players.json_path(2, 233),
                         "/api/fpl/gw2/players/233.json")
        self.assertEqual(fpl_players.tier_path("GK"), "/fpl/tiers/gk/")
        self.assertEqual(fpl_players.tier_path("FWD"), "/fpl/tiers/fwd/")


def _pool(n=20, position="MID"):
    """n synthetic rows, x_points descending from n, ownership ascending —
    so xpts rank 1 is the LEAST owned (maximum ownership gap)."""
    return [{"name": f"P{i:02d}", "team": "ARS", "position": position,
             "x_points": float(n - i), "ownership_pct": float(i + 1),
             "price": 5.0 + i * 0.1}
            for i in range(n)]


class TestVerdicts(unittest.TestCase):
    def test_letters_follow_the_percentile_cuts(self):
        letters = fpl_players.verdict_letters(_pool(20))
        # 20 players: index 0 (0%) = S, 1-3 (<20%) = A, 4-9 (<50%) = B,
        # 10-15 (<80%) = C, 16-19 = D
        self.assertEqual(letters["P00"], "S")
        self.assertEqual(letters["P01"], "A")
        self.assertEqual(letters["P03"], "A")
        self.assertEqual(letters["P04"], "B")
        self.assertEqual(letters["P09"], "B")
        self.assertEqual(letters["P10"], "C")
        self.assertEqual(letters["P15"], "C")
        self.assertEqual(letters["P16"], "D")
        self.assertEqual(letters["P19"], "D")

    def test_letters_are_per_position(self):
        """A weak forward must not inherit a strong midfield's percentile —
        each position pool is ranked on its own."""
        rows = _pool(19) + [{"name": "LoneFwd", "team": "ARS",
                             "position": "FWD", "x_points": 0.1,
                             "ownership_pct": 1.0, "price": 4.5}]
        letters = fpl_players.verdict_letters(rows)
        self.assertEqual(letters["LoneFwd"], "S")   # top of a pool of one

    def test_calls_follow_the_letters(self):
        self.assertEqual(fpl_players._CALL_BY_LETTER["S"], "buy")
        self.assertEqual(fpl_players._CALL_BY_LETTER["B"], "hold")
        self.assertEqual(fpl_players._CALL_BY_LETTER["D"], "pass")


class TestRanks(unittest.TestCase):
    def test_gap_is_own_rank_minus_xpts_rank(self):
        rows = _pool(10)
        xp, own = fpl_players.rank_maps(rows)
        # P00: best projection (rank 1), least owned (rank 10) -> gap +9,
        # i.e. under-owned relative to the projection.
        self.assertEqual(xp["P00"], 1)
        self.assertEqual(own["P00"], 10)
        self.assertEqual(xp["P09"], 10)
        self.assertEqual(own["P09"], 1)

    def test_missing_values_rank_last_not_crash(self):
        rows = _pool(3)
        rows[1]["x_points"] = None
        rows[1]["ownership_pct"] = None
        xp, own = fpl_players.rank_maps(rows)
        self.assertEqual(xp["P01"], 3)
        self.assertEqual(own["P01"], 3)


def _fx(match_id, home, away, gw, kickoff="2026-08-28T19:00:00Z"):
    return {"match_id": match_id, "home": home, "away": away,
            "kickoff_utc": kickoff, "fantasy_round": gw, "stage": "GW"}


_FX_ROWS = [
    _fx("m1", "ARS", "LIV", 2),
    _fx("m2", "MCI", "ARS", 3),
    _fx("m3", "ARS", "BUR", 4),
    _fx("m4", "EVE", "ARS", 5),
    _fx("m5", "ARS", "TOT", 6),          # 5th fixture: beyond the strip
    _fx("m0", "ARS", "MUN", 1),          # past gameweek: excluded
]

_ODDS_BY_GW = {
    2: {"matches": {"m1": {"lam_home": 1.9, "lam_away": 0.9}}},
    3: {"matches": {"m2": {"lam_home": 1.8, "lam_away": 1.0,
                           "source": "fdr_prior_calibrated_on_gw1_market_odds"}}},
    # gw4 cache exists but lacks m3; gw5 cache absent entirely.
    4: {"matches": {}},
}


class TestFixtureStrip(unittest.TestCase):
    def test_next_four_from_the_gameweek_in_order(self):
        strip = fpl_players.fixture_strip("ARS", 2, _FX_ROWS, _ODDS_BY_GW)
        self.assertEqual([f["gw"] for f in strip], [2, 3, 4, 5])
        self.assertEqual([f["opponent"] for f in strip],
                         ["LIV", "MCI", "BUR", "EVE"])
        self.assertEqual([f["venue"] for f in strip], ["H", "A", "H", "A"])

    def test_priced_fixture_carries_lambdas_and_difficulty(self):
        strip = fpl_players.fixture_strip("ARS", 2, _FX_ROWS, _ODDS_BY_GW)
        home = strip[0]           # ARS at home, lam 1.9 vs 0.9 -> easy
        self.assertEqual(home["lam_for"], 1.9)
        self.assertEqual(home["lam_against"], 0.9)
        self.assertEqual(home["difficulty"], 1)
        self.assertEqual(home["source"], "market")   # unstamped = market
        away = strip[1]           # ARS away: lam_for is the AWAY lambda
        self.assertEqual(away["lam_for"], 1.0)
        self.assertEqual(away["lam_against"], 1.8)
        self.assertEqual(away["difficulty"], 5)
        self.assertIn("fdr_prior", away["source"])

    def test_unpriced_fixture_degrades_never_guesses(self):
        strip = fpl_players.fixture_strip("ARS", 2, _FX_ROWS, _ODDS_BY_GW)
        for f in strip[2:]:       # missing match entry AND missing cache
            self.assertIsNone(f["difficulty"])
            self.assertIsNone(f["lam_for"])
            self.assertEqual(f["source"], "unpriced")

    def test_difficulty_buckets(self):
        cases = [(2.0, 1.0, 1), (1.5, 1.1, 2), (1.2, 1.2, 3),
                 (1.0, 1.5, 4), (0.9, 1.9, 5)]
        for lam_for, lam_against, want in cases:
            self.assertEqual(fpl_players._difficulty(lam_for, lam_against),
                             want, (lam_for, lam_against))


# A hand-built PMF over 100 sims with known statistics, so the assembly and
# chart tests can assert real numbers rather than "something was drawn".
# cumulative: 0:8 2:20 3:38 4:58 6:74 7:84 9:91 13:96 17:99 24:100
_ALPHA_PMF = {0: 8, 2: 12, 3: 18, 4: 20, 6: 16, 7: 10, 9: 7, 13: 5, 17: 3,
              24: 1}
_ALPHA_STATS = {"p10": 2, "median": 4, "mode": 4, "p90": 13,
                "p_haul": 0.09, "p_blank": 0.2}


def _assembly_inputs(with_six_week=True, with_note=False,
                     with_distribution=True):
    rows = [
        {"name": "Alpha", "team": "ARS", "position": "MID", "x_points": 8.0,
         "captain_ev": 16.0, "ceiling": 14.0, "value": 0.8, "bonus": 0.6,
         "defcon": 0.2, "p_defcon": 0.1, "cs_points": 0.3, "price": 10.0,
         "ownership_pct": 12.0, "kickoff": "2026-08-28T19:00:00+00:00",
         "start_prob": 0.9},
        {"name": "Beta", "team": "LIV", "position": "MID", "x_points": 4.0,
         "captain_ev": 8.0, "ceiling": 7.0, "value": 0.8, "bonus": 0.2,
         "defcon": 0.4, "p_defcon": 0.2, "cs_points": 0.3, "price": 5.0,
         "ownership_pct": 40.0, "kickoff": "2026-08-28T19:00:00+00:00",
         "start_prob": 0.8},
    ]
    if with_distribution:
        rows[0].update(dict(_ALPHA_STATS), distribution=dict(_ALPHA_PMF))
        rows[1].update(distribution={0: 30, 1: 10, 2: 20, 5: 30, 8: 10},
                       p10=0, median=2, mode=0, p90=5, p_haul=0.0,
                       p_blank=0.6)
    players_by_name = {
        "Alpha": {"id": 11, "name": "Alpha"},
        "Beta": {"id": 22, "name": "Beta"},
    }
    elements_by_id = {
        11: {"id": 11, "web_name": "Alpha", "status": "a", "news": "",
             "total_points": 12, "event_points": 7, "minutes": 180},
        22: {"id": 22, "web_name": "Béta", "status": "d",
             "news": "Knock - 75% chance of playing",
             "total_points": 2, "event_points": 2, "minutes": 65},
    }
    notes = {}
    if with_note:
        from core.research import ResearchEntry
        notes["Beta"] = ResearchEntry(name="Beta", status="doubtful",
                                      sources=["https://example.test"],
                                      updated="2026-08-24")
    six_week = None
    if with_six_week:
        six_week = {"Alpha": {"team": "ARS", "position": "MID", "price": 10.0,
                              "own": 12.0,
                              "gw": {"1": 8.0, "2": 6.5, "3": 7.1}}}
    squad_names = {"model": {"Alpha"}, "consensus": set()}
    return rows, players_by_name, elements_by_id, notes, squad_names, six_week


def _payloads(**kw):
    (rows, by_name, by_id, notes, squads, six_week) = _assembly_inputs(**kw)
    return fpl_players.assemble_payloads(
        rows, by_name, by_id, notes, squads, six_week,
        _FX_ROWS, _ODDS_BY_GW, gameweek=2,
        generated_at="2026-08-24T10:00:00+00:00")


class TestAssembly(unittest.TestCase):
    def test_payloads_sorted_by_x_points_with_full_schema(self):
        payloads, unmatched = _payloads()
        self.assertEqual(unmatched, [])
        self.assertEqual([p["name"] for p in payloads], ["Alpha", "Beta"])
        p = payloads[0]
        self.assertEqual(p["id"], 11)
        self.assertEqual(p["slug"], "11-alpha")
        self.assertEqual(p["page"], "/fpl/players/11-alpha/")
        self.assertEqual(p["projection"]["x_points"], 8.0)
        self.assertEqual(p["projection"]["start_prob"], 0.9)
        self.assertEqual(p["kickoff"], "2026-08-28T19:00:00+00:00")

    def test_season_block_reads_the_raw_element(self):
        payloads, _ = _payloads()
        alpha = payloads[0]
        self.assertEqual(alpha["season"],
                         {"total_points": 12, "event_points": 7,
                          "minutes": 180, "realized_ppm": 1.2})

    def test_news_and_status_are_verbatim(self):
        payloads, _ = _payloads()
        beta = payloads[1]
        self.assertEqual(beta["status"], "d")
        self.assertEqual(beta["news"], "Knock - 75% chance of playing")

    def test_ownership_gap(self):
        payloads, _ = _payloads()
        alpha, beta = payloads
        # Alpha: xpts rank 1, own rank 2 -> +1 (under-owned)
        self.assertEqual(alpha["ranks"],
                         {"xpts_rank": 1, "own_rank": 2, "own_vs_xpts_gap": 1})
        self.assertEqual(beta["ranks"]["own_vs_xpts_gap"], -1)

    def test_verdict_carries_letter_band_and_call(self):
        payloads, _ = _payloads()
        alpha = payloads[0]
        self.assertEqual(alpha["verdict_tier"], alpha["verdict"]["tier"])
        self.assertEqual(alpha["verdict"]["price_band"], "Premium")  # £10.0m
        self.assertEqual(payloads[1]["verdict"]["price_band"], "Budget")  # £5m
        self.assertIn(alpha["verdict"]["call"], ("buy", "hold", "pass"))

    def test_six_week_vector_present_and_gracefully_absent(self):
        payloads, _ = _payloads()
        self.assertEqual(payloads[0]["six_week_xpts"],
                         {"1": 8.0, "2": 6.5, "3": 7.1})
        self.assertIsNone(payloads[1]["six_week_xpts"])   # not in the matrix
        payloads_no_cache, _ = _payloads(with_six_week=False)
        self.assertIsNone(payloads_no_cache[0]["six_week_xpts"])

    def test_distribution_carries_the_pmf_and_the_six_statistics(self):
        payloads, _ = _payloads()
        dist = payloads[0]["distribution"]
        self.assertEqual(dist["histogram"], _ALPHA_PMF)
        self.assertEqual(dist["sims"], 100)
        for key, want in _ALPHA_STATS.items():
            self.assertEqual(dist[key], want, key)

    def test_distribution_is_null_when_the_artifact_predates_histograms(self):
        payloads, _ = _payloads(with_distribution=False)
        for p in payloads:
            self.assertIn("distribution", p)
            self.assertIsNone(p["distribution"])

    def test_squad_membership_and_note_provenance(self):
        payloads, _ = _payloads(with_note=True)
        alpha, beta = payloads
        self.assertEqual(alpha["squads"], {"model": True, "consensus": False})
        self.assertEqual(alpha["notes"], [])
        self.assertEqual(beta["notes"], ["Beta"])
        self.assertEqual(beta["flag"], "doubtful")

    def test_unmatched_row_is_reported_not_guessed(self):
        rows, by_name, by_id, notes, squads, six_week = _assembly_inputs()
        rows.append(dict(rows[0], name="Ghost"))
        payloads, unmatched = fpl_players.assemble_payloads(
            rows, by_name, by_id, notes, squads, six_week, _FX_ROWS,
            _ODDS_BY_GW, 2, "2026-08-24T10:00:00+00:00")
        self.assertEqual(unmatched, ["Ghost"])
        self.assertEqual(len(payloads), 2)

    def test_json_envelope_adds_provenance_and_drops_the_slug(self):
        payloads, _ = _payloads()
        env = fpl_players.player_json(payloads[0], "method text",
                                      "https://example.test",
                                      "https://l.test", "CC BY")
        self.assertEqual(env["methodology"], "method text")
        self.assertEqual(env["license_text"], "CC BY")
        self.assertNotIn("slug", env)
        self.assertIn("slug", payloads[0])   # the input is not mutated


class TestCardHtml(unittest.TestCase):
    def _card(self, **kw):
        payloads, _ = _payloads(**kw)
        return payloads, fpl_players.card_html(payloads[0])

    def test_semantic_figure_with_data_attributes(self):
        _, html = self._card()
        self.assertIn('<figure class="player-card"', html)
        self.assertIn('data-id="11"', html)
        self.assertIn('data-x-points="8.0"', html)
        self.assertIn('data-tier="S"', html)
        self.assertIn('data-price-band="Premium"', html)
        self.assertIn('data-own-gap="1"', html)
        self.assertIn("<figcaption", html)
        self.assertIn('<h1 class="pc-name">Alpha</h1>', html)

    def test_premium_slot_no_longer_claims_the_distribution(self):
        """Decision D1 (2026-08-26): distributions are FREE. The premium slot
        keeps its reserved space but must not promise something the card is
        already giving away."""
        _, html = self._card()
        self.assertIn('class="pc-premium"', html)
        self.assertIn("🔒", html)                       # the lock glyph
        self.assertIn("Premium — coming soon: your-team fit · dossier alerts",
                      html)
        self.assertNotIn("full distribution", html)
        self.assertNotIn('class="pc-dist-chart"', html)  # no reserved stripe

    def test_distribution_chart_renders_under_the_stat_rows(self):
        _, html = self._card()
        self.assertIn('class="pc-dist"', html)
        self.assertIn('aria-label="Simulated points distribution"', html)
        self.assertIn("<svg", html)
        # placed between the stat rows and the fixture strip
        self.assertLess(html.index("pc-statrow2"), html.index("pc-dist"))
        self.assertLess(html.index("pc-dist"), html.index("pc-fixtures"))

    def test_distribution_chart_caption_names_the_sim_count_and_the_marks(self):
        _, html = self._card()
        self.assertIn("100 simulations", html)          # sum of the PMF counts
        self.assertIn("floor P10", html)
        self.assertIn("most likely", html)
        self.assertIn("ceiling", html)

    def test_distribution_chart_marks_floor_mode_and_ceiling(self):
        _, html = self._card()
        for label in ("floor <b>2</b>", "most likely <b>4</b>",
                      "ceiling <b>13</b>"):
            self.assertIn(label, html)

    def test_the_marks_are_html_not_svg_text(self):
        """Text inside the viewBox would scale with it — 7px on a card is a
        27px shout at full page width. The SVG carries geometry only."""
        svg = fpl_players._distribution_svg(_payloads()[0][0])
        self.assertNotIn("<text", svg)
        self.assertIn('preserveAspectRatio="none"', svg)

    def test_distribution_chart_is_absent_when_the_artifact_predates_it(self):
        payloads, _ = _payloads(with_distribution=False)
        html = fpl_players.card_html(payloads[0])
        self.assertNotIn("pc-dist", html)
        # and the card still renders everything else
        self.assertIn('class="pc-verdict"', html)

    def test_distribution_chart_is_deterministic(self):
        payloads, _ = _payloads()
        self.assertEqual(fpl_players._distribution_svg(payloads[0]),
                         fpl_players._distribution_svg(payloads[0]))

    def test_distribution_chart_clips_the_freak_tail(self):
        """One sim in a thousand at 40 points must not flatten every real bar:
        the drawn range stops at the 99th percentile."""
        payloads, _ = _payloads()
        payloads[0]["distribution"].update(
            histogram={0: 500, 4: 499, 40: 1}, sims=1000,
            p10=0, median=0, mode=0, p90=4)
        svg = fpl_players._distribution_svg(payloads[0])
        # 0..4 inclusive is five slots; only 0 and 4 carry mass, so two bars.
        self.assertEqual(svg.count("<rect"), 2)
        # a bar for the 40-point sim would be a 41st slot, squashing the rest
        widths = {float(w) for w in re.findall(r'<rect [^>]*width="([\d.]+)"',
                                               svg)}
        self.assertTrue(all(w > 20.0 for w in widths), widths)

    def test_fixture_strip_chips_tint_by_difficulty(self):
        _, html = self._card()
        self.assertIn('class="pc-fixtures"', html)
        self.assertIn("LIV (H)", html)
        self.assertIn('class="fx fx-d1"', html)         # priced: green/easy
        self.assertIn('class="fx fx-unpriced"', html)   # no lambdas: gray
        self.assertIn('data-source="unpriced"', html)

    def test_six_week_form_art_is_a_layered_svg(self):
        _, html = self._card()
        self.assertIn('class="pc-sixweek"', html)
        self.assertIn('aria-label="Six-gameweek expected-points form"', html)
        # the sim-cloud layers: 3 translucent areas + the true series' fill.
        # Counted inside the six-week block only — the distribution chart's
        # bars carry fill-opacity too.
        form = html[html.index("pc-sixweek"):html.index("pc-decomp")]
        self.assertEqual(form.count("fill-opacity"), 4)
        self.assertIn("GW2 6.50", html)                 # data in the <title>
        # no player without a horizon vector draws one
        payloads, _ = _payloads(with_six_week=False)
        self.assertNotIn("pc-sixweek", fpl_players.card_html(payloads[0]))

    def test_form_art_is_deterministic(self):
        """No RNG in the site layer: identical inputs, identical bytes."""
        payloads, _ = _payloads()
        self.assertEqual(fpl_players.card_html(payloads[0]),
                         fpl_players.card_html(payloads[0]))

    def test_decomposition_strip_sums_the_projection(self):
        _, html = self._card()
        self.assertIn('class="pc-decomp"', html)
        for cls in ("pcd-attack", "pcd-cs", "pcd-defcon", "pcd-bonus"):
            self.assertIn(cls, html)
        self.assertIn("Clean sheets (per-match est.) — 0.30 xPts", html)
        # attack = 8.0 - (0.3 + 0.2 + 0.6) = 6.9
        self.assertIn("Goals, assists &amp; appearance — 6.90 xPts", html)

    def test_club_code_gets_the_club_color_class(self):
        payloads, _ = _payloads()
        beta_html = fpl_players.card_html(payloads[1])   # LIV
        self.assertIn('class="pc-clubcode club-LIV"', beta_html)
        self.assertIn(".club-LIV{color:#c8102e}", fpl_players.CARD_CSS)

    def test_hero_number_and_verdict_line(self):
        _, html = self._card()
        self.assertIn('<div class="pc-hero"><b>8.00</b>', html)
        self.assertIn('class="pc-verdict">buy · tier S · Premium</div>', html)

    def test_news_renders_verbatim_when_present_only(self):
        payloads, _ = _payloads()
        beta_html = fpl_players.card_html(payloads[1])
        self.assertIn("Knock - 75% chance of playing", beta_html)
        alpha_html = fpl_players.card_html(payloads[0])
        self.assertNotIn("pc-news", alpha_html)

    def test_heading_level_is_configurable(self):
        payloads, _ = _payloads()
        html = fpl_players.card_html(payloads[0], heading="h2")
        self.assertIn('<h2 class="pc-name">', html)
        self.assertNotIn("<h1", html)

    def test_all_card_styling_lives_in_the_one_marked_block(self):
        with open(fpl_players.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("CARD STYLE — DIRECTION", src)    # the marked block
        self.assertIn(".player-card{", fpl_players.CARD_CSS)
        self.assertIn(".pd-table{", fpl_players.CARD_CSS)
        self.assertIn(".pc-premium", fpl_players.CARD_CSS)
        self.assertIn(".pc-dist", fpl_players.CARD_CSS)
        # landing-row layout lives in its own block so player pages (which
        # embed CARD_CSS) never carry landing rules — and vice versa
        self.assertIn(".tcf-row{", fpl_players.TOP_CARDS_CSS)
        self.assertNotIn(".tcf-row", fpl_players.CARD_CSS)


class TestPlayerPage(unittest.TestCase):
    def _page(self):
        payloads, _ = _payloads(with_note=True)
        return payloads, fpl_players.player_page_html(
            payloads[1], 2, date_str="24 August 2026", methodology="Method.")

    def test_card_on_top_json_alternate_and_data_table(self):
        _, html = self._page()
        self.assertIn('<figure class="player-card"', html)
        self.assertIn('<link rel="alternate" type="application/json" '
                      'href="/api/fpl/gw2/players/22.json">', html)
        self.assertIn('class="pd-table"', html)
        self.assertIn("Expected points (xPts)", html)
        self.assertIn("Realized pts/£m", html)

    def test_provenance_names_the_notes_by_name_only(self):
        _, html = self._page()
        self.assertIn("Research notes on file: Beta", html)
        self.assertNotIn("https://example.test", html)   # names ONLY, no links

    def test_no_notes_says_pure_model_output(self):
        payloads, _ = _payloads()
        html = fpl_players.player_page_html(payloads[0], 2)
        self.assertIn("No research notes on file", html)
        self.assertIn("our model squad", html)            # membership line

    def test_canonical_is_the_player_page(self):
        _, html = self._page()
        self.assertIn('<link rel="canonical" '
                      'href="https://evmax.ai/fpl/players/22-beta/">', html)


class TestIndexPage(unittest.TestCase):
    def _index(self):
        payloads, _ = _payloads()
        return fpl_players.index_page_html(
            payloads, 2, "/api/fpl/gw2/players.json",
            date_str="24 August 2026")

    def test_h1_is_check_your_player(self):
        self.assertIn("<h1>Check your player</h1>", self._index())

    def test_search_form_points_at_the_bulk_feed(self):
        html = self._index()
        self.assertIn('data-players-url="/api/fpl/gw2/players.json"', html)
        self.assertIn('<script src="/js/players.js" defer></script>', html)
        self.assertIn("<noscript>", html)

    def test_no_js_fallback_is_an_alphabetical_table(self):
        html = self._index()
        self.assertIn('id="player-index-table"', html)
        # alphabetical by slugified name: Alpha before Beta
        self.assertLess(html.find(">Alpha<"), html.find(">Beta<"))
        self.assertIn('href="/fpl/players/11-alpha/"', html)

    def test_tier_boards_are_linked(self):
        html = self._index()
        for seg in ("gk", "def", "mid", "fwd"):
            self.assertIn(f'href="/fpl/tiers/{seg}/"', html)


class TestTierPage(unittest.TestCase):
    def test_groups_s_to_d_with_letter_xpts_and_price(self):
        rows = _pool(20)
        by_name = {r["name"]: {"id": i + 100}
                   for i, r in enumerate(rows)}
        by_id = {i + 100: {"id": i + 100, "web_name": r["name"], "status": "a",
                           "news": "", "total_points": 0, "event_points": 0,
                           "minutes": 0}
                 for i, r in enumerate(rows)}
        payloads, _ = fpl_players.assemble_payloads(
            rows, by_name, by_id, {}, {}, None, [], {}, 2, "t")
        html = fpl_players.tier_page_html("MID", payloads, 2)
        self.assertIn("Midfielders, tiered S to D", html)
        for label in ("S — elite this week", "A — strong", "B — solid",
                      "C — fringe", "D — avoid"):
            self.assertIn(label, html)
        # S group renders before D group
        self.assertLess(html.find("S — elite"), html.find("D — avoid"))
        self.assertIn(">P00<", html)
        self.assertIn("£5.0m", html)

    def test_only_the_positions_players_appear(self):
        payloads, _ = _payloads()          # two MIDs
        html = fpl_players.tier_page_html("FWD", payloads, 2)
        self.assertNotIn(">Alpha<", html)


class TestTopCards(unittest.TestCase):
    """Owner correction 2026-08-25: the landing's top-cards row shows the
    FULL card_html face for the top four — not compact thumbnails."""

    def _payloads(self, n=8):
        rows = _pool(n)
        by_name = {r["name"]: {"id": i} for i, r in enumerate(rows)}
        by_id = {i: {"id": i, "web_name": r["name"], "status": "a", "news": "",
                     "total_points": 0, "event_points": 0, "minutes": 0}
                 for i, r in enumerate(rows)}
        payloads, _ = fpl_players.assemble_payloads(
            rows, by_name, by_id, {}, {}, None, [], {}, 2, "t")
        return payloads

    def test_top_four_full_faces_linking_to_pages(self):
        html = fpl_players.top_cards_html(self._payloads())
        # four FULL card faces — the same figure card_html emits
        self.assertEqual(html.count('<figure class="player-card"'), 4)
        self.assertIn('href="/fpl/players/0-p00/"', html)
        self.assertNotIn(">P04<", html)                  # 5th does not render
        # full-face internals present (not the rejected thumbnail module)
        self.assertIn("pc-statrow", html)
        self.assertIn("pc-verdict", html)
        self.assertIn("pc-premium", html)
        self.assertNotIn("tc-card", html)

    def test_kicker_line_and_check_your_player_link(self):
        html = fpl_players.top_cards_html(self._payloads())
        self.assertIn("This week's top cards — from 50,000 simulations", html)
        self.assertIn('href="/fpl/players/"', html)      # opens the index
        # the kicker renders before the row, the link right under the kicker
        self.assertLess(html.find("tcf-kicker"), html.find("tcf-check"))
        self.assertLess(html.find("tcf-check"), html.find("tcf-row"))

    def test_embedded_faces_use_h2_not_h1(self):
        html = fpl_players.top_cards_html(self._payloads())
        self.assertIn('<h2 class="pc-name">', html)
        self.assertNotIn("<h1", html)


class TestPlayersJs(unittest.TestCase):
    """The search script follows /js/rate.js's conventions: self-hosted IIFE,
    data-* driven, one same-origin fetch, no storage, no third parties."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.abspath(
            fpl_players.__file__)), "assets", "js", "players.js")
        with open(path, encoding="utf-8") as fh:
            cls.js = fh.read()

    def test_reads_the_feed_url_from_the_form_attribute(self):
        self.assertIn('getAttribute("data-players-url")', self.js)

    def test_no_storage_no_third_party_no_tracking(self):
        """Scan the CODE only — the header comment documents the posture and
        legitimately names the things the code must never use."""
        import re
        code = re.sub(r"/\*.*?\*/", "", self.js, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        for banned in ("localStorage", "sessionStorage", "document.cookie",
                       "http://", "https://", "XMLHttpRequest"):
            self.assertNotIn(banned, code)   # no storage, no absolute URLs

    def test_normalization_matches_rate_js(self):
        self.assertIn('normalize("NFD")', self.js)
        self.assertIn("\\u0300-\\u036f", self.js)


class TestModeCarriesItsShare(unittest.TestCase):
    """A wide distribution's mode is a weak claim (Bruno GW2 peaks at 10 points
    in 9.3% of sims, with 13 right behind at 8.5%). "most likely 10" bare
    overstates it, so the card prints the mode's own share beside it."""

    def _payload(self, histogram, sims):
        return {"name": "P", "team": "MUN", "position": "MID", "price": 12.0,
                "x_points": 8.6,
                "distribution": {"histogram": histogram, "sims": sims,
                                 "p10": 1, "median": 8, "mode": 10, "p90": 17,
                                 "p_haul": 0.42, "p_blank": 0.17}}

    def test_share_is_printed_next_to_the_mode(self):
        html = fpl_players._distribution_html(
            self._payload({"10": 930, "13": 850, "2": 8220}, 10000))
        self.assertIn("most likely", html)
        self.assertIn("<b>10</b> <i>9%</i>", html)

    def test_missing_histogram_degrades_to_the_bare_mode(self):
        payload = self._payload({}, 0)
        payload["distribution"]["histogram"] = {}
        html = fpl_players._distribution_html(payload)
        self.assertEqual(html, "")
