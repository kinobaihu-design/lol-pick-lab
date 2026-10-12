"use strict";
// Logic of the hidden card editor (admin page, slice 2).
// It accepts ONLY a champion's mastery or one of its 8 traits, with ONLY the allowed values, and changes
// ONLY scoring/cards.json and its copy site/data/cards.json (never review.json), one commit per edit.
const common = require("./admin-common");
const { AdminError, REPO } = common;

const CARD_FILES = ["scoring/cards.json", "site/data/cards.json"];
const MASTERY = { main: "Main", good: "Good", average: "Average", below_average: "Below average", never_played: "Never played" };
const TRAITS = {   // in the order the card file keeps them
  wave_clear: "Wave clear", team_utility: "Team utility", aoe: "AoE", cc: "CC",
  sustain: "Sustain", burst: "Burst", poke: "Poke", vision: "Vision"
};
const LEVELS = { none: "None", low: "Low", mid: "Mid", high: "High" };
const REQUEST_KEYS = ["password", "champion", "field", "from", "value"];
const MAX_TRIES = 3;
const CLASH = "Someone else changed the cards, reload and try again";

const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

// Checks the request fields. Returns {champion, field, from, value} or throws.
function validate(body) {
  const bad = new AdminError(400, "That change isn't allowed");
  if (!body || typeof body !== "object" || Array.isArray(body)) throw bad;
  if (Object.keys(body).some((k) => REQUEST_KEYS.indexOf(k) < 0)) throw bad;
  const { champion, field, from, value } = body;
  if (![champion, field, from, value].every((x) => typeof x === "string") || champion.length > 40) throw bad;
  const values = field === "mastery" ? MASTERY : has(TRAITS, field) ? LEVELS : null;
  if (!values || !has(values, from) || !has(values, value) || from === value) throw bad;
  return { champion: champion, field: field, from: from, value: value };
}

function labels(edit) {
  const values = edit.field === "mastery" ? MASTERY : LEVELS;
  const what = edit.field === "mastery" ? "mastery" : TRAITS[edit.field];
  return { what: what, from: values[edit.from], to: values[edit.value] };
}

function message(edit) {
  const l = labels(edit);
  return "Card edit: " + edit.champion + " " + l.what + " " + l.from + " → " + l.to;
}

// Returns the new text of the card file with exactly one change, made in place so the rest of the file
// stays byte for byte the same. Throws if the champion is unknown or the card no longer has `from`.
function applyEdit(text, edit) {
  let data;
  try { data = JSON.parse(text); } catch (e) { throw new AdminError(502, "The card file could not be read, try later"); }
  const card = (data.cards || []).find((c) => c.name === edit.champion);
  if (!card) throw new AdminError(404, "Unknown champion");
  const now = edit.field === "mastery" ? card.mastery : (card.traits && card.traits[edit.field]) || "none";
  if (now !== edit.from) throw new AdminError(409, CLASH);

  const start = text.indexOf("\n   \"name\": " + JSON.stringify(edit.champion) + ",\n");
  const end = text.indexOf("\n  }", start);
  if (start < 0 || end < 0) throw new AdminError(500, "The card file has an unexpected layout, nothing was changed");
  let block = text.slice(start, end);
  const expected = JSON.parse(JSON.stringify(data));
  const target = expected.cards.find((c) => c.name === edit.champion);

  if (edit.field === "mastery") {
    block = block.replace(/\n   "mastery": "[a-z_]+"/, "\n   \"mastery\": " + JSON.stringify(edit.value));
    target.mastery = edit.value;
  } else {
    const traits = Object.assign({}, card.traits);
    if (edit.value === "none") delete traits[edit.field]; else traits[edit.field] = edit.value;
    const ordered = {};
    Object.keys(TRAITS).forEach((k) => { if (has(traits, k)) ordered[k] = traits[k]; });
    const lines = Object.keys(ordered).map((k) => "    " + JSON.stringify(k) + ": " + JSON.stringify(ordered[k]));
    const body = lines.length ? "{\n" + lines.join(",\n") + "\n   }" : "{}";
    block = block.replace(/\n   "traits": \{[^}]*\}/, () => "\n   \"traits\": " + body);
    target.traits = ordered;
  }
  const result = text.slice(0, start) + block + text.slice(end);
  // Safety net: the new file must be the old data with only this one change.
  let again;
  try { again = JSON.parse(result); } catch (e) { again = null; }
  if (!again || JSON.stringify(again) !== JSON.stringify(expected) || result === text) {
    throw new AdminError(500, "The edit could not be made safely, nothing was changed");
  }
  return result;
}

async function readCards(call, head) {
  return call.text("/contents/scoring/cards.json?ref=" + head);
}

// POST: change one value on one card.
async function handleEdit(request, env, deps) {
  try {
    await common.checkAccess(request, env, deps.sleep, "POST");
    const edit = validate(request.body);
    const call = common.github(deps.fetch, env.GITHUB_TOKEN);
    for (let attempt = 0; attempt < MAX_TRIES; attempt++) {
      // Read the newest card file right before saving, so two quick edits can't overwrite each other.
      const head = await common.currentHead(call);
      const text = applyEdit(await readCards(call, head), edit);
      const files = {};
      CARD_FILES.forEach((path) => { files[path] = text; });
      try {
        const url = await common.commitToMain(call, head, files, message(edit), CARD_FILES);
        const l = labels(edit);
        return { status: 200, body: { ok: true, message: "Saved: " + edit.champion + " " + l.what + " " + l.from + " → " + l.to + " ✓", commit_url: url } };
      } catch (e) {
        if (!(e instanceof AdminError) || e.code !== "branch-moved") throw e;   // main moved: read again and retry
      }
    }
    throw new AdminError(409, "The main branch kept changing, press the button again");
  } catch (e) {
    return common.failure(e);
  }
}

// GET: the newest cards, for the admin page to show (public data, no password needed).
async function handleList(request, env, deps) {
  try {
    if (request.method !== "GET") throw new AdminError(405, "Use the admin page");
    if (!env.ADMIN_PASSWORD || !env.GITHUB_TOKEN) throw new AdminError(503, "Admin not set up yet");
    const call = common.github(deps.fetch, env.GITHUB_TOKEN);
    const head = await common.currentHead(call);
    let data;
    try { data = JSON.parse(await readCards(call, head)); } catch (e) {
      if (e instanceof AdminError) throw e;
      throw new AdminError(502, "The card file could not be read, try later");
    }
    return { status: 200, body: { ok: true, cards: data.cards } };
  } catch (e) {
    return common.failure(e);
  }
}

async function handle(request, env, deps) {
  return request.method === "GET" ? handleList(request, env, deps) : handleEdit(request, env, deps);
}

module.exports = { handle, handleEdit, handleList, validate, applyEdit, message, CARD_FILES, MASTERY, TRAITS, LEVELS, CLASH, REPO };
