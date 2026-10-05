// Generates tests/fixtures/js_parity.json: the plugin's JS models run on real
// scan pairs, as ground truth for the Python port. Run from the repo root:
//   node scripts/make_parity_fixture.cjs
const fs = require("fs"), path = require("path")
const I = require(path.join(__dirname, "../legacy/js/Interpolation.js"))
const F = path.join(__dirname, "../data/legacy/plugin-cache/frames/")
const pairs = [["202609232205", "202609232210"], ["202609232250", "202609232255"], ["202609240055", "202609240100"], ["202609201200", "202609201205"]]
const out = []
for (const [ka, kb] of pairs) {
  const load = (k) => { const g = JSON.parse(fs.readFileSync(F + `dk.com.${k}.500_max.h5.nowcast-grid.json`)); g.values = Float32Array.from(g.values); return g }
  const a = load(ka), b = load(kb)
  const rec = { a: Array.from(a.values), b: Array.from(b.values), rows: b.rows, cols: b.cols, leads: {} }
  const per = I.extrapolateSequence(a, b, 24, 8, 6, 1.0), glo = I.extrapolateSequence(a, b, 24, 8, 6, 1.0, true)
  for (const k of [1, 6, 12, 24]) rec.leads[k] = { block: Array.from(per[k - 1].rawValues), global: Array.from(glo[k - 1].rawValues) }
  const bl = I.computeBlockMotion(a, b, 8, 6)
  rec.motion = bl.map((x) => [x.dx, x.dy, x.confidence])
  out.push(rec)
}
// Four-scan sequences: the widget's multi-scan global vector (needs the plugin
// repo's current Interpolation.js; PLUGIN_DIR overrides the default sibling path).
const PLUGIN = process.env.PLUGIN_DIR || path.join(__dirname, "../../omarchy-rain-radar-denmark-widget")
const IM = require(path.join(PLUGIN, "Interpolation.js"))
const seqs = [["202609232150", "202609232155", "202609232200", "202609232205"], ["202609232245", "202609232250", "202609232255", "202609232300"],
  ["202609240050", "202609240055", "202609240100", "202609240105"], ["202609201150", "202609201155", "202609201200", "202609201205"]]
const seqOut = []
for (const keys of seqs) {
  const loadK = (k) => { const g = JSON.parse(fs.readFileSync(F + `dk.com.${k}.500_max.h5.nowcast-grid.json`)); g.values = Float32Array.from(g.values); return g }
  const g = keys.map(loadK)
  const v = IM.globalMotionFromFrames(g, 8, 6) || { dx: 0, dy: 0 }
  const seq = IM.extrapolateSequence(g[2], g[3], 24, 8, 6, 1.0, v)
  const rec = { frames: g.map((x) => Array.from(x.values)), rows: g[3].rows, cols: g[3].cols, vector: [v.dx, v.dy], leads: {} }
  for (const k of [1, 6, 12, 24]) rec.leads[k] = Array.from(seq[k - 1].rawValues)
  seqOut.push(rec)
}
fs.writeFileSync(path.join(__dirname, "../tests/fixtures/js_parity_seq.json"), JSON.stringify(seqOut))
console.log("sequences", seqOut.length)
fs.mkdirSync(path.join(__dirname, "../tests/fixtures"), { recursive: true })
fs.writeFileSync(path.join(__dirname, "../tests/fixtures/js_parity.json"), JSON.stringify(out))
console.log("pairs", out.length)
