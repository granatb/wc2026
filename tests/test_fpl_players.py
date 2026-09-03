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
                              # gw4 included so the axis carries an UNPRICED
                              # opponent (BUR) — the grey leg of the key
                              "gw": {"1": 8.0, "2": 6.5, "3": 7.1, "4": 6.0}}}
    # Alpha starts for us; Beta is on the consensus bench — the two ends
    # of the stance ladder, so the assembly tests exercise both.
    squad_roles = {"model": {"Alpha": "XI"}, "consensus": {"Beta": "Bench"}}
    return rows, players_by_name, elements_by_id, notes, squad_roles, six_week


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
        self.assertIn(alpha["verdict"]["rank_call"], ("buy", "hold", "pass"))
        self.assertNotIn("call", alpha["verdict"])

    def test_six_week_vector_present_and_gracefully_absent(self):
        payloads, _ = _payloads()
        self.assertEqual(payloads[0]["six_week_xpts"],
                         {"1": 8.0, "2": 6.5, "3": 7.1, "4": 6.0})
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
        self.assertEqual(alpha["squads"],
                         {"model": True, "consensus": False,
                          "model_role": "XI", "consensus_role": None})
        self.assertEqual(beta["squads"],
                         {"model": False, "consensus": True,
                          "model_role": None, "consensus_role": "Bench"})
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

    def test_no_premium_slot_survives_anywhere_on_the_card(self):
        """The slot was reserved 2026-08-24 and REMOVED 2026-08-26 (owner): a
        lock advertising features that do not exist is clutter on a card whose
        job is to answer a question in five seconds."""
        _, html = self._card()
        self.assertNotIn("pc-premium", html)
        # "Premium" survives only as the PRICE BAND (data-price-band), never as
        # a locked feature slot.
        self.assertNotIn("Premium — coming soon", html)
        self.assertNotIn("🔒", html)


    def test_distribution_chart_renders_under_the_stat_rows(self):
        _, html = self._card()
        self.assertIn('class="pc-dist"', html)
        self.assertIn('aria-label="Simulated points distribution"', html)
        self.assertIn("<svg", html)
        # inside the fold, after the ledger; fixtures sit UP on the timeline
        self.assertLess(html.index("pc-ledger"), html.index("pc-dist"))
        self.assertLess(html.index("pc-dotopps"), html.index("pc-dist"))

    def test_distribution_chart_caption_names_the_sim_count(self):
        """The caption carries the provenance (how many simulations); the
        floor / most likely / ceiling marks sit above the chart where they
        label their own rules, so repeating them below wrapped every card to
        two ragged lines (owner, 2026-08-26)."""
        _, html = self._card()
        self.assertIn("100 simulations", html)   # the fixture PMF's n
        self.assertNotIn("floor P10 · most likely · ceiling", html)
        self.assertIn("floor", html)      # the marks themselves remain
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

    def test_fixtures_sit_on_the_timeline_axis_as_coloured_boxes(self):
        # Opponents under the dots ("team names could be under the dots on X
        # axis", owner 2026-08-27) as small boxes: 3-letter code, colour =
        # difficulty, NO venue and no CAPS/lowercase convention — that mix was
        # "all mixed up" (owner, 2026-09-03); venue lives in the ties rail.
        _, html = self._card()
        self.assertIn('class="pc-dotopps"', html)
        self.assertIn('class="fxb fxb-d1"', html)         # priced: green/easy
        self.assertIn('class="fxb fxb-unpriced"', html)   # no lambdas: dashed
        self.assertIn(">LIV</span>", html)
        self.assertIn(">MCI</span>", html)                # away is caps too
        self.assertNotIn(">mci</span>", html)
        self.assertNotIn("pc-fxcol", html)

    def test_the_axis_carries_its_key(self):
        """Owner, 2026-08-26: "we don't know what green means in GW below".
        The key moved into the timeline caption with the opponents."""
        _, html = self._card()
        self.assertNotIn("CAPS = home", html)
        self.assertIn("box colour = fixture difficulty", html)
        self.assertIn("grey = not priced yet", html)

    def test_form_band_is_the_dot_timeline(self):
        _, html = self._card()
        self.assertIn('class="pc-form"', html)
        self.assertIn('class="pc-dots"', html)
        self.assertIn('aria-label="Points by gameweek: played, then projected"',
                      html)
        # Alpha's six-week vector is GW1-3 and the card is GW2, so the strip is
        # GW2 and GW3 — both projected, none played (nothing is cached).
        self.assertIn("GW2 6.5 projected", html)
        self.assertIn("<span>GW2</span>", html)
        # no player without a horizon vector and without history draws one
        payloads, _ = _payloads(with_six_week=False)
        bare = fpl_players.card_html(payloads[0])
        self.assertIn("pc-dots-empty", bare)
        self.assertNotIn("<svg", bare.split("pc-dist")[0])

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
        # the two hero numbers: the projection and its price efficiency
        self.assertIn('<b>8.00</b><i>xPts</i>', html)
        self.assertIn("<i>pts/£m</i>", html)
        self.assertIn('class="pc-verdict">we own him, in our XI</div>',
                      html)

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
        # the membership line names the ROLE, not just the squad
        self.assertIn("Currently in the XI of our squad.", html)

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
    """The landing's opening module. Owner 2026-08-26: "start by showing most
    transferred in and their cards, most transferred out, our picks, our
    takes, and model's tier on each of them" — three labelled rows of the FULL
    card_html face (2026-08-25: not compact thumbnails), takes on the two
    crowd rows."""

    def _payloads(self, n=8):
        rows = _pool(n)
        by_name = {r["name"]: {"id": i} for i, r in enumerate(rows)}
        # P00 is dumped hardest, P01 bought hardest; P02/P03 are our squad.
        by_id = {i: {"id": i, "web_name": r["name"], "status": "a", "news": "",
                     "total_points": 0, "event_points": 0, "minutes": 0,
                     "transfers_in_event": (n - i) * 10,
                     "transfers_out_event": (i + 1) * 10}
                 for i, r in enumerate(rows)}
        squad_roles = {"model": {"P02": "XI", "P03": "Bench", "P07": "XI"},
                       "consensus": {}}
        payloads, _ = fpl_players.assemble_payloads(
            rows, by_name, by_id, {}, squad_roles, None, [], {}, 2, "t")
        return payloads

    def test_three_labelled_rows_with_our_picks_leading(self):
        """Our squad first. It ran third, so the page opened on what everyone
        else was doing and buried the thing we are accountable for (owner,
        2026-08-27)."""
        html = fpl_players.top_cards_html(self._payloads())
        kickers = re.findall(r'class="tcf-kicker">([^<]+)<', html)
        self.assertEqual(kickers, ["Our picks this gameweek",
                                   "Most transferred in this gameweek",
                                   "Most transferred out this gameweek"])
        self.assertIn("tcf-lead", html)
        # and the heading is a real heading, not another grey kicker
        self.assertIn('<h2 class="tcf-kicker">', html)
        self.assertEqual(html.count('class="tcf-row"'), 3)
        # every row names what it is
        self.assertEqual(html.count('class="tcf-intro"'), 3)

    def test_full_faces_linking_to_pages(self):
        html = fpl_players.top_cards_html(self._payloads())
        # 3 bought + 3 dumped + the 3 players in this fixture's squad —
        # all FULL faces, the same figure card_html emits (three per row,
        # owner 2026-08-27)
        self.assertEqual(html.count('<figure class="player-card"'), 9)
        self.assertIn('href="/fpl/players/0-p00/"', html)
        self.assertIn("pc-ledger", html)
        self.assertIn("pc-verdict", html)
        self.assertNotIn("pc-premium", html)
        self.assertNotIn("tc-card", html)

    def test_the_crowd_rows_carry_a_take_and_our_picks_does_not(self):
        html = fpl_players.top_cards_html(self._payloads())
        self.assertEqual(html.count("Crowd is buying."), 3)
        self.assertEqual(html.count("Crowd is selling."), 3)
        # six takes for six crowd cards, none under our own picks —
        # our picks LEAD, so the slice runs to the next row, not to the end
        self.assertEqual(html.count('class="tcf-take"'), 6)
        picks = html[html.index("Our picks this gameweek"):
                     html.index("Most transferred in this gameweek")]
        self.assertNotIn("tcf-take", picks)

    def test_check_your_player_sits_under_the_last_row(self):
        html = fpl_players.top_cards_html(self._payloads())
        self.assertIn('href="/fpl/players/"', html)
        self.assertGreater(html.find("tcf-check"),
                           html.find("Most transferred out this gameweek"))

    def test_embedded_faces_use_h2_not_h1(self):
        html = fpl_players.top_cards_html(self._payloads())
        self.assertIn('<h2 class="pc-name">', html)
        self.assertNotIn("<h1", html)

    def test_a_row_with_nothing_in_it_is_omitted_not_rendered_empty(self):
        payloads = self._payloads()
        for p in payloads:                     # nobody in our squad
            p["squads"]["model"] = False
        html = fpl_players.top_cards_html(payloads)
        self.assertNotIn("Our picks", html)
        self.assertEqual(html.count('class="tcf-row"'), 2)

    def test_no_payloads_at_all_emits_nothing(self):
        self.assertEqual(fpl_players.top_cards_html([]), "")


