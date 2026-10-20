// Hidden admin page (v1.5): login, one table of all cards, several edits, one "Save all" (one commit, one rescore),
// the Comfort preview, and the "Mastery review done" button. The login is a 30-day cookie set by the helper; the
// password is typed once on the login screen and never stored in the page.
(function () {
  var P = window.ComfortPreview;
  var HEADERS = { "Content-Type": "application/json", "X-Admin-Request": "1" };
  var MASTERY = [["main", "Main"], ["good", "Good"], ["average", "Average"], ["below_average", "Below average"], ["never_played", "Never played"]];
  var TRAITS = [["wave_clear", "Wave clear"], ["team_utility", "Team utility"], ["aoe", "AoE"], ["cc", "CC"],
                ["sustain", "Sustain"], ["burst", "Burst"], ["poke", "Poke"], ["vision", "Vision"]];
  var LEVELS = [["none", "None"], ["low", "Low"], ["mid", "Mid"], ["high", "High"]];
  var LEVEL_NAME = { low: "Low", mid: "Mid", high: "High" };
  var MASTERY_NAME = {}; MASTERY.forEach(function (m) { MASTERY_NAME[m[0]] = m[1]; });
  var TRAIT_NAME = {}; TRAITS.forEach(function (t) { TRAIT_NAME[t[0]] = t[1]; });

  var cards = [];            // the newest cards from GitHub (kept up to date after each save)
  var rankedNames = [];      // riot names of the ranked champions that have a card (for the trait average)
  var pending = {};          // "Jinx|mastery" -> {champion, field, from, value}
  var rows = {};             // champion -> {main, detail, mastery: select, traits: {key: select}, badges, comfort}

  function $(id) { return document.getElementById(id); }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  var fmt = function (n, digits) { return Number(n).toFixed(digits); };
  var traitOf = function (card, key) { return (card.traits && card.traits[key]) || "none"; };

  function request(url, method, body) {
    return fetch(url, { method: method, headers: HEADERS, credentials: "same-origin", cache: "no-store",
                        body: body === undefined ? undefined : JSON.stringify(body) })
      .then(function (response) {
        return response.json().then(function (data) { return { status: response.status, data: data }; },
          function () { return { status: response.status, data: { ok: false, message: "Unexpected answer, try later" } }; });
      }, function () { return { status: 0, data: { ok: false, message: "Couldn't reach the helper, try later" } }; });
  }

  function link(node, url) {
    if (url && url.indexOf("https://github.com/") === 0) {
      node.appendChild(document.createTextNode(" "));
      var a = el("a", null, "See the commit on GitHub");
      a.href = url; a.target = "_blank"; a.rel = "noopener";
      node.appendChild(a);
    }
  }

  // ---- screens: login or editor
  function showLogin(message) {
    $("editor-view").hidden = true;
    $("session").hidden = true;
    $("login-view").hidden = false;
    var error = $("login-error");
    error.className = "adminerror";
    error.textContent = message || "";
    $("password").focus();
  }

  function showEditor() {
    $("login-view").hidden = true;
    $("editor-view").hidden = false;
    $("session").hidden = false;
    if (cards.length) return Promise.resolve();      // coming back after a timeout: keep the pending changes
    return loadCards();
  }

  $("login-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var button = $("login-button"), error = $("login-error");
    button.disabled = true;
    button.textContent = "Checking…";
    error.className = "adminerror";
    error.textContent = "";
    request("/api/admin-login", "POST", { password: $("password").value }).then(function (out) {
      button.disabled = false;
      button.textContent = "Log in";
      if (out.data.ok) {
        $("password").value = "";
        showEditor();
      } else {
        error.textContent = out.data.message || "Couldn't log in, try later";
        $("password").focus();
        $("password").select();
      }
    });
  });

  $("logout").addEventListener("click", function () {
    request("/api/admin-login", "DELETE").then(function () { showLogin(""); });
  });

  // A helper said "log in": back to the login screen, keeping the pending changes.
  function sessionEnded() {
    showLogin("Your login ended. Log in again; your unsaved changes are kept.");
  }

  // ---- Mastery review done
  $("review-done").addEventListener("click", function () {
    var button = $("review-done"), status = $("review-status");
    button.disabled = true;
    status.textContent = "Working…";
    request("/api/admin-review", "POST", {}).then(function (out) {
      button.disabled = false;
      if (out.status === 401) { status.textContent = ""; sessionEnded(); return; }
      status.textContent = out.data.message || "Unexpected answer, try later";
      link(status, out.data.commit_url);
    });
  });

  // ---- cards
  function pendingList() { return Object.keys(pending).map(function (k) { return pending[k]; }); }

  function currentAverage() { return P.traitAverage(cards, rankedNames); }

  function badges(card) {
    var holder = document.createDocumentFragment();
    var any = false;
    TRAITS.forEach(function (t) {
      var level = traitOf(card, t[0]);
      if (level === "none") return;
      any = true;
      var span = el("span", "trait trait-" + level);
      span.appendChild(el("b", null, t[1]));
      span.appendChild(document.createTextNode(" " + LEVEL_NAME[level]));
      holder.appendChild(span);
    });
    if (!any) holder.appendChild(el("span", "more", "no traits"));
    return holder;
  }

  function makeSelect(options, value) {
    var select = document.createElement("select");
    options.forEach(function (o) {
      var option = document.createElement("option");
      option.value = o[0]; option.textContent = o[1]; option.selected = o[0] === value;
      select.appendChild(option);
    });
    return select;
  }

  function setChange(card, field, value, select) {
    var key = card.name + "|" + field;
    var from = field === "mastery" ? card.mastery : traitOf(card, field);
    if (value === from) delete pending[key];
    else pending[key] = { champion: card.name, field: field, from: from, value: value };
    select.classList.toggle("changed", value !== from);
    $("save-status").textContent = "";
    refresh();
  }

  function buildRows() {
    var body = $("cards-table").tBodies[0];
    body.textContent = "";
    rows = {};
    cards.slice().sort(function (a, b) { return a.name.localeCompare(b.name); }).forEach(function (card) {
      var r = { card: card, traits: {} };
      var tr = el("tr");
      var name = el("td", "champ", card.name);
      name.appendChild(el("small", null, card.kind + " · " + card.main_type.replace("_", " ")));
      tr.appendChild(name);

      var m = el("td");
      r.mastery = makeSelect(MASTERY, card.mastery);
      r.mastery.setAttribute("aria-label", card.name + " mastery");
      r.mastery.addEventListener("change", function () { setChange(card, "mastery", r.mastery.value, r.mastery); });
      m.appendChild(r.mastery);
      tr.appendChild(m);

      var t = el("td");
      r.toggle = el("button", "traitsbtn");
      r.toggle.type = "button";
      r.toggle.setAttribute("aria-expanded", "false");
      r.toggle.setAttribute("aria-label", card.name + " traits, tap to edit");
      r.toggle.addEventListener("click", function () {
        var open = r.detail.hidden;
        r.detail.hidden = !open;
        r.toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
      t.appendChild(r.toggle);
      tr.appendChild(t);

      r.comfort = el("td", "num");
      tr.appendChild(r.comfort);
      body.appendChild(tr);
      r.main = tr;

      var detail = el("tr");
      detail.hidden = true;
      var cell = el("td");
      cell.colSpan = 4;
      var grid = el("div", "traitgrid");
      TRAITS.forEach(function (tr2) {
        var label = el("label", null, tr2[1]);
        var select = makeSelect(LEVELS, traitOf(card, tr2[0]));
        select.addEventListener("change", function () { setChange(card, tr2[0], select.value, select); });
        label.appendChild(select);
        grid.appendChild(label);
        r.traits[tr2[0]] = select;
      });
      cell.appendChild(grid);
      detail.appendChild(cell);
      body.appendChild(detail);
      r.detail = detail;
      rows[card.name] = r;
    });
    applySearch();
  }

  function applySearch() {
    var q = $("search").value.toLowerCase().replace(/[^a-z0-9]/g, "");
    var shown = 0;
    Object.keys(rows).forEach(function (name) {
      var r = rows[name];
      var hit = !q || name.toLowerCase().replace(/[^a-z0-9]/g, "").indexOf(q) >= 0;
      r.main.hidden = !hit;
      if (!hit) r.detail.hidden = true;
      if (hit) shown++;
    });
    $("cards-count").textContent = shown + " of " + cards.length + " cards";
  }
  $("search").addEventListener("input", applySearch);

  // Redraws everything that depends on the pending changes: row highlights, Comfort, the changes box.
  function refresh() {
    var list = pendingList();
    var avg = currentAverage();
    var preview = list.length ? P.previewBatch(cards, rankedNames, list) : null;
    Object.keys(rows).forEach(function (name) {
      var r = rows[name], card = r.card;
      var changed = preview && preview.byChampion[name];
      r.main.classList.toggle("rowchanged", !!changed);
      r.toggle.textContent = "";
      r.toggle.appendChild(badges(applied(card)));
      r.toggle.appendChild(el("span", "more", "▾"));
      r.comfort.textContent = "";
      if (changed) {
        var span = el("span", "comfortchange");
        span.appendChild(document.createTextNode(fmt(changed.before, 1) + " → "));
        span.appendChild(el("b", null, fmt(changed.after, 1)));
        r.comfort.appendChild(span);
      } else {
        r.comfort.appendChild(el("span", "comfortnow", fmt(P.comfort(card, avg), 1)));
      }
    });
    drawChanges(list, preview);
    $("save-all").disabled = !list.length;
  }

  // The card with its pending changes applied (for the trait badges).
  function applied(card) {
    var copy = JSON.parse(JSON.stringify(card));
    pendingList().forEach(function (c) {
      if (c.champion !== card.name) return;
      if (c.field === "mastery") copy.mastery = c.value;
      else if (c.value === "none") { if (copy.traits) delete copy.traits[c.field]; }
      else { copy.traits = copy.traits || {}; copy.traits[c.field] = c.value; }
    });
    return copy;
  }

  function changeText(c) {
    if (c.field === "mastery") return "Mastery: " + MASTERY_NAME[c.from] + " → " + MASTERY_NAME[c.value];
    var name = function (v) { return v === "none" ? "None" : LEVEL_NAME[v]; };
    return TRAIT_NAME[c.field] + ": " + name(c.from) + " → " + name(c.value);
  }

  function drawChanges(list, preview) {
    var box = $("changes-box");
    box.hidden = !list.length;
    var holder = $("changes-list");
    holder.textContent = "";
    if (!list.length) { $("changes-trait-line").textContent = ""; return; }
    var champions = list.map(function (c) { return c.champion; }).filter(function (n, i, all) { return all.indexOf(n) === i; });
    $("changes-title").textContent = "Unsaved changes (" + list.length + (list.length === 1 ? " change" : " changes") +
      ", " + champions.length + (champions.length === 1 ? " champion)" : " champions)");
    champions.forEach(function (name) {
      var group = el("div", "changegroup");
      group.appendChild(el("b", null, name));
      var p = preview.byChampion[name];
      group.appendChild(el("span", "comfortline", "Comfort " + fmt(p.before, 1) + " → " + fmt(p.after, 1)));
      var ul = el("ul");
      list.filter(function (c) { return c.champion === name; }).forEach(function (c) {
        var li = el("li", null, changeText(c));
        var undo = el("button", "undo", "✕");
        undo.type = "button";
        undo.setAttribute("aria-label", "Undo: " + name + " " + changeText(c));
        undo.addEventListener("click", function () { undoChange(c); });
        li.appendChild(undo);
        ul.appendChild(li);
      });
      group.appendChild(ul);
      holder.appendChild(group);
    });
    var traitChanged = list.some(function (c) { return c.field !== "mastery"; });
    $("changes-trait-line").textContent = traitChanged && Math.abs(preview.traitAverageAfter - preview.traitAverageBefore) > 1e-9
      ? "Trait average " + fmt(preview.traitAverageBefore, 2) + " → " + fmt(preview.traitAverageAfter, 2) + ": every card's Comfort moves slightly."
      : "";
  }

  function undoChange(c) {
    var r = rows[c.champion];
    var select = c.field === "mastery" ? r.mastery : r.traits[c.field];
    select.value = c.from;
    select.classList.remove("changed");
    delete pending[c.champion + "|" + c.field];
    refresh();
  }

  function discardAll() {
    pendingList().forEach(function (c) { undoChange(c); });
    $("reload-cards").hidden = true;
  }
  $("discard-all").addEventListener("click", function () { discardAll(); $("save-status").textContent = ""; });

  $("save-all").addEventListener("click", function () {
    var list = pendingList();
    if (!list.length) return;
    var status = $("save-status");
    $("save-all").disabled = true;
    $("discard-all").disabled = true;
    status.textContent = "Saving…";
    request("/api/admin-card", "POST", { changes: list.map(function (c) {
      return { champion: c.champion, field: c.field, from: c.from, value: c.value };
    }) }).then(function (out) {
      $("discard-all").disabled = false;
      if (out.status === 401) { status.textContent = ""; $("save-all").disabled = false; sessionEnded(); return; }
      if (!out.data.ok) {
        status.textContent = out.data.message || "Unexpected answer, try later";
        $("save-all").disabled = false;
        if (out.status === 409) $("reload-cards").hidden = false;
        return;
      }
      // Saved: the cards in memory now have the new values, nothing is pending.
      list.forEach(function (c) {
        var card = rows[c.champion].card;
        if (c.field === "mastery") card.mastery = c.value;
        else if (c.value === "none") delete card.traits[c.field];
        else card.traits[c.field] = c.value;
      });
      pending = {};
      $("reload-cards").hidden = true;
      buildRows();
      refresh();
      status.textContent = out.data.message + " Scores update in about 3 minutes.";
      link(status, out.data.commit_url);
    });
  });

  $("reload-cards").addEventListener("click", function () {
    pending = {};
    $("save-status").textContent = "";
    $("reload-cards").hidden = true;
    loadCards();
  });

  window.addEventListener("beforeunload", function (event) {
    if (pendingList().length) { event.preventDefault(); event.returnValue = ""; }
  });

  // ---- loading
  function loadScores() {
    function names(data) { return (data.pick_score_list || []).map(function (r) { return r.riot_name; }); }
    return fetch(window.SETTINGS.DATA_URL).then(function (r) { return r.json(); }).then(names)
      .catch(function () { return fetch(window.SETTINGS.FALLBACK_URL).then(function (r) { return r.json(); }).then(names); })
      .catch(function () { return []; });
  }

  function loadCards() {
    $("cards-count").textContent = "Loading the cards…";
    return Promise.all([
      fetch("/api/admin-card", { cache: "no-store" }).then(function (r) { return r.json(); })
        .catch(function () { return { ok: false, message: "Couldn't reach the helper, try later" }; }),
      loadScores()
    ]).then(function (both) {
      if (!both[0].ok) { $("cards-count").textContent = both[0].message || "Couldn't load the cards, try later"; return; }
      cards = both[0].cards;
      rankedNames = both[1];
      buildRows();
      refresh();
    });
  }

  // ---- start: logged in already (cookie), or the login screen
  request("/api/admin-login", "GET").then(function (out) {
    if (!out.data.ok) { showLogin(out.data.message || "Couldn't reach the helper, try later"); return; }
    if (out.data.loggedIn) showEditor(); else showLogin("");
  });
})();
