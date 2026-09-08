"""Regression cases for the September review: evidence and event invariants."""
import json
import random
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core import forecast_archive as archive, engine_events as engine, fixtures, ratings, fpl_bench
from games.fpl import model


class ArchiveTests(unittest.TestCase):
    boot = {"events": [{"id": 4, "deadline_time": "2026-09-11T17:00:00Z"}]}

    def test_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(archive, "ROOT", Path(tmp)):
            record = archive.freeze(4, {"rows": [{"player_id": 1, "x_points": 4}]}, self.boot,
                                    datetime(2026, 9, 10, tzinfo=timezone.utc))
            self.assertEqual(archive.load(4), record)
            path = Path(tmp) / 'gw4' / (record['artifact_id'] + '.json')
            changed = dict(record, rows=[])
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                archive.load(4)

    def test_deadline_is_strict_and_missing_deadline_fails_closed(self):
        for boot, now in [(self.boot, '2026-09-11T17:00:00Z'), ({}, '2026-09-10T00:00:00Z')]:
            with self.assertRaises(ValueError):
                archive.freeze(4, {}, boot, now)

    def test_incomplete_live_results_cannot_be_banked(self):
        for payload in [{}, {'fixtures': [{'finished': False}], 'live': {'elements': [{}]}},
                        {'fixtures': [{'finished': True}], 'live': {}}]:
            with self.assertRaises(ValueError):
                archive.require_final(payload)
        archive.require_final({'fixtures': [{'finished': True}], 'live': {'elements': [{'id': 1}]}})

    def test_late_only_squads_do_not_fall_back(self):
        # Use the actual version schema, with timezone-normalized comparisons.
        frozen = {'versions': [{'taken_at': '2026-09-11T19:00:00+02:00', 'squads': {'source': {'xi': []}}}]}
        self.assertEqual(fpl_bench.latest_squads(frozen, '2026-09-11T17:00:00Z'), {})


