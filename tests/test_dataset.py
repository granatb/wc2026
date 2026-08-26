"""Phase 2B task 1 — the public CC BY dataset emitters (evmax/dataset.py).

Pure functions, hand-built rows: every assertion below is checkable on paper.
The DEFENSIVE requirement is the point of half these tests — the distribution
columns arrive on a parallel branch, so a row WITHOUT them must still emit a
complete, stably-shaped record (CSV column present and empty, JSON key absent).
"""

from __future__ import annotations

import csv
import io
import unittest

from evmax import dataset


def _row(name, x_points, **kw):
    """A gameweek artifact row as games/fpl/model._derive_row emits it."""
    row = {
        "name": name,
        "team": "MUN",
        "position": "MID",
        "x_points": x_points,
        "captain_ev": round(2 * x_points, 2),
        "ceiling": x_points + 6.0,
        "price": 8.0,
        "ownership_pct": 12.5,
        "value": round(x_points / 8.0, 3),
        "bonus": 0.5,
        "defcon": 0.4,
        "p_defcon": 0.2,
        "cs_points": 0.3,
        "kickoff": "2026-08-22T11:30:00+00:00",
        "start_prob": 0.9,
    }
    row.update(kw)
    return row


_GEN = "2026-08-26T09:00:00+00:00"


class TestGameweekPayloadMeta(unittest.TestCase):
    def test_meta_carries_the_cc_by_licence_and_attribution(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN)
        self.assertEqual(p["meta"]["license"], "CC BY 4.0")
        self.assertIn("creativecommons.org/licenses/by/4.0", p["meta"]["license_url"])
        self.assertIn("evmax", p["meta"]["attribution"])
        self.assertIn("https://evmax.ai", p["meta"]["attribution"])

    def test_meta_carries_a_source_url_and_a_method_one_liner(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN)
        self.assertTrue(p["meta"]["source"].startswith("http"))
        self.assertIn("/data/", p["meta"]["source"])
        self.assertIn("Monte-Carlo", p["meta"]["method"])
        self.assertEqual(p["meta"]["generated_at"], _GEN)

    def test_top_level_names_the_gameweek_and_the_player_count(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0), _row("B", 3.0)], _GEN)
        self.assertEqual(p["gameweek"], 2)
        self.assertEqual(p["count"], 2)
        self.assertEqual(len(p["players"]), 2)

    def test_players_sort_by_x_points_descending(self):
        p = dataset.gameweek_payload(2, [_row("Low", 3.0), _row("High", 9.0)],
                                     _GEN)
        self.assertEqual([r["name"] for r in p["players"]], ["High", "Low"])


class TestGameweekPayloadColumns(unittest.TestCase):
    def test_every_projection_column_survives(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN)
        rec = p["players"][0]
        for key in ("gameweek", "name", "team", "position", "price",
                    "ownership_pct", "x_points", "captain_ev", "ceiling",
                    "value", "bonus", "defcon", "p_defcon", "cs_points",
                    "start_prob", "verdict_tier", "verdict_call"):
            self.assertIn(key, rec)
        self.assertEqual(rec["x_points"], 6.0)
        self.assertEqual(rec["captain_ev"], 12.0)

    def test_start_prob_is_rounded_not_shipped_at_raw_float_precision(self):
        """The build threads start_prob straight off the priors, so it arrives
        as 0.9210526315789473. Publishing that claims a precision the model
        does not have."""
        p = dataset.gameweek_payload(
            2, [_row("A", 6.0, start_prob=0.9210526315789473)], _GEN)
        self.assertEqual(p["players"][0]["start_prob"], 0.921)

    def test_a_missing_start_prob_stays_none(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0, start_prob=None)],
                                     _GEN)
        self.assertIsNone(p["players"][0]["start_prob"])

    def test_element_ids_are_threaded_in_when_the_build_supplies_them(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN,
                                     ids={"A": 427})
        self.assertEqual(p["players"][0]["id"], 427)

    def test_an_unknown_id_is_null_not_a_guess(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN, ids={})
        self.assertIsNone(p["players"][0]["id"])

    def test_verdict_tier_is_derived_from_the_rows_themselves(self):
        rows = [_row(f"P{i}", 10.0 - i) for i in range(10)]
        p = dataset.gameweek_payload(2, rows, _GEN)
        tiers = {r["name"]: r["verdict_tier"] for r in p["players"]}
        self.assertEqual(tiers["P0"], "S")          # top 5%
        self.assertIn(tiers["P9"], ("C", "D"))      # bottom of the board
        calls = {r["verdict_call"] for r in p["players"]}
        self.assertTrue(calls <= {"buy", "hold", "pass"})


