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
 * Rates the full 15, not just the XI: tag a name with (B) to mark it as
 * bench. Bench players get an xPts line but are excluded from the projected
 * total (XI + doubled captain only) and instead get a "sub chain" note when
 * a same-position XI starter kicks off earlier -- FIFA's automatic subs are
 * DNP-only and only fire at round end, but manual subs are allowed up to the
 * round's last kickoff, so managers routinely start the earlier fixture and
 * hold a stronger later-kickoff player in reserve. A strong, unflagged bench
 * player is very often intentional, not a mistake -- check the chain note
 * before calling it wasted.
 *
 * Ported 1:1 from scripts/rate_team.py (the Reddit rate-my-team CLI) so the
 * browser tool and the CLI never disagree on name matching or output shape:
 *   _norm()          -> normalize()
 *   match()          -> matchPlayer()
 *   flags_for()       -> flagGlyph()
 *   chain_note()      -> chainNote()
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
  var datalist = document.getElementById("players-dl");

  var playersCache = null; // {round, generated_at, methodology, players: [...]}
  var MAX_NAMES_WARN = 15;

  // Fill the slot-picker's shared datalist as soon as the feed loads, best
  // projection first, so the browser's autocomplete surfaces the strongest
  // players at the top of every slot's suggestions.
  function fillDatalist(players) {
    if (!datalist || datalist.children.length) return;
    players
      .slice()
      .sort(function (a, b) { return (b.x_points || 0) - (a.x_points || 0); })
      .forEach(function (p) {
        var opt = document.createElement("option");
        opt.value = p.name;
        opt.label = p.team + " · " + p.position + " · " + fmt1(p.x_points) + " xPts";
        datalist.appendChild(opt);
      });
  }

  // Slot picker -> the same "name (c) / name (b)" text the paste box takes,
  // so both input modes share one parse + compute path.
  function slotsAsText() {
    var rows = Array.prototype.slice.call(form.querySelectorAll(".slot"));
    var capIdx = -1;
    var capRadio = form.querySelector('input[name="cap"]:checked');
    if (capRadio) capIdx = parseInt(capRadio.value, 10);
    var xiSeen = -1;
    var parts = [];
    rows.forEach(function (inp) {
      var name = (inp.value || "").trim();
      var isBench = inp.getAttribute("data-bench") === "1";
      if (!isBench) xiSeen += 1;
      if (!name) return;
      if (isBench) {
        parts.push(name + " (b)");
      } else {
        parts.push(xiSeen === capIdx ? name + " (c)" : name);
      }
    });
    return parts.join(", ");
  }

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

  // --- parse the textarea into cleaned names + captain + bench flags -------
  // (mirrors main()'s (C)/(B) tag parsing)
  function parseInput(raw) {
    var names = raw
      .replace(/\n/g, ",")
      .split(",")
      .map(function (t) { return t.trim(); })
      .filter(function (t) { return t.length > 0; });

    var capName = null;
    var cleaned = [];
    var benchFlags = [];
    for (var i = 0; i < names.length; i++) {
      var n = names[i];
      var isBench = n.toLowerCase().indexOf("(b)") !== -1;
      if (isBench) {
        n = n.toLowerCase().replace("(b)", "").trim();
      }
      if (n.toLowerCase().indexOf("(c)") !== -1) {
        n = n.toLowerCase().replace("(c)", "").trim();
        capName = n;
      }
      cleaned.push(n);
      benchFlags.push(isBench);
    }
    return { names: cleaned, capName: capName, benchFlags: benchFlags };
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

  // --- sub-chain note (mirrors chain_note()) --------------------------------
  // A bench player is a deliberate "chain" option, not a wasted slot, if some
  // XI starter of the same position kicks off earlier -- manual subs are
  // allowed up to the round's last kickoff, so the manager can watch that
  // match then swap the bench player in before his own kicks off.
  function chainNote(benchRow, xiRows) {
    if (!benchRow.kickoff) return "";
    var benchKo = new Date(benchRow.kickoff).getTime();
    var earlier = xiRows.filter(function (r) {
      return r.position === benchRow.position && r.kickoff &&
        new Date(r.kickoff).getTime() < benchKo;
    });
    if (!earlier.length) return "";
    var lastKo = Math.max.apply(null, earlier.map(function (r) { return new Date(r.kickoff).getTime(); }));
    var gapH = Math.round((benchKo - lastKo) / 3600000);
    var names = earlier.map(function (r) { return r.name; }).join(", ");
    return "(chain option for " + names + " -- kicks off first, ~" + gapH + "h to react)";
  }

  // --- armband chain (mirrors captain_chain()) -------------------------------
  // The captaincy can be moved mid-round like manual subs: captain an early
  // kickoff, keep the double on a haul, otherwise roll the band to a later
  // player before he kicks off. Chain = best-cEV player per kickoff slot among
  // those playing before the best static captain (the anchor) whose ceiling
  // beats the anchor's single xPts; ends at the anchor.
  function captainChain(xiRows) {
    var scored = xiRows.filter(function (r) { return r.kickoff; });
    if (!scored.length) return [];
    var anchor = scored[0];
    scored.forEach(function (r) {
      if ((r.captain_ev || 0) > (anchor.captain_ev || 0)) anchor = r;
    });
    var anchorKo = new Date(anchor.kickoff).getTime();
    var bestAt = {};
    scored.forEach(function (r) {
      var ko = new Date(r.kickoff).getTime();
      if (ko >= anchorKo || (r.ceiling || 0) <= anchor.x_points) return;
      if (!bestAt[ko] || (r.captain_ev || 0) > (bestAt[ko].captain_ev || 0)) bestAt[ko] = r;
    });
    var links = Object.keys(bestAt).map(function (k) { return bestAt[k]; });
    if (!links.length) return [];
    links.sort(function (a, b) { return new Date(a.kickoff) - new Date(b.kickoff); });
    links.push(anchor);
    return links;
  }

  function chainAdviceText(chain) {
    var hops = chain.map(function (r) { return r.name; }).join(" → ");
    var thrs = [];
    for (var i = 0; i < chain.length - 1; i++) {
      var rest = chain.slice(i + 1).map(function (r) { return r.x_points || 0; });
      thrs.push(Math.round(Math.max.apply(null, rest)));
    }
    var allSame = thrs.every(function (t) { return t === thrs[0]; });
    var rule;
    if (allSame) {
      rule = "keep the band wherever it lands on a " + thrs[0] + "+ score, otherwise roll it forward";
    } else {
      rule = thrs.map(function (t, i) {
        return "roll off " + chain[i].name + " if he scores under ~" + t;
      }).join(", ");
    }
    return "Armband chain (captain can be moved mid-round): " + hops + " — " + rule + ".";
  }

  // --- core compute: mirrors main()'s matching/scoring loop -----------------
  function computeRating(players, parsed) {
    var xiLines = [], benchLines = []; // {row, isCap, flag, note}
    var missing = [];
    var xiRows = [];
    var capRow = null;
    var total = 0;

    for (var i = 0; i < parsed.names.length; i++) {
      var n = parsed.names[i];
      var isBench = parsed.benchFlags[i];
      var m = matchPlayer(players, n);
      if (!m.row) {
        missing.push(n);
        continue;
      }
      var isCap = !isBench && parsed.capName && normalize(parsed.capName).length > 0 &&
        normalize(m.row.name).indexOf(normalize(parsed.capName)) !== -1;
      if (isCap) capRow = m.row;
      var line = {
        row: m.row,
        isCap: !!isCap,
        flag: flagGlyph(m.row),
        note: m.note,
        bench: isBench,
      };
      if (isBench) {
        benchLines.push(line);
      } else {
        xiRows.push(m.row);
        xiLines.push(line);
        total += m.row.x_points * (isCap ? 2 : 1);
      }
    }

    benchLines.forEach(function (line) {
      var cn = chainNote(line.row, xiRows);
      if (cn) line.note = line.note ? line.note + " " + cn : cn;
    });

    var bestCap = null;
    for (var j = 0; j < xiRows.length; j++) {
      var r = xiRows[j];
      if (bestCap === null || (r.captain_ev || 0) > (bestCap.captain_ev || 0)) {
        bestCap = r;
      }
    }

    return {
      xiLines: xiLines,
      benchLines: benchLines,
      lines: xiLines.concat(benchLines),
      missing: missing,
      total: total,
      capRow: capRow,
      bestCap: bestCap,
      chain: captainChain(xiRows),
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

    function appendLine(line) {
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
    }

    if (result.xiLines.length) {
      card.appendChild(el("p", { cls: "rate-section", text: "Starting XI" }));
      result.xiLines.forEach(appendLine);
    }

    var totalRow = el("div", { cls: "rate-total" });
    totalRow.appendChild(el("span", { text: "Projected total (XI only, captain doubled)" }));
    totalRow.appendChild(el("b", { text: fmt1(result.total) + " pts" }));
    card.appendChild(totalRow);

    if (result.benchLines.length) {
      card.appendChild(el("p", { cls: "rate-section", text: "Bench" }));
      result.benchLines.forEach(appendLine);
    }

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

    if (result.chain && result.chain.length > 1) {
      card.appendChild(el("p", { cls: "rate-capcheck", text: chainAdviceText(result.chain) }));
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

    function pushLine(line) {
      var capmark = line.isCap ? " **(C)**" : "";
      var extras = [];
      if (line.flag) extras.push(line.flag.text);
      if (line.note) extras.push(line.note);
      var extraStr = extras.length ? "  " + extras.join(" ") : "";
      out.push("- " + line.row.name + capmark + " — **" + fmt1(line.row.x_points) + " xPts**" + extraStr);
    }

    if (result.xiLines.length) {
      out.push("Starting XI:");
      result.xiLines.forEach(pushLine);
      out.push("");
    }
    out.push("**Projected total: " + fmt1(result.total) + " pts** (XI only, captain doubled)");
    if (result.benchLines.length) {
      out.push("");
      out.push("Bench:");
      result.benchLines.forEach(pushLine);
    }
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
    if (result.chain && result.chain.length > 1) {
      out.push("");
      out.push(chainAdviceText(result.chain));
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
    // slot picker wins when it has anything in it; the paste box is the fallback
    var raw = slotsAsText() || (input ? input.value : "") || "";
    if (!raw.trim()) {
      showError("Pick your players above (or paste the squad as text) first.");
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

  form.addEventListener("keydown", function (ev) {
    var isEnter = ev.key === "Enter" || ev.keyCode === 13;
    if (!isEnter) return;
    if (ev.metaKey || ev.ctrlKey) {
      ev.preventDefault();
      runRating();
    } else if (ev.target && ev.target.classList && ev.target.classList.contains("slot")) {
      // plain Enter in a slot input shouldn't submit a half-filled squad --
      // move focus to the next slot instead
      ev.preventDefault();
      var slots = Array.prototype.slice.call(form.querySelectorAll(".slot"));
      var next = slots[slots.indexOf(ev.target) + 1];
      if (next) next.focus();
    }
  });

  // warm the feed + fill the autocomplete immediately (one same-origin GET)
  loadPlayers().then(function (data) {
    fillDatalist(data.players || []);
  }).catch(function () { /* rated on submit instead; errors surface there */ });
})();
