"""Publish a dated official-results update without running or restating forecasts."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from evmax import render, writer
from scripts.validate_site import validate

SOURCE = REPO / 'evmax/assets/editorial/fpl-gw9/status.json'
API = '/api/fpl/status.json'


def make_status(bootstrap: dict, fixtures: list, captured_at: str) -> dict:
    """Keep official match completion distinct from checked gameweek finality."""
    current = next(e for e in bootstrap['events'] if e.get('is_current'))
    upcoming = next(e for e in bootstrap['events'] if e.get('is_next'))
    previous = next(e for e in bootstrap['events'] if e['id'] == current['id'] - 1)
    teams = {team['id']: team['name'] for team in bootstrap['teams']}

    def week(event):
        matches = [{key: fixture.get(key) for key in (
            'id', 'event', 'kickoff_time', 'finished', 'finished_provisional',
            'team_h', 'team_a', 'team_h_score', 'team_a_score')}
            for fixture in fixtures if fixture.get('event') == event['id']]
        for match in matches:
            match.update(home=teams[match['team_h']], away=teams[match['team_a']])
        final = bool(matches) and event.get('finished') is True and event.get('data_checked') is True and all(m['finished'] for m in matches)
        return {'gameweek': event['id'], 'status': 'final' if final else 'provisional',
                'event': {key: event.get(key) for key in ('id', 'finished', 'data_checked', 'average_entry_score')},
                'played': sum(bool(m['finished'] or m['finished_provisional']) for m in matches),
                'fixtures': matches}

    return {'schema_version': 1, 'publication_type': 'status_update',
            'captured_at': captured_at, 'current': week(current), 'previous': week(previous),
            'next': {'gameweek': upcoming['id'], 'deadline_time': upcoming['deadline_time'],
                     'preview_target': 'Tuesday morning, 3 November',
                     'forecast_status': 'not_published'},
            'sources': ['https://fantasy.premierleague.com/api/bootstrap-static/',
                        'https://fantasy.premierleague.com/api/fixtures/']}


def archive_card_note(page: str, preview: dict) -> str:
    """Date the existing preview label while retaining every projection value."""
    when = datetime.fromisoformat(preview['as_of'].replace('Z', '+00:00'))
    note = (f'<b>Archived preview</b> Gameweek {preview["gameweek"]} cards, simulated '
            f'{when.day} {when:%B %Y}. Prices, availability and projections reflect '
            'that capture. <a style="text-decoration:underline" href="/fpl/gw9/update/">'
            'Current gameweek update</a>.')
    return re.sub(r'<p class="(pc-preview|tcf-preview)">.*?</p>',
                  lambda m: f'<p class="{m[1]}">{note}</p>', page, flags=re.S)


def render_pages(record: dict) -> tuple[str, str]:
    """Use the site's existing hero, table and article styles for official results."""
    current, previous, upcoming = record['current'], record['previous'], record['next']
    gw = current['gameweek']
    stamp = datetime.fromisoformat(record['captured_at'].replace('Z', '+00:00'))
    date = f'{stamp.day} {stamp:%B %Y}'
    deadline = datetime.fromisoformat(upcoming['deadline_time'].replace('Z', '+00:00'))
    deadline_text = f'{deadline:%A} {deadline.day} {deadline:%B}, {deadline:%H:%M} UTC'
    pending = [f for f in current['fixtures'] if not (f['finished'] or f['finished_provisional'])]
    title = (f'GW{gw}: {current["played"]} matches played, {len(pending)} still to come'
             if pending else f'GW{gw}: All {current["played"]} matches played')
    final = current['status'] == 'final'
    preview_path = upcoming.get('preview_path')
    preview_copy = (f'The early GW{upcoming["gameweek"]} preview is now published.'
                    if preview_path else f'Our first preview is targeted for {upcoming["preview_target"]}.')
    summary = (f'GW{gw} results are final and checked. ' if final else f'GW{gw} results remain provisional. ')
    if final:
        summary += f'The official average was {current["event"]["average_entry_score"]} points. '
    summary += f'The GW{upcoming["gameweek"]} deadline is {deadline_text}. {preview_copy}'
    rows = []
    for fixture in current['fixtures']:
        played = fixture['finished'] or fixture['finished_provisional']
        score = f'{fixture["team_h_score"]}–{fixture["team_a_score"]}' if played else 'To play'
        kickoff = datetime.fromisoformat(fixture['kickoff_time'].replace('Z', '+00:00'))
        detail = ('Final' if final else 'Played; FPL checks pending') if played else f'{kickoff.day} {kickoff:%B, %H:%M} UTC'
        rows.append(f'<tr><td>{html.escape(fixture["home"])}</td><td>{score}</td>'
                    f'<td>{html.escape(fixture["away"])}</td><td>{detail}</td></tr>')
    table = ('<div class="table-wrap" style="overflow-x:auto"><table class="rank">'
             '<thead><tr><th>Home</th><th>Score</th><th>Away</th><th>Status</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    previous_copy = (f'GW{previous["gameweek"]} is final and checked. The official average was '
                     f'{previous["event"]["average_entry_score"]} points.'
                     if previous['status'] == 'final' else f'GW{previous["gameweek"]} is awaiting final checks.')
    preview_body = (f'<p><a style="text-decoration:underline" href="{html.escape(preview_path, quote=True)}">'
                    f'Read the early GW{upcoming["gameweek"]} preview</a>: refreshed player forecasts and '
                    'captain rankings, provisional ahead of the European fixtures.</p>' if preview_path else
                    f'<p>Target: <strong>{upcoming["preview_target"]}</strong>, after the remaining '
                    'GW9 result and finality checks. The preview needs a completed refresh of '
                    'player data, minutes, injury news and market odds, followed by a new model run. '
                    'This update contains official match results and the deadline; no new expected-points forecast is published.</p>')
    finality_body = ('All fixtures are finished and FPL marks the event finished and data checked.' if final else
                    'Played matches and bonus points remain subject to the official FPL checks. '
                    'We will treat the gameweek as final only when all fixtures are finished '
                    'and FPL marks the event finished and data checked.')
    body = (f'<p><strong>Updated {date} at {stamp:%H:%M} UTC.</strong> '
            f'{html.escape(summary)}</p><h2>GW{gw} {"final results" if final else "results so far"}</h2>{table}'
            f'<p>{finality_body}</p>'
            f'<h2>Completed gameweek</h2><p>{previous_copy} '
            'The latest graded Model XI is GW7, which scored 59. '
            'There is no frozen GW8 or GW9 model forecast to add to that ledger. '
            '<a style="text-decoration:underline" href="/track-record/">See the graded record</a>.</p>'
            f'<h2>First GW{upcoming["gameweek"]} preview</h2>'
            f'{preview_body}'
            f'<p><strong>Deadline: {deadline_text}</strong> (19:30 Denmark time).</p>'
            '<h2>Earlier analysis</h2><p>'
            '<a style="text-decoration:underline" href="/fpl/gw8/preview/">GW8 preview, 21 October</a> · '
            '<a style="text-decoration:underline" href="/fpl/players/">Player projections</a> · '
            '<a style="text-decoration:underline" href="/fpl/gw7/confirmed-pair/">GW7 final selection and result</a>.</p>'
            '<h2>Sources</h2><p><a style="text-decoration:underline" '
            'href="https://fantasy.premierleague.com/api/bootstrap-static/">Official FPL events and deadline</a> · '
            '<a style="text-decoration:underline" href="https://fantasy.premierleague.com/api/fixtures/">'
            'Official fixtures</a> · <a style="text-decoration:underline" href="/api/fpl/status.json">'
            'Captured status data</a>.</p>')
    prose = {'headline': title, 'standfirst': summary, 'body_html': body,
             'body_md': writer._html_to_md(body)}
    article = render.article_page(gw, 'update', title, prose, [], [], API, '',
        generated_at=record['captured_at'], date_str=date, show_table=False,
        available_rounds=list(range(1, upcoming['gameweek'] + 1 if preview_path else gw + 1)), section=render.FPL)
    article = re.sub(r'<figure class="fig">\s*<figcaption>.*?</figcaption>\s*</figure>', '', article, flags=re.S)
    article = re.sub(r'<h2>Bottom line</h2>\s*<p>\s*</p>', '', article)
    article = article.replace('By the evmax model', 'By evmax')
    home = render.landing_page(gw, {'slug': 'update', 'prose': prose,
        'viz_html': table}, [], date_str=date, section=render.FPL,
        available_rounds=list(range(1, upcoming['gameweek'] + 1 if preview_path else gw + 1)), pre_feed_html=body[body.index('<h2>Completed gameweek'):])
    home = re.sub(r'<p class="hs-what">.*?</p>',
        f'<p class="hs-what">Official results updated {date}, {stamp:%H:%M} UTC. GW{gw} is {current["status"]}.</p>', home, flags=re.S)
    home = home.replace('<div class="pagelabel">Latest analysis</div>\n<div class="feed"></div>', '')
    home = home.replace('Read the full analysis', 'Read the current update').replace('By the evmax model', 'By evmax')
    home = re.sub(r'<title>.*?</title>', f'<title>{html.escape(title)} | evmax</title>', home, count=1)
    home = re.sub(r'(<meta (?:name="description"|property="og:description"|name="twitter:description") content=")[^"]*(")',
                  lambda m: m[1]+html.escape(summary, quote=True)+m[2], home)
    home = home.replace(f'{render.FPL.label} {render.FPL.kicker(gw)} — simulation-based picks', html.escape(title))
    for name, page in [('home', home), ('article', article)]:
        page = page.replace('href="/fpl/gw8/"', 'href="/fpl/gw8/preview/"')
        if name == 'home': home = page
        else: article = page
    return home, article