class TestDistributionFieldsAreDefensive(unittest.TestCase):
    """The parallel branch adds these; this branch must work before AND after."""

    def test_a_row_without_distribution_fields_still_emits(self):
        p = dataset.gameweek_payload(2, [_row("A", 6.0)], _GEN)
        rec = p["players"][0]
        for key in dataset.DISTRIBUTION_FIELDS:
            self.assertNotIn(key, rec)
        self.assertFalse(p["meta"]["has_distributions"])

    def test_distribution_fields_are_carried_when_the_row_has_them(self):
        row = _row("A", 6.0, p10=1.0, median=5.0, mode=2.0, p90=13.0,
                   p_haul=0.21, p_blank=0.34)
        p = dataset.gameweek_payload(2, [row], _GEN)
        rec = p["players"][0]
        self.assertEqual(rec["p10"], 1.0)
        self.assertEqual(rec["p90"], 13.0)
        self.assertEqual(rec["p_haul"], 0.21)
        self.assertTrue(p["meta"]["has_distributions"])

    def test_the_raw_pmf_is_carried_in_json_but_never_in_csv(self):
        row = _row("A", 6.0, distribution={"2": 100, "6": 400})
        p = dataset.gameweek_payload(2, [row], _GEN)
        self.assertEqual(p["players"][0]["distribution"], {"2": 100, "6": 400})
        self.assertNotIn("distribution", dataset.CSV_COLUMNS)


class TestToCsv(unittest.TestCase):
    def test_header_is_stable_and_row_count_matches_players(self):
        rows = [_row("A", 6.0), _row("B", 3.0), _row("C", 1.0)]
        text = dataset.to_csv(dataset.gameweek_payload(2, rows, _GEN))
        parsed = list(csv.reader(io.StringIO(text)))
        self.assertEqual(parsed[0], list(dataset.CSV_COLUMNS))
        self.assertEqual(len(parsed) - 1, 3)

    def test_header_is_identical_with_and_without_distribution_fields(self):
        plain = dataset.to_csv(dataset.gameweek_payload(2, [_row("A", 6.0)],
                                                        _GEN))
        rich = dataset.to_csv(dataset.gameweek_payload(
            2, [_row("A", 6.0, p10=1.0, median=5.0, mode=2.0, p90=13.0,
                     p_haul=0.2, p_blank=0.3)], _GEN))
        self.assertEqual(plain.split("\r\n")[0], rich.split("\r\n")[0])

    def test_a_row_without_distribution_fields_leaves_those_cells_empty(self):
        text = dataset.to_csv(dataset.gameweek_payload(2, [_row("A", 6.0)],
                                                       _GEN))
        rec = list(csv.DictReader(io.StringIO(text)))[0]
        for key in dataset.DISTRIBUTION_FIELDS:
            if key in dataset.CSV_COLUMNS:
                self.assertEqual(rec[key], "")
        self.assertEqual(rec["name"], "A")
        self.assertEqual(rec["x_points"], "6.0")

    def test_a_name_containing_a_comma_is_quoted_rfc4180(self):
        text = dataset.to_csv(dataset.gameweek_payload(
            2, [_row("Smith, Jr.", 6.0)], _GEN))
        self.assertIn('"Smith, Jr."', text)
        rec = list(csv.DictReader(io.StringIO(text)))[0]
        self.assertEqual(rec["name"], "Smith, Jr.")

    def test_a_name_containing_a_quote_is_escaped_rfc4180(self):
        text = dataset.to_csv(dataset.gameweek_payload(
            2, [_row('O"Brien', 6.0)], _GEN))
        rec = list(csv.DictReader(io.StringIO(text)))[0]
        self.assertEqual(rec["name"], 'O"Brien')

    def test_lines_end_crlf_and_there_is_no_index_column(self):
        text = dataset.to_csv(dataset.gameweek_payload(2, [_row("A", 6.0)],
                                                       _GEN))
        self.assertTrue(text.endswith("\r\n"))
        self.assertEqual(dataset.CSV_COLUMNS[0], "gameweek")

    def test_a_none_value_renders_as_an_empty_cell_never_the_word_none(self):
        text = dataset.to_csv(dataset.gameweek_payload(
            2, [_row("A", 6.0, price=None, value=None)], _GEN))
        self.assertNotIn("None", text)
        rec = list(csv.DictReader(io.StringIO(text)))[0]
        self.assertEqual(rec["price"], "")


