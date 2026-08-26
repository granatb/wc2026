#!/usr/bin/env node
/**
 * evmax MCP server — the agent front door to the public FPL data.
 *
 * Phase 2B / spec D4: a THIN CLIENT over the public API. No infrastructure, no
 * database, no secrets, no build step, no state. Every number it returns was
 * already fetchable with curl; this exists so an agent does not have to know
 * the URL scheme.
 *
 *   npx evmax-mcp
 *   claude mcp add evmax -- npx -y evmax-mcp
 *
 * Base URL defaults to https://evmax.ai; EVMAX_BASE_URL overrides it (the
 * smoke test and a local `dist/` preview both use that).
 *
 * TWO THINGS THIS FILE IS CAREFUL ABOUT
 *
 * 1. A 200 IS NOT A SUCCESS. The site is on Cloudflare Pages, which serves the
 *    HTML 404 fallback with status 200 for an unknown path. A naive client
 *    would hand an agent a page of HTML as if it were data. fetchJson checks
 *    the content type AND parses, and treats an HTML body as "not published".
 *
 * 2. THE DATASET IS PREFERRED, NOT REQUIRED. The bulk dataset under
 *    /api/fpl/dataset/ is the richest source (price, ownership, verdicts,
 *    distributions). Where it is not published for a gameweek, the tools fall
 *    back to the per-gameweek feeds that have always been live, and SAY which
 *    source answered. A tool that silently returned less would be worse than
 *    one that explains itself.
 *
 * Every tool result ends with its source URL and the CC BY attribution line.
 * That is the deal the data is published under and the server states it every
 * single time rather than assuming the agent read the README.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

export const BASE_URL = (process.env.EVMAX_BASE_URL || "https://evmax.ai")
  .replace(/\/+$/, "");

export const LICENSE_LINE =
  "CC BY 4.0 — attribute evmax (https://evmax.ai)";

const DATASET_BASE = "/api/fpl/dataset";
const USER_AGENT = "evmax-mcp/0.1.0 (+https://evmax.ai/data/)";
const TIMEOUT_MS = 15000;

/** A fetch failure an agent can act on. Never a stack trace. */
export class EvmaxError extends Error {}

/**
 * GET a JSON document off the public site.
 *
 * Returns null when the path is simply not published (404, or the Pages HTML
 * fallback served with a 200). Throws EvmaxError for anything that is a real
 * problem — the network, a server error, a truncated body — because those two
 * cases call for completely different advice to the agent.
 */
