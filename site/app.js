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

  function drawTable(data) {
    var body = document.getElementById("rows");
    body.textContent = "";
    F.ranked(data.pick_score_list).forEach(function (c, i) {
      var tr = el("tr");
      cell(tr, i + 1, "num rank");
      cell(tr, c.name, "champ");
      var tierCell = el("td", "tiercell");
      var badge = el("span", "tier tier-" + c.tier, F.tierText(c));
      if (c.tier_capped_by_floor) badge.title = "Held down to B by the stats floor (win rate far below average)";
      tierCell.appendChild(badge);
      tr.appendChild(tierCell);
      cell(tr, F.number(c.pick_score, 1), "num score");
      cell(tr, F.number(c.comfort, 1), "num");
      cell(tr, F.number(c.stats, 1), "num");
      cell(tr, F.number(c.otp_points, 1), "num");
      cell(tr, F.number(c.win_rate, 2) + "%", "num");
      var delta = c.win_rate_delta;
      cell(tr, F.signed(delta, 2), "num " + (delta > 0.005 ? "up" : delta < -0.005 ? "down" : ""));
      cell(tr, F.games(c.real_games), "num");
      body.appendChild(tr);
    });
  }

  loadScores().then(function (result) {
    drawHeader(result.data, result.fallback);
    drawTable(result.data);
    document.getElementById("loading").hidden = true;
    document.getElementById("content").hidden = false;
  }, function () {
    var loading = document.getElementById("loading");
    loading.textContent = "The scores could not be loaded. Try again in a few minutes.";
    loading.className = "notice bad";
  });
})();
