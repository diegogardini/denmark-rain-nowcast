#!/usr/bin/env node
// Development tool: scores the plugin's two forecasts against what the radar
// then measured, so their accuracy is known rather than assumed.
//
//   node tools/forecast-verify.cjs collect   one pass: fetch new radar scans,
//                                            record forecasts, score any that
//                                            have come due
//   node tools/forecast-verify.cjs report    aggregate scores so far
//
// Meant to be run every ~30 min (see forecast-verify-loop.sh). Each pass:
//  - downloads any new DMI radar scans (the ground truth) and keeps them
//    coarsened onto HARMONIE's 40x30 grid;
//  - issues our radar nowcast from the two newest scans, once with the
//    per-block motion field and once with one global vector, and records
//    each at +30/60/90/120 min;
//  - fetches HARMONIE (heavy, throttled) at most every 3 h, giving up on the
//    first refusal, and records its next three hourly steps;
//  - scores every recorded forecast whose valid time now has a radar scan,
//    against that scan, and against "persistence" (the scan at issue time
//    held unchanged) as the baseline to beat.
//
// Everything lives in its own directory, not the plugin's cache.
const fs = require("node:fs")
const path = require("node:path")
const cp = require("node:child_process")
const root = path.join(__dirname, "..")
const RadarModel = require(path.join(root, "RadarModel.js"))
const ForecastModel = require(path.join(root, "ForecastModel.js"))
const MapModel = require(path.join(root, "MapModel.js"))
const Interpolation = require(path.join(root, "Interpolation.js"))

const DIR = process.env.RAIN_VERIFY_DIR ||
  path.join(process.env.XDG_STATE_HOME || path.join(process.env.HOME, ".local/state"), "omarchy/cache/rain-radar-denmark-verify")
const HARMONIE_EVERY_MS = 3 * 3600e3
const HARMONIE_RETRY_MS = 30 * 60e3
const NOWCAST_EVERY_MS = 25 * 60e3
const NOWCAST_LEADS = [6, 12, 18, 24] // steps of 5 min
const HB = MapModel.harmonieBounds, COLS = 40, ROWS = 30
for (const d of ["scans", "fine", "forecasts"]) fs.mkdirSync(path.join(DIR, d), { recursive: true })

const readJson = (p, fallback) => { try { return JSON.parse(fs.readFileSync(p, "utf8")) } catch (e) { return fallback } }
const writeJson = (p, v) => fs.writeFileSync(p, JSON.stringify(v))
const keyOf = (ms) => new Date(ms).toISOString().replace(/[-:T]/g, "").slice(0, 12)
const isoOf = (ms) => new Date(ms).toISOString().replace(".000Z", "Z")
const round3 = (a) => Array.from(a, (x) => Math.round(x * 1000) / 1000)
const statePath = path.join(DIR, "state.json")
const state = readJson(statePath, { lastScanMs: 0, lastNowcastMs: 0, harmonie: { lastSuccess: 0, lastAttempt: 0 } })
const saveState = () => writeJson(statePath, state)
const out = { scans: 0, forecasts: 0, verified: 0, notes: [] }

// Mean of the fine grid's cells inside each HARMONIE cell.
function coarsen(grid, raw) {
  const v = raw && grid.rawValues ? grid.rawValues : grid.values
  const sum = new Float64Array(COLS * ROWS), n = new Float64Array(COLS * ROWS)
  const cl = (grid.bounds.east - grid.bounds.west) / grid.cols, cb = (grid.bounds.north - grid.bounds.south) / grid.rows
  for (let r = 0; r < grid.rows; r++) {
    const lat = grid.bounds.north - (r + 0.5) * cb
    if (lat < HB.south || lat >= HB.north) continue
    const R = Math.floor((HB.north - lat) / (HB.north - HB.south) * ROWS)
    for (let c = 0; c < grid.cols; c++) {
      const lon = grid.bounds.west + (c + 0.5) * cl
      if (lon < HB.west || lon >= HB.east) continue
      const C = Math.floor((lon - HB.west) / (HB.east - HB.west) * COLS)
      sum[R * COLS + C] += v[r * grid.cols + c]; n[R * COLS + C]++
    }
  }
  return round3(sum.map((s, i) => (n[i] ? s / n[i] : 0)))
}