class TestCrowdVsModel(unittest.TestCase):
    """The three rows' selection functions and the generated take."""

    @staticmethod
    def _p(name, tier="B", rank=41, in_event=0, out_event=0, model=False,
           xpts=5.0):
        return {"name": name, "slug": f"1-{name}",
                "verdict": {"tier": tier}, "ranks": {"xpts_rank": rank},
                "transfers": {"in_event": in_event, "out_event": out_event},
                "squads": {"model": model},
                "projection": {"x_points": xpts}}

    def test_the_buying_take_names_the_tier_and_the_rank(self):
        self.assertEqual(
            fpl_players.model_take(self._p("A", tier="B", rank=41), "in"),
            "Crowd is buying. Model has him tier B, 41st by xPts this week.")

    def test_the_selling_take_says_still_only_when_the_model_disagrees(self):
        self.assertEqual(
            fpl_players.model_take(self._p("A", tier="A", rank=6), "out"),
            "Crowd is selling. Model still has him tier A, 6th.")
        self.assertEqual(
            fpl_players.model_take(self._p("B", tier="C", rank=180), "out"),
            "Crowd is selling. Model has him tier C, 180th.")

    def test_ordinals_including_the_teens(self):
        for n, want in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"),
                        (11, "11th"), (12, "12th"), (13, "13th"),
                        (21, "21st"), (101, "101st"), (111, "111th")):
            self.assertEqual(fpl_players._ordinal(n), want, n)

    def test_the_take_never_states_a_fact_absent_from_the_row(self):
        """Every number in the sentence comes off the payload."""
        p = self._p("X", tier="S", rank=3)
        take = fpl_players.model_take(p, "in")
        for token in re.findall(r"\d+", take):
            self.assertEqual(token, "3")

    def test_leaders_rank_by_the_right_direction(self):
        pool = [self._p("Hot", in_event=900, out_event=1),
                self._p("Cold", in_event=1, out_event=900),
                self._p("Mid", in_event=50, out_event=50)]
        self.assertEqual(
            [p["name"] for p in fpl_players.transfer_leaders(pool, "in")],
            ["Hot", "Mid", "Cold"])
        self.assertEqual(
            [p["name"] for p in fpl_players.transfer_leaders(pool, "out")],
            ["Cold", "Mid", "Hot"])

    def test_a_player_the_crowd_never_moved_is_not_padded_in(self):
        pool = [self._p("Hot", in_event=900), self._p("Still", in_event=0)]
        self.assertEqual(
            [p["name"] for p in fpl_players.transfer_leaders(pool, "in")],
            ["Hot"])

    def test_our_picks_are_the_highest_xpts_players_in_our_squad(self):
        pool = [self._p("BestOverall", xpts=99.0, model=False),
                self._p("OurBest", xpts=9.0, model=True),
                self._p("OurWorst", xpts=2.0, model=True)]
        self.assertEqual(
            [p["name"] for p in fpl_players.our_picks(pool, count=2)],
            ["OurBest", "OurWorst"])


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


