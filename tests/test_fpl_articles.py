"""Phase 4: FPL-specific article ranking and squad building."""
from __future__ import annotations

import unittest

from evmax import fpl_articles


def _row(name, pos, xp, price=5.0, team="ARS", **kw):
    row = {
        "name": name, "position": pos, "team": team,
        "x_points": xp, "captain_ev": round(2 * xp, 2), "ceiling": xp * 1.8,
        "price": price, "value": round(xp / price, 3) if price else None,
        "ownership_pct": 10.0, "bonus": 0.4, "defcon": 0.0, "p_defcon": 0.0,
        "cs_points": 0.0, "kickoff": "2026-08-21T19:00:00+00:00",
    }
    row.update(kw)
    return row


class TestCaptains(unittest.TestCase):
    def test_ranked_by_captain_ev_with_ranks(self):
        rows = [_row("Low", "MID", 4.0), _row("High", "FWD", 7.0)]
        out = fpl_articles.captains(rows)
        self.assertEqual([e["name"] for e in out], ["High", "Low"])
        self.assertEqual([e["rank"] for e in out], [1, 2])

    def test_kickoff_order_is_annotated(self):
        """A manager picks a captain against the deadline but a VICE against the
        chain of kickoffs — kickoff_order 1 is the earliest of the candidates."""
        rows = [_row("Late", "FWD", 7.0, kickoff="2026-08-23T15:00:00+00:00"),
                _row("Early", "MID", 6.0, kickoff="2026-08-21T19:00:00+00:00")]
        out = fpl_articles.captains(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Early"]["kickoff_order"], 1)
        self.assertEqual(by_name["Late"]["kickoff_order"], 2)

    def test_missing_kickoff_sorts_last_without_crashing(self):
        rows = [_row("NoKo", "FWD", 7.0, kickoff=None),
                _row("Known", "MID", 6.0)]
        out = fpl_articles.captains(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Known"]["kickoff_order"], 1)
        self.assertEqual(by_name["NoKo"]["kickoff_order"], 2)

    def test_does_not_mutate_the_input_rows(self):
        """The same row list feeds all six articles; a mutation here would leak
        kickoff_order into every other article's entries."""
        rows = [_row("A", "FWD", 7.0)]
        fpl_articles.captains(rows)
        self.assertNotIn("kickoff_order", rows[0])
        self.assertNotIn("rank", rows[0])


class TestDefenders(unittest.TestCase):
    def test_includes_goalkeepers_and_excludes_outfield_attackers(self):
        rows = [_row("Keeper", "GK", 5.0), _row("Back", "DEF", 6.0),
                _row("Mid", "MID", 8.0), _row("Fwd", "FWD", 9.0)]
        out = fpl_articles.defenders(rows)
        self.assertEqual(sorted(e["name"] for e in out), ["Back", "Keeper"])

    def test_ranked_by_x_points(self):
        rows = [_row("Keeper", "GK", 5.0), _row("Back", "DEF", 6.0)]
        self.assertEqual([e["name"] for e in fpl_articles.defenders(rows)],
                         ["Back", "Keeper"])


class TestEfficiency(unittest.TestCase):
    def test_ranked_by_value_and_tiered(self):
        rows = [_row("Cheap", "DEF", 4.0, price=4.5),
                _row("Prem", "FWD", 9.0, price=14.0)]
        out = fpl_articles.efficiency(rows)
        self.assertEqual(out[0]["name"], "Cheap")     # 0.889 vs 0.643 per million
        self.assertEqual(out[0]["tier"], "Budget")
        self.assertEqual(out[1]["tier"], "Premium")

    def test_priceless_rows_are_dropped(self):
        rows = [_row("NoPrice", "MID", 8.0, price=None), _row("Ok", "MID", 4.0)]
        self.assertEqual([e["name"] for e in fpl_articles.efficiency(rows)], ["Ok"])


class TestDefconLeaders(unittest.TestCase):
    def test_ranked_by_probability_not_points(self):
        rows = [_row("Solid", "DEF", 4.0, p_defcon=0.71, defcon=1.42),
                _row("Flaky", "DEF", 6.0, p_defcon=0.20, defcon=0.40)]
        out = fpl_articles.defcon_leaders(rows)
        self.assertEqual([e["name"] for e in out], ["Solid", "Flaky"])

    def test_goalkeepers_are_excluded(self):
        """GK is not DefCon-eligible (games/fpl/model.DEFCON_THRESHOLD has no GK),
        so a keeper in this list would be a published impossibility."""
        rows = [_row("Keeper", "GK", 5.0, p_defcon=0.9),
                _row("Back", "DEF", 4.0, p_defcon=0.5)]
        self.assertEqual([e["name"] for e in fpl_articles.defcon_leaders(rows)],
                         ["Back"])

    def test_zero_probability_players_are_dropped(self):
        """A player with no DefCon history projects 0.0 and would pad the list with
        names that can never earn the points."""
        rows = [_row("Back", "DEF", 4.0, p_defcon=0.5),
                _row("Nothing", "MID", 6.0, p_defcon=0.0)]
        self.assertEqual([e["name"] for e in fpl_articles.defcon_leaders(rows)],
                         ["Back"])

    def test_threshold_is_carried_for_the_prose(self):
        rows = [_row("Back", "DEF", 4.0, p_defcon=0.5),
                _row("Engine", "MID", 6.0, p_defcon=0.4)]
        out = fpl_articles.defcon_leaders(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Back"]["defcon_threshold"], 10)
        self.assertEqual(by_name["Engine"]["defcon_threshold"], 12)


def _pool(n_per_pos=8, teams=("ARS", "LIV", "MCI", "CHE", "NEW", "AVL", "BHA")):
    """A pool big enough to build a legal 15 in any formation, priced 4.0-9.5."""
    rows, i = [], 0
    for pos in ("GK", "DEF", "MID", "FWD"):
        for k in range(n_per_pos):
            i += 1
            rows.append(_row(f"{pos}{k}", pos, 8.0 - k * 0.4,
                             price=4.0 + k * 0.5, team=teams[i % len(teams)]))
    return rows


class TestFplSquad(unittest.TestCase):
    def test_squad_is_fifteen_with_the_right_quota(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        self.assertEqual(len(entries), 15)
        counts = {}
        for e in entries:
            counts[e["position"]] = counts.get(e["position"], 0) + 1
        self.assertEqual(counts, {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3})

    def test_within_budget(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        self.assertLessEqual(meta["total_cost"], 100.0)
        self.assertAlmostEqual(meta["left_over"], 100.0 - meta["total_cost"], places=2)

    def test_no_more_than_three_per_club(self):
        entries, _meta = fpl_articles.fpl_squad(_pool())
        counts = {}
        for e in entries:
            counts[e["team"]] = counts.get(e["team"], 0) + 1
        self.assertTrue(all(c <= 3 for c in counts.values()),
                        f"club cap violated: {counts}")

    def test_club_cap_holds_when_one_club_dominates_the_pool(self):
        """The adversarial case: the eleven best players all play for one club, so
        a cap-blind greedy build would pick them and ship an illegal squad."""
        rows = _pool()
        for r in rows[:11]:
            r["team"] = "ARS"
            r["x_points"] = 12.0
            r["value"] = round(12.0 / r["price"], 3)
        entries, _meta = fpl_articles.fpl_squad(rows)
        arsenal = sum(1 for e in entries if e["team"] == "ARS")
        self.assertLessEqual(arsenal, 3)

    def test_no_duplicate_players(self):
        """A swap loop that re-selects a player already in the squad would silently
        field him twice."""
        entries, _meta = fpl_articles.fpl_squad(_pool())
        names = [e["name"] for e in entries]
        self.assertEqual(len(names), len(set(names)))

    def test_xi_formation_is_legal(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        xi = [e for e in entries if e["role"] == "XI"]
        self.assertEqual(len(xi), 11)
        counts = {pos: sum(1 for e in xi if e["position"] == pos)
                  for pos in ("GK", "DEF", "MID", "FWD")}
        self.assertEqual(counts["GK"], 1)
        self.assertTrue(3 <= counts["DEF"] <= 5)
        self.assertTrue(2 <= counts["MID"] <= 5)
        self.assertTrue(1 <= counts["FWD"] <= 3)
        self.assertEqual(meta["formation"],
                         f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}")

    def test_roles_and_ranks(self):
        entries, _meta = fpl_articles.fpl_squad(_pool())
        xi = [e for e in entries if e["role"] == "XI"]
        bench = [e for e in entries if e["role"] == "Bench"]
        self.assertEqual(len(bench), 4)
        self.assertEqual([e["rank"] for e in xi], list(range(1, 12)))
        self.assertEqual([e["rank"] for e in bench], [12, 13, 14, 15])

    def test_meta_xi_xpoints_matches_the_xi(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        xi = [e for e in entries if e["role"] == "XI"]
        self.assertAlmostEqual(meta["xi_xpoints"],
                               round(sum(e["x_points"] for e in xi), 2), places=2)

    def test_impossible_budget_raises(self):
        rows = _pool()
        for r in rows:
            r["price"] = 15.0
        with self.assertRaises(ValueError):
            fpl_articles.fpl_squad(rows)

    def test_priceless_rows_are_excluded(self):
        rows = _pool()
        rows[0]["price"] = None
        entries, _meta = fpl_articles.fpl_squad(rows)
        self.assertNotIn(rows[0]["name"], [e["name"] for e in entries])

    def test_too_few_players_at_a_position_raises(self):
        rows = [r for r in _pool() if r["position"] != "FWD"]
        with self.assertRaises(ValueError):
            fpl_articles.fpl_squad(rows)

    def test_does_not_mutate_the_input_rows(self):
        rows = _pool()
        fpl_articles.fpl_squad(rows)
        for r in rows:
            self.assertNotIn("role", r)
            self.assertNotIn("rank", r)

    def test_cap_is_configurable(self):
        # _pool()'s default 7 clubs cannot host a 15-man squad at 2 per club
        # (7 x 2 = 14), so this case needs an eighth club to be satisfiable at
        # all. The cap being arithmetically impossible is a fixture problem, not
        # something the builder could solve.
        pool = _pool(teams=("ARS", "LIV", "MCI", "CHE", "NEW", "AVL", "BHA", "TOT"))
        entries, _meta = fpl_articles.fpl_squad(pool, max_per_club=2)
        counts = {}
        for e in entries:
            counts[e["team"]] = counts.get(e["team"], 0) + 1
        self.assertTrue(all(c <= 2 for c in counts.values()), counts)


# 20 clubs, so a 15-man squad never runs out of clubs and the BUDGET is the only
# binding constraint. The cap-binding case is _tier_locked_pool below.
_CORRELATED_CLUBS = tuple("T%02d" % n for n in range(20))


def _correlated_pool():
    """A pool where price rises WITH xPts, modelled on the real feed: premiums at
    ~14.8m/8.2xP down to enablers at 4.0m/1.0xP.

    The _pool() fixture above is anti-correlated -- its cheapest player is also its
    best -- so the naive best-XI build lands miles under budget and NEITHER repair
    loop ever fires. Here the naive build overshoots 100.0m badly, which is the
    real-world case and the only way to exercise the repair half of the builder.
    """
    rows, i = [], 0
    for pos in ("GK", "DEF", "MID", "FWD"):
        for k in range(10):
            i += 1
            rows.append(_row(f"{pos}{k}", pos, 1.0 + k * 0.8,
                             price=4.0 + k * 1.2,
                             team=_CORRELATED_CLUBS[i % len(_CORRELATED_CLUBS)]))
    return rows


def _tier_locked_pool():
    """Correlated prices AND a club per price tier, so the three cheapest tiers can
    supply only 3 players each and the CLUB CAP -- not the budget -- sets the floor
    on what a legal squad can cost."""
    clubs = tuple("C%d" % n for n in range(10))
    rows, i = [], 0
    for pos in ("GK", "DEF", "MID", "FWD"):
        for k in range(10):
            i += 1
            rows.append(_row(f"{pos}{k}", pos, 2.0 + k * 0.9,
                             price=4.0 + k * 1.1, team=clubs[i % len(clubs)]))
    return rows


class TestFplSquadRepairLoops(unittest.TestCase):
    """Cover the budget repair half of fpl_squad.

    Every assertion in TestFplSquad above runs on a pool where the build lands at
    72.0m of a 100.0m budget, so the downgrade and upgrade loops are never entered
    at all. These tests drive both.
    """

    def assert_squad_is_legal(self, entries, meta, cap=3, budget=100.0):
        """Quota, budget, formation and cap -- the four invariants a swap must
        preserve. A repair loop that fixes the budget by breaking the quota, the
        formation or the cap would still be a bug."""
        self.assertEqual(len(entries), 15)
        quota = {}
        for e in entries:
            quota[e["position"]] = quota.get(e["position"], 0) + 1
        self.assertEqual(quota, {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3})
        self.assertLessEqual(meta["total_cost"], budget)
        clubs = {}
        for e in entries:
            clubs[e["team"]] = clubs.get(e["team"], 0) + 1
        self.assertTrue(all(c <= cap for c in clubs.values()),
                        f"club cap violated: {clubs}")
        xi = [e for e in entries if e["role"] == "XI"]
        self.assertEqual(len(xi), 11)
        counts = {pos: sum(1 for e in xi if e["position"] == pos)
                  for pos in ("GK", "DEF", "MID", "FWD")}
        self.assertEqual(counts["GK"], 1)
        self.assertTrue(3 <= counts["DEF"] <= 5, counts)
        self.assertTrue(2 <= counts["MID"] <= 5, counts)
        self.assertTrue(1 <= counts["FWD"] <= 3, counts)

    def test_downgrade_loop_brings_an_overspent_squad_under_budget(self):
        rows = _correlated_pool()
        # With the budget lifted, the greedy build takes the best (and so the most
        # expensive) XI and overshoots by a wide margin -- this is what the
        # downgrade loop has to repair, and it is why the loop exists.
        _unrepaired, naive = fpl_articles.fpl_squad(rows, budget=1e9)
        self.assertGreater(naive["total_cost"], 150.0)

        entries, meta = fpl_articles.fpl_squad(rows)
        self.assertLessEqual(meta["total_cost"], 100.0)
        self.assert_squad_is_legal(entries, meta)

    def test_downgrade_loop_respects_the_club_cap_while_repairing(self):
        """The cap assertion in the test above cannot fail -- that pool has 20 clubs
        for 15 places. Here the cap is what sets the floor, so the downgrade loop
        must refuse cheaper players whose club is already full."""
        rows = _tier_locked_pool()
        entries, meta = fpl_articles.fpl_squad(rows)
        self.assert_squad_is_legal(entries, meta)

        # 93.0m is the cheapest legal squad here: only 3 players may come from each
        # price tier, so the floor is 3 x (4.0 + 5.1 + 6.2 + 7.3 + 8.4). A
        # cap-blind builder would reach 88.8m by overloading the cheap tiers.
        _e, tight = fpl_articles.fpl_squad(rows, budget=93.0)
        self.assertEqual(tight["total_cost"], 93.0)
        with self.assertRaises(ValueError):
            fpl_articles.fpl_squad(rows, budget=92.9)

    def test_upgrade_loop_spends_leftover_budget(self):
        rows = _correlated_pool()
        entries, meta = fpl_articles.fpl_squad(rows)

        # Prices sit on a 1.2m grid, so any upgrade costs at least 1.2m more than
        # the player it replaces. Leftover below one grid step therefore means the
        # loop stopped because nothing affordable was left, not because it quit early.
        self.assertGreaterEqual(meta["left_over"], 0.0)
        self.assertLess(meta["left_over"], 1.2,
                        f"upgrade loop left {meta['left_over']}m unspent")

        # The load-bearing comparison: a budget too tight to permit any upgrade
        # yields a strictly worse XI. Without this, "left_over is small" would also
        # be satisfied by a builder that merely spent money without gaining points.
        _tight_entries, tight = fpl_articles.fpl_squad(rows, budget=89.0)
        self.assertGreater(meta["xi_xpoints"], tight["xi_xpoints"])

        # Characterisation of the current greedy heuristic, NOT a mathematical
        # optimum -- 88.8m is the cheapest legal squad in this pool, and a future
        # tuning change may legitimately move these. Treat a diff here as expected.
        self.assertEqual(tight["total_cost"], 88.8)

    def test_repair_loops_never_introduce_a_duplicate(self):
        """Both loops re-select from the whole pool, so a missing membership check
        is the one way this builder could field the same player twice. The
        duplicate test above runs on a pool where neither loop fires."""
        for budget in (100.0, 95.0, 92.0, 89.0):
            with self.subTest(budget=budget):
                entries, meta = fpl_articles.fpl_squad(_correlated_pool(),
                                                       budget=budget)
                names = [e["name"] for e in entries]
                self.assertEqual(len(names), len(set(names)), f"duplicate: {names}")
                keys = [(e["name"], e["team"], e["position"], e["price"])
                        for e in entries]
                self.assertEqual(len(keys), len(set(keys)))
                self.assert_squad_is_legal(entries, meta, budget=budget)


def _match(home, away, p_cs_home=0.4, p_cs_away=0.2, gf=1.6, ga=1.1,
           market=True, kickoff="2026-08-21T19:00:00+00:00"):
    return {"match_id": f"{home}-{away}", "home": home, "away": away,
            "kickoff": kickoff, "exp_home_goals": gf, "exp_away_goals": ga,
            "exp_total": round(gf + ga, 2), "top_scoreline": "2-1",
            "p_home": 0.5, "p_draw": 0.25, "p_away": 0.25,
            "p_cs_home": p_cs_home, "p_cs_away": p_cs_away, "market": market}


class TestTicker(unittest.TestCase):
    def test_one_row_per_club_with_opponent_and_both_sides(self):
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV"])
        self.assertEqual(sorted(e["name"] for e in out), ["ARS", "LIV"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["opponents"], "LIV (H)")
        self.assertEqual(by_name["LIV"]["opponents"], "ARS (A)")
        self.assertAlmostEqual(by_name["ARS"]["exp_goals_for"], 1.6)
        self.assertAlmostEqual(by_name["ARS"]["exp_goals_against"], 1.1)
        self.assertAlmostEqual(by_name["LIV"]["exp_goals_for"], 1.1)
        self.assertAlmostEqual(by_name["LIV"]["exp_goals_against"], 1.6)

    def test_clean_sheet_probability_follows_the_right_side(self):
        out = fpl_articles.ticker([_match("ARS", "LIV", p_cs_home=0.55,
                                          p_cs_away=0.15)], ["ARS", "LIV"])
        by_name = {e["name"]: e for e in out}
        self.assertAlmostEqual(by_name["ARS"]["exp_clean_sheets"], 0.55)
        self.assertAlmostEqual(by_name["LIV"]["exp_clean_sheets"], 0.15)

    def test_double_gameweek_sums_goals_and_clean_sheets(self):
        matches = [_match("ARS", "LIV", p_cs_home=0.4, gf=1.6, ga=1.1),
                   _match("BUR", "ARS", p_cs_away=0.5, gf=0.9, ga=1.8,
                          kickoff="2026-08-24T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        ars = {e["name"]: e for e in out}["ARS"]
        self.assertEqual(ars["fixtures"], 2)
        self.assertEqual(ars["opponents"], "LIV (H), BUR (A)")
        self.assertAlmostEqual(ars["exp_clean_sheets"], 0.9)      # 0.4 + 0.5
        self.assertAlmostEqual(ars["exp_goals_for"], 3.4)         # 1.6 + 1.8
        self.assertAlmostEqual(ars["exp_goals_against"], 2.0)     # 1.1 + 0.9

    def test_double_gameweek_opponents_are_kickoff_ordered(self):
        """Listed in the order they are played, not the order the feed happens to
        return them."""
        matches = [_match("BUR", "ARS", kickoff="2026-08-24T19:00:00+00:00"),
                   _match("ARS", "LIV", kickoff="2026-08-21T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        self.assertEqual({e["name"]: e for e in out}["ARS"]["opponents"],
                         "LIV (H), BUR (A)")

    def test_blank_gameweek_club_is_listed_with_zeroes(self):
        """A blank is the single most actionable thing a ticker can tell a manager
        — omitting the club entirely hides it."""
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV", "EVE"])
        eve = {e["name"]: e for e in out}["EVE"]
        self.assertEqual(eve["fixtures"], 0)
        self.assertEqual(eve["opponents"], "—")
        self.assertEqual(eve["exp_clean_sheets"], 0.0)
        self.assertEqual(eve["env"], "blank")

    def test_club_in_a_fixture_but_not_in_the_club_list_is_still_included(self):
        """Dropping a real fixture because the club list is stale would silently
        lose data; better to include it."""
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS"])
        self.assertIn("LIV", [e["name"] for e in out])

    def test_sorted_by_expected_clean_sheets_with_ranks(self):
        matches = [_match("ARS", "LIV", p_cs_home=0.6, p_cs_away=0.1)]
        out = fpl_articles.ticker(matches, ["ARS", "LIV"])
        self.assertEqual([e["name"] for e in out], ["ARS", "LIV"])
        self.assertEqual([e["rank"] for e in out], [1, 2])

    def test_provenance_is_per_club(self):
        matches = [_match("ARS", "LIV", market=True),
                   _match("BUR", "EVE", market=False)]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR", "EVE"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["basis"], "market")
        self.assertEqual(by_name["BUR"]["basis"], "model")
        self.assertEqual(by_name["EVE"]["basis"], "model")

    def test_mixed_provenance_double_reports_the_weaker_basis(self):
        """One priced fixture and one unpriced is not "market" — claiming it would
        overstate the confidence of the combined number."""
        matches = [_match("ARS", "LIV", market=True),
                   _match("BUR", "ARS", market=False,
                          kickoff="2026-08-24T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        self.assertEqual({e["name"]: e for e in out}["ARS"]["basis"], "mixed")

    def test_a_blank_club_has_no_provenance_claim(self):
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV", "EVE"])
        self.assertEqual({e["name"]: e for e in out}["EVE"]["basis"], "—")

    def test_environment_labels(self):
        matches = [_match("ARS", "LIV", gf=2.2, ga=1.4),     # 3.6 total -> blowout
                   _match("BUR", "EVE", gf=1.0, ga=0.9)]     # 1.9 total -> avoid
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR", "EVE"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["env"], "blowout")
        self.assertEqual(by_name["BUR"]["env"], "avoid")

    def test_a_double_is_labelled_a_double_regardless_of_goals(self):
        matches = [_match("ARS", "LIV"),
                   _match("BUR", "ARS", kickoff="2026-08-24T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        self.assertEqual({e["name"]: e for e in out}["ARS"]["env"], "double")

    def test_empty_gameweek_gives_every_club_a_blank_row(self):
        out = fpl_articles.ticker([], ["ARS", "LIV"])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(e["env"] == "blank" for e in out))