// ---- radar ground truth ----
async function collectRadar() {
  const now = Date.now()
  const start = state.lastScanMs ? state.lastScanMs : now - 3 * 3600e3
  const res = await fetch(RadarModel.buildItemsUrl(MapModel.dmiBbox, isoOf(start), isoOf(now + 300e3)), { signal: AbortSignal.timeout(30000) })
  if (!res.ok) { out.notes.push("radar list HTTP " + res.status); return }
  const items = RadarModel.parseItemsResponse(await res.text())
  for (const item of items.slice(0, 80)) {
    const ms = Date.parse(item.datetime), key = keyOf(ms)
    if (fs.existsSync(path.join(DIR, "scans", key + ".json"))) { state.lastScanMs = Math.max(state.lastScanMs, ms); continue }
    const tmp = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "verify-"))
    try {
      const h5 = path.join(tmp, item.id)
      const dl = await fetch(item.downloadUrl, { signal: AbortSignal.timeout(40000) })
      if (!dl.ok) { out.notes.push("download HTTP " + dl.status); continue }
      fs.writeFileSync(h5, Buffer.from(await dl.arrayBuffer()))
      const conv = cp.spawnSync("bash", [path.join(root, "helpers/dmi-radar-to-png"), h5, path.join(tmp, "out")], { timeout: 60000 })
      const fine = readJson(path.join(tmp, "out.nowcast-grid.json"), null)
      if (conv.status !== 0 || !fine) { out.notes.push("convert failed " + key); continue }
      writeJson(path.join(DIR, "scans", key + ".json"), { time: isoOf(ms), values: coarsen(fine, false) })
      writeJson(path.join(DIR, "fine", key + ".json"), fine)
      state.lastScanMs = Math.max(state.lastScanMs, ms)
      out.scans++
    } finally { fs.rmSync(tmp, { recursive: true, force: true }) }
  }
  // keep only the newest few fine grids (only the last two are ever used)
  const fines = fs.readdirSync(path.join(DIR, "fine")).sort()
  for (const f of fines.slice(0, Math.max(0, fines.length - 3))) fs.unlinkSync(path.join(DIR, "fine", f))
}

// ---- our nowcast ----
function issueNowcast() {
  const fines = fs.readdirSync(path.join(DIR, "fine")).sort()
  if (fines.length < 2) return
  const a = readJson(path.join(DIR, "fine", fines[fines.length - 2]), null), b = readJson(path.join(DIR, "fine", fines[fines.length - 1]), null)
  if (!a || !b) return
  const tA = Date.parse(keyToIso(fines[fines.length - 2])), tB = Date.parse(keyToIso(fines[fines.length - 1]))
  if (tB <= state.lastNowcastMs || tB - state.lastNowcastMs < NOWCAST_EVERY_MS && state.lastNowcastMs) return
  const stepMin = Math.max(1, Math.min(15, (tB - tA) / 60000))
  // Two variants from the same two scans, so they are scored on identical
  // cases: "nowcast" (per-block motion field, the plugin's default) and
  // "nowcast-global" (one shared vector, docs/FORECAST-VERIFICATION.md
  // section 11). The report pairs them.
  const variants = [["nowcast", "nowcast", false], ["nowcast-global", "nowcastg", true]]
  for (const [model, prefix, useGlobal] of variants) {
    const seq = Interpolation.extrapolateSequence(a, b, Math.max(...NOWCAST_LEADS), 8, 6, 1.0, useGlobal)
    for (const k of NOWCAST_LEADS) {
      const validMs = tB + k * stepMin * 60000
      writeJson(path.join(DIR, "forecasts", `${prefix}-${keyOf(tB)}-${k * 5}.json`), {
        model, issueMs: tB, validMs, leadMin: Math.round(k * stepMin), values: coarsen(seq[k - 1], true)
      })
      out.forecasts++
    }
  }
  state.lastNowcastMs = tB
}
const keyToIso = (file) => { const k = file.slice(0, 12); return `${k.slice(0, 4)}-${k.slice(4, 6)}-${k.slice(6, 8)}T${k.slice(8, 10)}:${k.slice(10, 12)}:00Z` }

