// Loads the scores file and draws the tier table. Reads only; it never talks to Riot.
(function () {
  var F = window.Format, S = window.SETTINGS;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function load(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      if (!F.looksLikeScores(data)) throw new Error("not a scores file");
      return data;
    });
  }

  function loadScores() {
    return load(S.DATA_URL).then(
      function (data) { return { data: data, fallback: false }; },
      function () { return load(S.FALLBACK_URL).then(function (data) { return { data: data, fallback: true }; }); }
    );
  }

  function drawHeader(data, fallback) {
    document.getElementById("patch").textContent = "Patch " + data.patch;
    var when = new Date(data.generated);
    var hours = F.ageHours(data.generated, new Date());
    var local = isNaN(when) ? data.generated : when.toLocaleString("en-US", {
      day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
    document.getElementById("updated").textContent = local + " (" + F.describeAge(hours) + ")";
    document.getElementById("average").textContent = F.number(data.diamond_plus_average_win_rate, 2) + "%";
    document.getElementById("count").textContent = data.pick_score_list.length;

    var notice = document.getElementById("notice");
    notice.textContent = "";
    if (fallback) {
      notice.className = "notice warn";
      notice.textContent = "Showing a saved copy that ships with this page, not the live data. The live scores could not be reached.";
    }
    if (F.isStale(data.generated, new Date(), S.STALE_AFTER_HOURS)) {
      var stale = el("p", "notice bad", "These scores are more than " + S.STALE_AFTER_HOURS +
        " hours old. The collector may have stopped; check the Actions page on GitHub.");
      document.getElementById("notices").appendChild(stale);
    }
  }

  function cell(row, text, className) {
    var td = el("td", className, text);
    row.appendChild(td);
    return td;
  }

  var COLSPAN = 10;
  var state = { data: null, list: [], rankOf: {}, key: "pick_score", dir: "desc", open: {} };

  // Mastery as 5 small dots (more filled = better), colored by level; the name is in the tooltip.
  function masteryIcon(c) {
    var level = F.masteryLevel(c.mastery);
    var icon = el("span", "mastery mastery-" + c.mastery);
    icon.title = "Mastery: " + F.masteryText(c.mastery);
    icon.setAttribute("role", "img");
    icon.setAttribute("aria-label", "Mastery: " + F.masteryText(c.mastery));
    for (var i = 1; i <= 5; i++) icon.appendChild(el("i", i <= level ? "on" : ""));
    return icon;
  }

  function detailRow(c) {
    var tr = el("tr", "detail");
    var td = el("td"); td.colSpan = COLSPAN;
    var grid = el("div", "detailgrid");

    var traits = el("div");
    traits.appendChild(el("h3", null, "Traits"));
    var list = F.traitList(c.traits), box = el("div", "traits");
    if (!list.length) box.appendChild(el("span", "sub", "No card details in this file."));
    list.forEach(function (t) {
      var span = el("span", "trait trait-" + t.level);
      span.appendChild(el("b", null, t.name));
      span.appendChild(document.createTextNode(" " + t.levelName));
      box.appendChild(span);
    });
    traits.appendChild(box);
    grid.appendChild(traits);

    var data = el("div");
    data.appendChild(el("h3", null, "Data"));
    if (c.mastery) data.appendChild(el("p", null, "Mastery: " + F.masteryText(c.mastery)));
    var label = F.dataLabel(c);
    if (label) data.appendChild(el("p", null, label));
    data.appendChild(el("p", null, "Sample size: " + F.sampleLabel(c.real_games, S.SAMPLE_SIZE_LIMITS) +
      " (" + F.games(c.real_games) + " games)"));
    if (c.pick_rate !== undefined) data.appendChild(el("p", null, "Pick rate: " + F.number(100 * c.pick_rate, 1) + "%"));
    grid.appendChild(data);

    var otp = el("div");
    otp.appendChild(el("h3", null, "One-tricks (OTP)"));
    otp.appendChild(el("p", null, F.otpText(c)));
    if (c.otp_win_rate !== null && c.otp_win_rate !== undefined) {
      otp.appendChild(el("p", null, "OTP win rate " + F.number(c.otp_win_rate, 1) + "% vs " +
        F.number(c.overall_win_rate_raw, 1) + "% for everyone"));
    }
    grid.appendChild(otp);

    td.appendChild(grid);
    tr.appendChild(td);
    return tr;
  }

  function drawTable() {
    var body = document.getElementById("rows");
    body.textContent = "";
    var rows = F.sortRows(state.list, state.key, state.dir);
    rows.forEach(function (c) {
      var tr = el("tr");
      cell(tr, state.rankOf[c.name], "num rank");

      var nameCell = el("td", "champ");
      var btn = el("button", "champbtn", c.name);
      btn.type = "button";
      btn.setAttribute("aria-expanded", state.open[c.name] ? "true" : "false");
      btn.addEventListener("click", function () {
        state.open[c.name] = !state.open[c.name];
        drawTable();
      });
      nameCell.appendChild(btn);
      tr.appendChild(nameCell);

      var tierCell = el("td", "tiercell");
      tierCell.appendChild(el("span", "tier tier-" + c.tier, F.tierText(c)));
      tr.appendChild(tierCell);

      cell(tr, F.number(c.pick_score, 1), "num score");
      var comfortCell = cell(tr, F.number(c.comfort, 1), "num");
      if (c.mastery) comfortCell.appendChild(masteryIcon(c));
      cell(tr, F.number(c.stats, 1), "num");

      var otpCell = cell(tr, F.number(c.otp_points, 1), "num");
      otpCell.title = F.otpText(c);
      otpCell.appendChild(el("span", "sub", (c.otp_players || 0) + " players, " + F.games(c.otp_games || 0) + " games"));

      var wrCell = cell(tr, F.number(c.win_rate, 2) + "%", "num");
      if (F.hasWinRateWarning(c, S.WIN_RATE_WARNING_DELTA)) {
        var w = el("span", "warnsign", " \u26A0");
        w.title = "Win rate is 1.5 points or more below the Diamond+ average (warning only; the tier doesn't change)";
        wrCell.appendChild(w);
      }
      var delta = c.win_rate_delta;
      cell(tr, F.signed(delta, 2), "num " + (delta > 0.005 ? "up" : delta < -0.005 ? "down" : ""));

      var sample = F.sampleLabel(c.real_games, S.SAMPLE_SIZE_LIMITS);
      var gamesCell = cell(tr, F.games(c.real_games), "num");
      gamesCell.appendChild(el("span", "sub sample-" + sample.split(" ")[0], sample + " sample"));
      body.appendChild(tr);
      if (state.open[c.name]) body.appendChild(detailRow(c));
    });
    markHeaders();
  }

  function markHeaders() {
    Array.prototype.forEach.call(document.querySelectorAll("th[data-sort]"), function (th) {
      var on = th.getAttribute("data-sort") === state.key;
      if (on) th.setAttribute("aria-sort", state.dir === "asc" ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  }

  function wireHeaders() {
    Array.prototype.forEach.call(document.querySelectorAll("th[data-sort]"), function (th) {
      th.tabIndex = 0;
      function go() {
        var key = th.getAttribute("data-sort");
        if (state.key === key) state.dir = state.dir === "asc" ? "desc" : "asc";
        else { state.key = key; state.dir = F.firstDirection(key); }
        drawTable();
      }
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  }

  function drawNotRanked(data) {
    var items = data.cards_not_ranked || [];
    var section = document.getElementById("notranked");
    var list = document.getElementById("notranked-list");
    list.textContent = "";
    items.forEach(function (entry) { list.appendChild(el("li", null, F.notRankedText(entry))); });
    section.hidden = items.length === 0;
  }

  // The page always opens sorted by Pick Score (so by tier); the sort is not remembered.
  function start(data) {
    state.data = data;
    state.list = data.pick_score_list;
    state.rankOf = {};
    F.ranked(data.pick_score_list).forEach(function (c, i) { state.rankOf[c.name] = i + 1; });
    wireHeaders();
    drawTable();
    drawNotRanked(data);
  }

  loadScores().then(function (result) {
    drawHeader(result.data, result.fallback);
    start(result.data);
    document.getElementById("loading").hidden = true;
    document.getElementById("content").hidden = false;
  }, function () {
    var loading = document.getElementById("loading");
    loading.textContent = "The scores could not be loaded. Try again in a few minutes.";
    loading.className = "notice bad";
  });
})();
