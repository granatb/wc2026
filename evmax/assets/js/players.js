/*
 * evmax /fpl/players/ -- client-side instant player search.
 *
 * Same posture as /js/rate.js (the site's first first-party script): self-
 * hosted from this origin, sets no cookies, uses no localStorage/
 * sessionStorage, loads no external scripts or fonts, and makes exactly one
 * network request: a GET to this gameweek's players feed (same-origin,
 * public, cacheable -- the URL rides in on the form's data-players-url).
 * Nothing the visitor types is ever sent anywhere; matching runs entirely
 * in the browser. No analytics, no tracking, no third-party requests.
 *
 * The page renders and works with JS disabled: the full alphabetical table
 * below the search box is server-rendered, and this script only adds the
 * instant-filter layer on top (hiding the table while a query is active).
 *
 * Name normalization mirrors rate.js normalize() so the two tools never
 * disagree on how "Sánchez" matches "sanchez".
 */
(function () {
  "use strict";

  var form = document.getElementById("player-search-form");
  if (!form) return; // page markup not present (defensive; shouldn't happen)

  var input = document.getElementById("player-search");
  var resultsEl = document.getElementById("player-search-results");
  var table = document.getElementById("player-index-table");
  var playersUrl = form.getAttribute("data-players-url");

  var playersCache = null; // {gameweek, players: [...]}
  var fetchStarted = false;
  var pendingCb = null; // latest waiter while the one fetch is in flight
  var MAX_RESULTS = 30;

  // --- name normalization (mirrors /js/rate.js normalize) ------------------
  function normalize(s) {
    if (!s) return "";
    var decomposed = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    var lower = decomposed.toLowerCase();
    var out = "";
    for (var i = 0; i < lower.length; i++) {
      var ch = lower[i];
      out += /[a-z0-9]/.test(ch) ? ch : " ";
    }
    return out.replace(/\s+/g, " ").trim();
  }

  function fmt1(x) {
    return typeof x === "number" ? x.toFixed(1) : "—";
  }

  function loadPlayers(cb) {
    if (playersCache) { cb(playersCache); return; }
    pendingCb = cb; // only the LATEST query renders once the feed lands
    if (fetchStarted) return; // one request only
    fetchStarted = true;
    fetch(playersUrl, { credentials: "omit" })
      .then(function (r) {
        if (!r.ok) throw new Error("players feed HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        playersCache = data;
        if (pendingCb) { var run = pendingCb; pendingCb = null; run(data); }
      })
      .catch(function () {
        // Feed unreachable: leave the server-rendered table as the tool.
        fetchStarted = false;
        pendingCb = null;
        if (resultsEl) resultsEl.textContent = "";
        if (table) table.style.display = "";
      });
  }

  function render(matches, query) {
    if (!resultsEl) return;
    if (!query) {
      resultsEl.textContent = "";
      if (table) table.style.display = "";
      return;
    }
    if (table) table.style.display = "none";
    if (!matches.length) {
      resultsEl.innerHTML =
        '<p class="pi-hint">No player matches “' +
        escapeHtml(query) + "”.</p>";
      return;
    }
    var rows = matches.slice(0, MAX_RESULTS).map(function (p) {
      var href = p.page || "#";
      return (
        '<tr><td><a href="' + href + '" style="color:var(--greend)">' +
        escapeHtml(p.name) + "</a></td><td>" + escapeHtml(p.team || "") +
        "</td><td>" + escapeHtml(p.position || "") + "</td><td>" +
        fmt1(p.x_points) + "</td></tr>"
      );
    });
    resultsEl.innerHTML =
      '<table class="pd-table"><thead><tr><th>Player</th><th>Team</th>' +
      "<th>Pos</th><th>xPts</th></tr></thead><tbody>" +
      rows.join("") + "</tbody></table>";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
      }[c];
    });
  }

  function search(query) {
    var q = normalize(query);
    if (!q) { pendingCb = null; render([], ""); return; }
    loadPlayers(function (data) {
      var players = data.players || [];
      var matches = players.filter(function (p) {
        var hay = normalize(
          (p.name || "") + " " + (p.team || "") + " " + (p.position || ""));
        return hay.indexOf(q) !== -1;
      });
      matches.sort(function (a, b) {
        return (b.x_points || 0) - (a.x_points || 0);
      });
      render(matches, query);
    });
  }

  input.addEventListener("input", function () { search(input.value); });
  input.addEventListener("focus", function () { loadPlayers(function () {}); });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault(); // no server to submit to -- the search IS the page
    search(input.value);
  });
})();