class TestIndexPayload(unittest.TestCase):
    def test_index_lists_every_gameweek_with_both_file_paths(self):
        idx = dataset.index_payload([1, 2], generated_at=_GEN)
        self.assertEqual([g["gameweek"] for g in idx["gameweeks"]], [1, 2])
        self.assertEqual(idx["gameweeks"][0]["json"],
                         "/api/fpl/dataset/gw1.json")
        self.assertEqual(idx["gameweeks"][0]["csv"],
                         "/api/fpl/dataset/gw1.csv")
        self.assertEqual(idx["all"]["json"], "/api/fpl/dataset/all.json")
        self.assertEqual(idx["all"]["csv"], "/api/fpl/dataset/all.csv")

    def test_index_carries_the_same_licence_meta(self):
        idx = dataset.index_payload([1], generated_at=_GEN)
        self.assertEqual(idx["meta"]["license"], "CC BY 4.0")

    def test_gameweeks_are_sorted_and_deduplicated(self):
        idx = dataset.index_payload([3, 1, 3, 2], generated_at=_GEN)
        self.assertEqual([g["gameweek"] for g in idx["gameweeks"]], [1, 2, 3])


class TestMergeAll(unittest.TestCase):
    def _payloads(self):
        gw1 = dataset.gameweek_payload(1, [_row("A", 4.0), _row("B", 9.0)],
                                       _GEN)
        gw2 = dataset.gameweek_payload(2, [_row("C", 7.0), _row("D", 8.0)],
                                       _GEN)
        return [gw2, gw1]                       # deliberately out of order

    def test_rows_order_by_gameweek_then_x_points_desc(self):
        merged = dataset.merge_all(self._payloads())
        self.assertEqual([(r["gameweek"], r["name"]) for r in merged["players"]],
                         [(1, "B"), (1, "A"), (2, "D"), (2, "C")])

    def test_merged_payload_names_its_gameweeks_and_counts(self):
        merged = dataset.merge_all(self._payloads())
        self.assertEqual(merged["gameweeks"], [1, 2])
        self.assertEqual(merged["count"], 4)
        self.assertEqual(merged["meta"]["license"], "CC BY 4.0")

    def test_merging_nothing_is_an_empty_dataset_not_a_crash(self):
        merged = dataset.merge_all([])
        self.assertEqual(merged["players"], [])
        self.assertEqual(merged["gameweeks"], [])
        self.assertEqual(merged["count"], 0)

    def test_the_merged_payload_csvs_with_the_same_header(self):
        merged = dataset.merge_all(self._payloads())
        text = dataset.to_csv(merged)
        parsed = list(csv.reader(io.StringIO(text)))
        self.assertEqual(parsed[0], list(dataset.CSV_COLUMNS))
        self.assertEqual(len(parsed) - 1, 4)


class TestColumnGlossary(unittest.TestCase):
    """The /data/ page and docs/DATASET.md both render from this one table, so
    a column added to the CSV without a definition is a test failure."""

    def test_every_csv_column_has_a_glossary_entry(self):
        for col in dataset.CSV_COLUMNS:
            self.assertIn(col, dataset.COLUMN_GLOSSARY, col)

    def test_glossary_entries_are_type_plus_meaning(self):
        for col, (typ, meaning) in dataset.COLUMN_GLOSSARY.items():
            self.assertTrue(typ)
            self.assertTrue(meaning.strip())

    def test_the_repo_schema_doc_lists_every_column(self):
        """docs/DATASET.md is the mirror an integrator reads before writing a
        line of code. A column that ships without a row there is a column
        somebody will misread."""
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", "DATASET.md")
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        for col in dataset.CSV_COLUMNS:
            with self.subTest(col=col):
                self.assertIn(f"| `{col}` |", doc)
        self.assertIn(f"| `{dataset.PMF_FIELD}` |", doc)
        self.assertIn(dataset.ATTRIBUTION_LINE, doc)


if __name__ == "__main__":
    unittest.main()
