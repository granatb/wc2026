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
        self.assertGreaterEqual(r["ceiling_ratio"], 1.0)

    def test_a_keeper_with_no_goal_upside_gets_ceiling_ratio_of_one(self):
        """Goalkeepers can't score outfield-style points, so with zero goal upside
        their ceiling equals their mean — ceiling_ratio should be exactly 1.0, the
        signal that flags 'safe floor, no big-haul scenario' captains."""
        means = {"Keeper": {"position": "GK", "goals": 0.0, "assists": 0.0,
                            "clean_sheet": 0.4, "played": 1.0, "yellow": 0.0, "red": 0.0,
                            "sot": 0.0, "saves": 2.0, "conc_beyond": 0.1, "minutes": 90.0,
                            "goal_share": 0.0, "assist_share": 0.0}}
        samples = {"Keeper": [0, 0, 0, 0, 0]}  # never scores -> no ceiling upside
        meta = {"Keeper": {"team": "England", "position": "GK", "price": 5.0,
                           "ownership_pct": 10.0}}
        rows = articles.build_rows(means, samples, meta, {})
        self.assertAlmostEqual(rows[0]["ceiling_ratio"], 1.0, places=3)

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


class WildcardSquadTest(unittest.TestCase):
    def _pool(self):
        """Price positively correlated with x_points -- the realistic case where
        cheap players are genuinely weaker, so bench-cheap != bench-best."""
        rows = []
        rows += [_row(f"GK{i}", "GK", 5.5 - i * 0.25, price=5.5 - i * 0.25)
                for i in range(4)]
        rows += [_row(f"DEF{i}", "DEF", 6.5 - i * 0.25, price=6.5 - i * 0.25)
                for i in range(10)]
        rows += [_row(f"MID{i}", "MID", 7.5 - i * 0.25, price=7.5 - i * 0.25)
                for i in range(10)]
        rows += [_row(f"FWD{i}", "FWD", 8.5 - i * 0.25, price=8.5 - i * 0.25)
                for i in range(8)]
        return rows

    def test_returns_15_with_legal_quotas(self):
        entries, meta = articles.wildcard_squad(self._pool())
        self.assertEqual(len(entries), 15)
        counts = {}
        for e in entries:
            counts[e["position"]] = counts.get(e["position"], 0) + 1
        self.assertEqual(counts, {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3})

    def test_budget_respected(self):
        entries, meta = articles.wildcard_squad(self._pool(), budget=100.0)
        total = sum(e["price"] for e in entries)
        self.assertLessEqual(round(total, 2), 100.0)
        self.assertAlmostEqual(meta["total_cost"], round(total, 2), places=2)
        self.assertAlmostEqual(meta["left_over"], round(100.0 - total, 2), places=2)

    def test_xi_first_ordering_by_x_points(self):
        entries, meta = articles.wildcard_squad(self._pool())
        xi = [e for e in entries if e["role"] == "XI"]
        bench = [e for e in entries if e["role"] == "Bench"]
        self.assertEqual(len(xi), 11)
        self.assertEqual(len(bench), 4)
        self.assertEqual([e["rank"] for e in xi], list(range(1, 12)))
        self.assertEqual([e["rank"] for e in bench], [12, 13, 14, 15])
        # XI ranked by x_points desc
        xpts = [e["x_points"] for e in xi]
        self.assertEqual(xpts, sorted(xpts, reverse=True))

    def test_roles_assigned_to_every_entry(self):
        entries, meta = articles.wildcard_squad(self._pool())
        self.assertTrue(all(e["role"] in ("XI", "Bench") for e in entries))

    def test_meta_fields_present(self):
        entries, meta = articles.wildcard_squad(self._pool())
        for key in ("total_cost", "xi_xpoints", "formation", "budget", "left_over"):
            self.assertIn(key, meta)
        xi = [e for e in entries if e["role"] == "XI"]
        self.assertAlmostEqual(meta["xi_xpoints"], round(sum(e["x_points"] for e in xi), 2),
                               places=2)
        self.assertEqual(meta["formation"], articles.formation_of(xi))
        self.assertEqual(meta["budget"], 100.0)

    def test_tight_budget_forces_downgrade_repair(self):
        """A budget above the cheapest-possible legal squad but below the greedy
        best-XI cost must trigger the downgrade repair loop, not just fail."""
        pool = self._pool()
        # Cheapest possible legal squad in this pool costs ~83.25m (2 cheapest GK +
        # 5 cheapest DEF + 5 cheapest MID + 3 cheapest FWD); a naive best-XI-first
        # build costs ~96.5m. 88.0m sits in between -- feasible only via repair.
        entries, meta = articles.wildcard_squad(pool, budget=88.0)
        self.assertEqual(len(entries), 15)
        self.assertLessEqual(meta["total_cost"], 88.0)

    def test_impossible_pool_raises_value_error(self):
        # Only 2 defenders available -- can never fill the 5-DEF quota.
        pool = [_row(f"GK{i}", "GK", 5.0, price=5.0) for i in range(2)]
        pool += [_row(f"DEF{i}", "DEF", 5.0, price=5.0) for i in range(2)]
        pool += [_row(f"MID{i}", "MID", 5.0, price=5.0) for i in range(5)]
        pool += [_row(f"FWD{i}", "FWD", 5.0, price=5.0) for i in range(3)]
        with self.assertRaises(ValueError):
            articles.wildcard_squad(pool)

    def test_infeasible_budget_raises_value_error(self):
        pool = self._pool()
        with self.assertRaises(ValueError):
            articles.wildcard_squad(pool, budget=1.0)

    def test_rows_missing_price_are_excluded(self):
        pool = self._pool()
        pool[0] = dict(pool[0])
        pool[0]["price"] = None
        entries, meta = articles.wildcard_squad(pool)
        self.assertNotIn(pool[0]["name"], [e["name"] for e in entries])


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
        expected = ["captains", "matches", "fixtures", "transfers", "wildcard",
                    "defenders", "risky", "efficiency", "blowout-transfers"]
        self.assertEqual(articles.ARTICLES, expected)

    def test_matches_is_second(self):
        self.assertEqual(articles.ARTICLES[1], "matches")

    def test_fixtures_is_third(self):
        self.assertEqual(articles.ARTICLES[2], "fixtures")

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
                    "top_scoreline", "p_home", "p_draw", "p_away", "close",
                    "p_cs_home", "p_cs_away"}
        for entry in result:
            self.assertTrue(required.issubset(entry.keys()),
                            f"Missing keys: {required - entry.keys()}")

    def test_p_cs_from_simulated_marginals(self):
        """England (home) keeps a clean sheet whenever Senegal (away) is held to
        0: (2,0)+(1,0) = 500... plus (0,0) with away=0 too -> (2,0)+(1,0)+(0,0)
        = 300+200+100 = 600/1000 = 0.6. Senegal's clean sheet (England held to 0)
        is (0,0)+(0,1)+(0,2) = 100+100+100 = 300/1000 = 0.3."""
        result = articles.match_predictions(self._ms, fantasy_round=3)
        england = next(e for e in result if e["home"] == "England")
        self.assertAlmostEqual(england["p_cs_home"], 0.6, places=2)
        self.assertAlmostEqual(england["p_cs_away"], 0.3, places=2)

    def test_p_cs_fallback_uses_poisson_from_lambdas(self):
        """When match_samples is empty, p_cs falls back to exp(-lam_opponent)."""
        import math
        result = articles.match_predictions({}, fantasy_round=3)
        england = next(e for e in result if e["home"] == "England")
        # fixture stub default lambdas: lam_home=1.5, lam_away=0.8
        self.assertAlmostEqual(england["p_cs_home"], math.exp(-0.8), places=3)
        self.assertAlmostEqual(england["p_cs_away"], math.exp(-1.5), places=3)

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

    def test_group_round_has_no_advance_fields(self):
        """Round 3 is a group matchday — a draw doesn't eliminate anyone, so
        advancement probability isn't meaningful and must not be emitted."""
        result = articles.match_predictions(self._ms, fantasy_round=3)
        for entry in result:
            self.assertNotIn("p_advance_home", entry)
            self.assertNotIn("p_advance_away", entry)

    def test_knockout_round_has_advance_fields_summing_to_one(self):
        """Round 5 (>= KNOCKOUT_ROUND_START) is straight knockout: every fixture
        must carry p_advance_home + p_advance_away == 1 (someone always advances)."""
        result = articles.match_predictions(self._ms, fantasy_round=5)
        for entry in result:
            self.assertIn("p_advance_home", entry)
            self.assertIn("p_advance_away", entry)
            self.assertAlmostEqual(
                entry["p_advance_home"] + entry["p_advance_away"], 1.0, places=2)

    def test_knockout_advance_favours_the_stronger_lambda_side_on_a_draw(self):
        """England (lam_home=1.5) is stronger than Senegal (lam_away=0.8) in the
        fixture stub, so England's advance probability should exceed its raw
        90-minute win probability once the drawn share is split by strength."""
        result = articles.match_predictions(self._ms, fantasy_round=5)
        england = next(e for e in result if e["home"] == "England")
        self.assertGreater(england["p_advance_home"], england["p_home"])

    def test_results_param_marks_finished_fixture_and_keeps_predictions(self):
        """When a (home, away) pair is present in `results`, the entry gains
        final_score + finished=True while every prediction field survives —
        this is predicted-vs-actual, not a replacement."""
        results = {("england", "senegal"): {"hs": 2, "as": 1}}
        result = articles.match_predictions(self._ms, fantasy_round=3, results=results)
        england = next(e for e in result if e["home"] == "England")
        spain = next(e for e in result if e["home"] == "Spain")
        self.assertEqual(england["final_score"], "2-1")
        self.assertTrue(england["finished"])
        # prediction fields untouched
        self.assertIn("top_scoreline", england)
        self.assertIn("p_home", england)
        # the other, unmatched fixture is not marked finished
        self.assertNotIn("finished", spain)

    def test_results_none_means_no_fixture_marked_finished(self):
        """Default (pre-round / non-live) behaviour: no results param -> no
        finished/final_score fields at all, matching today's output shape."""
        result = articles.match_predictions(self._ms, fantasy_round=3)
        for entry in result:
            self.assertNotIn("finished", entry)
            self.assertNotIn("final_score", entry)

    def test_results_lookup_is_unaffected_by_unmatched_pair(self):
        """A results map with no matching (home, away) key leaves every entry
        exactly as if results=None had been passed."""
        results = {("brazil", "argentina"): {"hs": 1, "as": 0}}
        result = articles.match_predictions(self._ms, fantasy_round=3, results=results)
        for entry in result:
            self.assertNotIn("finished", entry)


