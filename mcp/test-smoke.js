#!/usr/bin/env node
/**
 * evmax MCP smoke test — hits the LIVE site and asserts every tool's shape.
 *
 *   cd mcp && npm install && node test-smoke.js
 *   EVMAX_BASE_URL=http://localhost:8788 node test-smoke.js   # a local build
 *
 * MANUAL, ON PURPOSE. This is NOT part of the Python suite: it makes real
 * network requests to https://evmax.ai, so it belongs to the operator's
 * pre-publish checklist, not to a run that has to work offline and be
 * deterministic. Read-only GETs of public JSON only — it never writes
 * anything, anywhere.
 *
 * WHAT IT ASSERTS. Shape and honesty, never a specific number: the live site
 * moves to a new gameweek every week, and a smoke test pinned to "Haaland
 * projects 7.2" would fail every Friday for no reason. So: each tool answers,
 * the answer carries the CC BY line and a source URL, and errors read as
 * sentences rather than stack traces.
 *
 * IT ALSO PROVES THE 404 HANDLING. Cloudflare Pages serves the HTML 404
 * fallback with status 200, so a client that trusted the status code would
 * hand an agent a web page as data. One case below fetches a path that
 * certainly does not exist and requires null back.
 */

import {
  BASE_URL, EvmaxError, LICENSE_LINE, TOOLS, callTool, currentGameweek,
  fetchJson, matchPlayer, suggestNames,
} from "./index.js";

let passed = 0;
let failed = 0;
const failures = [];

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failed += 1;
    failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function textOf(result) {
  return (result.content || []).map((c) => c.text || "").join("\n");
}

