// Hidden admin page. Slice 1: the "Mastery review done" button. Slice 2: card editing (mastery and the 8 traits)
// with a live Comfort preview. The typed password goes to the helper with every action and is cleared afterwards;
// the helper decides everything else (the patch, the allowed values). Nothing is stored in the page.
(function () {
  var input = document.getElementById("admin-password");
  var P = window.ComfortPreview;
  var MASTERY = [["main", "Main"], ["good", "Good"], ["average", "Average"], ["below_average", "Below average"], ["never_played", "Never played"]];
  var TRAITS = [["wave_clear", "Wave clear"], ["team_utility", "Team utility"], ["aoe", "AoE"], ["cc", "CC"],
                ["sustain", "Sustain"], ["burst", "Burst"], ["poke", "Poke"], ["vision", "Vision"]];
  var LEVELS = [["none", "None"], ["low", "Low"], ["mid", "Mid"], ["high", "High"]];
  var cards = [];          // the newest cards from GitHub (kept up to date after each saved change)
  var rankedNames = [];    // riot names of the ranked champions that have a card (for the trait average)

  function showWith(element, text, link, linkText) {
    element.textContent = text;
    if (link && link.indexOf("https://github.com/") === 0) {
      element.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = link;
      a.textContent = linkText || "See the commit on GitHub";
      a.target = "_blank";
      a.rel = "noopener";
      element.appendChild(a);
    }
  }

  function send(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (response) {
        return response.json().catch(function () { return { ok: false, message: "Unexpected answer, try later" }; });
      }, function () { return { ok: false, message: "Couldn't reach the helper, try later" }; });
  }

  // ---- slice 1: Mastery review done
  var form = document.getElementById("admin-form");
  var button = document.getElementById("admin-review-done");
  var status = document.getElementById("admin-status");
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    button.disabled = true;
    showWith(status, "Working…");
    send("/api/admin-review", { password: input.value }).then(function (data) {
      showWith(status, data.message || "Unexpected answer, try later", data.commit_url);
      input.value = "";
      button.disabled = false;
    });
  });

  // ---- slice 2: cards
  function option(pair, selected) {
    var o = document.createElement("option");
    o.value = pair[0];
    o.textContent = pair[1];
    o.selected = pair[0] === selected;
    return o;
  }
  function select(name, pairs, selected) {
    var label = document.createElement("label");
    label.appendChild(document.createTextNode(name));
    var s = document.createElement("select");
    pairs.forEach(function (pair) { s.appendChild(option(pair, selected)); });
    label.appendChild(s);
    return { label: label, select: s };
  }
  var traitOf = function (card, key) { return (card.traits && card.traits[key]) || "none"; };
  var fmt = function (n, digits) { return Number(n).toFixed(digits); };

  function renderCard(card, holder) {
    var box = document.createElement("section");
    box.className = "admin-card";
    var title = document.createElement("h3");
    title.textContent = card.name + " ";
    var sub = document.createElement("small");
    sub.textContent = "(" + card.kind + ", " + card.main_type.replace("_", " ") + ")";
    title.appendChild(sub);
    box.appendChild(title);

    var fields = document.createElement("div");
    fields.className = "admin-fields";
    var controls = [];
    var m = select("Mastery", MASTERY, card.mastery);
    fields.appendChild(m.label);
    controls.push({ field: "mastery", select: m.select, current: card.mastery });
    TRAITS.forEach(function (t) {
      var c = select(t[1], LEVELS, traitOf(card, t[0]));
      fields.appendChild(c.label);
      controls.push({ field: t[0], select: c.select, current: traitOf(card, t[0]) });
    });
    box.appendChild(fields);

    var preview = document.createElement("p");
    preview.className = "admin-preview";
    var update = document.createElement("button");
    update.type = "button";
    update.textContent = "Update";
    update.disabled = true;
    var result = document.createElement("p");
    result.className = "admin-result";
    result.setAttribute("role", "status");
    box.appendChild(preview);
    box.appendChild(update);
    box.appendChild(result);
    holder.appendChild(box);

    function changes() {
      return controls.filter(function (c) { return c.select.value !== c.current; })
        .map(function (c) { return { field: c.field, from: c.current, value: c.select.value }; });
    }
    function refresh() {
      var list = changes();
      controls.forEach(function (c) { c.select.classList.toggle("changed", c.select.value !== c.current); });
      update.disabled = list.length === 0;
      if (!list.length) { preview.textContent = ""; return; }
      var p = P.preview(cards, rankedNames, card.name, list);
      var text = "Comfort " + fmt(p.comfortBefore, 1) + " → " + fmt(p.comfortAfter, 1);
      if (list.some(function (c) { return c.field !== "mastery"; }) && Math.abs(p.traitAverageAfter - p.traitAverageBefore) > 1e-9) {
        text += " · trait average " + fmt(p.traitAverageBefore, 2) + " → " + fmt(p.traitAverageAfter, 2) +
          ", all cards move slightly";
      }
      preview.textContent = text;
    }
    controls.forEach(function (c) { c.select.addEventListener("change", refresh); });

    update.addEventListener("click", function () {
      var list = changes();
      if (!list.length) return;
      var password = input.value;
      input.value = "";
      update.disabled = true;
      controls.forEach(function (c) { c.select.disabled = true; });
      showWith(result, "Saving…");
      var last = null;
      // One change after the other, each as its own commit. Stops at the first problem.
      list.reduce(function (chain, change) {
        return chain.then(function (ok) {
          if (!ok) return false;
          return send("/api/admin-card", { password: password, champion: card.name, field: change.field, from: change.from, value: change.value })
            .then(function (data) {
              if (!data.ok) { showWith(result, data.message || "Unexpected answer, try later"); return false; }
              last = data;
              var control = controls.filter(function (c) { return c.field === change.field; })[0];
              control.current = change.value;
              if (change.field === "mastery") card.mastery = change.value;
              else if (change.value === "none") delete card.traits[change.field];
              else card.traits[change.field] = change.value;
              showWith(result, data.message, data.commit_url);
              return true;
            });
        });
      }, Promise.resolve(true)).then(function (ok) {
        if (ok && last) showWith(result, "Saved ✓ The scores update in a few minutes.", last.commit_url);
        controls.forEach(function (c) { c.select.disabled = false; });
        refresh();
      });
    });
  }

  function renderCards() {
    var holder = document.getElementById("admin-cards");
    holder.textContent = "";
    cards.slice().sort(function (a, b) { return a.name.localeCompare(b.name); })
      .forEach(function (card) { renderCard(card, holder); });
  }

  function loadScores() {
    function names(data) { return (data.pick_score_list || []).map(function (r) { return r.riot_name; }); }
    return fetch(window.SETTINGS.DATA_URL).then(function (r) { return r.json(); }).then(names)
      .catch(function () { return fetch(window.SETTINGS.FALLBACK_URL).then(function (r) { return r.json(); }).then(names); })
      .catch(function () { return []; });
  }

  var cardsStatus = document.getElementById("admin-cards-status");
  Promise.all([
    fetch("/api/admin-card", { cache: "no-store" }).then(function (r) { return r.json(); })
      .catch(function () { return { ok: false, message: "Couldn't reach the helper, try later" }; }),
    loadScores()
  ]).then(function (both) {
    var data = both[0];
    if (!data.ok) { cardsStatus.textContent = data.message || "Couldn't load the cards, try later"; return; }
    cards = data.cards;
    rankedNames = both[1];
    cardsStatus.textContent = cards.length + " cards. Dropdowns start at each card's current values.";
    renderCards();
  });
})();