class TestFixturesCaption(unittest.TestCase):
    """The chips' key (owner 2026-08-26: "we don't know what green means in GW
    below"). It states the count and the direction of the tint, and mentions
    grey only when a grey chip is actually there to explain."""

    def test_counts_the_chips_and_names_the_direction(self):
        priced = [{"gw": g, "difficulty": 2} for g in (2, 3, 4, 5)]
        self.assertEqual(fpl_players.fixtures_caption(priced),
                         "next 4 · greener = easier fixture")

    def test_grey_is_explained_only_when_a_grey_chip_exists(self):
        mixed = [{"gw": 2, "difficulty": 2}, {"gw": 3, "difficulty": None}]
        self.assertEqual(fpl_players.fixtures_caption(mixed),
                         "next 2 · greener = easier fixture · "
                         "grey = not priced yet")

    def test_a_short_strip_says_how_short_it_is(self):
        self.assertTrue(fpl_players.fixtures_caption(
            [{"gw": 2, "difficulty": 1}]).startswith("next 1 ·"))


class TestDotTimeline(unittest.TestCase):
    """The card's stat-art (owner 2026-08-26, replacing the area wave: "but we
    can have last few realised and next few projected dots right? the wave
    seems hard to get"). Solid dots are gameweeks he PLAYED, hollow dots are
    the model's forecast, and the strip degrades honestly to whichever half
    exists."""

    @staticmethod
    def _payload(history=None, six_week=None, gameweek=5):
        return {"id": 1, "name": "P", "gameweek": gameweek,
                "form_history": history, "six_week_xpts": six_week}

    @staticmethod
    def _history(pairs):
        """[(round, points, minutes), ...] -> cache rows."""
        return [{"round": r, "total_points": p, "minutes": m}
                for r, p, m in pairs]

    def test_today_every_dot_is_projected(self):
        """GW2 of a new season: one played gameweek, nowhere near the three
        the strip would need to lead with a record. Six-week vector GW1-6, so
        the strip is GW2-6, all projected. This is the CORRECT output today."""
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(1, 2, 90)]),
            six_week={"1": 7.0, "2": 8.6, "3": 6.1, "4": 5.5, "5": 6.0,
                      "6": 7.2},
            gameweek=2))
        self.assertEqual([d["mode"] for d in dots],
                         ["played"] + ["projected"] * 5)
        self.assertEqual([d["gw"] for d in dots], [1, 2, 3, 4, 5, 6])

    def test_played_dots_carry_actual_points_projected_carry_rounded_xpts(self):
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(1, 2, 90), (2, 13, 90), (3, 6, 62)]),
            six_week={"4": 8.6, "5": 4.2},
            gameweek=4))
        played = [d for d in dots if d["mode"] == "played"]
        projected = [d for d in dots if d["mode"] == "projected"]
        self.assertEqual([d["value"] for d in played], [2.0, 13.0, 6.0])
        self.assertEqual([d["display"] for d in played], ["2", "13", "6"])
        # the DOT sits on the whole-point lattice; the precise figure survives
        # in the title text, because the rounding is a drawing decision
        self.assertEqual([d["value"] for d in projected], [9.0, 4.0])
        self.assertEqual([d["display"] for d in projected], ["8.6", "4.2"])

    def test_at_most_three_played_and_seven_dots_in_total(self):
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(r, r, 90) for r in range(1, 9)]),
            six_week={str(g): 5.0 for g in range(9, 20)},
            gameweek=9))
        self.assertEqual(len(dots), 7)
        self.assertEqual([d["gw"] for d in dots if d["mode"] == "played"],
                         [6, 7, 8])                 # the last three he played
        self.assertEqual([d["gw"] for d in dots if d["mode"] == "projected"],
                         [9, 10, 11, 12])           # the next four

    def test_an_unused_substitute_is_not_a_played_gameweek(self):
        """Zero minutes is an absence, not a bad performance — a dot at zero
        would read as the latter."""
        history = self._history([(1, 2, 90), (2, 0, 0), (3, 5, 88)])
        self.assertEqual(fpl_players.played_gameweeks(
            self._payload(history=history)), 2)
        dots = fpl_players.form_dots(self._payload(history=history,
                                                   gameweek=4))
        self.assertEqual([d["gw"] for d in dots], [1, 3])

    def test_the_horizon_never_re_projects_a_gameweek_already_played(self):
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(1, 4, 90)]),
            six_week={"1": 6.0, "2": 5.0},
            gameweek=1))
        self.assertEqual([(d["gw"], d["mode"]) for d in dots],
                         [(1, "played"), (2, "projected")])

    def test_degrades_to_realized_only_then_to_nothing(self):
        only_played = fpl_players.form_dots(self._payload(
            history=self._history([(1, 3, 90)]), six_week=None, gameweek=2))
        self.assertEqual([d["mode"] for d in only_played], ["played"])
        self.assertEqual(fpl_players.form_dots(self._payload()), [])

    def test_svg_marks_are_non_scaling_strokes_not_circles(self):
        """A <circle> in a stretched viewBox is an egg at one card width and a
        circle at neither; round-capped non-scaling strokes are discs of exact
        device pixels on both surfaces."""
        payload = self._payload(
            history=self._history([(1, 2, 90)]),
            six_week={"2": 8.6, "3": 4.0}, gameweek=2)
        svg = fpl_players._dots_svg(fpl_players.form_dots(payload))
        self.assertNotIn("<circle", svg)
        self.assertIn('stroke-linecap="round"', svg)
        self.assertEqual(svg.count('vector-effect="non-scaling-stroke"'),
                         svg.count("<line"))
        self.assertNotIn("<text", svg)           # every label is HTML

    def test_the_now_line_only_appears_between_the_two_halves(self):
        both = fpl_players._dots_svg(fpl_players.form_dots(self._payload(
            history=self._history([(1, 2, 90)]), six_week={"2": 6.0},
            gameweek=2)))
        self.assertIn("pc-now", both)
        projected_only = fpl_players._dots_svg(fpl_players.form_dots(
            self._payload(six_week={"2": 6.0, "3": 5.0}, gameweek=2)))
        self.assertNotIn("pc-now", projected_only)

    def test_both_halves_share_one_vertical_scale(self):
        """A projected 8 must sit level with a realized 8, or the strip invites
        a comparison it then fakes."""
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(1, 8, 90)]), six_week={"2": 8.0},
            gameweek=2))
        svg = fpl_players._dots_svg(dots)
        stem_re = r'x1="([\d.]+)" y1="43\.0" x2="\1" y2="([\d.]+)"'
        stems = [y for _x, y in re.findall(stem_re, svg)]
        self.assertEqual(len(stems), 2)          # one stem per dot
        self.assertEqual(stems[0], stems[1])     # equal points, equal height
        self.assertEqual(stems[0], "9.00")       # both at the top of the scale
        # ... and an unequal pair does NOT land at the same height
        uneven = fpl_players._dots_svg(fpl_players.form_dots(self._payload(
            history=self._history([(1, 8, 90)]), six_week={"2": 2.0},
            gameweek=2)))
        uneven_stems = [y for _x, y in re.findall(stem_re, uneven)]
        self.assertNotEqual(uneven_stems[0], uneven_stems[1])

    def test_labels_and_legend_are_html_and_the_caption_is_the_key(self):
        html = fpl_players._dots_html(self._payload(
            history=self._history([(1, 2, 90)]),
            six_week={"2": 8.6, "3": 4.0}, gameweek=2))
        self.assertIn('grid-template-columns:repeat(3,1fr)', html)
        # "GW" once, then bare round numbers — six GW-prefixed labels touch
        # at mobile card width
        for label in ("<span>GW1</span>", "<span>2</span>", "<span>3</span>"):
            self.assertIn(label, html)
        self.assertIn('<span class="pc-dc-played">played</span>', html)
        self.assertIn('<span class="pc-dc-proj">projected</span>', html)
        # the legend only claims what the strip actually shows
        projected_only = fpl_players._dots_html(self._payload(
            six_week={"2": 8.6}, gameweek=2))
        self.assertNotIn("pc-dc-played", projected_only)
        self.assertIn("pc-dc-proj", projected_only)

    def test_title_spells_the_strip_out(self):
        dots = fpl_players.form_dots(self._payload(
            history=self._history([(1, 2, 90)]),
            six_week={"2": 8.6}, gameweek=2))
        self.assertEqual(fpl_players.dots_title(dots),
                         "GW1 2 points played · GW2 8.6 projected")

    def test_the_strip_is_deterministic(self):
        payload = self._payload(history=self._history([(1, 2, 90)]),
                                six_week={"2": 8.6, "3": 4.0}, gameweek=2)
        self.assertEqual(fpl_players._dots_html(payload),
                         fpl_players._dots_html(payload))


