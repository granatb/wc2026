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
