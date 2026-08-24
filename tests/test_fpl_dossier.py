"""games/fpl/dossier.py — player dossiers + the publish gate (phase 5 task 2).

Offline: synthetic squad entries, priors and bootstrap rows through the real
dossier/gate path. The gate's contract (spec D1): a red dossier passes ONLY
behind a sourced research note dated on/after the feed snapshot — refusal,
not warning.
"""

from __future__ import annotations

import unittest

from core.research import ResearchEntry
from games.fpl import dossier


def _entry(name="Watkins", position="FWD"):
    return {"name": name, "position": position, "is_starter": True,
            "bench_order": None, "is_captain": False, "is_vice": False}


def _player(name="Watkins", team="AVL", position="FWD", status="a",
            pid=1, news=""):
    return {"id": pid, "name": name, "team": team, "position": position,
            "status": status, "news": news, "price": 9.0}


def _note(name="Watkins", sources=("https://example.test/report",),
          updated="2026-08-24", override=None):
    return ResearchEntry(name=name, sources=list(sources), updated=updated,
                         start_prob_override=override)


class TestBuildDossier(unittest.TestCase):
    def test_green_player_is_not_red(self):
        d = dossier.build_dossier(_entry(), {"start_prob": 0.9,
                                             "source": "proxy"},
                                  _player(), None)
        self.assertFalse(d["red"])
        self.assertEqual(d["reasons"], [])
        self.assertEqual(d["status"], "a")
        self.assertEqual(d["start_source"], "proxy")

    def test_non_available_status_is_red(self):
        d = dossier.build_dossier(_entry(), {"start_prob": 0.9,
                                             "source": "proxy"},
                                  _player(status="i", news="Knee injury"),
                                  None)
        self.assertTrue(d["red"])
        self.assertTrue(any("status" in r for r in d["reasons"]))
        self.assertTrue(any("Knee injury" in r for r in d["reasons"]))

    def test_low_proxy_start_is_red_but_note_sourced_start_is_green(self):
        proxy = dossier.build_dossier(_entry(), {"start_prob": 0.6,
                                                 "source": "proxy"},
                                      _player(), None)
        self.assertTrue(proxy["red"])
        noted = dossier.build_dossier(_entry(), {"start_prob": 0.6,
                                                 "source": "proxy"},
                                      _player(), _note(override=0.6))
        self.assertFalse(noted["red"])
        self.assertEqual(noted["start_source"], "note")
        self.assertEqual(noted["start_prob"], 0.6)

    def test_club_change_since_capture_is_red(self):
        d = dossier.build_dossier(_entry("Konsa", "DEF"),
                                  {"start_prob": 0.95, "source": "proxy"},
                                  _player("Konsa", team="ARS",
                                          position="DEF"),
                                  None, captured_team="AVL")
        self.assertTrue(d["red"])
        self.assertTrue(d["club_changed"])
        self.assertTrue(any("AVL" in r and "ARS" in r for r in d["reasons"]))

    def test_outflow_spike_is_red(self):
        d = dossier.build_dossier(_entry(), {"start_prob": 0.9,
                                             "source": "proxy"},
                                  _player(), None, outflow=True)
        self.assertTrue(d["red"])
        self.assertTrue(d["outflow_flag"])

    def test_unresolved_name_is_red(self):
        d = dossier.build_dossier(_entry("Sangaré"), {"start_prob": None,
                                                      "source": "proxy"},
                                  None, None)
        self.assertTrue(d["red"])
        self.assertTrue(any("unresolved" in r for r in d["reasons"]))

    def test_alias_resolution_marks_name_drift_without_going_red(self):
        d = dossier.build_dossier(_entry("Sangaré"),
                                  {"start_prob": 0.9, "source": "proxy"},
                                  _player("I.Sangaré", team="NFO",
                                          position="FWD"), None)
        self.assertTrue(d["name_drift"])
        self.assertFalse(d["red"])
        self.assertEqual(d["web_name"], "I.Sangaré")