class TestCardConsistency(unittest.TestCase):
    """Every card keeps the same vertical rhythm. A player with no six-gameweek
    history (a new signing) gets an honest empty band, not a missing block that
    shrinks his card out of line with the row (owner, 2026-08-26). And no card
    advertises a premium slot: the lock was removed the same day."""

    def _payload(self, six_week=None):
        return {"id": 1, "name": "P", "team": "MUN", "position": "MID",
                "price": 6.0, "gameweek": 2, "status": "a", "news": "",
                "ownership_pct": 5.0, "six_week_xpts": six_week,
                "projection": {"x_points": 5.0, "ceiling": 12.0,
                               "captain_ev": 10.0, "value": 0.8},
                "season": {"total_points": 8, "realized_ppm": 1.3, "minutes": 90},
                "ranks": {"own_vs_xpts_gap": 3},
                "verdict": {"tier": "A", "price_band": "Mid",
                            "stance": "we do not own him",
                            "rank_call": "buy"},
                "fixtures": [], "distribution": None, "page": "/fpl/players/1-p/"}

    def test_card_without_history_keeps_the_form_band(self):
        html = fpl_players.card_html(self._payload(None))
        self.assertIn("pc-form", html)
        self.assertIn("no gameweek history yet", html)

    def test_card_with_history_draws_the_chart_in_the_same_band(self):
        html = fpl_players.card_html(self._payload({"1": 5.0, "2": 4.0, "3": 6.0, "4": 5.5, "5": 4.5, "6": 5.0}))
        self.assertIn("pc-form", html)
        self.assertNotIn("no gameweek history yet", html)
        self.assertIn("<svg", html)

    def test_no_card_advertises_a_premium_slot(self):
        for six in (None, {"1": 5.0, "2": 4.0, "3": 6.0}):
            html = fpl_players.card_html(self._payload(six))
            self.assertNotIn("pc-premium", html)
            self.assertNotIn("Premium", html)
            self.assertNotIn("🔒", html)


