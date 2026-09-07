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
    return ledger.report_from_directory(protocol, ROOT/'records')


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
        versions = ', '.join(score['model_versions']) if score else 'Awaiting forecast provider'
        rows.append('<tr><td>'+html.escape(label)+'<br><small>'+html.escape(versions)+'</small></td>'+
                    ''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>')
    weeks = ', '.join(map(str, data['gameweeks'])) or 'None yet'
    pending = ', '.join(map(str, data['pending_gameweeks'])) or 'None'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The season experiment | evmax</title>{render._HEAD_COMMON}{render._FONTS}
<style>{render._STYLE}
main{{max-width:1050px;margin:40px auto;padding:0 24px}}h1{{font-size:36px}}p{{margin:18px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:14px;text-align:left;border-bottom:1px solid var(--line)}}
small{{color:var(--ink3)}}.scroll{{overflow-x:auto}}.status{{padding:18px;background:#eaf5ee;border-radius:10px}}
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
<p>Lower forecast error is better; more squad points is better. Forecast losses are averaged
with equal weight per gameweek on identical player populations. A lucky captain can win a
week without proving that the underlying forecast is better. We do not automatically select a winner.</p>
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