class TestGate(unittest.TestCase):
    def _red(self, name="Watkins"):
        return dossier.build_dossier(
            _entry(name), {"start_prob": 0.9, "source": "proxy"},
            _player(name, status="i", news="Hamstring"), None)

    def test_green_squad_passes(self):
        greens = [dossier.build_dossier(_entry(), {"start_prob": 0.9,
                                                   "source": "proxy"},
                                        _player(), None)]
        ok, failures = dossier.gate(greens, {})
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_red_without_note_fails_naming_the_player(self):
        ok, failures = dossier.gate([self._red()], {},
                                    snapshot_date="2026-08-24")
        self.assertFalse(ok)
        self.assertEqual(failures[0]["name"], "Watkins")
        self.assertTrue(any("status" in r for r in failures[0]["reasons"]))

    def test_red_with_sourced_dated_note_passes(self):
        notes = {"Watkins": _note(updated="2026-08-24")}
        ok, failures = dossier.gate([self._red()], notes,
                                    snapshot_date="2026-08-24")
        self.assertTrue(ok, failures)

    def test_note_with_empty_sources_does_not_override(self):
        notes = {"Watkins": _note(sources=(), updated="2026-08-24")}
        ok, _failures = dossier.gate([self._red()], notes,
                                     snapshot_date="2026-08-24")
        self.assertFalse(ok)

    def test_note_older_than_the_snapshot_does_not_override(self):
        notes = {"Watkins": _note(updated="2026-08-19")}
        ok, _failures = dossier.gate([self._red()], notes,
                                     snapshot_date="2026-08-24")
        self.assertFalse(ok)

    def test_without_a_snapshot_a_sourced_note_suffices(self):
        notes = {"Watkins": _note(updated="2026-08-19")}
        ok, _failures = dossier.gate([self._red()], notes, snapshot_date=None)
        self.assertTrue(ok)

    def test_note_found_under_the_current_web_name_too(self):
        red = dossier.build_dossier(
            _entry("Sangaré"), {"start_prob": 0.9, "source": "proxy"},
            _player("I.Sangaré", status="i"), None)
        notes = {"I.Sangaré": _note("I.Sangaré")}
        ok, _failures = dossier.gate([red], notes, snapshot_date=None)
        self.assertTrue(ok)


class TestAssemble(unittest.TestCase):
    _STATE = {
        "team_name": "The Model XI",
        "aliases": {"Sangaré": "I.Sangaré"},
        "squad": [_entry("Watkins", "FWD"), _entry("Sangaré", "FWD")],
    }
    _PLAYERS = [_player("Watkins", pid=1),
                _player("I.Sangaré", team="NFO", pid=2)]

    def test_assembles_one_dossier_per_squad_entry(self):
        ds = dossier.assemble(self._STATE, self._PLAYERS,
                              {"Watkins": 0.87, "I.Sangaré": 0.9}, {})
        self.assertEqual([d["name"] for d in ds], ["Watkins", "Sangaré"])
        self.assertEqual(ds[0]["start_prob"], 0.87)
        self.assertFalse(ds[0]["red"])

    def test_alias_resolves_and_flags_drift(self):
        ds = dossier.assemble(self._STATE, self._PLAYERS,
                              {"Watkins": 0.87, "I.Sangaré": 0.9}, {})
        self.assertTrue(ds[1]["name_drift"])
        self.assertEqual(ds[1]["web_name"], "I.Sangaré")
        self.assertFalse(ds[1]["red"])

    def test_feed_flags_reach_the_dossiers(self):
        ds = dossier.assemble(self._STATE, self._PLAYERS,
                              {"Watkins": 0.87, "I.Sangaré": 0.9}, {},
                              captured_teams={"1": "MUN"},
                              outflow_ids={"2"})
        self.assertTrue(ds[0]["club_changed"])   # Watkins captured at MUN
        self.assertTrue(ds[1]["outflow_flag"])   # the Sangaré id spikes

    def test_note_override_threads_through_by_state_name(self):
        players = [_player("Watkins", pid=1)]
        state = {"team_name": "T", "squad": [_entry("Watkins", "FWD")]}
        ds = dossier.assemble(state, players, {"Watkins": 0.6},
                              {"Watkins": _note(override=0.85)})
        self.assertEqual(ds[0]["start_source"], "note")
        self.assertFalse(ds[0]["red"])

    def test_unresolvable_entry_yields_a_red_dossier_not_a_crash(self):
        state = {"team_name": "T", "squad": [_entry("Ghost", "FWD")]}
        ds = dossier.assemble(state, self._PLAYERS, {}, {})
        self.assertTrue(ds[0]["red"])
        self.assertTrue(any("unresolved" in r for r in ds[0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