class TestStanceReplacesTheCall(unittest.TestCase):
    """The card used to print a rank-derived "buy" for players our own
    published squad refuses to own. Owner, 2026-08-26: "We say we don't buy
    haaland and call him S premium buy". The face now states OUR POSITION; the
    model's opinion is the tier; nothing tells a reader to buy anything."""

    @staticmethod
    def _rows():
        return [{"name": n, "team": "MCI", "position": "FWD",
                 "x_points": 9.0 - i, "captain_ev": 18.0, "ceiling": 15.0,
                 "value": 0.6, "bonus": 0.5, "defcon": 0.0, "p_defcon": 0.0,
                 "cs_points": 0.0, "price": 15.0, "ownership_pct": 50.0,
                 "start_prob": 0.95}
                for i, n in enumerate(("Haaland", "Starter", "Benched",
                                       "ConsXI", "ConsBench"))]

    def _payloads(self):
        rows = self._rows()
        by_name = {r["name"]: {"id": 100 + i, "name": r["name"]}
                   for i, r in enumerate(rows)}
        by_id = {100 + i: {"id": 100 + i, "web_name": r["name"], "status": "a",
                           "news": "", "total_points": 12, "event_points": 6,
                           "minutes": 90}
                 for i, r in enumerate(rows)}
        squad_roles = {
            "model": {"Starter": "XI", "Benched": "Bench"},
            "consensus": {"ConsXI": "XI", "ConsBench": "Bench",
                          "Starter": "XI"},
        }
        payloads, _ = fpl_players.assemble_payloads(
            rows, by_name, by_id, {}, squad_roles, None, [], {}, 2,
            "2026-08-26T10:00:00+00:00")
        return {p["name"]: p for p in payloads}

    def test_stance_ladder(self):
        self.assertEqual(fpl_players.squad_stance("XI", None), "we own him, in our XI")
        self.assertEqual(fpl_players.squad_stance("Bench", None),
                         "we own him, on our bench")
        self.assertEqual(fpl_players.squad_stance(None, "XI"),
                         "the consensus squad owns him, we do not")
        self.assertEqual(fpl_players.squad_stance(None, "Bench"),
                         "on the consensus bench, we do not own him")
        self.assertEqual(fpl_players.squad_stance(None, None),
                         "we do not own him")

    def test_our_squad_outranks_the_reference_squad(self):
        """A player in both is described by OUR position — the site's own team
        is the claim it is entitled to make."""
        self.assertEqual(fpl_players.squad_stance("XI", "XI"), "we own him, in our XI")
        self.assertEqual(fpl_players.squad_stance("Bench", "XI"),
                         "we own him, on our bench")

    def test_a_player_in_neither_squad_never_renders_the_word_buy(self):
        """THE acceptance test. Haaland is tier S and Premium and in neither
        published squad; his card must not tell anyone to buy him."""
        haaland = self._payloads()["Haaland"]
        self.assertEqual(haaland["verdict"]["tier"], "S")
        self.assertEqual(haaland["verdict"]["price_band"], "Premium")
        self.assertEqual(haaland["verdict"]["rank_call"], "buy")   # the JSON
        for html in (fpl_players.card_html(haaland),
                     fpl_players.player_page_html(haaland, 2)):
            self.assertNotIn("buy", html.lower())
            self.assertIn("we do not own him", html)

    def test_a_player_in_our_xi_renders_in_our_xi(self):
        starter = self._payloads()["Starter"]
        html = fpl_players.card_html(starter)
        self.assertIn('class="pc-verdict">we own him, in our XI', html)
        self.assertIn('data-stance="we own him, in our XI"', html)

    def test_every_stance_reaches_the_card_face(self):
        want = {"Haaland": "we do not own him",
                "Starter": "we own him, in our XI",
                "Benched": "we own him, on our bench",
                "ConsXI": "the consensus squad owns him, we do not",
                "ConsBench": "on the consensus bench, we do not own him"}
        payloads = self._payloads()
        for name, stance in want.items():
            self.assertEqual(payloads[name]["verdict"]["stance"], stance, name)
            self.assertIn(f'data-stance="{stance}"',
                          fpl_players.card_html(payloads[name]), name)

    def test_no_rendered_surface_reads_the_rank_call(self):
        """It survives in the JSON so a consumer keyed on it keeps working,
        renamed and documented — but nothing silently depends on it."""
        payloads = self._payloads()
        for p in payloads.values():
            self.assertNotIn("call", p["verdict"])
            self.assertIn("rank_call", p["verdict"])
            self.assertNotIn("data-call", fpl_players.card_html(p))
        env = fpl_players.player_json(payloads["Haaland"], "m", "u", "l", "t")
        self.assertEqual(env["verdict"]["rank_call"], "buy")

    def test_the_page_keeps_the_model_and_our_position_apart(self):
        html = fpl_players.player_page_html(self._payloads()["Benched"], 2)
        self.assertIn("<td>Model tier</td>", html)
        self.assertIn("<td>Our position</td><td>we own him, on our bench</td>", html)
        self.assertIn("Currently in the bench of our squad.", html)

    def test_the_consensus_bench_is_not_described_as_the_consensus_xi(self):
        html = fpl_players.player_page_html(self._payloads()["ConsBench"], 2)
        self.assertIn("on the consensus bench, we do not own him", html)
        self.assertNotIn("the consensus squad owns him, we do not", html)


