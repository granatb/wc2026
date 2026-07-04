/*
 * evmax /rate/ -- client-side team rater.
 *
 * This is the site's FIRST first-party JavaScript. It is self-hosted from
 * this same origin, sets no cookies, uses no localStorage/sessionStorage,
 * loads no external scripts or fonts, and makes exactly one network request:
 * a GET to this round's /api/round/{N}/players.json (same-origin, public,
 * cacheable). Nothing the visitor types is ever sent anywhere -- all matching
 * and simulation-output math below runs entirely in the browser. No
 * analytics, no tracking pixels, no third-party requests of any kind.
 *
 * The page (/rate/) renders and explains itself with JS disabled (see the
 * <noscript> block in evmax/render.py:rate_page) -- this script only adds
 * the interactive layer on top.
 *
 * Ported 1:1 from scripts/rate_team.py (the Reddit rate-my-team CLI) so the
 * browser tool and the CLI never disagree on name matching or output shape:
 *   _norm()          -> normalize()
 *   match()          -> matchPlayer()
 *   flags_for()       -> flagGlyph()
 *   main()'s per-line -> renderResults() / asPlainText()
 */
(function () {
  "use strict";

  var form = document.getElementById("rate-form");
  if (!form) return; // page markup not present (defensive; shouldn't happen)

  var input = document.getElementById("team-input");
  var resultsEl = document.getElementById("rate-results");
  var btn = document.getElementById("rate-btn");
  var round = form.getAttribute("data-round");
  var playersUrl = form.getAttribute("data-players-url");

  var playersCache = null; // {round, generated_at, methodology, players: [...]}
  var MAX_NAMES_WARN = 15;

  // --- name normalization (mirrors scripts/rate_team.py _norm) --------------
  function normalize(s) {
    if (!s) return "";
    // NFD decompose + strip combining marks (diacritics), same approach as
    // Python's unicodedata.normalize("NFD") + category "Mn" filter.
    var decomposed = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    var lower = decomposed.toLowerCase();
    var out = "";
    for (var i = 0; i < lower.length; i++) {
      var ch = lower[i];
      if (/[a-z0-9]/.test(ch)) out += ch;
    }
    return out;
  }

  // --- fetch the round's players feed ---------------------------------------
  function loadPlayers() {
    if (playersCache) return Promise.resolve(playersCache);
    return fetch(playersUrl, { credentials: "omit" })
      .then(function (res) {
        if (!res.ok) throw new Error("players feed returned " + res.status);
        return res.json();
      })
      .then(function (data) {
        playersCache = data;
        return data;
      });
  }

  // --- parse the textarea into cleaned names + captain (mirrors main()) ----
  function parseInput(raw) {
    var names = raw
      .replace(/\n/g, ",")
      .split(",")
      .map(function (t) { return t.trim(); })
      .filter(function (t) { return t.length > 0; });

    var capName = null;
    var cleaned = [];
    for (var i = 0; i < names.length; i++) {
      var n = names[i];
      if (n.toLowerCase().indexOf("(c)") !== -1) {
        n = n.toLowerCase().replace("(c)", "").trim();
        capName = n;
      }
      cleaned.push(n);
    }
    return { names: cleaned, capName: capName };
  }

  // --- match a wanted name against the players list (mirrors match()) ------
  // Order: exact normalized match -> unique substring match (either direction)
  // -> best-x_points among multiple substring matches (with a note listing
  // the runners-up, same as the CLI's "(matched X; also: ...)").
  function matchPlayer(players, wanted) {
    var nw = normalize(wanted);
    if (!nw) return { row: null, note: null };

    var exact = players.filter(function (p) { return normalize(p.name) === nw; });
    if (exact.length) return { row: exact[0], note: null };

    var part = players.filter(function (p) {
      var np = normalize(p.name);
      return np.indexOf(nw) !== -1 || nw.indexOf(np) !== -1;
    });
    if (part.length === 1) return { row: part[0], note: null };
    if (part.length > 1) {
      part.sort(function (a, b) { return (b.x_points || 0) - (a.x_points || 0); });
      var also = part.slice(1, 3).map(function (p) { return p.name; }).join(", ");
      return {
        row: part[0],
        note: "(matched '" + part[0].name + "'; also: " + also + ")",
      };
    }
    return { row: null, note: null };
  }

  // --- flag glyph (mirrors flags_for()) -------------------------------------
  function flagGlyph(row) {
    if (row.flag === "out") return { text: "🚫 OUT", cls: "out" };
    if (row.flag === "doubtful") return { text: "⚠ doubtful", cls: "doubtful" };
    return null;
  }

  function fmt1(n) {
    return (Math.round(n * 10) / 10).toFixed(1);
  }

  // --- core compute: mirrors main()'s matching/scoring loop -----------------
  function computeRating(players, parsed) {
    var lines = []; // {row, isCap, flag, note}
    var missing = [];
    var matchedRows = [];
    var capRow = null;
    var total = 0;

    for (var i = 0; i < parsed.names.length; i++) {
      var n = parsed.names[i];
      var m = matchPlayer(players, n);
      if (!m.row) {
        missing.push(n);
        continue;
      }
      matchedRows.push(m.row);
      var isCap = parsed.capName && normalize(parsed.capName).length > 0 &&
        normalize(m.row.name).indexOf(normalize(parsed.capName)) !== -1;
      if (isCap) capRow = m.row;
      lines.push({
        row: m.row,
        isCap: !!isCap,
        flag: flagGlyph(m.row),
        note: m.note,
      });
      total += m.row.x_points * (isCap ? 2 : 1);
    }

    var bestCap = null;
    for (var j = 0; j < matchedRows.length; j++) {
      var r = matchedRows[j];
      if (bestCap === null || (r.captain_ev || 0) > (bestCap.captain_ev || 0)) {
        bestCap = r;
      }
    }

    return {
      lines: lines,
      missing: missing,
      total: total,
      capRow: capRow,
      bestCap: bestCap,
    };
  }

  // --- render results as HTML (DOM-built, no innerHTML of user text) -------
  function el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.cls) e.className = opts.cls;
    if (opts.text !== undefined) e.textContent = opts.text;
    if (opts.html !== undefined) e.innerHTML = opts.html;
    return e;
  }

  function renderResults(result, roundNo, simsLabel) {
    resultsEl.innerHTML = "";

    var card = el("div", { cls: "rate-card" });

    var lede = el("p", {
      cls: "rate-hint",
      text: "Ran your team through the model (" + simsLabel + ", Round " + roundNo + "):",
    });
    card.appendChild(lede);

    if (result.lines.length === 0) {
      card.appendChild(el("p", { cls: "rate-warn", text: "None of those names matched this round's player pool." }));
    }

    result.lines.forEach(function (line) {
      var row = el("div", { cls: "rate-row" });
      var left = el("span");
      var nameSpan = el("span", { cls: "rn", text: line.row.name });
      left.appendChild(nameSpan);
      if (line.isCap) left.appendChild(el("span", { cls: "rc", text: "(C)" }));
      if (line.flag) left.appendChild(el("span", { cls: "rf " + line.flag.cls, text: " " + line.flag.text }));
      if (line.note) {
        var noteEl = el("span", { cls: "rnote", text: line.note });
        left.appendChild(noteEl);
      }
      row.appendChild(left);
      row.appendChild(el("b", { cls: "rx", text: fmt1(line.row.x_points) + " xPts" }));
      card.appendChild(row);
    });

    var totalRow = el("div", { cls: "rate-total" });
    totalRow.appendChild(el("span", { text: "Projected total (captain doubled)" }));
    totalRow.appendChild(el("b", { text: fmt1(result.total) + " pts" }));
    card.appendChild(totalRow);

    // Captain check
    if (result.capRow && result.bestCap) {
      var capText;
      if (normalize(result.capRow.name) === normalize(result.bestCap.name)) {
        capText = "Captain check: " + result.capRow.name + " ✔ — top captain EV in your squad (" +
          fmt1(result.capRow.captain_ev) + ").";
      } else {
        capText = "Captain check: model prefers " + result.bestCap.name + " (" +
          fmt1(result.bestCap.captain_ev) + " cEV vs " + result.capRow.name + " " +
          fmt1(result.capRow.captain_ev) + ").";
      }
      card.appendChild(el("p", { cls: "rate-capcheck", text: capText }));
    } else if (result.bestCap) {
      card.appendChild(el("p", {
        cls: "rate-capcheck",
        text: "Best captain in your squad by the sims: " + result.bestCap.name +
          " (" + fmt1(result.bestCap.captain_ev) + " cEV).",
      }));
    }

    if (result.missing.length) {
      card.appendChild(el("p", {
        cls: "rate-missing",
        text: "Couldn't match: " + result.missing.join(", "),
      }));
    }

    if (result.lines.length > MAX_NAMES_WARN) {
      var warn = el("p", {
        cls: "rate-warn",
        text: "That's a lot of names for one XI/squad -- rated all of them anyway.",
      });
      card.insertBefore(warn, card.firstChild.nextSibling);
    }

    var copyBtn = el("button", { text: "Copy as text" });
    copyBtn.type = "button";
    copyBtn.id = "rate-copy";
    copyBtn.addEventListener("click", function () {
      var text = asPlainText(result, roundNo, simsLabel);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          copyBtn.textContent = "Copied!";
          setTimeout(function () { copyBtn.textContent = "Copy as text"; }, 1500);
        });
      }
    });
    card.appendChild(copyBtn);

    resultsEl.appendChild(card);
  }

  // --- plain-text render (mirrors main()'s print() output, Reddit-ready) ---
  function asPlainText(result, roundNo, simsLabel) {
    var out = [];
    out.push("Ran your team through my Monte-Carlo model (" + simsLabel +
      " on de-vigged market odds, Round " + roundNo + "):");
    out.push("");
    result.lines.forEach(function (line) {
      var capmark = line.isCap ? " **(C)**" : "";
      var extras = [];
      if (line.flag) extras.push(line.flag.text);
      if (line.note) extras.push(line.note);
      var extraStr = extras.length ? "  " + extras.join(" ") : "";
      out.push("- " + line.row.name + capmark + " — **" + fmt1(line.row.x_points) + " xPts**" + extraStr);
    });
    out.push("");
    out.push("**Projected total: " + fmt1(result.total) + " pts** (captain doubled)");
    if (result.capRow && result.bestCap) {
      if (normalize(result.capRow.name) === normalize(result.bestCap.name)) {
        out.push("");
        out.push("Captain check: **" + result.capRow.name + " ✔** — top captain EV in your squad (" +
          fmt1(result.capRow.captain_ev) + ").");
      } else {
        out.push("");
        out.push("Captain check: model prefers **" + result.bestCap.name + "** (" +
          fmt1(result.bestCap.captain_ev) + " cEV vs " + result.capRow.name + " " +
          fmt1(result.capRow.captain_ev) + ").");
      }
    } else if (result.bestCap) {
      out.push("");
      out.push("Best captain in your squad by my sims: **" + result.bestCap.name + "** (" +
        fmt1(result.bestCap.captain_ev) + " cEV).");
    }
    if (result.missing.length) {
      out.push("");
      out.push("(couldn't match: " + result.missing.join(", ") + ")");
    }
    out.push("");
    out.push("*(my own model — de-vigged odds → Dixon-Coles → Monte-Carlo, scored on official fantasy rules; graded publicly each round)*");
    return out.join("\n");
  }

  function showError(msg) {
    resultsEl.innerHTML = "";
    resultsEl.appendChild(el("p", { cls: "rate-warn", id: "rate-error", text: msg }));
  }

  function runRating() {
    var raw = input.value || "";
    if (!raw.trim()) {
      showError("Paste a squad first — names comma or newline separated.");
      return;
    }
    var parsed = parseInput(raw);
    if (!parsed.names.length) {
      showError("Couldn't find any player names in that input.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Rating…";

    loadPlayers()
      .then(function (data) {
        var players = data.players || [];
        var result = computeRating(players, parsed);
        renderResults(result, data.round || round, "50,000 sims");
      })
      .catch(function (err) {
        showError("Couldn't load this round's projections (" + err.message +
          "). Try again, or read the full data at " + playersUrl + ".");
      })
      .then(function () {
        btn.disabled = false;
        btn.textContent = "Rate my team";
      });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    runRating();
  });

  input.addEventListener("keydown", function (ev) {
    var isEnter = ev.key === "Enter" || ev.keyCode === 13;
    if (isEnter && (ev.metaKey || ev.ctrlKey)) {
      ev.preventDefault();
      runRating();
    }
  });
})();
