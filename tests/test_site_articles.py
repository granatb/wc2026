import json
import os
import tempfile
import unittest

from evmax import articles


class LoadPlayerMetaTest(unittest.TestCase):
    def _write(self, players):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"_comment": "x", "players": players}, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_maps_name_to_metadata(self):
        path = self._write([
            {"name": "Kane", "aliases": [], "team": "England", "fifa_pos": "FWD",
             "fifa_price": 11.0, "ownership": 42.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertEqual(meta["Kane"]["team"], "England")
        self.assertEqual(meta["Kane"]["position"], "FWD")
        self.assertEqual(meta["Kane"]["price"], 11.0)
        self.assertEqual(meta["Kane"]["ownership_pct"], 42.0)

    def test_aliases_also_resolve(self):
        path = self._write([
            {"name": "Bruno Fernandes", "aliases": ["B. Fernandes"], "team": "Portugal",
             "fifa_pos": "MID", "fifa_price": 9.5, "ownership": 18.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertIn("B. Fernandes", meta)
        self.assertEqual(meta["B. Fernandes"]["position"], "MID")


class BuildRowsTest(unittest.TestCase):
    def setUp(self):
        self.means = {
            "Kane": {"position": "FWD", "goals": 0.8, "assists": 0.2, "clean_sheet": 0.3,
                     "played": 1.0, "yellow": 0.1, "red": 0.0, "sot": 1.2, "saves": 0.0,
                     "conc_beyond": 0.4, "minutes": 90.0, "goal_share": 0.4, "assist_share": 0.2},
        }
        self.samples = {"Kane": [0, 1, 0, 2, 1]}
        self.meta = {"Kane": {"team": "England", "position": "FWD", "price": 11.0,
                              "ownership_pct": 42.0}}
        self.kickoffs = {"England": "2026-06-26T19:00:00+00:00"}

    def test_row_has_xpts_ceiling_captain_value_kickoff(self):
        rows = articles.build_rows(self.means, self.samples, self.meta, self.kickoffs)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["name"], "Kane")
        self.assertGreater(r["x_points"], 0)
        self.assertAlmostEqual(r["captain_ev"], 2 * r["x_points"], places=6)
        self.assertGreaterEqual(r["ceiling"], r["x_points"])  # P85 goals >= mean goals
        self.assertAlmostEqual(r["value"], round(r["x_points"] / 11.0, 3), places=6)
        self.assertEqual(r["kickoff"], "2026-06-26T19:00:00+00:00")

    def test_players_without_meta_or_position_are_skipped(self):
        means = dict(self.means)
        means["Ghost"] = dict(self.means["Kane"])  # no meta entry
        rows = articles.build_rows(means, {"Kane": [0, 1], "Ghost": [0]}, self.meta, self.kickoffs)
        self.assertEqual([r["name"] for r in rows], ["Kane"])


def _row(name, pos, xp, own=20.0, price=8.0, ceiling=None):
    return {"name": name, "team": name + "land", "position": pos, "x_points": xp,
            "captain_ev": 2 * xp, "ceiling": ceiling if ceiling is not None else xp,
            "price": price, "ownership_pct": own, "value": xp / price, "kickoff": None}


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row("A", "FWD", 9.0, own=50.0, price=11.0),
            _row("B", "MID", 6.0, own=3.0, price=6.0),
            _row("C", "DEF", 4.5, own=1.0, price=4.0),
        ]

    def test_rank_captains_orders_by_captain_ev_desc_and_assigns_rank(self):
        out = articles.rank_captains(self.rows)
        self.assertEqual([r["name"] for r in out], ["A", "B", "C"])
        self.assertEqual(out[0]["rank"], 1)

    def test_rank_value_orders_by_value_desc(self):
        out = articles.rank_value(self.rows)
        # C: 4.5/4=1.125, B: 6/6=1.0, A: 9/11=0.818
        self.assertEqual([r["name"] for r in out], ["C", "B", "A"])

    def test_differentials_filter_low_owned_and_min_xpts(self):
        out = articles.differentials(self.rows)
        # own<10 AND x_points>=4.0 -> B(6.0,own3) and C(4.5,own1); A excluded (own 50)
        self.assertEqual(sorted(r["name"] for r in out), ["B", "C"])
        self.assertEqual(out[0]["x_points"], 6.0)  # sorted by xpts desc -> B first


class SelectXITest(unittest.TestCase):
    def _pool(self):
        rows = []
        rows += [_row(f"GK{i}", "GK", 5 - i * 0.1) for i in range(3)]
        rows += [_row(f"DEF{i}", "DEF", 6 - i * 0.1) for i in range(8)]
        rows += [_row(f"MID{i}", "MID", 7 - i * 0.1) for i in range(8)]
        rows += [_row(f"FWD{i}", "FWD", 8 - i * 0.1) for i in range(6)]
        return rows

    def test_returns_valid_xi(self):
        xi = articles.select_xi(self._pool(), "x_points")
        self.assertEqual(len(xi), articles.XI_SIZE)
        counts = {}
        for r in xi:
            counts[r["position"]] = counts.get(r["position"], 0) + 1
        self.assertEqual(counts["GK"], 1)
        self.assertGreaterEqual(counts["DEF"], 3)
        self.assertGreaterEqual(counts["MID"], 2)
        self.assertGreaterEqual(counts["FWD"], 1)
        for pos, mx in articles.POS_MAX.items():
            self.assertLessEqual(counts.get(pos, 0), mx)

    def test_ranks_by_the_given_key(self):
        # high-ceiling XI should sort on ceiling, not x_points
        pool = self._pool()
        pool[10]["ceiling"] = 99.0  # a DEF with huge ceiling
        xi = articles.select_xi(pool, "ceiling")
        self.assertEqual(xi[0]["ceiling"], 99.0)

    def test_assigns_sequential_rank_1_to_11(self):
        xi = articles.select_xi(self._pool(), "x_points")
        self.assertEqual([r["rank"] for r in xi], list(range(1, 12)))

    def test_does_not_mutate_input_rows(self):
        pool = self._pool()
        articles.select_xi(pool, "x_points")
        self.assertNotIn("rank", pool[0])  # original rows untouched

    def test_raises_when_position_pool_too_small(self):
        # only 2 defenders but POS_MIN["DEF"] == 3
        pool = [_row("GK0", "GK", 5.0)]
        pool += [_row(f"DEF{i}", "DEF", 6 - i * 0.1) for i in range(2)]
        pool += [_row(f"MID{i}", "MID", 7 - i * 0.1) for i in range(5)]
        pool += [_row(f"FWD{i}", "FWD", 8 - i * 0.1) for i in range(5)]
        with self.assertRaises(ValueError):
            articles.select_xi(pool, "x_points")


class BlowoutTest(unittest.TestCase):
    def test_blowout_transfers_picks_attackers_from_highest_lambda_fixtures(self):
        # two fixtures; (Spain vs Malta) has the biggest combined lambda
        fixture_totals = {("Spain", "Malta"): 4.2, ("Iran", "Qatar"): 2.1}
        teams_in_blowout = {"Spain", "Malta"}
        rows = [
            _row("Oyarzabal", "FWD", 7.0), _row("Pedri", "MID", 5.5),
            _row("Cucurella", "DEF", 3.0),       # defender -> excluded (attackers only)
            _row("IranFwd", "FWD", 6.0),         # not in a blowout fixture
        ]
        for r in rows:
            r["team"] = {"Oyarzabal": "Spain", "Pedri": "Spain", "Cucurella": "Spain",
                         "IranFwd": "Iran"}[r["name"]]
        out = articles.blowout_transfers(rows, teams_in_blowout)
        self.assertEqual([r["name"] for r in out], ["Oyarzabal", "Pedri"])
        self.assertEqual(out[0]["rank"], 1)


class EfficiencyTest(unittest.TestCase):
    def test_efficiency_ranks_by_value_desc(self):
        rows = [_row("A", "FWD", 9.0, price=11.0), _row("B", "MID", 6.0, price=6.0),
                _row("C", "DEF", 4.5, price=4.0)]
        out = articles.efficiency(rows)
        self.assertEqual([r["name"] for r in out], ["C", "B", "A"])  # 1.125 > 1.0 > 0.818
        self.assertEqual(out[0]["rank"], 1)


class ByPositionTest(unittest.TestCase):
    def test_by_position_filters_and_ranks_by_xpoints(self):
        rows = [
            _row("Trippier", "DEF", 6.0),
            _row("Kane",     "FWD", 9.0),
            _row("Mazraoui", "DEF", 5.5),
            _row("Foden",    "MID", 7.0),
        ]
        out = articles.by_position(rows, "DEF")
        self.assertEqual([r["name"] for r in out], ["Trippier", "Mazraoui"])
        self.assertEqual(out[0]["rank"], 1)
        self.assertEqual(out[1]["rank"], 2)

    def test_by_position_empty_when_no_match(self):
        rows = [_row("Kane", "FWD", 9.0)]
        out = articles.by_position(rows, "GK")
        self.assertEqual(out, [])


class RiskyTest(unittest.TestCase):
    def test_risky_filters_by_ownership_and_ranks_by_ceiling(self):
        rows = [
            _row("Diallo",  "FWD", 5.0, own=1.0,  ceiling=18.0),
            _row("Kane",    "FWD", 9.0, own=40.0, ceiling=14.0),   # excluded: own >= 25
            _row("Wirtz",   "MID", 7.0, own=12.0, ceiling=11.0),
        ]
        out = articles.risky(rows)
        names = [r["name"] for r in out]
        self.assertIn("Diallo", names)
        self.assertIn("Wirtz", names)
        self.assertNotIn("Kane", names)  # own 40% >= 25
        self.assertEqual(out[0]["name"], "Diallo")  # highest ceiling first
        self.assertEqual(out[0]["rank"], 1)

    def test_risky_excludes_none_ownership(self):
        rows = [_row("Ghost", "MID", 5.0, own=None, ceiling=20.0)]
        rows[0]["ownership_pct"] = None
        out = articles.risky(rows)
        self.assertEqual(out, [])


class ArticleSetTest(unittest.TestCase):
    def test_articles_list_has_correct_slugs(self):
        expected = ["captains", "matches", "best-xi", "defenders", "risky", "efficiency",
                    "blowout-transfers"]
        self.assertEqual(articles.ARTICLES, expected)

    def test_matches_is_second(self):
        self.assertEqual(articles.ARTICLES[1], "matches")

    def test_article_titles_match_articles(self):
        for slug in articles.ARTICLES:
            self.assertIn(slug, articles.ARTICLE_TITLES,
                          f"ARTICLE_TITLES missing slug '{slug}'")


class FormationTest(unittest.TestCase):
    def test_formation_string(self):
        xi = ([_row("g", "GK", 1)] + [_row(f"d{i}", "DEF", 1) for i in range(3)]
              + [_row(f"m{i}", "MID", 1) for i in range(4)]
              + [_row(f"f{i}", "FWD", 1) for i in range(3)])
        self.assertEqual(articles.formation_of(xi), "3-4-3")


# ---------------------------------------------------------------------------
# MatchSample stub — avoids importing the full engine in a unit test.
# ---------------------------------------------------------------------------

class _FakeMatchSample:
    """Minimal stand-in for core.engine_events.MatchSample."""

    def __init__(self, match_id, home, away, scorelines):
        self.match_id = match_id
        self.home = home
        self.away = away
        self.scorelines = scorelines          # {(hg, ag): count}
        self.sims = sum(scorelines.values())

    def prob(self, hg, ag):
        return self.scorelines.get((hg, ag), 0) / self.sims if self.sims else 0.0

    def marginal_home(self):
        from collections import defaultdict
        d = defaultdict(int)
        for (hg, _ag), c in self.scorelines.items():
            d[hg] += c
        return {k: v / self.sims for k, v in d.items()}

    def marginal_away(self):
        from collections import defaultdict
        d = defaultdict(int)
        for (_hg, ag), c in self.scorelines.items():
            d[ag] += c
        return {k: v / self.sims for k, v in d.items()}

    def outcome_probs(self):
        d = {"H": 0, "D": 0, "A": 0}
        for (hg, ag), c in self.scorelines.items():
            d["H" if hg > ag else "A" if ag > hg else "D"] += c
        return {k: v / self.sims for k, v in d.items()}


class _FakeFixture:
    """Minimal stand-in for core.fixtures.Fixture."""

    def __init__(self, match_id, home, away, kickoff_iso, lam_home=1.5, lam_away=0.8):
        from datetime import datetime, timezone
        self.match_id = match_id
        self.home = home
        self.away = away
        self.kickoff = datetime.fromisoformat(kickoff_iso).replace(tzinfo=timezone.utc)
        self._lh = lam_home
        self._la = lam_away

    def lambdas(self):
        return self._lh, self._la


class MatchPredictionsTest(unittest.TestCase):
    """Unit tests for articles.match_predictions using synthetic inputs."""

    def _make_match_samples(self):
        """Two synthetic MatchSamples:
        - 'decided': England dominant (H wins ~70% → max outcome > 0.45, close=False)
        - 'close':   perfectly balanced three-way (H/D/A each ~33%, close=True)
        """
        decided_sl = {
            (2, 0): 300, (1, 0): 200, (2, 1): 100,
            (0, 0): 100, (1, 1): 100, (0, 1): 100, (0, 2): 100,
        }  # H wins 600/1000 = 60% → max outcome = 0.60 > 0.45

        close_sl = {
            (1, 0): 333, (0, 0): 334, (0, 1): 333,
        }  # H 33.3%, D 33.4%, A 33.3% → max = 0.334 < 0.45

        return {
            "m1": _FakeMatchSample("m1", "England", "Senegal", decided_sl),
            "m2": _FakeMatchSample("m2", "Spain", "Germany", close_sl),
        }

    def _patch_fixtures(self, fake_fixtures):
        """Temporarily replace core.fixtures.by_round with fake data."""
        import core.fixtures as core_fx
        original = core_fx.by_round
        core_fx.by_round = lambda r: fake_fixtures
        return original

    def _restore_fixtures(self, original):
        import core.fixtures as core_fx
        core_fx.by_round = original

    def setUp(self):
        self._fake_fx = [
            _FakeFixture("m1", "England", "Senegal", "2026-06-28T18:00:00+00:00"),
            _FakeFixture("m2", "Spain", "Germany",   "2026-06-28T21:00:00+00:00"),
        ]
        self._orig = self._patch_fixtures(self._fake_fx)
        self._ms = self._make_match_samples()

    def tearDown(self):
        self._restore_fixtures(self._orig)

    def test_returns_one_entry_per_fixture(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        self.assertEqual(len(result), 2)

    def test_entry_has_required_keys(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        required = {"match", "home", "away", "kickoff",
                    "exp_home_goals", "exp_away_goals", "exp_total",
                    "top_scoreline", "p_home", "p_draw", "p_away", "close"}
        for entry in result:
            self.assertTrue(required.issubset(entry.keys()),
                            f"Missing keys: {required - entry.keys()}")

    def test_top_scoreline_format(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        for entry in result:
            parts = entry["top_scoreline"].split("-")
            self.assertEqual(len(parts), 2, f"Bad scoreline: {entry['top_scoreline']}")
            self.assertTrue(parts[0].isdigit() and parts[1].isdigit(),
                            f"Non-numeric scoreline: {entry['top_scoreline']}")

    def test_probabilities_sum_to_one(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        for entry in result:
            total = entry["p_home"] + entry["p_draw"] + entry["p_away"]
            self.assertAlmostEqual(total, 1.0, places=1,
                                   msg=f"Probs don't sum to 1 for {entry['match']}: {total}")

    def test_close_flag_decided_fixture(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        england = next(e for e in result if e["home"] == "England")
        # Decided fixture: p_home ~0.60 > 0.45 → close=False
        self.assertFalse(england["close"],
                         f"Expected close=False for decided fixture, got {england}")

    def test_close_flag_balanced_fixture(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        spain = next(e for e in result if e["home"] == "Spain")
        # Balanced fixture: max prob ~0.33 < 0.45 → close=True
        self.assertTrue(spain["close"],
                        f"Expected close=True for balanced fixture, got {spain}")

    def test_sorted_by_kickoff(self):
        result = articles.match_predictions(self._ms, fantasy_round=3)
        kickoffs = [e["kickoff"] for e in result]
        self.assertEqual(kickoffs, sorted(kickoffs))

    def test_fallback_when_match_absent_from_samples(self):
        """When match_samples is empty, falls back to lambda-Poisson grid."""
        result = articles.match_predictions({}, fantasy_round=3)
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertIn("top_scoreline", entry)
            self.assertIsInstance(entry["close"], bool)