export async function fetchJson(path) {
  const url = `${BASE_URL}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/json", "user-agent": USER_AGENT },
      signal: controller.signal,
    });
  } catch (err) {
    const why = err && err.name === "AbortError"
      ? `no response within ${TIMEOUT_MS / 1000}s`
      : (err && err.message) || "network error";
    throw new EvmaxError(`Could not reach ${url} (${why}).`);
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 404) return null;
  if (!response.ok) {
    throw new EvmaxError(
      `${url} returned HTTP ${response.status}. The site may be mid-deploy; ` +
      `try again in a minute.`);
  }

  const contentType = (response.headers.get("content-type") || "")
    .toLowerCase();
  const body = await response.text();
  // The Pages 404 fallback: HTML, status 200. Not an error — just not
  // published — so the caller can fall back to another source.
  if (contentType.includes("text/html") || body.trimStart().startsWith("<")) {
    return null;
  }
  try {
    return JSON.parse(body);
  } catch {
    throw new EvmaxError(
      `${url} did not return valid JSON. It may have been served from a stale ` +
      `cache; try again shortly.`);
  }
}

/** Fetch a CSV/text document; null when not published. */
async function fetchText(path) {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: { "user-agent": USER_AGENT },
  }).catch((err) => {
    throw new EvmaxError(`Could not reach ${url} (${err.message}).`);
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new EvmaxError(`${url} returned HTTP ${response.status}.`);
  }
  const body = await response.text();
  if (body.trimStart().startsWith("<!doctype")) return null;
  return body;
}

// ---------------------------------------------------------------------------
// Source resolution
// ---------------------------------------------------------------------------

/** The gameweek the site is currently publishing, or null. */
export async function currentGameweek() {
  const latest = await fetchJson("/api/latest.json");
  return latest && typeof latest.gameweek === "number" ? latest.gameweek : null;
}

/** The dataset manifest, or null when the dataset is not published yet. */
export async function datasetIndex() {
  return fetchJson(`${DATASET_BASE}/index.json`);
}

/**
 * Every gameweek that has data of any kind, with what each one carries.
 * Sources, in order of richness: the dataset manifest, the graded accuracy
 * files, and the currently published gameweek.
 */
export async function listGameweeks() {
  const seen = new Map();
  const note = (gw, key, path) => {
    if (!seen.has(gw)) seen.set(gw, { gameweek: gw });
    seen.get(gw)[key] = path;
  };

  const index = await datasetIndex();
  if (index && Array.isArray(index.gameweeks)) {
    for (const entry of index.gameweeks) {
      note(entry.gameweek, "dataset_json", entry.json);
      note(entry.gameweek, "dataset_csv", entry.csv);
    }
  }

  const current = await currentGameweek();
  if (current !== null) {
    note(current, "projections", `/api/fpl/gw${current}/players.json`);
  }

  // Graded gameweeks: walk back from the current one. Cheap (one HEAD-sized
  // GET each) and bounded — there are 38 gameweeks in a season, and a gap is
  // not a stop condition because a gameweek can be ungraded while a later one
  // is graded.
  const ceiling = current === null ? 38 : current;
  for (let gw = 1; gw <= ceiling; gw += 1) {
    const path = `/api/fpl/accuracy/gw${gw}.json`;
    const graded = await fetchJson(path);
    if (graded) note(gw, "accuracy", path);
  }

  return [...seen.values()].sort((a, b) => a.gameweek - b.gameweek);
}

/**
 * {rows, source, hasDistributions} for one gameweek.
 *
 * The dataset carries price, ownership, verdicts and (once stored)
 * distributions; the players feed is the always-live fallback and deliberately
 * carries no price or ownership — the tool result says which one answered so
 * an agent never reports a missing column as a zero.
 */
export async function projectionsFor(gameweek) {
  const payload = await fetchJson(`${DATASET_BASE}/gw${gameweek}.json`);
  if (payload && Array.isArray(payload.players)) {
    return {
      rows: payload.players,
      source: `${BASE_URL}${DATASET_BASE}/gw${gameweek}.json`,
      kind: "dataset",
      hasDistributions: Boolean(payload.meta && payload.meta.has_distributions),
    };
  }
  const feed = await fetchJson(`/api/fpl/gw${gameweek}/players.json`);
  if (feed && Array.isArray(feed.players)) {
    return {
      rows: feed.players,
      source: `${BASE_URL}/api/fpl/gw${gameweek}/players.json`,
      kind: "players-feed",
      hasDistributions: false,
    };
  }
  return null;
}

// Letters NFD cannot decompose — they are base letters, not letter+mark — that
// real Premier League squad lists carry. Mirrors evmax/fpl_players.py's
// _TRANSLIT so a name matches here exactly as it does on the site.
const TRANSLIT = {
  "ø": "o", "æ": "ae", "ł": "l", "đ": "d", "ß": "ss", "ð": "d", "þ": "th",
};

const norm = (s) =>
  (s || "")
    .toLowerCase()
    .replace(/[øæłđßðþ]/g, (c) => TRANSLIT[c])
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]/g, "");

/** Best name match in a row list: exact, then prefix, then substring. */
export function matchPlayer(rows, name) {
  const want = norm(name);
  if (!want) return null;
  const exact = rows.filter((r) => norm(r.name) === want);
  if (exact.length) return exact[0];
  const starts = rows.filter((r) => norm(r.name).startsWith(want));
  if (starts.length) return starts[0];
  const contains = rows.filter((r) => norm(r.name).includes(want));
  return contains.length ? contains[0] : null;
}

/** Near misses, so a failed lookup can suggest rather than just refuse. */
export function suggestNames(rows, name, limit = 6) {
  const want = norm(name);
  const head = want.slice(0, 3);
  if (!head) return [];
  return rows
    .filter((r) => norm(r.name).includes(head))
    .slice(0, limit)
    .map((r) => r.name);
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

export const TOOLS = [
  {
    name: "list_gameweeks",
    description:
      "List every Premier League gameweek evmax has published data for, and " +
      "what each one carries (bulk dataset files, projections feed, graded " +
      "accuracy). Call this first when you do not know which gameweek to ask " +
      "about.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "get_projections",
    description:
      "Projected FPL points for every simulated player in a gameweek, from " +
      "50,000 Monte-Carlo simulations. Optionally filter by position and cap " +
      "the number of rows. Ordered by projected points, highest first.",
    inputSchema: {
      type: "object",
      properties: {
        gameweek: {
          type: "integer",
          description: "Gameweek number. Defaults to the current one.",
        },
        position: {
          type: "string",
          enum: ["GK", "DEF", "MID", "FWD"],
          description: "Restrict to one position.",
        },
        limit: {
          type: "integer",
          description: "Maximum rows to return (default 25, max 200).",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "get_player",
    description:
      "Everything evmax projects for one player in one gameweek — projected " +
      "points, captain EV, ceiling, price, ownership and our verdict tier " +
      "where published. Matches on name, accents and punctuation ignored.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Player name, e.g. 'Haaland'." },
        gameweek: {
          type: "integer",
          description: "Gameweek number. Defaults to the current one.",
        },
      },
      required: ["name"],
      additionalProperties: false,
    },
  },
  {
    name: "get_duel",
    description:
      "The running model-vs-crowd duel: evmax's own published XI against a " +
      "consensus XI assembled from what the popular FPL sources recommended, " +
      "both frozen before the deadline, scored on official FPL points.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "get_accuracy",
    description:
      "How accurate evmax has been: per-gameweek mean absolute error against " +
      "realized official points, compared with FPL's own ep_next projection " +
      "where it was captured. The graded ledger, misses included.",
    inputSchema: {
      type: "object",
      properties: {
        gameweek: {
          type: "integer",
          description: "One gameweek's full grading detail. Omit for the " +
            "whole ledger.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "get_distribution",
    description:
      "The shape of a player's gameweek, not just the mean: the distribution " +
      "of simulated point outcomes — floor, median, most likely, ceiling, and " +
      "the probability of a haul or a blank.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Player name." },
        gameweek: {
          type: "integer",
          description: "Gameweek number. Defaults to the current one.",
        },
      },
      required: ["name"],
      additionalProperties: false,
    },
  },
];

const DISTRIBUTION_KEYS = ["p10", "median", "mode", "p90", "p_haul", "p_blank"];

function block(lines, source) {
  const text = Array.isArray(lines) ? lines.join("\n") : String(lines);
  return {
    content: [{
      type: "text",
      text: `${text}\n\nSource: ${source}\n${LICENSE_LINE}`,
    }],
  };
}

function errorBlock(message) {
  return { content: [{ type: "text", text: message }], isError: true };
}

async function resolveGameweek(requested) {
  if (typeof requested === "number") return requested;
  const current = await currentGameweek();
  if (current === null) {
    throw new EvmaxError(
      "Could not work out the current gameweek — " +
      `${BASE_URL}/api/latest.json is not answering. Pass a gameweek number.`);
  }
  return current;
}

const fmt = (v, digits = 2) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(digits);

async function toolListGameweeks() {
  const rows = await listGameweeks();
  if (!rows.length) {
    return errorBlock(
      `No published gameweeks found at ${BASE_URL}. If you are pointing ` +
      `EVMAX_BASE_URL at a local build, check the site was built first.`);
  }
  const lines = [`evmax has published data for ${rows.length} gameweek(s):`, ""];
  for (const row of rows) {
    const has = [];
    if (row.dataset_json) has.push("bulk dataset (JSON + CSV)");
    if (row.projections) has.push("projections feed");
    if (row.accuracy) has.push("graded accuracy");
    lines.push(`- Gameweek ${row.gameweek}: ${has.join(", ")}`);
  }
  return block(lines, `${BASE_URL}/data/`);
}

async function toolGetProjections(args) {
  const gameweek = await resolveGameweek(args.gameweek);
  const result = await projectionsFor(gameweek);
  if (!result) {
    return errorBlock(
      `No projections published for gameweek ${gameweek}. Call ` +
      `list_gameweeks to see what exists.`);
  }
  const limit = Math.min(Math.max(args.limit || 25, 1), 200);
  let rows = result.rows;
  if (args.position) {
    rows = rows.filter((r) => r.position === args.position);
    if (!rows.length) {
      return errorBlock(
        `No ${args.position} rows in gameweek ${gameweek}'s data.`);
    }
  }
  rows = [...rows]
    .sort((a, b) => (b.x_points || 0) - (a.x_points || 0))
    .slice(0, limit);

  const lines = [
    `Gameweek ${gameweek} projections — top ${rows.length}` +
    (args.position ? ` ${args.position}` : "") +
    ` by projected points (50,000 simulations).`,
    "",
  ];
  for (const r of rows) {
    const parts = [
      `${r.name} (${r.team}, ${r.position})`,
      `xPts ${fmt(r.x_points)}`,
      `captain EV ${fmt(r.captain_ev)}`,
      `ceiling ${fmt(r.ceiling)}`,
    ];
    if (r.price !== undefined && r.price !== null) {
      parts.push(`£${fmt(r.price, 1)}m`);
    }
    if (r.ownership_pct !== undefined && r.ownership_pct !== null) {
      parts.push(`${fmt(r.ownership_pct, 1)}% owned`);
    }
    if (r.verdict_tier) parts.push(`tier ${r.verdict_tier}`);
    lines.push(`- ${parts.join(" · ")}`);
  }
  if (result.kind === "players-feed") {
    lines.push("",
      "Note: served from the projections feed, which carries no price or " +
      "ownership — the bulk dataset (which does) is not published for this " +
      "gameweek.");
  }
  return block(lines, result.source);
}