class TestHeroBounds(unittest.TestCase):
    """The hero mean, flanked by its own distribution (owner 2026-08-26: "we
    have space to show small lower bound expected points in the middle and
    small upper bound")."""

    def test_floor_and_ceiling_are_one_demoted_caption_line(self):
        """They flanked the hero at near-hero size and dominated the face they
        were only meant to qualify ("Floor and ceiling can be lower", owner
        2026-08-27). One muted line under the hero pair now."""
        payloads, _ = _payloads()
        html = fpl_players.card_html(payloads[0])
        hero = html[html.index('class="pc-hero"'):html.index("pc-form")]
        self.assertIn('class="pc-heroline"', hero)
        self.assertIn("floor 2 · ceiling 13", hero)
        self.assertNotIn("pc-bound", hero)
        # and the hero pair itself is xPts then pts/£m
        self.assertLess(hero.index("<i>xPts</i>"), hero.index("<i>pts/£m</i>"))

    def test_a_card_without_a_distribution_degrades_silently(self):
        payloads, _ = _payloads(with_distribution=False)
        html = fpl_players.card_html(payloads[0])
        self.assertIn("<b>8.00</b><i>xPts</i>", html)
        self.assertNotIn("pc-heroline", html)
        self.assertNotIn("10th and 90th percentile", html)