class IsFinishedStatusTest(unittest.TestCase):
    def test_recognises_espn_style_full_time(self):
        self.assertTrue(articles._is_finished_status("STATUS_FULL_TIME"))

    def test_recognises_espn_style_final_aet_and_pen(self):
        self.assertTrue(articles._is_finished_status("STATUS_FINAL_AET"))
        self.assertTrue(articles._is_finished_status("STATUS_FINAL_PEN"))

    def test_recognises_fifa_feed_lowercase_complete(self):
        self.assertTrue(articles._is_finished_status("complete"))

    def test_scheduled_is_not_finished(self):
        self.assertFalse(articles._is_finished_status("scheduled"))
        self.assertFalse(articles._is_finished_status("STATUS_SCHEDULED"))

    def test_none_or_empty_is_not_finished(self):
        self.assertFalse(articles._is_finished_status(None))
        self.assertFalse(articles._is_finished_status(""))


class FinishedResultsMapTest(unittest.TestCase):
    def _patch_fifa_fixtures(self, fake_fixtures):
        import core.fifa_api as fifa_api
        original = fifa_api.fixtures
        fifa_api.fixtures = lambda: fake_fixtures
        self.addCleanup(setattr, fifa_api, "fixtures", original)

    def test_only_finished_fixtures_with_scores_are_included(self):
        self._patch_fifa_fixtures([
            {"round": 5, "status": "complete", "home": "France", "away": "Paraguay",
             "hs": 3, "as": 0},
            {"round": 5, "status": "scheduled", "home": "Spain", "away": "Germany",
             "hs": None, "as": None},
        ])
        out = articles.finished_results_map(5)
        self.assertEqual(out[("france", "paraguay")], {"hs": 3, "as": 0})
        self.assertNotIn(("spain", "germany"), out)

    def test_country_alias_normalisation_matches_espn_vs_fifa_spellings(self):
        """USMNT (FIFA feed) must key-match 'USA' (ESPN/core.fixtures spelling)
        via fifa_api._ckey's country-alias table."""
        self._patch_fifa_fixtures([
            {"round": 5, "status": "STATUS_FULL_TIME", "home": "USMNT", "away": "South Korea",
             "hs": 1, "as": 1},
        ])
        out = articles.finished_results_map(5)
        self.assertIn(("usa", "korea republic"), out)

    def test_missing_score_fields_are_excluded(self):
        self._patch_fifa_fixtures([
            {"round": 5, "status": "complete", "home": "France", "away": "Paraguay",
             "hs": None, "as": None},
        ])
        self.assertEqual(articles.finished_results_map(5), {})