async function toolGetPlayer(args) {
  const gameweek = await resolveGameweek(args.gameweek);
  const result = await projectionsFor(gameweek);
  if (!result) {
    return errorBlock(`No projections published for gameweek ${gameweek}.`);
  }
  const row = matchPlayer(result.rows, args.name);
  if (!row) {
    const near = suggestNames(result.rows, args.name);
    return errorBlock(
      `No player matching "${args.name}" in gameweek ${gameweek}.` +
      (near.length ? ` Did you mean: ${near.join(", ")}?` : ""));
  }
  const lines = [
    `${row.name} — ${row.team}, ${row.position}, gameweek ${gameweek}`,
    "",
    `Projected points: ${fmt(row.x_points)}`,
    `If captained:     ${fmt(row.captain_ev)}`,
    `Ceiling:          ${fmt(row.ceiling)} (mean of his best 15% of sims)`,
  ];
  if (row.price !== undefined && row.price !== null) {
    lines.push(`Price:            £${fmt(row.price, 1)}m`);
  }
  if (row.ownership_pct !== undefined && row.ownership_pct !== null) {
    lines.push(`Ownership:        ${fmt(row.ownership_pct, 1)}%`);
  }
  if (row.value !== undefined && row.value !== null) {
    lines.push(`Points per £m:    ${fmt(row.value, 3)}`);
  }
  if (row.start_prob !== undefined && row.start_prob !== null) {
    lines.push(`Start probability: ${fmt(row.start_prob * 100, 0)}%`);
  }
  if (row.verdict_tier) {
    lines.push(`Verdict:          tier ${row.verdict_tier}` +
      (row.verdict_call ? ` (${row.verdict_call})` : ""));
  }
  if (row.flag) lines.push(`Availability flag: ${row.flag}`);
  if (DISTRIBUTION_KEYS.some((k) => row[k] !== undefined)) {
    lines.push("", "Call get_distribution for the full shape of his gameweek.");
  }
  return block(lines, result.source);
}