class EventTests(unittest.TestCase):
    def player(self, name, pos='MID', **kw):
        return ratings.PlayerPrior(name, 'A', pos, 1, 90, 1, 1, 0, False, **kw)

    def test_scorer_cannot_assist_his_own_goal_and_off_pitch_cannot_score(self):
        squad = [self.player('A'), self.player('B')]
        for seed in range(40):
            goals, assists = engine._allocate_events([10], squad, {'A': (0, 90), 'B': (60, 90)},
                                                     random.Random(seed), {'A': 1, 'B': 1},
                                                     {'A': 1, 'B': 1}, 1)
            self.assertEqual(dict(goals), {'A': 1})
            self.assertEqual(dict(assists), {})

    def test_lineups_have_at_most_one_keeper_and_ten_outfield(self):
        squad = [self.player(str(i), 'GK' if i < 3 else 'MID', cameo_prob=1) for i in range(25)]
        intervals = engine._intervals(squad, {p.name: 1 for p in squad}, random.Random(1))
        for minute in range(90):
            active = [p for p in squad if p.name in intervals and intervals[p.name][0] <= minute < intervals[p.name][1]]
            self.assertLessEqual(sum(p.position == 'GK' for p in active), 1)
            self.assertLessEqual(sum(p.position != 'GK' for p in active), 10)

    def test_midfielder_clean_sheet_and_exact_conceded_threshold(self):
        fx = fixtures.Fixture('review', 'A', 'B', datetime(2026, 9, 10, tzinfo=timezone.utc),
                              'PL', 999, lam_home=0, lam_away=0)
        samples, _ = engine.simulate_round(999, sims=100, fixture_list=[fx],
                                         priors=lambda t: [self.player('Mid')] if t == 'A' else [])
        self.assertGreater(samples['Mid'].clean_sheet, 90)
        self.assertEqual(samples['Mid'].conc_beyond, 0)
        sample = engine.PlayerSample('Def', 'A', 'DEF', sims=4, played=4, conceded=4,
                                     conceded_samples=[0, 0, 1, 3])
        self.assertEqual(model._conceded_series(sample), [0, 0, 1, 3])
        self.assertEqual(sum(x // 2 for x in model._conceded_series(sample)) / 4, .25)

class DecisionTests(unittest.TestCase):
    def test_bench_keeper_upgrade_has_no_xi_value_and_captain_upgrade_counts_twice(self):
        from games.fpl.transfers import weekly_utility
        squad, rows = [], {}
        for pos, values in {'GK': [5, 1], 'DEF': [6, 5, 4, 1, 0],
                            'MID': [6, 5, 4, 1, 0], 'FWD': [10, 9, 1]}.items():
            for i, value in enumerate(values):
                name = pos + str(i)
                squad.append({'name': name, 'position': pos})
                rows[name] = {'x_points': value}
        original = weekly_utility(squad, rows)
        rows['GK1']['x_points'] = 4
        self.assertEqual(weekly_utility(squad, rows), original)
        rows['FWD0']['x_points'] = 11
        self.assertEqual(weekly_utility(squad, rows), original + 2)

    def test_dc_scoreline_is_used_by_sampling(self):
        from core.odds_math import score_matrix_dc
        fx = fixtures.Fixture('dc-review', 'A', 'B', datetime(2026, 9, 10, tzinfo=timezone.utc),
                              'GW', 999, lam_home=1, lam_away=1, rho=-0.3)
        _, matches = engine.simulate_round(999, sims=10000, fixture_list=[fx], priors=lambda t: [])
        self.assertAlmostEqual(matches['dc-review'].prob(0, 0), score_matrix_dc(1, 1, -.3)[0, 0], delta=.01)

    def test_regrading_keeps_original_receipt(self):
        from games.fpl.grading import write_accuracy
        with tempfile.TemporaryDirectory() as tmp:
            write_accuracy(1, {'n': 1, 'mae_ours': 2}, out_dir=tmp)
            write_accuracy(1, {'n': 1, 'mae_ours': 3}, out_dir=tmp)
            previous = list((Path(tmp) / 'revisions').glob('*.json'))
            self.assertEqual(len(previous), 1)
            self.assertEqual(json.loads(previous[0].read_text())['mae_ours'], 2)


class HistoricalBuildTests(unittest.TestCase):
    def test_locked_build_does_not_simulate_or_publish_a_fabricated_full_board(self):
        from evmax import fpl_build, render
        from core import fpl_api
        if fpl_api.read_cache('bootstrap') is None:
            self.skipTest('local FPL archive integration cache unavailable')
        site_url = render.SITE_URL
        try:
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(fpl_build.fpl_model, 'load_gameweek', side_effect=AssertionError('historical data reload')), \
                 patch.object(engine, 'simulate_round', side_effect=AssertionError('historical resimulation')):
                # preview=False: the preview cards are the one thing a locked
                # build IS allowed to simulate (the next open gameweek); this
                # test is about the locked gameweek's own board staying frozen.
                fpl_build.build(1, 200, tmp, use_llm=False, live=False, preview=False)
                dataset = json.loads((Path(tmp) / 'api/fpl/dataset/gw1.json').read_text())
                self.assertEqual(dataset['status'], 'unavailable')
                # No archive banner on the landing (owner decision 2026-09-08).
                self.assertNotIn('Legacy archive', (Path(tmp) / 'index.html').read_text())
        finally:
            render.SITE_URL = site_url

class FreshnessTests(unittest.TestCase):
    def test_freshness_requires_matching_bytes_and_a_recent_past_observation(self):
        payload = {'elements': [1]}
        meta = {'payload_sha256': archive.digest(payload), 'recorded_at': '2026-09-07T10:00:00Z'}
        archive.require_fresh(payload, meta, '2026-09-07T12:00:00Z')
        for data, when in [({}, '2026-09-07T12:00:00Z'), (payload, '2026-09-09T12:00:00Z'),
                           (payload, '2026-09-07T09:00:00Z')]:
            with self.assertRaises(ValueError):
                archive.require_fresh(data, meta, when)
