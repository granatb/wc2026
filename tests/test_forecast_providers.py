import copy
import hashlib
import unittest
from pathlib import Path

from core import forecast_archive as evidence
from games.fpl import forecast_providers as providers
from scripts import evaluate_challenger as ridge
from test_fpl_experiments import bootstrap, fixtures, NOW


def context():
    boot = bootstrap()
    boot['events'] = [dict(id=g, finished=g < 4, is_next=g == 4,
                          deadline_time=f'2026-09-{g:02d}T12:30:00Z') for g in range(1, 5)]
    boot['events'][-1]['deadline_time'] = '2026-09-12T12:30:00Z'
    for p in boot['elements']:
        p.update(minutes=270, total_points=6, ep_next='3', status='a')
    fx = fixtures()[:1]
    fx[0].update(team_h=1, team_a=2, started=False)
    history = [dict(gameweek=g, fetched_at=NOW, fixtures=[dict(event=g, finished=True)],
                    live=dict(elements=[dict(id=p['id'], stats=dict(minutes=90, total_points=2,
                        expected_goals='0.1', expected_assists='0.05')) for p in boot['elements']]))
               for g in range(1,4)]
    return dict(gameweek=4, captured_at=NOW, bootstrap=boot, all_fixtures=fx, fixtures=fx,
        receipts={key:dict(recorded_at=NOW, payload_sha256=evidence.digest(value))
                  for key,value in [('bootstrap',boot),('all_fixtures',fx)]},
        history=history, odds=dict(gameweek=4,captured_at=NOW), backfill={},
        ffiq=dict(generated_at=NOW, players=[dict(fpl_id=1,club='T1',web_name='P1',gws=[dict(gw=4,proj=5)])]))


def trained():
    return providers.seal(dict(model_version='test', trained_through='2024-05-01T00:00:00Z',
        features=ridge.FEATURES, weights=[1]+[0]*8, cold_start_points={p:1 for p in ['GK','DEF','MID','FWD']},
        feature_source_sha256=hashlib.sha256(Path(ridge.__file__).read_bytes()).hexdigest()))


def fake_market(boot, fx, odds, backfill, sims):
    return {p['id']:2 for p in boot['elements']}, dict(sims=sims)