class TestValueCell(unittest.TestCase):
    """Projected pts/£m is back and is the primary figure; realized only
    appears once the division means something (owner 2026-08-26: "but we used
    to have expected points per million")."""

    @staticmethod
    def _payload(played, value=0.72, realized=1.41):
        return {"projection": {"value": value},
                "season": {"realized_ppm": realized},
                "form_history": [{"round": r, "total_points": 5, "minutes": 90}
                                 for r in range(1, played + 1)]}

    def test_below_the_bar_only_the_projection_shows(self):
        cell = fpl_players.value_cell(self._payload(played=2))
        self.assertEqual(cell, "<span>value <b>0.72 pts/£m</b></span>")
        self.assertNotIn("so far", cell)

    def test_at_the_bar_realized_joins_it(self):
        cell = fpl_players.value_cell(self._payload(played=3))
        self.assertEqual(cell, "<span>pts/£m <b>0.72</b> proj · "
                               "<b>1.41</b> so far</span>")

    def test_the_bar_is_the_dot_timelines_own_played_count(self):
        self.assertEqual(fpl_players.REALIZED_PPM_MIN_PLAYED,
                         fpl_players.DOTS_PLAYED_MAX)

    def test_a_missing_realized_figure_never_forces_the_pair(self):
        payload = self._payload(played=5)
        payload["season"]["realized_ppm"] = None
        self.assertNotIn("so far", fpl_players.value_cell(payload))

    def test_the_card_carries_the_projected_value_today(self):
        """GW2 reality: nobody has three played gameweeks, so every card shows
        the projection alone."""
        payloads, _ = _payloads()
        html = fpl_players.card_html(payloads[0])
        # the projection is the SECOND HERO now, not a stat row
        self.assertIn('<span class="pc-hn pc-hn2"><b>0.80</b><i>pts/£m</i></span>', html)
        self.assertNotIn("so far", html)


