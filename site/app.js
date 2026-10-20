// Loads the scores file and draws the tier table. Reads only; it never talks to Riot.
(function () {
  var F = window.Format, S = window.SETTINGS, H = window.HELP;

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

  function versionNumber(text) {
    var m = /^v?(\d+)\.(\d+)$/.exec(String(text || ""));
    return m ? Number(m[1]) * 1000 + Number(m[2]) : 0;
  }

  // The live scores file is used. Only when it is from an older model version than this page needs, and the
  // saved copy that ships with the page is newer, the saved copy is shown (with a notice) until the next collector run.
  // Opening the page as index.html?saved forces the saved copy (handy for checking).
  function loadScores() {
    var saved = function () { return load(S.FALLBACK_URL); };
    if (/[?&]saved\b/.test(location.search)) return saved().then(function (data) { return { data: data, fallback: true, forced: true }; });
    return load(S.DATA_URL).then(function (live) {
      if (versionNumber(live.model_version) >= versionNumber(S.MIN_MODEL_VERSION)) return { data: live, fallback: false };
      return saved().then(function (copy) {
        if (versionNumber(copy.model_version) > versionNumber(live.model_version)) return { data: copy, fallback: true, older: true };
        return { data: live, fallback: false };
      }, function () { return { data: live, fallback: false }; });
    }, function () {
      return saved().then(function (data) { return { data: data, fallback: true }; });
    });
  }

  // The champion cards (type, traits, mastery...) are read straight from the cards file, never from the collector.
  function loadCards() {
    return fetch(S.CARDS_URL, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (file) { return Array.isArray(file.cards) ? file.cards : []; }, function () { return []; });
  }

  // The one setting for the mastery review reminder; if it can't be read the line says "unknown".
  function loadReview() {
    return fetch(S.REVIEW_URL, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (file) { return file.last_mastery_review_patch; }, function () { return null; });
  }

  function drawHeader(data, fallback, how) {
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
      notice.textContent = how.forced
        ? "Showing the saved copy that ships with this page, because you asked for it (?saved), not the live data."
        : how.older
          ? "The live scores file is from an older model version, so this page shows its newer saved copy until the next collector run."
          : "Showing a saved copy that ships with this page, not the live data. The live scores could not be reached.";
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
  var state = { data: null, byId: {}, open: {} };

  // ---- instant hover help: any element with data-tip shows its text at once (no browser delay) ----
  var tip = document.getElementById("tip");
  function showTip(target) {
    var text = target.getAttribute("data-tip");
    if (!text) return;
    tip.textContent = text;
    tip.hidden = false;
    var box = target.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.max(8, Math.min(box.left + box.width / 2 - w / 2, window.innerWidth - w - 8));
    var top = box.bottom + 8;
    if (top + h > window.innerHeight - 8) top = Math.max(8, box.top - h - 8);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() { tip.hidden = true; }
  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (t) showTip(t); else hideTip();
  });
  document.addEventListener("focusin", function (e) {
    var t = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (t) showTip(t); else hideTip();
  });
  document.addEventListener("focusout", hideTip);
  document.addEventListener("scroll", hideTip, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") hideTip(); });

  // Hover help for the tab buttons and headings that name a text in help.js.
  function wireTips() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-tip-key]"), function (node) {
      var text = H[node.getAttribute("data-tip-key")];
      if (text) node.setAttribute("data-tip", text);
    });
  }

  // A table whose column titles sort it. `columns` says how each column sorts (see format.js);
  // `drawRows(item, body)` adds the rows for one item. Each table remembers nothing between visits.
  function sortableTable(id, columns, firstKey, tie, drawRows) {
    var table = document.getElementById(id);
    var self = { list: [], key: firstKey, dir: F.firstDirection(firstKey, columns) };
    var heads = Array.prototype.slice.call(table.querySelectorAll("th[data-sort]"));

    self.draw = function () {
      var body = table.tBodies[0];
      body.textContent = "";
      F.sortRows(self.list, self.key, self.dir, columns, tie).forEach(function (item) { drawRows(item, body); });
      heads.forEach(function (th) {
        if (th.getAttribute("data-sort") === self.key) th.setAttribute("aria-sort", self.dir === "asc" ? "ascending" : "descending");
        else th.removeAttribute("aria-sort");
      });
    };

    heads.forEach(function (th) {
      var key = th.getAttribute("data-sort");
      th.tabIndex = 0;
      if (H[key]) th.setAttribute("data-tip", H[key]);
      function go() {
        if (self.key === key) self.dir = self.dir === "asc" ? "desc" : "asc";
        else { self.key = key; self.dir = F.firstDirection(key, columns); }
        self.draw();
      }
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    return self;
  }

  // "Data: 96% this patch": easy to spot, with the rule in a hover bubble.
  function dataChip(c) {
    var label = F.dataLabel(c);
    if (!label) return null;
    var chip = el("span", "chip", label);
    chip.setAttribute("data-tip", H.data_label);
    return chip;
  }

  // A number in a colored box: green above the average, red below, stronger the further away (tier steps).
  function colorBox(text, value, stats) {
    var box = el("span", F.stepClass(F.spreadStep(value, stats.mean, stats.spread, S.SPREAD_STEPS)), text);
    return box;
  }

  function tierBadge(tier) {
    return el("span", "tier tier-" + tier, tier);
  }

  function winRateCell(tr, c) {
    var wrCell = cell(tr, F.number(c.win_rate, 2) + "%", "num");
    if (F.hasWinRateWarning(c, S.WIN_RATE_WARNING_DELTA)) {
      var w = el("span", "warnsign", " \u26A0");
      w.setAttribute("data-tip", "Win rate is 1.5 points or more below the Diamond+ average (warning only; the tier doesn't change)");
      wrCell.appendChild(w);
    }
    return wrCell;
  }

  function deltaCell(tr, c) {
    var delta = c.win_rate_delta;
    cell(tr, F.signed(delta, 2), "num " + (delta > 0.005 ? "up" : delta < -0.005 ? "down" : ""));
  }

  // Mastery as 5 small dots (more filled = better), colored by level; the name is in the tooltip.
  function masteryIcon(c) {
    var level = F.masteryLevel(c.mastery);
    var icon = el("span", "mastery mastery-" + c.mastery);
    icon.setAttribute("data-tip", "Mastery: " + F.masteryText(c.mastery));
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
    var shown = F.otpWinRateText(c, S.OTP_MIN_GAMES_SHOWN);
    otp.appendChild(el("p", null, shown === "too few games" ? "OTP win rate: too few games" :
      "OTP win rate " + shown + " vs " + F.number(c.overall_win_rate_raw, 1) + "% for everyone"));
    grid.appendChild(otp);

    td.appendChild(grid);
    tr.appendChild(td);
    return tr;
  }

  // ---- Tier list tab (unchanged) ----
  function tierRows(c, body) {
    var tr = el("tr");
    cell(tr, state.rankOf[c.name], "num rank");

    var nameCell = el("td", "champ");
    var btn = el("button", "champbtn", c.name);
    btn.type = "button";
    btn.setAttribute("aria-expanded", state.open[c.name] ? "true" : "false");
    btn.addEventListener("click", function () {
      state.open[c.name] = !state.open[c.name];
      tables.tier.draw();
    });
    var reach = F.bestReachText(c);
    if (reach) btn.setAttribute("data-tip", reach);
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
    otpCell.setAttribute("data-tip", F.otpText(c));
    otpCell.appendChild(el("span", "sub", (c.otp_players || 0) + " players, " + F.games(c.otp_games || 0) + " bot-lane games"));

    winRateCell(tr, c);
    deltaCell(tr, c);

    var sample = F.sampleLabel(c.real_games, S.SAMPLE_SIZE_LIMITS);
    var gamesCell = cell(tr, F.games(c.real_games), "num");
    gamesCell.appendChild(el("span", "sub sample-" + sample.split(" ")[0], sample + " sample"));
    var chip = dataChip(c);
    if (chip) gamesCell.appendChild(chip);
    body.appendChild(tr);
    if (state.open[c.name]) body.appendChild(detailRow(c));
  }

  // ---- Meta tab ----
  function nameWithLabel(tr, c) {
    var td = el("td", "champ", c.name);
    if (c.has_card === false) td.appendChild(el("span", "nocard", "no card yet"));
    tr.appendChild(td);
  }

  function metaRows(c, body) {
    var tr = el("tr");
    cell(tr, state.metaRankOf[c.name], "num rank");
    nameWithLabel(tr, c);
    var metaCell = cell(tr, "", "num");
    metaCell.appendChild(colorBox(F.number(c.meta_score, 1), c.meta_score, state.metaStats));
    cell(tr, F.number(c.win_rate_points, 1), "num");
    cell(tr, F.number(c.pick_rate_points, 1), "num");
    winRateCell(tr, c);
    deltaCell(tr, c);
    cell(tr, F.number(100 * c.pick_rate, 1) + "%", "num");
    var sample = F.sampleLabel(c.real_games, S.SAMPLE_SIZE_LIMITS);
    var gamesCell = cell(tr, F.games(c.real_games), "num");
    gamesCell.appendChild(el("span", "sub sample-" + sample.split(" ")[0], sample + " sample"));
    var chip = dataChip(c);
    if (chip) gamesCell.appendChild(chip);
    body.appendChild(tr);
  }

  function needsRows(c, body) {
    var tr = el("tr");
    cell(tr, state.metaRankOf[c.name], "num rank");
    cell(tr, c.name, "champ");
    var needCell = cell(tr, "", "num");
    needCell.appendChild(colorBox(F.number(c.meta_score, 1), c.meta_score, state.metaStats));
    winRateCell(tr, c);
    cell(tr, F.number(100 * c.pick_rate, 1) + "%", "num");
    cell(tr, F.games(c.real_games), "num");
    body.appendChild(tr);
  }

  // ---- Comfort tab ----
  function comfortRows(c, body) {
    var p = c.comfort_parts, tr = el("tr");
    cell(tr, c.name, "champ");
    var comfortCell = cell(tr, "", "num");
    comfortCell.appendChild(colorBox(F.number(c.comfort, 1), c.comfort, state.comfortStats));

    var traitCell = el("td", "traitcell");
    traitCell.appendChild(el("b", "traitscore", F.number(p.trait_score, 1)));
    var box = el("span", "traits compact");
    F.traitList(c.traits).forEach(function (t) {
      var span = el("span", "trait trait-" + t.level);
      span.appendChild(el("b", null, t.name));
      span.appendChild(document.createTextNode(" " + t.levelName));
      box.appendChild(span);
    });
    traitCell.appendChild(box);
    tr.appendChild(traitCell);

    var masteryCell = cell(tr, "");
    if (c.mastery) masteryCell.appendChild(masteryIcon(c));

    var D = "detail-col";
    cell(tr, F.mainTypeText(c) || "\u2013", D);
    cell(tr, F.secondaryTypeText(c) || "\u2013", D);
    cell(tr, F.number(p.type_points, 1), "num " + D);
    cell(tr, F.masteryPointsText(c), D + " num");
    cell(tr, F.number(p.base, 1), "num " + D);
    cell(tr, F.signed(p.kit_adjustment, 2), "num " + D);
    cell(tr, F.difficultyText(c), "num " + D);
    cell(tr, F.signed(p.difficulty_adjustment, 2), "num " + D);
    cell(tr, F.signed(p.range_adjustment, 2), "num " + D);
    cell(tr, F.flexText(c), "num " + D);
    body.appendChild(tr);
  }

  // ---- Growth tab: the Utopy table ----
  var UTOPY_LEVELS = ["never_played", "below_average", "average", "good", "main"];

  // The small line under a champion's name: sample size (Low / Medium / High) and the data-freshness chip,
  // the same words and look as on the Tier list.
  function utopyMeta(c) {
    var line = el("span", "sub utopy-meta");
    var sample = F.sampleLabel(c.real_games, S.SAMPLE_SIZE_LIMITS);
    line.appendChild(el("span", "sample-" + sample.split(" ")[0], sample + " sample"));
    var chip = dataChip(c);
    if (chip) { line.appendChild(document.createTextNode(" ")); line.appendChild(chip); }
    return line;
  }

  function utopyRows(t, body) {
    var tr = el("tr");
    if (t.unranked) {
      tr.className = "utopy-grey";
      var name = cell(tr, t.name, "champ u-champ");
      var sample = F.sampleLabel(t.real_games, S.SAMPLE_SIZE_LIMITS);
      name.appendChild(el("span", "sub", sample + " sample \u00b7 " + F.utopyReason(t.failed) + " \u00b7 " + F.utopyUnrankedNumbers(t)));
      var span = cell(tr, "no score this patch");
      span.colSpan = UTOPY_LEVELS.length + 1;
      body.appendChild(tr);
      return;
    }
    var ranked = state.byId[t.id] || {};
    var nameCell = cell(tr, t.name, "champ u-champ");
    nameCell.appendChild(utopyMeta(ranked));
    var here = UTOPY_LEVELS.indexOf(t.current_mastery);
    UTOPY_LEVELS.forEach(function (level, i) {
      var td = el("td", "num utopy-cell");
      var s = t.scores[level];
      var pill = el("span", "tier tier-" + s.tier + (level === t.current_mastery ? " utopy-now" : ""), F.number(s.score, 1));
      if (level === t.current_mastery) pill.setAttribute("data-tip", "Your mastery now");
      td.appendChild(pill);
      // Only levels above yours count: a score that would beat your current #3 pick.
      if (i > here && state.third && s.score > state.third.score) {
        var up = el("span", "utopy-up", "\u2191");
        up.setAttribute("data-tip", "Would beat your current #3 pick (" + state.third.name + ", " + F.number(state.third.score, 1) + ")");
        td.appendChild(up);
      }
      tr.appendChild(td);
    });
    var skill = el("td", "skill u-skill");
    var parts = F.skillParts(ranked, S.OTP_MIN_GAMES_SHOWN);
    if (parts) {
      skill.appendChild(el("b", parts.delta > 0 ? "skill-pos" : parts.delta < 0 ? "skill-neg" : "", parts.percent));
      skill.appendChild(el("span", "skill-rest", " \u00b7 " + parts.rest));
    } else {
      skill.appendChild(el("span", "skill-rest", "too few games"));
    }
    tr.appendChild(skill);
    body.appendChild(tr);
  }

  // ---- tabs ----
  var tables = {};
  function selectTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll("[role=tab]"), function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-tab") === name ? "true" : "false");
    });
    Array.prototype.forEach.call(document.querySelectorAll(".tabpanel"), function (p) {
      p.hidden = p.id !== "tab-" + name;
    });
    hideTip();
  }

  function wireTabs() {
    var buttons = Array.prototype.slice.call(document.querySelectorAll("[role=tab]"));
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () { selectTab(b.getAttribute("data-tab")); });
      b.addEventListener("keydown", function (e) {
        var to = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : -1;
        if (to < 0) return;
        var next = buttons[(to + buttons.length) % buttons.length];
        next.focus();
        selectTab(next.getAttribute("data-tab"));
      });
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

  function rankMap(list, key) {
    var map = {};
    list.slice().sort(function (a, b) { return b[key] - a[key]; }).forEach(function (c, i) { map[c.name] = i + 1; });
    return map;
  }

  // The page always opens on the Tier list, sorted by Pick Score (so by tier); sorts are not remembered.
  function start(data, cards, reviewPatch) {
    state.data = data;
    var picks = data.pick_score_list;
    var metaList = data.meta_score_list || picks;
    F.applyCards(picks, cards);
    F.applyCards(metaList, cards);
    document.getElementById("patchmix").textContent = F.patchMixText(data.patch, F.patchMix(metaList));
    state.metaStats = F.meanAndSpread(metaList.map(function (c) { return c.meta_score; }));
    state.comfortStats = F.meanAndSpread(picks.map(function (c) { return c.comfort; }));
    state.rankOf = {};
    F.ranked(picks).forEach(function (c, i) { state.rankOf[c.name] = i + 1; });
    state.metaRankOf = rankMap(metaList, "meta_score");
    state.comfortRankOf = rankMap(picks, "comfort");
    picks.forEach(function (c) { state.byId[c.id] = c; });

    var review = F.masteryReview(reviewPatch, data.patch);
    var reviewLine = document.getElementById("mastery-review");
    reviewLine.textContent = review.text;
    reviewLine.className = "notice " + review.level;

    wireTips();
    wireTabs();

    tables.tier = sortableTable("tier-table", F.SORT_COLUMNS, "pick_score", null, tierRows);
    tables.tier.list = picks;
    tables.tier.draw();

    tables.meta = sortableTable("meta-table", F.META_COLUMNS, "meta_score", function (c) { return c.meta_score; }, metaRows);
    tables.meta.list = metaList;
    tables.meta.draw();

    var needs = F.needsCard(metaList);
    tables.needs = sortableTable("needs-table", F.META_COLUMNS, "meta_score", function (c) { return c.meta_score; }, needsRows);
    tables.needs.list = needs;
    tables.needs.draw();
    document.getElementById("needs-wrap").hidden = needs.length === 0;
    document.getElementById("needs-empty").hidden = needs.length !== 0;

    tables.comfort = sortableTable("comfort-table", F.COMFORT_COLUMNS, "c_comfort", function (c) { return c.pick_score; }, comfortRows);
    tables.comfort.list = picks.filter(function (c) { return c.comfort_parts; });
    tables.comfort.draw();

    // Your current #3 pick: a score above it earns the small up arrow in the Utopy table.
    var byScore = picks.slice().sort(function (a, b) { return b.pick_score - a.pick_score; });
    state.third = byScore.length >= 3 ? { score: byScore[2].pick_score, name: byScore[2].name } : null;
    var hasUtopy = Array.isArray(data.utopy_table);
    var utopy = (data.utopy_table || []).map(function (t) {
      var copy = {};
      Object.keys(t).forEach(function (k) { copy[k] = t[k]; });
      var ranked = state.byId[t.id];
      if (ranked && ranked.mastery) copy.current_mastery = ranked.mastery;      // your card now, even before the next collector run
      copy.skill_delta = F.skillDelta(ranked, S.OTP_MIN_GAMES_SHOWN);
      return copy;
    });
    // Carded champions that are not ranked this patch: grey rows at the bottom, no score.
    (hasUtopy ? (data.cards_not_ranked || []) : []).forEach(function (c) {
      var copy = {};
      Object.keys(c).forEach(function (k) { copy[k] = c[k]; });
      copy.unranked = true;
      utopy.push(copy);
    });
    tables.utopy = sortableTable("utopy-table", F.UTOPY_COLUMNS, "u_main", function (t) { return t.unranked ? -1 : t.scores.main.score; }, utopyRows);
    tables.utopy.list = utopy;
    tables.utopy.draw();
    document.getElementById("utopy-wrap").hidden = !hasUtopy;
    document.getElementById("utopy-old").hidden = hasUtopy;
    document.getElementById("utopy-basis").textContent = "Based on patch " + data.patch + " data; can change each patch.";

    drawNotRanked(data);
  }

  Promise.all([loadScores(), loadCards(), loadReview()]).then(function (both) {
    var result = both[0];
    drawHeader(result.data, result.fallback, result);
    start(result.data, both[1], both[2]);
    document.getElementById("loading").hidden = true;
    document.getElementById("content").hidden = false;
  }, function () {
    var loading = document.getElementById("loading");
    loading.textContent = "The scores could not be loaded. Try again in a few minutes.";
    loading.className = "notice bad";
  });
})();