class ProviderTests(unittest.TestCase):
    def test_model_identity_separates_input_changes_from_parameter_changes(self):
        first, _ = providers.build_boards(context(), trained(), now=NOW, market_fn=fake_market)
        c = context()
        c['bootstrap']['elements'][0]['ep_next'] = '9'
        c['receipts']['bootstrap']['payload_sha256'] = evidence.digest(c['bootstrap'])
        second, _ = providers.build_boards(c, trained(), now=NOW, market_fn=fake_market)
        for arm in first:
            self.assertEqual(first[arm]['model_identity_sha256'], second[arm]['model_identity_sha256'])
        fitted = trained(); fitted.pop('artifact_id'); fitted['weights'][0] = 2
        third, _ = providers.build_boards(c, providers.seal(fitted), now=NOW, market_fn=fake_market)
        self.assertNotEqual(first['statistical']['model_identity_sha256'], third['statistical']['model_identity_sha256'])
        self.assertEqual(first['market']['model_identity_sha256'], third['market']['model_identity_sha256'])

    def test_full_population_and_fixed_blend_with_explicit_fallback(self):
        boards, source = providers.build_boards(context(), trained(), now=NOW, market_fn=fake_market)
        self.assertEqual({len(b['predictions']) for b in boards.values()}, {20})
        cols = {arm:{r['player_id']:r['x_points'] for r in b['predictions']} for arm,b in boards.items()}
        self.assertEqual(cols['hybrid'][1], 1.5)
        self.assertEqual(cols['consensus'][1], 4)
        self.assertEqual(cols['consensus'][2], 3)
        self.assertEqual(cols['statistical'][3], 0)  # team blank
        self.assertEqual(source['consensus']['ffiq_matched'], 1)
        self.assertIsNone(boards['consensus']['trained_through'])
        providers.verify(source)
        providers.verify_board_source('market', boards['market'], source)
        changed = copy.deepcopy(boards['market'])
        changed['predictions'][0]['x_points'] += 1
        with self.assertRaises(ValueError):
            providers.verify_board_source('market', changed, source)

    def test_no_future_or_partial_history(self):
        for mutation in ('missing_week', 'partial_player', 'future', 'unfinished', 'wrong_week'):
            c = context()
            if mutation == 'missing_week': c['history'].pop()
            if mutation == 'partial_player': c['history'][0]['live']['elements'].pop()
            if mutation == 'future': c['history'][0]['fetched_at'] = '2027-01-01T00:00:00Z'
            if mutation == 'unfinished': c['history'][0]['fixtures'][0]['finished'] = False
            if mutation == 'wrong_week': c['history'][0]['fixtures'][0]['event'] = 4
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                providers.build_boards(c, trained(), now=NOW, market_fn=fake_market)

    def test_stale_or_mismatched_provider_context(self):
        for mutation in ('odds', 'ffiq', 'boot', 'fixture', 'training', 'checksum'):
            c, t = context(), trained()
            if mutation == 'odds': c['odds']['captured_at'] = '2026-09-01T00:00:00Z'
            if mutation == 'ffiq': c['ffiq']['generated_at'] = '2026-09-01T00:00:00Z'
            if mutation == 'boot': c['bootstrap']['elements'][0]['now_cost'] += 1
            if mutation == 'fixture': c['fixtures'] = []
            if mutation == 'training':
                t.pop('artifact_id'); t['trained_through'] = NOW; t = providers.seal(t)
            if mutation == 'checksum': t['weights'][0] = 1000
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                providers.build_boards(c, t, now=NOW, market_fn=fake_market)

    def test_external_identity_duplicate_and_ep_next_guards(self):
        for mutation in ('club', 'duplicate', 'next', 'nonfinite', 'no_coverage'):
            c = context()
            if mutation == 'club': c['ffiq']['players'][0]['club'] = 'wrong'
            if mutation == 'duplicate': c['ffiq']['players'] *= 2
            if mutation == 'next': c['bootstrap']['events'][-1]['is_next'] = False
            if mutation == 'nonfinite': c['ffiq']['players'][0]['gws'][0]['proj'] = 'NaN'
            if mutation == 'no_coverage': c['ffiq']['players'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                providers.consensus_predictions(c['bootstrap'], c['fixtures'], c['ffiq'], 4, NOW)

    def test_feature_transform_matches_historical_research(self):
        x = ridge.feature_vector([dict(total_points=2,minutes=90,expected_goals=.1,expected_assists=.2)]*3, 'DEF')
        self.assertEqual(x[:3], [1,2,1])
        self.assertEqual(x[5:], [2,0,1,0])

    def test_stats_ignore_market_and_fc_ratings_and_gate_unavailability(self):
        c = context(); h = providers.live_histories(c['bootstrap'], 4, c['history'], NOW)
        before, _ = providers.statistical_predictions(c['bootstrap'], c['fixtures'], h, trained())
        c['bootstrap']['elements'][0].update(fc27=99, ep_next=9999, selected_by_percent='100')
        after, _ = providers.statistical_predictions(c['bootstrap'], c['fixtures'], h, trained())
        self.assertEqual(before, after)
        c['bootstrap']['elements'][0]['status'] = 'i'
        after, _ = providers.statistical_predictions(c['bootstrap'], c['fixtures'], h, trained())
        self.assertEqual(after[1], 0)

    def test_unknown_external_training_is_explicit_not_allowed_for_internal_models(self):
        from games.fpl import experiments
        from test_fpl_experiments import submissions, PROTOCOL
        boot = bootstrap(); subs = submissions(boot)
        subs['consensus'].update(trained_through=None, training_disclosed=False)
        record = experiments.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())
        self.assertIsNone(record['arms']['consensus']['trained_through'])
        subs['statistical'].update(trained_through=None, training_disclosed=False)
        with self.assertRaisesRegex(ValueError, 'internal models'):
            experiments.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())