async function toolGetDuel() {
  const gameweek = await resolveGameweek(undefined);
  const [ours, theirs] = await Promise.all([
    fetchJson(`/api/fpl/gw${gameweek}/our-squad.json`),
    fetchJson(`/api/fpl/gw${gameweek}/consensus-squad.json`),
  ]);
  if (!ours || !theirs) {
    return errorBlock(
      `The two squad feeds for gameweek ${gameweek} are not both published ` +
      `yet, so there is no duel to report.`);
  }
  const a = ours.squad || {};
  const b = theirs.squad || {};

  // The running score comes from the graded gameweeks, not from this week's
  // projections — a duel scored on projections would be us marking our own
  // homework.
  let model = 0;
  let crowd = 0;
  const history = [];
  for (let gw = 1; gw < gameweek; gw += 1) {
    const graded = await fetchJson(`/api/fpl/accuracy/gw${gw}.json`);
    const squads = graded && graded.squads;
    if (!squads) continue;
    const m = squads["our-squad"] && squads["our-squad"].realized_official;
    const c = squads["consensus-squad"] &&
      squads["consensus-squad"].realized_official;
    if (typeof m !== "number" || typeof c !== "number") continue;
    if (m > c) model += 1;
    else if (c > m) crowd += 1;
    history.push(`  GW${gw}: model ${m} — crowd ${c}`);
  }
  const label = model > crowd ? "model leads"
    : crowd > model ? "crowd leads" : "level";

  const lines = [
    `Model vs crowd — running score ${model}-${crowd} (${label}).`,
    "",
    `Gameweek ${gameweek}, both XIs frozen before the deadline:`,
    `  Model XI ("${a.team_name || "The Model XI"}") — ${a.formation || "?"}, ` +
    `captain ${a.captain || "?"}, projected ${fmt(a.projected_total)}`,
    `  Consensus XI — ${b.formation || "?"}, captain ${b.captain || "?"}, ` +
    `projected ${fmt(b.projected_total)}`,
  ];
  if (history.length) {
    lines.push("", "Graded so far (official FPL points):", ...history);
  } else {
    lines.push("", "No gameweek has been graded yet, so the score is 0-0.");
  }
  return block(lines, `${BASE_URL}/fpl/accuracy/`);
}

