"""Phase 5: ingesting the owner's hand-written lineup notes."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import research
from scripts import fpl_notes


class TestShorthandParsing(unittest.TestCase):
    def test_bare_status_words(self):
        out = fpl_notes.parse("Jacquet nailed\nGomez out\nBradley rotation\n")
        self.assertEqual(out["Jacquet"]["status"], "nailed")
        self.assertEqual(out["Gomez"]["status"], "out")
        self.assertEqual(out["Bradley"]["status"], "rotation_risk")

    def test_explicit_start_probability(self):
        out = fpl_notes.parse("Jacquet 0.9")
        self.assertAlmostEqual(out["Jacquet"]["start_prob_override"], 0.9)

    def test_status_and_probability_together(self):
        out = fpl_notes.parse("Jacquet nailed 0.95")
        self.assertEqual(out["Jacquet"]["status"], "nailed")
        self.assertAlmostEqual(out["Jacquet"]["start_prob_override"], 0.95)

    def test_trailing_comment_becomes_a_source(self):
        out = fpl_notes.parse("Jacquet nailed # Slot presser 20 Aug")
        self.assertEqual(out["Jacquet"]["sources"], ["Slot presser 20 Aug"])

    def test_multi_word_names(self):
        out = fpl_notes.parse("Van Hecke nailed")
        self.assertEqual(out["Van Hecke"]["status"], "nailed")

    def test_blank_lines_and_full_line_comments_ignored(self):
        self.assertEqual(fpl_notes.parse("\n\n# just a heading\n"), {})

    def test_unknown_status_word_raises(self):
        """Silently dropping an unrecognised word would lose a real instruction."""
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet definitelystarting")

    def test_out_of_range_probability_raises(self):
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet 1.4")

    def test_duplicate_name_raises(self):
        """Two lines for one player is a contradiction, not a merge."""
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet nailed\nJacquet out")

    def test_status_aliases_map_onto_the_overlay_vocabulary(self):
        """`rotation` is what an owner types; `rotation_risk` is what
        core/research.py and core/blend.py understand."""
        out = fpl_notes.parse("A rotation\nB rotation_risk\nC doubtful\nD suspended")
        self.assertEqual(out["A"]["status"], "rotation_risk")
        self.assertEqual(out["B"]["status"], "rotation_risk")
        self.assertEqual(out["C"]["status"], "doubtful")
        self.assertEqual(out["D"]["status"], "suspended")

    def test_status_word_is_case_insensitive(self):
        self.assertEqual(fpl_notes.parse("Jacquet OUT")["Jacquet"]["status"], "out")

    def test_probability_only_line_leaves_status_unset(self):
        out = fpl_notes.parse("Jacquet 0.9")
        self.assertIsNone(out["Jacquet"]["status"])

    def test_line_with_neither_status_nor_probability_raises(self):
        """A bare name says nothing the model can use — it is a typo, not a note."""
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet")

    def test_error_names_the_offending_line(self):
        with self.assertRaises(ValueError) as ctx:
            fpl_notes.parse("Jacquet nailed\nGomez wibble")
        self.assertIn("wibble", str(ctx.exception))

    def test_zero_probability_is_accepted(self):
        """0.0 is a legitimate pin (definitely benched), not an out-of-range value."""
        self.assertAlmostEqual(
            fpl_notes.parse("Jacquet 0")["Jacquet"]["start_prob_override"], 0.0)

    def test_negative_probability_raises(self):
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet -0.2")


class TestNameMatching(unittest.TestCase):
    FEED = ["Virgil", "B.Fernandes", "Jacquet", "Gomez", "Gabriel"]

    def test_exact_match(self):
        self.assertEqual(fpl_notes.match_name("Jacquet", self.FEED), "Jacquet")

    def test_case_insensitive(self):
        self.assertEqual(fpl_notes.match_name("jacquet", self.FEED), "Jacquet")

    def test_unmatched_returns_none_with_suggestions(self):
        m, suggestions = fpl_notes.match_name_verbose("Van Dijk", self.FEED)
        self.assertIsNone(m)
        self.assertTrue(suggestions)

    def test_ambiguous_prefix_is_not_guessed(self):
        """Two plausible targets must not be resolved by coin flip."""
        m, _ = fpl_notes.match_name_verbose("G", ["Gomez", "Gabriel"])
        self.assertIsNone(m)

    def test_unique_prefix_is_accepted(self):
        m, _ = fpl_notes.match_name_verbose("Jacq", self.FEED)
        self.assertEqual(m, "Jacquet")

    def test_ambiguous_prefix_suggests_the_candidates(self):
        _, suggestions = fpl_notes.match_name_verbose("G", ["Gomez", "Gabriel"])
        self.assertEqual(sorted(suggestions), ["Gabriel", "Gomez"])

    def test_unique_substring_is_accepted(self):
        self.assertEqual(fpl_notes.match_name("ernandes", self.FEED), "B.Fernandes")

    def test_punctuation_and_diacritics_are_ignored(self):
        """The feed writes `B.Fernandes`; nobody types the dot."""
        self.assertEqual(fpl_notes.match_name("B Fernandes", self.FEED), "B.Fernandes")
        self.assertEqual(fpl_notes.match_name("Munoz", ["Muñoz", "Virgil"]), "Muñoz")

    def test_exact_match_beats_a_longer_prefix_sibling(self):
        """`Gomez` must resolve even though `Gomez Jr` also starts with it."""
        self.assertEqual(fpl_notes.match_name("Gomez", ["Gomez", "Gomez Jr"]), "Gomez")

    def test_suggestions_are_a_shortlist_not_the_squad(self):
        feed = [f"Player{i}" for i in range(200)]
        _, suggestions = fpl_notes.match_name_verbose("Nobody", feed)
        self.assertLessEqual(len(suggestions), 8)

    def test_match_name_returns_none_when_ambiguous(self):
        self.assertIsNone(fpl_notes.match_name("G", ["Gomez", "Gabriel"]))


class TestNoteWriting(unittest.TestCase):
    def test_round_trips_through_core_research(self):
        """The test that proves the two halves fit: write a note, load it back via
        the real research loader, and confirm the entry says what was intended."""
        entries = fpl_notes.parse("Jacquet nailed 0.9  # Slot presser 20 Aug")
        with tempfile.TemporaryDirectory() as tmp:
            written = fpl_notes.write_notes(entries, gameweek=3,
                                            feed_names=["Jacquet", "Virgil"],
                                            research_dir=tmp)
            self.assertEqual(len(written), 1)
            with mock.patch.object(research, "RESEARCH_DIR", tmp):
                loaded = research.load_entries("players", 3)
                other_gw = research.load_entries("players", 4)

        self.assertIn("Jacquet", loaded)
        entry = loaded["Jacquet"]
        self.assertEqual(entry.entity, "player")
        self.assertEqual(entry.status, "nailed")
        self.assertAlmostEqual(entry.start_prob_override, 0.9)
        self.assertEqual(entry.round, 3)
        self.assertEqual(entry.sources, ["Slot presser 20 Aug"])
        self.assertEqual(entry.lambda_multiplier, 1.0)
        self.assertTrue(entry.updated)
        # Pinned per gameweek: a GW3 note must not leak into GW4.
        self.assertNotIn("Jacquet", other_gw)

    def test_round_trip_of_a_status_only_note(self):
        """`start_prob_override: null` has to survive the frontmatter round trip as
        None, not as the string "null" — a float check downstream would blow up."""
        with tempfile.TemporaryDirectory() as tmp:
            fpl_notes.write_notes(fpl_notes.parse("Gomez out"), gameweek=1,
                                  feed_names=["Gomez"], research_dir=tmp)
            with mock.patch.object(research, "RESEARCH_DIR", tmp):
                entry = research.load_entries("players", 1)["Gomez"]
        self.assertEqual(entry.status, "out")
        self.assertIsNone(entry.start_prob_override)
        # And it actually zeroes the player, weight or no weight.
        self.assertEqual(entry.adjust(0.5, 0.9, w=0.30), (0.0, 0.0))

    def test_note_is_keyed_on_the_feed_name_not_the_typed_name(self):
        """The owner types a prefix; the file must carry the name the sim keys on."""
        with tempfile.TemporaryDirectory() as tmp:
            fpl_notes.write_notes(fpl_notes.parse("Jacq nailed"), gameweek=1,
                                  feed_names=["Jacquet"], research_dir=tmp)
            with mock.patch.object(research, "RESEARCH_DIR", tmp):
                loaded = research.load_entries("players", 1)
        self.assertIn("Jacquet", loaded)
        self.assertNotIn("Jacq", loaded)

    def test_refuses_to_write_an_unmatched_name(self):
        """The Raphinha near-miss in reverse: a note nobody can look up is worse
        than no note, because it reads as done."""
        entries = fpl_notes.parse("Van Dijk out")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(fpl_notes.UnmatchedName) as ctx:
                fpl_notes.write_notes(entries, gameweek=1,
                                      feed_names=["Virgil", "Jacquet"],
                                      research_dir=tmp)
            players_dir = os.path.join(tmp, "players")
            self.assertEqual(
                [] if not os.path.isdir(players_dir) else os.listdir(players_dir),
                [], "nothing may be written when any name is unmatched")
        self.assertIn("Van Dijk", str(ctx.exception))

    def test_one_bad_name_blocks_the_whole_batch(self):
        """All-or-nothing: a half-applied batch is the state nobody can reason about."""
        entries = fpl_notes.parse("Jacquet nailed\nVan Dijk out")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(fpl_notes.UnmatchedName):
                fpl_notes.write_notes(entries, gameweek=1,
                                      feed_names=["Virgil", "Jacquet"],
                                      research_dir=tmp)
            players_dir = os.path.join(tmp, "players")
            self.assertFalse(os.path.isdir(players_dir) and os.listdir(players_dir))

    def test_unmatched_error_carries_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(fpl_notes.UnmatchedName) as ctx:
                fpl_notes.write_notes(fpl_notes.parse("Van Dijk out"), gameweek=1,
                                      feed_names=["Virgil", "Jacquet"],
                                      research_dir=tmp)
        self.assertTrue(ctx.exception.unmatched)
        self.assertEqual(ctx.exception.unmatched[0][0], "Van Dijk")

    def test_rewriting_the_same_player_replaces_the_note(self):
        """One file per player, overwritten — never a second file that
        core.research.find_duplicate_names would have to referee."""
        with tempfile.TemporaryDirectory() as tmp:
            fpl_notes.write_notes(fpl_notes.parse("Jacquet out"), gameweek=1,
                                  feed_names=["Jacquet"], research_dir=tmp)
            fpl_notes.write_notes(fpl_notes.parse("Jacquet nailed 0.9"), gameweek=1,
                                  feed_names=["Jacquet"], research_dir=tmp)
            self.assertEqual(len(os.listdir(os.path.join(tmp, "players"))), 1)
            with mock.patch.object(research, "RESEARCH_DIR", tmp):
                entry = research.load_entries("players", 1)["Jacquet"]
        self.assertEqual(entry.status, "nailed")

    def test_written_filenames_are_namespaced_to_fpl(self):
        """research/players/ is shared with the World Cup notes; an FPL note for
        `Kane` must not clobber the hand-written kane.md sitting next to it."""
        with tempfile.TemporaryDirectory() as tmp:
            fpl_notes.write_notes(fpl_notes.parse("Kane out"), gameweek=1,
                                  feed_names=["Kane"], research_dir=tmp)
            names = os.listdir(os.path.join(tmp, "players"))
        self.assertEqual(names, ["fpl-kane.md"])


class TestFeedNames(unittest.TestCase):
    def test_feed_names_are_disambiguated_like_the_sim(self):
        """core.fpl_priors renames colliding web_names before the engine ever sees
        them; a note written against the raw web_name would key nothing."""
        players = [
            {"id": 1, "name": "Palmer", "full_name": "Cole Palmer", "team": "CHE"},
            {"id": 2, "name": "Palmer", "full_name": "Alex Palmer", "team": "IPS"},
            {"id": 3, "name": "Jacquet", "full_name": "Amara Jacquet", "team": "LIV"},
        ]
        names = fpl_notes.feed_names(players)
        self.assertIn("Cole Palmer", names)
        self.assertIn("Alex Palmer", names)
        self.assertIn("Jacquet", names)
        self.assertNotIn("Palmer", names)


class TestRendering(unittest.TestCase):
    def test_frontmatter_has_no_stray_colon_breakage(self):
        """A source with a colon in it (every URL) must not corrupt the block."""
        entries = fpl_notes.parse("Jacquet nailed # https://example.com/a:b")
        with tempfile.TemporaryDirectory() as tmp:
            fpl_notes.write_notes(entries, gameweek=1, feed_names=["Jacquet"],
                                  research_dir=tmp)
            with mock.patch.object(research, "RESEARCH_DIR", tmp):
                entry = research.load_entries("players", 1)["Jacquet"]
        self.assertEqual(entry.sources, ["https://example.com/a:b"])

    def test_body_says_where_the_note_came_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = fpl_notes.write_notes(fpl_notes.parse("Jacquet nailed"),
                                          gameweek=1, feed_names=["Jacquet"],
                                          research_dir=tmp)
            with open(paths[0][1], encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("fpl_notes", text)


if __name__ == "__main__":
    unittest.main()


class TestStandingNotes(unittest.TestCase):
    """`standing` writes `from_round`, for facts that do not expire.

    Watkins, 2026-08-27: his GW2 note correctly zeroed a player whose move to
    Al-Hilal was agreed, but `round: 2` meant it stopped applying on Sunday, so
    the five-gameweek horizon projected him at 4-5 points a week from GW3 as a
    normal Villa striker. That understated the sale by about 19 points and sent
    the transfer optimizer after the wrong replacement. A tool that can only
    write round-scoped notes reproduces that bug every time a player leaves.
    """

    def test_standing_is_parsed_off_the_line(self):
        out = fpl_notes.parse("Watkins out standing")
        self.assertTrue(out["Watkins"]["standing"])
        self.assertEqual(out["Watkins"]["status"], "out")

    def test_an_ordinary_note_is_not_standing(self):
        self.assertFalse(fpl_notes.parse("Gibbs-White rotation")["Gibbs-White"]["standing"])

    def test_the_synonyms_all_work(self):
        for word in ("standing", "permanent", "forever", "from"):
            with self.subTest(word=word):
                out = fpl_notes.parse(f"Watkins out {word}")
                self.assertTrue(out["Watkins"]["standing"])

    def test_standing_composes_with_a_probability(self):
        out = fpl_notes.parse("Watkins out standing 0.05")
        self.assertTrue(out["Watkins"]["standing"])
        self.assertAlmostEqual(out["Watkins"]["start_prob_override"], 0.05)

    def test_standing_alone_is_not_a_note(self):
        # It says how long a fact lasts without ever stating the fact.
        with self.assertRaises(ValueError):
            fpl_notes.parse("Watkins standing")

    def test_render_emits_from_round_only_when_standing(self):
        entry = {"status": "out", "start_prob_override": 0.05,
                 "sources": ["goal.com"], "standing": True}
        text = fpl_notes.render_note("Watkins", entry, 2, updated="2026-08-27")
        self.assertIn("round: 2", text)
        self.assertIn("from_round: 2", text)

        entry["standing"] = False
        text = fpl_notes.render_note("Watkins", entry, 2, updated="2026-08-27")
        self.assertIn("round: 2", text)
        self.assertNotIn("from_round:", text)

    def test_a_standing_note_round_trips_through_core_research(self):
        """The written file must actually mean what the shorthand said."""
        from core import research
        entry = {"status": "out", "start_prob_override": 0.05,
                 "sources": ["goal.com 2026-08-27"], "standing": True}
        text = fpl_notes.render_note("Watkins", entry, 2, updated="2026-08-27")
        meta, _body = research.parse_frontmatter(text)
        parsed = research.ResearchEntry.from_meta(meta)
        self.assertEqual(parsed.from_round, 2)
        self.assertFalse(parsed.applies_to(1))   # GW1 is not rewritten
        self.assertTrue(parsed.applies_to(6))    # and GW6 still knows he is gone

    def test_check_output_shows_the_standing_scope(self):
        entry = {"status": "out", "start_prob_override": None,
                 "sources": [], "standing": True}
        self.assertIn("STANDING", fpl_notes._describe(entry))

    def test_check_output_stays_quiet_for_an_ordinary_note(self):
        entry = {"status": "out", "start_prob_override": None,
                 "sources": [], "standing": False}
        self.assertNotIn("STANDING", fpl_notes._describe(entry))