// ---- HARMONIE ----
async function collectHarmonie() {
  const now = Date.now(), h = state.harmonie
  if (now - h.lastSuccess < HARMONIE_EVERY_MS || now - h.lastAttempt < HARMONIE_RETRY_MS) return
  h.lastAttempt = now
  const firstHour = Math.ceil(now / 3600e3) * 3600e3
  for (let i = 0; i < 3; i++) {
    const validMs = firstHour + i * 3600e3
    let res
    try { res = await fetch(ForecastModel.buildCubeUrl(MapModel.harmonieBbox, new Date(validMs).toISOString()), { signal: AbortSignal.timeout(90000) }) }
    catch (e) { out.notes.push("HARMONIE fetch failed: " + e.message); return }
    if (!res.ok) { out.notes.push("HARMONIE HTTP " + res.status + " (backing off)"); return }
    const grid = ForecastModel.parseCubeToGrid(await res.text(), HB, COLS, ROWS)
    writeJson(path.join(DIR, "forecasts", `harmonie-${keyOf(now)}-${keyOf(validMs)}.json`), {
      // "issue" is when we fetched it; the model run itself is a few hours
      // older, so the true lead time is longer than leadMin.
      model: "harmonie", issueMs: now, validMs, leadMin: Math.round((validMs - now) / 60000), values: round3(grid.values)
    })
    out.forecasts++
    h.lastSuccess = now
    if (i < 2) await new Promise((r) => setTimeout(r, 15000))
  }
}

// ---- scoring ----
function metrics(pred, truth) {
  const n = pred.length
  let sp = 0, st = 0, mp = 0, mt = 0
  for (let i = 0; i < n; i++) { sp += pred[i]; st += truth[i] }
  mp = sp / n; mt = st / n
  let cov = 0, vp = 0, vt = 0
  for (let i = 0; i < n; i++) { cov += (pred[i] - mp) * (truth[i] - mt); vp += (pred[i] - mp) ** 2; vt += (truth[i] - mt) ** 2 }
  const m = { sumP: sp, sumT: st, corr: vp > 0 && vt > 0 ? cov / Math.sqrt(vp * vt) : null, wetP: 0, wetT: 0, maxT: 0 }
  for (const t of [0.1, 0.5]) {
    let hit = 0, miss = 0, fa = 0
    for (let i = 0; i < n; i++) { const P = pred[i] >= t, A = truth[i] >= t; if (P && A) hit++; else if (A) miss++; else if (P) fa++ }
    m["t" + t] = [hit, miss, fa]
  }
  for (let i = 0; i < n; i++) { if (pred[i] >= 0.1) m.wetP++; if (truth[i] >= 0.1) m.wetT++; m.maxT = Math.max(m.maxT, truth[i]) }
  m.wetP /= n; m.wetT /= n
  return m
}
const resultsPath = path.join(DIR, "results.jsonl")
function verify() {
  const done = new Set(fs.existsSync(resultsPath) ? fs.readFileSync(resultsPath, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).id) : [])
  const scanKeys = fs.readdirSync(path.join(DIR, "scans")).map((f) => f.slice(0, 12)).sort()
  const scanMs = (k) => Date.parse(keyToIso(k))
  let lines = ""
  for (const file of fs.readdirSync(path.join(DIR, "forecasts")).sort()) {
    if (done.has(file)) continue
    const f = readJson(path.join(DIR, "forecasts", file), null)
    if (!f) continue
    const truthKey = keyOf(Math.round(f.validMs / 300e3) * 300e3)
    if (!scanKeys.includes(truthKey)) continue
    const truth = readJson(path.join(DIR, "scans", truthKey + ".json"), null)
    // persistence baseline: newest scan at or before the issue time
    const baseKey = scanKeys.filter((k) => scanMs(k) <= f.issueMs).pop()
    const base = baseKey && f.issueMs - scanMs(baseKey) <= 20 * 60e3 ? readJson(path.join(DIR, "scans", baseKey + ".json"), null) : null
    if (!truth) continue
    lines += JSON.stringify({ id: file, model: f.model, leadMin: f.leadMin, issue: isoOf(f.issueMs), valid: isoOf(f.validMs),
      m: metrics(f.values, truth.values), base: base ? metrics(base.values, truth.values) : null }) + "\n"
    out.verified++
  }
  if (lines) fs.appendFileSync(resultsPath, lines)
}