class AdvancementMapTest(unittest.TestCase):
    def test_maps_home_and_away_teams_to_advance_probability(self):
        matches = [
            {"home": "England", "away": "Senegal",
             "p_advance_home": 0.7, "p_advance_away": 0.3},
            {"home": "Spain", "away": "Germany",
             "p_advance_home": 0.4, "p_advance_away": 0.6},
        ]
        out = articles.advancement_map(matches)
        self.assertEqual(out, {"England": 0.7, "Senegal": 0.3,
                               "Spain": 0.4, "Germany": 0.6})

    def test_empty_when_group_round_matches_lack_advance_fields(self):
        matches = [{"home": "England", "away": "Senegal"}]
        self.assertEqual(articles.advancement_map(matches), {})


class FixtureGuideTest(unittest.TestCase):
    """articles.fixture_guide: one entry per team, ranked by clean-sheet prob,
    tagged with a blowout/avoid/balanced goal environment."""

    def _match_entries(self):
        return [
            {"home": "England", "away": "Senegal", "exp_home_goals": 2.5,
             "exp_away_goals": 0.3, "exp_total": 2.8, "p_cs_home": 0.6, "p_cs_away": 0.05},
            {"home": "Spain", "away": "Germany", "exp_home_goals": 1.0,
             "exp_away_goals": 0.9, "exp_total": 1.9, "p_cs_home": 0.35, "p_cs_away": 0.3},
        ]

    def _rows(self):
        return [
            {"name": "Trippier", "team": "England", "position": "DEF", "x_points": 5.2},
            {"name": "Walker", "team": "England", "position": "DEF", "x_points": 4.1},
            {"name": "Pickford", "team": "England", "position": "GK", "x_points": 5.7},
            {"name": "Mendy", "team": "Senegal", "position": "GK", "x_points": 3.0},
        ]

    def test_one_entry_per_team(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        names = {e["name"] for e in out}
        self.assertEqual(names, {"England", "Senegal", "Spain", "Germany"})
        self.assertEqual(len(out), 4)

    def test_team_and_opponent_fields(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        england = next(e for e in out if e["name"] == "England")
        self.assertEqual(england["team"], "vs Senegal")
        self.assertEqual(england["position"], "—")

    def test_sorted_by_clean_sheet_desc_with_rank(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        cs_values = [e["p_clean_sheet"] for e in out]
        self.assertEqual(cs_values, sorted(cs_values, reverse=True))
        self.assertEqual(out[0]["rank"], 1)
        self.assertEqual(out[0]["name"], "England")  # p_cs_home=0.6, the max

    def test_env_blowout_avoid_balanced_classification(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        # England/Senegal fixture: exp_total=2.8 -> balanced (< 3.0 blowout threshold)
        england = next(e for e in out if e["name"] == "England")
        self.assertEqual(england["env"], "balanced")
        # Spain/Germany: exp_total=1.9 <= 2.1 -> avoid
        spain = next(e for e in out if e["name"] == "Spain")
        self.assertEqual(spain["env"], "avoid")

    def test_blowout_env_when_exp_total_at_or_above_threshold(self):
        matches = [{"home": "France", "away": "Panama", "exp_home_goals": 2.8,
                    "exp_away_goals": 0.4, "exp_total": 3.2, "p_cs_home": 0.6, "p_cs_away": 0.05}]
        out = articles.fixture_guide(matches, [])
        self.assertEqual(out[0]["env"], "blowout")

    def test_top_def_and_top_gk_are_best_by_xpoints(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        england = next(e for e in out if e["name"] == "England")
        self.assertEqual(england["top_def"], "Trippier (5.2)")
        self.assertEqual(england["top_gk"], "Pickford (5.7)")

    def test_missing_position_renders_as_dash(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        spain = next(e for e in out if e["name"] == "Spain")
        self.assertEqual(spain["top_def"], "—")
        self.assertEqual(spain["top_gk"], "—")

    def test_exp_goals_for_against_are_from_the_teams_own_perspective(self):
        out = articles.fixture_guide(self._match_entries(), self._rows())
        senegal = next(e for e in out if e["name"] == "Senegal")
        self.assertEqual(senegal["exp_goals_for"], 0.3)
        self.assertEqual(senegal["exp_goals_against"], 2.5)


class TransferPrioritiesTest(unittest.TestCase):
    def _rows(self):
        return [
            _row("StarFWD", "FWD", 9.0, price=10.0),
            _row("MidFWD", "FWD", 6.0, price=8.0),
            _row("BackupFWD", "FWD", 3.0, price=5.0),
        ]

    def test_ranks_by_value_over_replacement_with_no_advance_data(self):
        """Empty adv_map (group round) -> p_advance defaults to 1.0 for everyone,
        so the ranking degrades to pure value-over-replacement."""
        out = articles.transfer_priorities(self._rows(), adv_map={})
        # median xPts among the 3 FWDs is 6.0 -> StarFWD vor=+3.0, BackupFWD vor=-3.0
        self.assertEqual(out[0]["name"], "StarFWD")
        self.assertAlmostEqual(out[0]["vor"], 3.0)
        self.assertEqual(out[0]["p_advance"], 100.0)
        self.assertEqual(out[0]["rank"], 1)

    def test_low_advance_probability_can_drop_a_higher_xpts_player_below_a_safer_one(self):
        """On a CLOSE call (small value-over-replacement gap), a team facing a
        near-certain elimination should rank below a slightly-smaller edge on a
        team that's almost certainly through — the advancement discount decides
        the tie-break exactly where it matters most."""
        rows = [
            _row("RiskyStar", "FWD", 7.0, price=10.0),   # bigger raw edge...
            _row("SaferPick", "FWD", 6.9, price=8.0),     # ...but only marginally
            _row("Filler1", "FWD", 6.0, price=7.0),
            _row("Filler2", "FWD", 5.0, price=6.0),
        ]
        rows[0]["team"], rows[1]["team"] = "CoinflipTeam", "SafeTeam"
        adv_map = {"CoinflipTeam": 0.05, "SafeTeam": 0.95}
        out = articles.transfer_priorities(rows, adv_map)
        # median xPts of [7.0, 6.9, 6.0, 5.0] = (6.0+6.9)/2 = 6.45
        risky = next(r for r in out if r["name"] == "RiskyStar")
        safer = next(r for r in out if r["name"] == "SaferPick")
        self.assertAlmostEqual(risky["vor"], 0.55, places=2)
        self.assertAlmostEqual(safer["vor"], 0.45, places=2)
        self.assertGreater(risky["vor"], safer["vor"])          # bigger raw edge...
        self.assertGreater(safer["priority_score"], risky["priority_score"])  # ...but ranks lower
        self.assertLess(out.index(safer), out.index(risky))     # safer transfer is the higher priority

    def test_respects_top_n(self):
        rows = self._rows() * 5  # 15 rows across positions, still all FWD
        out = articles.transfer_priorities(rows, adv_map={}, top_n=3)
        self.assertEqual(len(out), 3)