async function toolGetAccuracy(args) {
  if (typeof args.gameweek === "number") {
    const path = `/api/fpl/accuracy/gw${args.gameweek}.json`;
    const graded = await fetchJson(path);
    if (!graded) {
      return errorBlock(
        `Gameweek ${args.gameweek} has not been graded. A gameweek is graded ` +
        `once every fixture in it has finished.`);
    }
    const worst = (graded.players || []).slice(0, 5).map(
      (p) => `  ${p.name}: projected ${fmt(p.x_points)}, scored ${p.realized}` +
        ` (off by ${fmt(p.err_ours)})`);
    const lines = [
      `Gameweek ${args.gameweek} — ${graded.n} players graded.`,
      "",
      `Our mean absolute error: ${fmt(graded.mae_ours, 3)}`,
      graded.mae_ep_next === null || graded.mae_ep_next === undefined
        ? "FPL's own ep_next: not captured for this gameweek (we started " +
          "capturing it from GW2)."
        : `FPL's own ep_next:      ${fmt(graded.mae_ep_next, 3)}` +
          ` (${graded.beat_ep_next ? "we were closer" : "ep_next was closer"})`,
    ];
    for (const [slug, line] of Object.entries(graded.squads || {})) {
      lines.push(`${slug}: projected ${fmt(line.projected)} → official ` +
        `${line.realized_official ?? line.realized}`);
    }
    if (worst.length) lines.push("", "Biggest misses:", ...worst);
    return block(lines, `${BASE_URL}${path}`);
  }

  const current = await currentGameweek();
  const ceiling = current === null ? 38 : current;
  const lines = ["evmax accuracy ledger — projections vs realized official " +
    "points, every graded gameweek:", ""];
  let found = 0;
  for (let gw = 1; gw <= ceiling; gw += 1) {
    const graded = await fetchJson(`/api/fpl/accuracy/gw${gw}.json`);
    if (!graded) continue;
    found += 1;
    const ep = graded.mae_ep_next === null || graded.mae_ep_next === undefined
      ? "ep_next not captured" : `FPL ep_next MAE ${fmt(graded.mae_ep_next, 3)}`;
    lines.push(`- GW${gw}: our MAE ${fmt(graded.mae_ours, 3)} over ` +
      `${graded.n} players · ${ep}`);
  }
  if (!found) {
    return errorBlock(
      "No gameweek has been graded yet. Grading happens once every fixture " +
      "in a gameweek has finished.");
  }
  lines.push("",
    "Lower MAE is better. Call get_accuracy with a gameweek for the " +
    "per-player detail, including our worst misses.");
  return block(lines, `${BASE_URL}/fpl/accuracy/`);
}