class TestRankedIndex(unittest.TestCase):
    """/fpl/players/ answers two questions the cards raised and never answered.

    A card says "model rank 11th" and points per million lived only inside the
    efficiency article's top-N, so neither the full ranking nor the value
    column existed anywhere a reader could reach (owner, 2026-08-27: "can we
    have top xpts per million ... and a full model rank somewhere").
    """

    def _payloads(self):
        out = []
        for i, (name, xp, price) in enumerate(
                [("Cheap", 6.0, 4.0), ("Best", 9.0, 12.0), ("Mid", 7.0, 7.0)]):
            out.append({
                "id": i, "slug": f"{i}-{name.lower()}", "name": name,
                "team": "LIV", "position": "MID", "price": price,
                "gameweek": 2, "status": "a",
                "projection": {"x_points": xp, "ceiling": xp * 2,
                               "captain_ev": xp * 2},
                "season": {"total_points": 0, "minutes": 0},
                "ranks": {"own_vs_xpts_gap": 0, "xpts_rank": i + 1},
                "verdict": {"tier": "A", "price_band": "Mid",
                            "stance": "we do not own him"},
                "ownership_pct": 1.0, "fixtures": [], "distribution": {},
            })
        return out

    def _html(self):
        return fpl_players.index_page_html(
            self._payloads(), 2, "/api/fpl/gw2/players.json")

    def test_the_table_is_in_model_rank_order(self):
        html = self._html()
        order = re.findall(r'data-name="([^"]+)"', html)
        self.assertEqual(order, ["Best", "Mid", "Cheap"])

    def test_every_row_carries_its_rank(self):
        html = self._html()
        self.assertIn('data-rank="1"', html)
        self.assertIn('data-rank="3"', html)
        self.assertIn('<td class="pi-rank">1</td>', html)

    def test_points_per_million_is_a_column(self):
        html = self._html()
        self.assertIn("pts/£m", html)
        # Cheap: 6.0 over £4.0m
        self.assertIn('data-perm="1.5000"', html)
        self.assertIn("<td>1.50</td>", html)

    def test_a_free_player_does_not_divide_by_zero(self):
        payloads = self._payloads()
        payloads[0]["price"] = 0
        html = fpl_players.index_page_html(payloads, 2, "/x.json")
        self.assertIn('data-perm="0.0000"', html)

    def test_the_columns_that_sort_say_so(self):
        html = self._html()
        for key in ("rank", "name", "xpts", "perm"):
            self.assertIn(f'data-sort="{key}"', html)

    def test_sorting_is_enhancement_not_a_requirement(self):
        """No-JS readers still get the ranking — it is the default order."""
        html = self._html()
        head = html.index("<tbody>")
        self.assertLess(html.index('data-name="Best"'),
                        html.index('data-name="Cheap"'))
        self.assertGreater(head, 0)