def publish(out: Path, record: dict, *, results_only: bool = False) -> None:
    """Update current surfaces in the cumulative export and retain forecast files."""
    stamp = datetime.fromisoformat(record['captured_at'].replace('Z', '+00:00'))
    if not 0 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 86400:
        raise ValueError('Status inputs need a fresh official capture before publication')
    if not out.exists():
        shutil.copytree(REPO/'dist', out)
    if results_only:
        # A results correction must not roll back the current preview homepage,
        # player cards or its original forecast-generation timestamp.
        home, article = render_pages(record)
        gw = record['current']['gameweek']
        for name, content in {
                f'fpl/gw{gw}/index.html': home,
                f'fpl/gw{gw}/update/index.html': article,
                API.lstrip('/'): json.dumps(record, indent=2, ensure_ascii=False)+'\n'}.items():
            target = out/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        errors = validate(out)
        if errors:
            raise ValueError(errors)
        return
    previous_latest = json.loads((out/'api/latest.json').read_text())
    archived_preview = previous_latest.get('preview') or previous_latest.get('archived_preview')
    prior = previous_latest.get('last_frozen_forecast') or previous_latest
    frozen = {key: prior[key] for key in ('gameweek', 'generated_at', 'forecast_artifact_id',
              'articles', 'final_selection_result') if key in prior}
    latest = {'publication_type': 'status_update',
              'gameweek': record['current']['gameweek'], 'generated_at': record['captured_at'],
              'current_status': {'data': API, 'article': '/fpl/gw9/update/', 'next_gameweek': record['next']},
              'articles': {'update': API}, 'archived_preview': archived_preview,
              'last_frozen_forecast': frozen}
    home, article = render_pages(record)
    files = {'index.html': home, 'fpl/gw9/index.html': home,
             'fpl/gw9/update/index.html': article,
             API.lstrip('/'): json.dumps(record, indent=2, ensure_ascii=False)+'\n',
             'api/latest.json': json.dumps(latest, indent=2, ensure_ascii=False)+'\n'}
    for name, content in files.items():
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    preview = json.loads((out/'api/fpl/preview/players.json').read_text())['preview']
    for base in ['fpl/players', 'fpl/tiers']:
        for path in (out/base).rglob('*.html'):
            before = path.read_text()
            after = archive_card_note(before, preview)
            if after != before:
                path.write_text(after)
    sitemap = out/'sitemap.xml'
    text = sitemap.read_text()
    for route in ['/fpl/gw9/', '/fpl/gw9/update/']:
        url = render.SITE_URL+route
        if url not in text:
            text = text.replace('</urlset>', f'<url><loc>{url}</loc><lastmod>{stamp:%Y-%m-%d}</lastmod></url></urlset>')
    sitemap.write_text(text)
    errors = validate(out)
    if errors:
        raise ValueError(errors)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=REPO/'data/releases/2026-11-02-status/site-preview')
    parser.add_argument('--results-only', action='store_true', help='Update results pages/feed while retaining the current forecast surfaces')
    args = parser.parse_args()
    publish(args.out, json.loads(SOURCE.read_text()), results_only=args.results_only)
    print(f'Validated official-status publication: {args.out}')
