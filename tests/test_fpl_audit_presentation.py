import copy
import tempfile
import unittest
from pathlib import Path
from core import forecast_archive
from evmax import writer, fpl_players, fpl_articles, dataset

class AuditPresentationTests(unittest.TestCase):
    def test_start_prior_is_not_presented_as_simulated_start_frequency(self):
        from test_fpl_players import _payloads
        payload = _payloads()[0][0]
        before = copy.deepcopy(payload)
        page = fpl_players.player_page_html(payload, 7)
        self.assertIn('Start prior (before lineup constraints)', page)
        self.assertIn('resulting simulated start frequency can be lower', page)
        self.assertIn('lineup constraints', dataset.COLUMN_GLOSSARY['start_prob'][1])
        self.assertEqual(payload, before)

    def test_comparator_copy_uses_recorded_method_and_shared_model(self):
        record = forecast_archive.load(6)
        state = record['states']['consensus']
        entries, meta = fpl_articles.squad_article(state, record['rows'])
        self.assertEqual(meta['method_note'], state['method_note'])
        with tempfile.TemporaryDirectory() as tmp:
            # A previous draft must not reintroduce the retired methodology.
            folder = Path(tmp)/'fpl-gw7'; folder.mkdir()
            (folder/'consensus-squad.md').write_text('Stale expert mention-tally draft')
            prose = writer.article_prose('consensus-squad', 7, entries, [], tmp,
                                         use_llm=False, cache_name='fpl-gw7', unit='Gameweek')
        self.assertIn('most-owned legal template', prose['body_html'])
        self.assertIn('Both squads use the same forecast model', prose['body_html'])
        self.assertNotIn('measures exactly', prose['body_html'])
        self.assertNotIn('majority armband', prose['standfirst'])
