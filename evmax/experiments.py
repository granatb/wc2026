"""Public, derived experiment standings. Registration is never a fake result."""
import html
import json
from pathlib import Path
from games.fpl import experiments as ledger
from evmax import render

PATH = '/fpl/experiments/'
API_PATH = '/api/fpl/experiments.json'
ROOT = Path(__file__).resolve().parents[1]/'experiments/fpl-2026-27'


def report():
    protocol = json.loads((ROOT/'protocol.json').read_text())
    data = ledger.report_from_directory(protocol, ROOT/'records')
    path = ROOT.parents[1]/'docs/research/2026-09-07-minutes-results.json'
    if path.exists():
        candidate = json.loads(path.read_text())
        data['minutes_research'] = dict(status=candidate['status'],
            model=candidate['model']['version'], trained_through=candidate['model']['trained_through'],
            heldout_start=candidate['heldout_start'],
            scores={name:{k:v for k,v in score.items() if k != 'calibration'}
                    for name,score in candidate['cohorts']['all_single_fixture'].items()},
            limitations=candidate['limitations'])
    fixture_reports = {}
    for phase in ('development', 'validation'):
        fixture_path = ROOT.parents[1]/('docs/research/2026-09-07-fixtures-'+phase+'.json')
        if fixture_path.exists():
            candidate = json.loads(fixture_path.read_text())
            fixture_reports[phase] = {k:candidate[k] for k in (
                'model', 'status', 'scores', 'fixture_minus_ablation_equal_gw_mse',
                'exploratory_block95', 'limitations')}
    if fixture_reports:
        data['fixture_research'] = fixture_reports
    shadow_path = ROOT/'fixture-shadow-status.json'
    if shadow_path.exists():
        data['fixture_shadow'] = json.loads(shadow_path.read_text())
    lineup_path = ROOT.parents[1]/'docs/research/2026-09-07-lineup-rehearsal.json'
    if lineup_path.exists():
        study = json.loads(lineup_path.read_text())
        data['lineup_research'] = dict(status=study['status'], gameweek=study['gameweek'],
            generated_at=study['generated_at'], artifact_id=study['artifact_id'],
            policy_version=study['policy_version'], limitations=study['limitations'],
            audit_deltas={arm:{mode:r['audit_delta'] for mode,r in modes.items()}
                          for arm,modes in study['results'].items()})
    joint_path = ROOT.parents[1]/'docs/research/2026-09-07-joint-lineup.json'
    if joint_path.exists():
        study = json.loads(joint_path.read_text())
        data['joint_lineup_research'] = {k:study[k] for k in (
            'status','gameweek','generated_at','source_artifact_id','sims_per_seed',
            'optimization_seed','audit_seed','audit_delta','monte_carlo_precision','limitations')}
    return data


