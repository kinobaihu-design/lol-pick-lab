// Helper for the Python tests (not a test itself). Reads JSON on stdin, writes JSON on stdout.
//   {"mode": "preview", "cards": [...], "ranked": [...], "scenarios": [{"name", "changes": [{"field","value"}]}]}
//   {"mode": "edit", "text": "<cards.json text>", "edits": [{"champion","field","from","value"}]}
//   {"mode": "batch", "cards": [...], "ranked": [...], "batches": [[{"champion","field","value"}, ...], ...]}
//   {"mode": "config"}
const P = require("../site/comfort-preview.js");
const A = require("../lib/admin-cards.js");
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
let out;
if (input.mode === "preview") {
  out = input.scenarios.map((s) => P.preview(input.cards, input.ranked, s.name, s.changes));
} else if (input.mode === "edit") {
  let text = input.text;
  out = input.edits.map((e) => (text = A.applyEdit(text, e)));
} else if (input.mode === "batch") {
  out = input.batches.map((b) => P.previewBatch(input.cards, input.ranked, b));
} else {
  out = P.CONFIG;
}
process.stdout.write(JSON.stringify(out));
