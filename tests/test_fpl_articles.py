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

    def test_same_fixture_candidates_share_a_kickoff_order(self):
        """Two candidates in the same match are the same kickoff instant — an
        enumeration (1, 2) would let the captains prose claim one of them
        'kicks off later' when neither does."""
        ko = "2026-08-21T19:00:00+00:00"
        rows = [_row("CapA", "FWD", 7.0, kickoff=ko),
                _row("CapB", "MID", 6.0, kickoff=ko),
                _row("Later", "FWD", 5.0,
                     kickoff="2026-08-23T15:00:00+00:00")]
        out = fpl_articles.captains(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["CapA"]["kickoff_order"],
                         by_name["CapB"]["kickoff_order"])
        self.assertEqual(by_name["CapA"]["kickoff_order"], 1)
        # dense rank: the next DISTINCT instant is 2, not 3
        self.assertEqual(by_name["Later"]["kickoff_order"], 2)

    def test_kickoff_order_ranks_only_the_published_slice(self):
        """kickoff_order 1 is the earliest kickoff AMONG THE PUBLISHED
        candidates: an earlier fixture outside the top slice must not shift
        every published rank up by one."""
        rows = [_row("Top", "FWD", 9.0, kickoff="2026-08-22T14:00:00+00:00"),
                _row("Second", "MID", 8.0,
                     kickoff="2026-08-23T15:00:00+00:00"),
                _row("Cut", "FWD", 1.0, kickoff="2026-08-21T19:00:00+00:00")]
        out = fpl_articles.captains(rows, top=2)
        self.assertEqual([e["name"] for e in out], ["Top", "Second"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Top"]["kickoff_order"], 1)
        self.assertEqual(by_name["Second"]["kickoff_order"], 2)


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


def _pool(n_per_pos=8, teams=("ARS", "LIV", "MCI", "CHE", "NEW", "AVL", "BHA")):
    """A pool big enough to build a legal 15 in any formation, priced 4.0-9.0."""
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

    def test_blank_gameweek_club_is_listed_with_zeroes(self):
        """A blank is the single most actionable thing a ticker can tell a manager
        — omitting the club entirely hides it."""
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV", "EVE"])
        eve = {e["name"]: e for e in out}["EVE"]
        self.assertEqual(eve["fixtures"], 0)
        self.assertEqual(eve["opponents"], "—")
        self.assertEqual(eve["exp_clean_sheets"], 0.0)
        self.assertEqual(eve["env"], "blank")

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

    def test_environment_labels(self):
        matches = [_match("ARS", "LIV", gf=2.2, ga=1.4),     # 3.6 total -> blowout
                   _match("BUR", "EVE", gf=1.0, ga=0.9)]     # 1.9 total -> avoid
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR", "EVE"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["env"], "blowout")
        self.assertEqual(by_name["BUR"]["env"], "avoid")


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


def _state_entry(name, pos, starter=True, bench_order=None, cap=False,
                 vice=False, team="ARS", price=5.0):
    return {"name": name, "position": pos, "is_starter": starter,
            "bench_order": bench_order, "is_captain": cap, "is_vice": vice,
            "team": team, "price": price}


def _squad_state(strategy="model", team_name="The Model XI"):
    """A validated-shape state: XI in state order (1 GK, 3 DEF, 5 MID, 2 FWD),
    bench GK/DEF/FWD/DEF. Names double as their artifact-row names."""
    return {
        "team_name": team_name,
        "strategy": strategy,
        "free_transfers": 1,
        "chips_used": [],
        "total_cost": 87.0,
        "squad": [
            _state_entry("Keeper", "GK"),
            _state_entry("Def1", "DEF"),
            _state_entry("Def2", "DEF"),
            _state_entry("Def3", "DEF"),
            _state_entry("Mid1", "MID", cap=True),
            _state_entry("Mid2", "MID", vice=True),
            _state_entry("Mid3", "MID"),
            _state_entry("Mid4", "MID"),
            _state_entry("Mid5", "MID"),
            _state_entry("Fwd1", "FWD"),
            _state_entry("Fwd2", "FWD"),
            _state_entry("Gk2", "GK", starter=False, bench_order=1),
            _state_entry("Def4", "DEF", starter=False, bench_order=2),
            _state_entry("Fwd3", "FWD", starter=False, bench_order=3),
            _state_entry("Def5", "DEF", starter=False, bench_order=4),
        ],
    }


def _squad_rows():
    """Artifact rows for every state name (plus a non-squad extra), with
    x_points chosen so the XI total and captain double are easy to hand-check."""
    spec = [("Keeper", "GK", 4.0), ("Def1", "DEF", 5.0), ("Def2", "DEF", 4.5),
            ("Def3", "DEF", 4.0), ("Mid1", "MID", 8.0), ("Mid2", "MID", 7.0),
            ("Mid3", "MID", 6.0), ("Mid4", "MID", 5.5), ("Mid5", "MID", 5.0),
            ("Fwd1", "FWD", 6.5), ("Fwd2", "FWD", 5.5), ("Gk2", "GK", 3.0),
            ("Def4", "DEF", 2.5), ("Fwd3", "FWD", 3.5), ("Def5", "DEF", 2.0),
            ("Extra", "MID", 9.9)]
    return [_row(n, p, xp) for n, p, xp in spec]


class TestSquadArticle(unittest.TestCase):
    # XI x_points sum: 4+5+4.5+4+8+7+6+5.5+5+6.5+5.5 = 61.0; captain Mid1 8.0
    # doubled -> projected_total 69.0.

    def test_entries_keep_state_order_with_roles_and_ranks(self):
        entries, _meta = fpl_articles.squad_article(_squad_state(), _squad_rows())
        self.assertEqual(len(entries), 15)
        self.assertEqual([e["name"] for e in entries[:11]],
                         ["Keeper", "Def1", "Def2", "Def3", "Mid1", "Mid2",
                          "Mid3", "Mid4", "Mid5", "Fwd1", "Fwd2"])
        self.assertEqual([e["name"] for e in entries[11:]],
                         ["Gk2", "Def4", "Fwd3", "Def5"])
        self.assertEqual([e["rank"] for e in entries], list(range(1, 16)))
        self.assertEqual([e["role"] for e in entries],
                         ["XI"] * 11 + ["Bench"] * 4)

    def test_bench_follows_bench_order_not_state_file_order(self):
        state = _squad_state()
        # scramble the bench entries' file order; bench_order must win
        state["squad"][11:] = [state["squad"][14], state["squad"][12],
                               state["squad"][11], state["squad"][13]]
        entries, _meta = fpl_articles.squad_article(state, _squad_rows())
        self.assertEqual([e["name"] for e in entries[11:]],
                         ["Gk2", "Def4", "Fwd3", "Def5"])

    def test_entries_carry_the_row_columns_and_the_captain_flags(self):
        entries, _meta = fpl_articles.squad_article(_squad_state(), _squad_rows())
        cap = next(e for e in entries if e["is_captain"])
        self.assertEqual(cap["name"], "Mid1")
        self.assertEqual(cap["x_points"], 8.0)
        self.assertEqual(cap["captain_ev"], 16.0)
        for key in ("x_points", "ceiling", "captain_ev", "value"):
            self.assertIn(key, entries[0])
        vice = next(e for e in entries if e["is_vice"])
        self.assertEqual(vice["name"], "Mid2")

    def test_meta_totals_formation_and_captain_double(self):
        _entries, meta = fpl_articles.squad_article(_squad_state(), _squad_rows())
        self.assertEqual(meta["xi_xpoints"], 61.0)
        self.assertEqual(meta["projected_total"], 69.0)   # + captain's 8.0 again
        self.assertEqual(meta["formation"], "3-5-2")
        self.assertEqual(meta["captain"], "Mid1")
        self.assertEqual(meta["vice"], "Mid2")
        self.assertEqual(meta["team_name"], "The Model XI")
        self.assertEqual(meta["strategy"], "model")
        self.assertEqual(meta["total_cost"], 87.0)

    def test_works_identically_for_a_consensus_state(self):
        state = _squad_state(strategy="consensus", team_name="The Consensus XI")
        _entries, meta = fpl_articles.squad_article(state, _squad_rows())
        self.assertEqual(meta["strategy"], "consensus")
        self.assertEqual(meta["team_name"], "The Consensus XI")
        self.assertEqual(meta["projected_total"], 69.0)

    def test_non_squad_rows_are_not_dragged_in(self):
        entries, _meta = fpl_articles.squad_article(_squad_state(), _squad_rows())
        self.assertNotIn("Extra", [e["name"] for e in entries])

    def test_state_name_missing_from_rows_raises(self):
        rows = [r for r in _squad_rows() if r["name"] != "Mid3"]
        with self.assertRaises(ValueError) as ctx:
            fpl_articles.squad_article(_squad_state(), rows)
        self.assertIn("Mid3", str(ctx.exception))