/** Every successful tool result must cite its source and its licence. */
function checkCitation(name, result) {
  const text = textOf(result);
  if (result.isError) {
    check(`${name}: error is a plain sentence`,
      !text.includes("at Object.") && !text.includes("\n    at "),
      "an error result leaked a stack trace");
    check(`${name}: error explains itself`, text.length > 20, text.slice(0, 80));
    return false;
  }
  check(`${name}: cites the licence`, text.includes(LICENSE_LINE));
  check(`${name}: cites a source URL`, /Source: https?:\/\//.test(text));
  return true;
}

async function section(title, fn) {
  console.log(`\n${title}`);
  try {
    await fn();
  } catch (err) {
    failed += 1;
    failures.push(`${title} threw: ${err && err.stack}`);
    console.log(`  FAIL ${title} threw: ${err && err.message}`);
  }
}

console.log(`evmax MCP smoke test → ${BASE_URL}`);

await section("fetch layer", async () => {
  const latest = await fetchJson("/api/latest.json");
  check("latest.json parses", latest && typeof latest === "object");
  check("latest.json names a gameweek", typeof latest.gameweek === "number",
    JSON.stringify(latest && latest.gameweek));

  // The load-bearing one: Pages answers an unknown path with the HTML landing
  // page and a 200. Null, not a page of HTML pretending to be data.
  const ghost = await fetchJson("/api/fpl/definitely-not-a-real-file.json");
  check("an unpublished path returns null, not HTML", ghost === null,
    ghost === null ? "" : `got ${typeof ghost}`);

  let threw = null;
  try {
    await fetchJson("http://127.0.0.1:1/nope");
  } catch (err) {
    threw = err;
  }
  check("an unreachable host raises EvmaxError, not a raw fetch error",
    threw instanceof EvmaxError, threw && threw.constructor.name);
});

await section("tool manifest", async () => {
  const names = TOOLS.map((t) => t.name);
  for (const expected of ["list_gameweeks", "get_projections", "get_player",
    "get_duel", "get_accuracy", "get_distribution"]) {
    check(`declares ${expected}`, names.includes(expected));
  }
  check("every tool has a description",
    TOOLS.every((t) => (t.description || "").length > 30));
  check("every tool has an object input schema",
    TOOLS.every((t) => t.inputSchema && t.inputSchema.type === "object"));
});

const gameweek = await currentGameweek();
console.log(`\n(current gameweek on the live site: ${gameweek})`);

await section("list_gameweeks", async () => {
  const result = await callTool("list_gameweeks", {});
  if (!checkCitation("list_gameweeks", result)) return;
  const text = textOf(result);
  check("names at least one gameweek", /Gameweek \d+/.test(text));
  check("says what each gameweek carries",
    /projections feed|bulk dataset|graded accuracy/.test(text));
});

await section("get_projections", async () => {
  const result = await callTool("get_projections", { limit: 5 });
  if (!checkCitation("get_projections", result)) return;
  const text = textOf(result);
  const rows = text.split("\n").filter((l) => l.startsWith("- "));
  check("returns exactly the requested number of rows", rows.length === 5,
    `got ${rows.length}`);
  check("each row carries a projection", rows.every((l) => /xPts \d/.test(l)));
  check("each row carries captain EV and ceiling",
    rows.every((l) => l.includes("captain EV") && l.includes("ceiling")));

  const filtered = await callTool("get_projections",
    { gameweek, position: "DEF", limit: 3 });
  const ftext = textOf(filtered);
  const frows = ftext.split("\n").filter((l) => l.startsWith("- "));
  check("position filter returns only that position",
    frows.length > 0 && frows.every((l) => l.includes(", DEF)")),
    frows[0]);

  const missing = await callTool("get_projections", { gameweek: 99 });
  check("an unpublished gameweek is a clear error, not a crash",
    missing.isError === true && textOf(missing).includes("99"));
});

await section("get_player", async () => {
  // Pick a real name off the live feed rather than hardcoding one — players
  // get sold, renamed and injured, and this test should outlive all three.
  const feed = await fetchJson(`/api/fpl/gw${gameweek}/players.json`);
  const sample = feed && feed.players && feed.players[0];
  check("the live players feed has rows", Boolean(sample));
  if (!sample) return;

  const result = await callTool("get_player", { name: sample.name, gameweek });
  if (!checkCitation("get_player", result)) return;
  const text = textOf(result);
  check("names the player", text.includes(sample.name));
  check("reports projected points", text.includes("Projected points:"));
  check("reports the captain figure", text.includes("If captained:"));
  check("reports the ceiling", text.includes("Ceiling:"));

  const lower = await callTool("get_player",
    { name: sample.name.toLowerCase(), gameweek });
  check("name matching ignores case", !lower.isError);

  const nobody = await callTool("get_player",
    { name: "Zzzznotaplayer", gameweek });
  check("an unknown name is a clear error", nobody.isError === true);
  check("the unknown-name error names what was asked for",
    textOf(nobody).includes("Zzzznotaplayer"));
});

await section("get_duel", async () => {
  const result = await callTool("get_duel", {});
  if (!checkCitation("get_duel", result)) return;
  const text = textOf(result);
  check("reports a running score", /running score \d+-\d+/.test(text));
  check("names both XIs",
    text.includes("Model XI") && text.includes("Consensus XI"));
  check("states who leads", /model leads|crowd leads|level/.test(text));
});

await section("get_accuracy", async () => {
  const ledger = await callTool("get_accuracy", {});
  if (!checkCitation("get_accuracy", ledger)) return;
  const text = textOf(ledger);
  check("lists at least one graded gameweek", /- GW\d+: our MAE/.test(text));
  check("says what MAE means", text.includes("Lower MAE is better"));

  const one = await callTool("get_accuracy", { gameweek: 1 });
  if (checkCitation("get_accuracy(1)", one)) {
    const otext = textOf(one);
    check("gameweek detail reports the player count",
      /\d+ players graded/.test(otext));
    check("gameweek detail reports our MAE",
      otext.includes("Our mean absolute error:"));
    // Spec D5 — GW1 predates the ep_next capture and must say so.
    check("GW1 states that ep_next was not captured",
      otext.includes("not captured"), otext.slice(0, 200));
  }

  const ungraded = await callTool("get_accuracy", { gameweek: 38 });
  check("an ungraded gameweek is a clear error",
    ungraded.isError === true && textOf(ungraded).includes("graded"));
});

await section("get_distribution", async () => {
  const feed = await fetchJson(`/api/fpl/gw${gameweek}/players.json`);
  const sample = feed && feed.players && feed.players[0];
  if (!sample) {
    check("live feed available for the distribution check", false);
    return;
  }
  const result = await callTool("get_distribution",
    { name: sample.name, gameweek });
  const text = textOf(result);
  if (result.isError) {
    // Correct behaviour while distributions are not yet published: say so in
    // plain language, name the player, and point at how to find one that has
    // them. NOT a stack trace and NOT a fabricated shape.
    check("the no-distribution message names the player",
      text.includes(sample.name), text.slice(0, 160));
    check("the no-distribution message explains why",
      text.includes("before evmax started storing"), text.slice(0, 160));
    check("the no-distribution message still gives the mean",
      text.includes("projected points"), text.slice(0, 160));
    check("the no-distribution message suggests a next step",
      text.includes("list_gameweeks"));
  } else {
    checkCitation("get_distribution", result);
    check("reports the floor", text.includes("Floor"));
    check("reports the most likely outcome", text.includes("Most likely"));
    check("reports haul and blank probabilities",
      text.includes("haul") && text.includes("blank"));
  }

  const nobody = await callTool("get_distribution",
    { name: "Zzzznotaplayer", gameweek });
  check("an unknown name is a clear error", nobody.isError === true);
});

await section("helpers", async () => {
  const rows = [{ name: "Ødegaard" }, { name: "B.Fernandes" },
    { name: "João Pedro" }];
  check("matches through accents", matchPlayer(rows, "odegaard") !== null);
  check("matches through punctuation",
    matchPlayer(rows, "b fernandes") !== null);
  check("matches a partial surname", matchPlayer(rows, "Joao") !== null);
  check("no match returns null", matchPlayer(rows, "Zzzz") === null);
  check("suggestions are offered for a near miss",
    suggestNames(rows, "Fernandez").length > 0);
});

await section("error hygiene", async () => {
  const unknown = await callTool("no_such_tool", {});
  check("an unknown tool is an error result, not a throw",
    unknown.isError === true);
  check("the unknown-tool message names the tool",
    textOf(unknown).includes("no_such_tool"));
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) {
  console.log("\nFailures:");
  for (const line of failures) console.log(`  - ${line}`);
  process.exit(1);
}
console.log("Smoke test green.");