async function toolGetDistribution(args) {
  const gameweek = await resolveGameweek(args.gameweek);
  const result = await projectionsFor(gameweek);
  if (!result) {
    return errorBlock(`No projections published for gameweek ${gameweek}.`);
  }
  const row = matchPlayer(result.rows, args.name);
  if (!row) {
    const near = suggestNames(result.rows, args.name);
    return errorBlock(
      `No player matching "${args.name}" in gameweek ${gameweek}.` +
      (near.length ? ` Did you mean: ${near.join(", ")}?` : ""));
  }
  const present = DISTRIBUTION_KEYS.filter((k) => row[k] !== undefined &&
    row[k] !== null);
  if (!present.length) {
    return errorBlock(
      `Gameweek ${gameweek} was published before evmax started storing ` +
      `per-player outcome distributions, so there is no shape to report for ` +
      `${row.name} — only the mean (${fmt(row.x_points)} projected points, ` +
      `ceiling ${fmt(row.ceiling)}). Call list_gameweeks to find a gameweek ` +
      `whose bulk dataset carries distributions.`);
  }
  const lines = [
    `${row.name} — ${row.team}, ${row.position}, gameweek ${gameweek}`,
    `The shape of his gameweek across 50,000 simulations:`,
    "",
    `Floor (10th pct):   ${fmt(row.p10, 1)}`,
    `Median:             ${fmt(row.median, 1)}`,
    `Most likely:        ${fmt(row.mode, 1)}`,
    `Strong week (90th): ${fmt(row.p90, 1)}`,
    `Ceiling:            ${fmt(row.ceiling)} (mean of his best 15% of sims)`,
    `Mean (projection):  ${fmt(row.x_points)}`,
    "",
    `Probability of a haul (10+ points):  ${fmt((row.p_haul || 0) * 100, 1)}%`,
    `Probability of a blank (2 or fewer): ${fmt((row.p_blank || 0) * 100, 1)}%`,
  ];
  if (row.distribution && typeof row.distribution === "object") {
    const pmf = Object.entries(row.distribution)
      .map(([pts, n]) => [Number(pts), Number(n)])
      .sort((a, b) => a[0] - b[0]);
    const total = pmf.reduce((sum, [, n]) => sum + n, 0) || 1;
    const top = [...pmf].sort((a, b) => b[1] - a[1]).slice(0, 8)
      .sort((a, b) => a[0] - b[0]);
    lines.push("", "Most likely outcomes:");
    for (const [pts, n] of top) {
      lines.push(`  ${String(pts).padStart(3)} pts: ` +
        `${((n / total) * 100).toFixed(1)}%`);
    }
  }
  return block(lines, result.source);
}

const HANDLERS = {
  list_gameweeks: toolListGameweeks,
  get_projections: toolGetProjections,
  get_player: toolGetPlayer,
  get_duel: toolGetDuel,
  get_accuracy: toolGetAccuracy,
  get_distribution: toolGetDistribution,
};

export async function callTool(name, args = {}) {
  const handler = HANDLERS[name];
  if (!handler) return errorBlock(`Unknown tool: ${name}`);
  try {
    return await handler(args || {});
  } catch (err) {
    // A stack trace is useless to an agent and alarming to a user. Anything
    // unexpected still comes back as one plain sentence it can act on.
    const message = err instanceof EvmaxError
      ? err.message
      : `Something went wrong talking to ${BASE_URL}: ` +
        `${(err && err.message) || err}`;
    return errorBlock(message);
  }
}

export async function main() {
  const server = new Server(
    { name: "evmax", version: "0.1.0" },
    { capabilities: { tools: {} } },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOLS,
  }));
  server.setRequestHandler(CallToolRequestSchema, async (request) =>
    callTool(request.params.name, request.params.arguments));
  await server.connect(new StdioServerTransport());
  console.error(`evmax MCP server ready (${BASE_URL})`);
}

// Only start the transport when run as a program — the smoke test imports
// this file for its exports.
const invokedDirectly = process.argv[1] &&
  import.meta.url === `file://${process.argv[1]}`;
if (invokedDirectly) {
  main().catch((err) => {
    console.error(`evmax MCP server failed to start: ${err.message}`);
    process.exit(1);
  });
}