// ---- report ----
function report() {
  const rows = fs.existsSync(resultsPath) ? fs.readFileSync(resultsPath, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []
  if (!rows.length) { console.log("no scored forecasts yet"); return }
  const groups = {}
  for (const r of rows) {
    const lead = r.model === "harmonie" ? Math.round(r.leadMin / 60) + "h" : r.leadMin + "min"
    ;(groups[r.model + " +" + lead] = groups[r.model + " +" + lead] || []).push(r)
  }
  const csi = (list, key, t) => { let h = 0, m = 0, f = 0; for (const x of list) { const c = x[key]?.["t" + t]; if (c) { h += c[0]; m += c[1]; f += c[2] } } return h + m + f ? (h / (h + m + f)).toFixed(2) : "  - " }
  const avg = (list, key) => { const v = list.map((x) => x[key]?.corr).filter((c) => c !== null && c !== undefined); return v.length ? (v.reduce((a, b) => a + b, 0) / v.length).toFixed(2) : "  - " }
  const ratio = (list, key) => { let p = 0, t = 0; for (const x of list) if (x[key]) { p += x[key].sumP; t += x[key].sumT } return t > 0 ? (p / t).toFixed(2) + "x" : "  - " }
  console.log("forecast scored vs radar     n   wet%  | rain ratio  corr  CSI@0.1  CSI@0.5 | persistence: ratio corr CSI@0.1")
  for (const name of Object.keys(groups).sort()) {
    const g = groups[name]
    const wet = (g.reduce((a, x) => a + x.m.wetT, 0) / g.length * 100).toFixed(0)
    console.log(`${name.padEnd(24)} ${String(g.length).padStart(4)} ${wet.padStart(5)}%  | ${ratio(g, "m").padStart(9)} ${avg(g, "m").padStart(6)} ${csi(g, "m", 0.1).padStart(8)} ${csi(g, "m", 0.5).padStart(8)} |             ${ratio(g, "base").padStart(6)} ${avg(g, "base").padStart(5)} ${csi(g, "base", 0.1).padStart(8)}`)
  }
  // Same issue time and lead, both variants scored: the fair comparison.
  const byKey = {}
  for (const r of rows) if (r.model === "nowcast" || r.model === "nowcast-global") (byKey[r.issue + "|" + r.leadMin] = byKey[r.issue + "|" + r.leadMin] || {})[r.model] = r
  const pairs = Object.entries(byKey).filter(([, v]) => v.nowcast && v["nowcast-global"])
  if (pairs.length) {
    console.log("\npaired: per-block vs global vector, same issue times      n | rain ratio (pb / gl)   sd log ratio (pb / gl)   corr (pb / gl)   CSI@0.1 (pb / gl)")
    for (const lead of [...new Set(pairs.map(([k]) => +k.split("|")[1]))].sort((x, y) => x - y)) {
      const P = pairs.filter(([k]) => +k.split("|")[1] === lead).map(([, v]) => v)
      const pb = P.map((v) => v.nowcast), gl = P.map((v) => v["nowcast-global"])
      const sd = (list) => { const l = list.filter((x) => x.m.sumP > 0 && x.m.sumT > 0).map((x) => Math.log(x.m.sumP / x.m.sumT)); if (l.length < 2) return "  - "; const m = l.reduce((a, b) => a + b, 0) / l.length; return Math.sqrt(l.reduce((a, b) => a + (b - m) ** 2, 0) / l.length).toFixed(2) }
      console.log(`  +${String(lead).padEnd(4)}min${" ".repeat(48)}${String(P.length).padStart(3)} | ${ratio(pb, "m").padStart(8)} / ${ratio(gl, "m").padEnd(8)}   ${sd(pb).padStart(8)} / ${sd(gl).padEnd(8)}   ${avg(pb, "m").padStart(6)} / ${avg(gl, "m").padEnd(6)}   ${csi(pb, "m", 0.1).padStart(6)} / ${csi(gl, "m", 0.1)}`)
    }
  }
  const wetCases = rows.filter((r) => r.m.wetT >= 0.2).length
  console.log(`${rows.length} scored (${wetCases} where >=20% of the area was raining); heaviest truth ${Math.max(...rows.map((r) => r.m.maxT)).toFixed(1)} mm/h`)
}

async function main() {
  const cmd = process.argv[2] || "collect"
  if (cmd === "report") return report()
  const lock = path.join(DIR, "lock")
  try { fs.writeFileSync(lock, String(process.pid), { flag: "wx" }) } catch (e) {
    const pid = parseInt(fs.readFileSync(lock, "utf8"), 10)
    try { process.kill(pid, 0); console.log("another pass is running"); return } catch (e2) { fs.writeFileSync(lock, String(process.pid)) }
  }
  try {
    await collectRadar()
    issueNowcast()
    await collectHarmonie().catch((e) => out.notes.push("HARMONIE error: " + e.message))
    verify()
  } catch (e) { out.notes.push("error: " + e.message) }
  finally { saveState(); fs.rmSync(lock, { force: true }) }
  console.log(`collect: +${out.scans} scans, +${out.forecasts} forecasts, +${out.verified} scored` + (out.notes.length ? " | " + out.notes.join("; ") : ""))
}
main()