def page(data):
    status = {
        'registered_not_started': 'Registered — awaiting the first complete pre-deadline comparison.',
        'forecasts_frozen_awaiting_results': 'Forecasts frozen — awaiting final results.',
        'prospective_results': 'Prospective results from frozen weekly forecasts.',
    }[data['status']]
    rows = []
    for arm, label in data['registered_arms'].items():
        score = data['arms'].get(arm)
        cells = ([str(score['net_points']), f"{score['rmse_equal_gameweek']:.3f}",
                  f"{score['mae_equal_gameweek']:.3f}", str(score['interventions'])]
                 if score else ['—']*4)
        versions = ', '.join(score['model_versions']) if score else 'Awaiting frozen weekly results'
        rows.append('<tr><td>'+html.escape(label)+'<br><small>'+html.escape(versions)+'</small></td>'+
                    ''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>')
    weeks = ', '.join(map(str, data['gameweeks'])) or 'None yet'
    pending = ', '.join(map(str, data['pending_gameweeks'])) or 'None'
    receipts = ''.join('<li>GW'+str(r['gameweek'])+': <code>'+html.escape(r['forecast_artifact_id'])+
                       '</code> — captured '+html.escape(r['captured_at'])+'</li>'
                       for r in data.get('receipts', []))
    receipt_section = ('<h2>Frozen forecast receipts</h2><ul>'+receipts+'</ul><p>These hashes identify retained forecasts. '
        'Local timestamps alone do not prove when a forecast was published; independent publication must precede the deadline.</p>'
        if receipts else '')
    analysis = data.get('analysis', {})
    cohort_labels = dict(all_players='All forecast players', prior_60plus='Prior 60+ minutes per gameweek',
                         selected_by_any_arm='Selected by at least one approach')
    detail_rows = []
    for cohort, scores in analysis.get('cohorts', {}).items():
        for arm, score in scores.items():
            error = '—' if score['rmse'] is None else f"{score['rmse']:.3f}"
            detail_rows.append('<tr><td>'+html.escape(cohort_labels[cohort])+'</td><td>'+
                html.escape(data['registered_arms'][arm])+'</td><td>'+str(score['gameweeks'])+
                '</td><td>'+str(score['player_gameweeks'])+'</td><td>'+error+'</td></tr>')
    comparison_rows = []
    for pair in analysis.get('comparisons', []):
        if pair['cohort'] != 'all_players':
            continue
        difference = '—' if pair['mean_mse_difference'] is None else f"{pair['mean_mse_difference']:+.3f}"
        interval = pair['interval95']
        uncertainty = (f"[{interval[0]:+.3f}, {interval[1]:+.3f}]" if interval else
            {'insufficient_gameweeks':'Fewer than 12 eligible weeks', 'mixed_model_versions':'Model versions changed',
             'undisclosed_model_revision':'External model revisions undisclosed',
             'nonconsecutive_gameweeks':'Gaps between eligible weeks'}[pair['status']])
        comparison_rows.append('<tr><td>'+html.escape(data['registered_arms'][pair['left']])+' minus '+
            html.escape(data['registered_arms'][pair['right']])+'</td><td>'+difference+'</td><td>'+
            html.escape(uncertainty)+'</td></tr>')
    learning_section = '<h2>What the comparison can tell us</h2><p>We report all players, players who averaged at least '
    learning_section += ('60 minutes per completed gameweek before the deadline, and the union of the four selected squads. '
        'Cohorts use frozen inputs, never the minutes a player eventually played. The 60-minute cohort uses a gameweek '
        'average, not a per-match average; empty cohorts have no score.</p>')
    if detail_rows:
        learning_section += ('<div class="scroll"><table><thead><tr><th>Population</th><th>Approach</th><th>Weeks</th>'
            '<th>Player-gameweeks</th><th>RMSE</th></tr></thead><tbody>'+''.join(detail_rows)+'</tbody></table></div>')
    if comparison_rows:
        learning_section += ('<h2>Paired forecast differences</h2><p>Each difference compares the same players in the same weeks. '
            'Negative mean squared error differences favor the first approach. These are exploratory comparisons, '
            'not a declaration of a winning model.</p><div class="scroll"><table><thead><tr><th>Comparison</th>'
            '<th>Mean MSE difference</th><th>95% exploratory interval</th></tr></thead><tbody>'+
            ''.join(comparison_rows)+'</tbody></table></div>')
    learning_section += '<p>'+html.escape(analysis.get('uncertainty_note', 'Awaiting prospective results.'))+'</p>'
    minutes_section = ''
    if data.get('minutes_research'):
        candidate = data['minutes_research']
        method_labels = {'transition':'Trained transitions', 'last4':'Last four recorded fixtures', 'season':'Season history'}
        minute_rows = ''.join('<tr><td>'+html.escape(method_labels[name])+'</td><td>'+str(s['n'])+'</td><td>'+
            f"{s['multiclass_brier']:.3f}</td><td>{s['minutes_mae']:.2f}</td><td>{s['minutes_rmse']:.2f}</td></tr>"
            for name,s in candidate['scores'].items())
        minutes_section = ('<h2>Minutes research: candidate, not production</h2><p>Trained on 2023/24 and evaluated on '
            '2024/25 player-only single-fixture gameweeks. The transition model predicts no appearance, under 60 minutes, '
            'or 60+ minutes. These are played-minute roles, not start probabilities.</p><div class="scroll"><table>'
            '<thead><tr><th>Method</th><th>Player-gameweeks</th><th>Role Brier score</th><th>Minutes MAE</th><th>Minutes RMSE</th>'
            '</tr></thead><tbody>'+minute_rows+'</tbody></table></div><p>Lower is better. The candidate improves probability '
            'scores and RMSE but worsens MAE against the last-four baseline. Cold starts remain weak; injuries, blanks '
            'and doubles are not validated. It has not replaced our production minutes assumptions.</p>')
    fixture_section = ''
    if data.get('fixture_research'):
        fixture_rows = []
        for phase, candidate in data['fixture_research'].items():
            season = {'development':'2024/25 development', 'validation':'2025/26 validation'}[phase]
            scores = candidate['scores']['all_recorded']
            fixture_rows.append('<tr><td>'+season+'</td><td>'+str(scores['fixture']['n'])+'</td><td>'+
                f"{scores['fixture']['rmse']:.3f}</td><td>{scores['ablation']['rmse']:.3f}</td></tr>")
        fixture_section = ('<h2>Fixture research: small historical improvement</h2><p>A separate candidate adds '
            'home/away and lagged team/opponent goal rates. Each fixture in a double gets its own forecast, '
            'using only history available before the gameweek cutoff. Both models were trained on 2023/24; '
            'the same specification was evaluated on the later season.</p><div class="scroll"><table>'
            '<thead><tr><th>Season</th><th>Player-gameweeks</th><th>Fixture RMSE</th><th>Without fixture features</th>'
            '</tr></thead><tbody>'+''.join(fixture_rows)+'</tbody></table></div><p>The comparison isolates fixture '
            'features within a per-fixture model, not performance against our production gameweek model or odds. '
            'These are retrospective extracts with an estimated deadline cutoff. Historical blank weeks, cold '
            'starts and availability remain unvalidated. The candidate is research only; live forecasts are unchanged.</p>')
    shadow_section = ''
    if data.get('fixture_shadow'):
        shadow = data['fixture_shadow']
        shadow_status = {'shadow_rehearsal_not_frozen':'Rehearsal only — not frozen',
                         'shadow_frozen':'Frozen — awaiting final results'}[shadow['state']]
        shadow_section = ('<h2>Live fixture shadow</h2><p>'+html.escape(shadow_status)+'. GW'+str(shadow['gameweek'])+
            ', observed '+html.escape(shadow['generated_at'])+'. Receipt-backed histories cover '+str(shadow['players'])+
            ' players; '+str(shadow['comparison_players'])+' qualify for the fixture-model comparison. '
            'Cold-start fallbacks: '+str(shadow['cold_starts'])+'. Blanks: '+str(shadow['blanks'])+'.</p>'
            '<p>This separate shadow compares fixture forecasts with the production statistical model on the same '
            'official inputs. It does not change the four squads. Cold starts copy production and are excluded '
            'from the fixture comparison. Forecast differences are not measured accuracy gains.</p>'
            '<p>Snapshot: <code>'+html.escape(shadow['artifact_id'])+'</code>. '
            'Raw histories and forecasts are retained privately. A local hash alone does not prove pre-deadline '
            'publication. This status describes the dated snapshot, not a continuously refreshed feed.</p>')
    lineup_section = ''
    if data.get('lineup_research'):
        study = data['lineup_research']
        lineup_rows = ''.join('<tr><td>'+html.escape(arm)+'</td><td>'+html.escape(mode.replace('_',' '))+
            f'</td><td>{delta:+.3f}</td></tr>' for arm,modes in study['audit_deltas'].items()
            for mode,delta in modes.items())
        lineup_section = ('<h2>Lineup decision rehearsal</h2><p>A scenario optimizer evaluates all 3,300 legal '
            'XI and outfield bench-order combinations, plus captain/vice pairs. It accounts for formation-constrained '
            'automatic substitutions and vice-captain fallback. This GW'+str(study['gameweek'])+
            ' rehearsal uses assumed appearances and a separate random-seed audit.</p><div class="scroll"><table>'
            '<thead><tr><th>Forecast</th><th>Appearance assumption</th><th>Audit points difference</th></tr></thead>'
            '<tbody>'+lineup_rows+'</tbody></table></div><p>These are simulated expectations, not observed gains. '
            'Decision changes require prospective validation. Shared-club dependence is a stress test, not an '
            'estimated correlation. The controlled four-arm policy remains unchanged.</p>')
    joint_section = ''
    if data.get('joint_lineup_research'):
        study = data['joint_lineup_research']
        low, high = study['monte_carlo_precision']['normal_interval95']
        joint_section = ('<h2>Joint engine sample check</h2><p>We now retain aligned appearance and points '
            'from the market engine itself. The retained samples reproduce its forecast means. The lineup '
            'optimizer uses '+str(study['sims_per_seed'])+' draws and is audited on a separate seed with the same '
            'number of draws.</p><p>Candidate minus baseline: '+f"{study['audit_delta']:+.3f}"+
            ' simulated points. The approximate Monte Carlo interval is '+f'[{low:+.3f}, {high:+.3f}]'+
            '. This measures sampling precision inside this simulator, not uncertainty about real-world gains.</p>'
            '<p>These samples belong to the market model; they are not distributions for the statistical or '
            'external forecasts. Engine assumptions still require calibration. The four-arm policy is unchanged.</p>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The season experiment | evmax</title>{render._HEAD_COMMON}{render._FONTS}
<style>{render._STYLE}
main{{max-width:1050px;margin:40px auto;padding:0 24px}}h1{{font-size:36px}}p{{margin:18px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:14px;text-align:left;border-bottom:1px solid var(--line)}}
small{{color:var(--ink3)}}code{{overflow-wrap:anywhere}}.scroll{{overflow-x:auto}}.status{{padding:18px;background:#eaf5ee;border-radius:10px}}
</style></head><body><header><div class="wrap"><a class="logo" href="/">ev<b>max</b></a></div></header>
<main><h1>Four approaches. One season of evidence.</h1>
<p class="status">{html.escape(status)}</p>
<p>These are virtual experimental squads, separate from our two existing published teams.
Every approach starts with the same 15 players and £100m budget. We freeze all four
forecasts together, then track their decisions and outcomes.</p>
<div class="scroll"><table><thead><tr><th>Approach / versions</th><th>Points after hits</th>
<th>Forecast RMSE</th><th>Forecast MAE</th><th>Human interventions</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p>Graded gameweeks: {weeks}. Frozen weeks awaiting grades: {pending}.</p>
{receipt_section}
<p>Lower forecast error is better; more squad points is better. Forecast losses are averaged
with equal weight per gameweek on identical player populations. A lucky captain can win a
week without proving that the underlying forecast is better. We do not automatically select a winner.</p>
{learning_section}
{minutes_section}
{fixture_section}
{shadow_section}
{lineup_section}
{joint_section}
<h2>The controlled decision policy</h2><p>Version 1 considers at most one positive-net transfer
per week, then selects a legal XI, captain and vice using expected points. Bank balances,
purchase and selling prices, free transfers and hits carry forward. Chips are disabled for
every approach. This is a controlled comparison, not a complete season optimizer.</p>
<p>Model versions and any human intervention are recorded before the deadline. Existing
history is never backfilled into this experiment. Missing providers, partial results,
changed rules or missing weeks stop the pipeline rather than silently changing the comparison.</p>
<h2>What the four forecasts use</h2>
<p>The market arm combines match odds with official player statistics, with editorial
overrides disabled. The statistical arm uses lagged points, minutes, xG and xA with
coefficients fitted on 2023/24. Neither internal model uses FC27 ratings.</p>
<p>The hybrid is a prespecified 50/50 average, not an optimized blend. The reference
averages official FPL projections with <a href="https://fantasyfootballiq.app">Fantasy Football IQ</a>;
players absent from FFIQ retain the official projection, with coverage recorded in the evidence.
External providers' training and underlying data lineage are undisclosed. No approach has
yet demonstrated a prospective advantage in this experiment.</p>
<p><a href="{API_PATH}">Download the experiment summary</a> ·
<a href="/fpl/compare/">Published comparisons</a> · <a href="/track-record/">Existing track record</a></p>
</main></body></html>'''


def publish(writer):
    data = report()
    writer(PATH+'index.html', page(data))
    writer(API_PATH, json.dumps(data, ensure_ascii=False, indent=2))
