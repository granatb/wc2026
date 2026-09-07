import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchJson, projectionsFor } from './index.js';

test('request timeout covers response body after headers arrive', async () => {
  const originalFetch = globalThis.fetch;
  const originalTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn, delay, ...args) => originalTimeout(fn, Math.min(delay, 10), ...args);
  globalThis.fetch = async (_url, options) => ({
    status: 200, ok: true, headers: {get: () => 'application/json'},
    text: () => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('body aborted')));
    }),
  });
  try {
    await assert.rejects(fetchJson('/slow-body.json'), /aborted/);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalTimeout;
  }
});

test('HTML fallback is never treated as API data', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({status: 200, ok: true,
    headers: {get: () => 'text/html'}, text: async () => '<!doctype html><h1>Missing</h1>'});
  try { assert.equal(await fetchJson('/missing.json'), null); }
  finally { globalThis.fetch = originalFetch; }
});

test('unavailable full dataset falls back to explicitly partial archive', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => ({status: 200, ok: true,
    headers: {get: () => 'application/json'}, text: async () => JSON.stringify(
      url.includes('/dataset/') ? {status: 'unavailable', players: []} :
      {coverage: 'published_articles_only', players: [{name: 'Archived player', x_points: 4}]})});
  try {
    const result = await projectionsFor(1);
    assert.equal(result.rows.length, 1);
    assert.equal(result.coverage, 'published_articles_only');
    assert.equal(result.hasDistributions, false);
  } finally { globalThis.fetch = originalFetch; }
});
