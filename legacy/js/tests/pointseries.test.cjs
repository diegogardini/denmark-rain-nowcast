const { test } = require('node:test')
const assert = require('node:assert/strict')
const PointSeries = require('../PointSeries.js')
const MapModel = require('../MapModel.js')
const Timeline = require('../Timeline.js')
const Interpolation = require('../Interpolation.js')

// 4 x 2 grid over a 4 deg x 2 deg box: each cell is 1 deg x 1 deg.
//   row 0 (north, lat 57-58): 1 2 3 4     row 1 (south, lat 56-57): 5 6 7 8
function tiny(values, rawValues) {
  return { cols: 4, rows: 2, bounds: { west: 8, east: 12, south: 56, north: 58 }, values: values || [1, 2, 3, 4, 5, 6, 7, 8], rawValues }
}

test('sampleGrid picks the cell containing the point, row 0 being north', () => {
  const g = tiny()
  assert.equal(PointSeries.sampleGrid(g, 57.5, 8.5), 1)
  assert.equal(PointSeries.sampleGrid(g, 57.5, 11.5), 4)
  assert.equal(PointSeries.sampleGrid(g, 56.5, 8.5), 5)
  assert.equal(PointSeries.sampleGrid(g, 56.5, 11.5), 8)
  assert.equal(PointSeries.sampleGrid(g, 57.2, 9.9), 2)
})

test('sampleGrid handles the grid edges and rejects points outside', () => {
  const g = tiny()
  assert.equal(PointSeries.sampleGrid(g, 58, 12), 4) // top-right corner belongs to the last column, first row
  assert.equal(PointSeries.sampleGrid(g, 56, 8), 5)
  assert.equal(PointSeries.sampleGrid(g, 58.01, 10), null)
  assert.equal(PointSeries.sampleGrid(g, 57, 7.99), null)
  assert.equal(PointSeries.sampleGrid(null, 57, 10), null)
  assert.equal(PointSeries.sampleGrid({}, 57, 10), null)
})

test('sampleGrid reads the unfaded field only when asked and available', () => {
  const g = tiny([1, 1, 1, 1, 1, 1, 1, 1], [9, 9, 9, 9, 9, 9, 9, 9])
  assert.equal(PointSeries.sampleGrid(g, 57.5, 8.5, false), 1)
  assert.equal(PointSeries.sampleGrid(g, 57.5, 8.5, true), 9)
  assert.equal(PointSeries.sampleGrid(tiny(), 57.5, 8.5, true), 1) // observed grids have no rawValues
})

test('sampleGrid matches where the map draws a cell (same layout as RadarMap.drawGrid)', () => {
  // A cell's centre, converted through the map projection and back, samples that same cell.
  const cols = 224, rows = 160, b = MapModel.bounds
  const values = new Float32Array(cols * rows)
  for (let i = 0; i < values.length; i++) values[i] = i
  const grid = { cols, rows, bounds: b, values }
  for (const [row, col] of [[0, 0], [10, 100], [80, 112], [159, 223], [37, 5]]) {
    const lat = b.north - (row + 0.5) * (b.north - b.south) / rows
    const lon = b.west + (col + 0.5) * (b.east - b.west) / cols
    assert.equal(PointSeries.sampleGrid(grid, lat, lon), row * cols + col)
  }
})

function series() {
  const observed = [
    { time: '2026-09-20T10:00:00Z', grid: tiny([0, 0, 0, 0, 1, 1, 1, 1]) },
    { time: '2026-09-20T10:05:00Z', grid: tiny([0, 0, 0, 0, 2, 2, 2, 2]) }
  ]
  const nowcast = [
    { time: '2026-09-20T10:10:00Z', grid: tiny([0, 0, 0, 0, 1, 1, 1, 1], [0, 0, 0, 0, 4, 4, 4, 4]) },
    { time: '2026-09-20T10:15:00Z', grid: tiny([0, 0, 0, 0, 1, 1, 1, 1], [0, 0, 0, 0, 6, 6, 6, 6]) },
    { time: '2026-09-20T10:20:00Z', grid: tiny([0, 0, 0, 0, 1, 1, 1, 1], [0, 0, 0, 0, 3, 3, 3, 3]) }
  ]
  return PointSeries.build(observed, nowcast, 56.5, 10)
}

test('build lines observed and nowcast up on a real time axis, in order', () => {
  const s = series()
  assert.deepEqual(s.points.map((p) => p.kind), ['observed', 'observed', 'nowcast', 'nowcast', 'nowcast'])
  assert.deepEqual(s.points.map((p) => p.mm), [1, 2, 4, 6, 3]) // nowcast uses the unfaded field
  assert.equal(s.nowMs, Date.parse('2026-09-20T10:05:00Z'))
  for (let i = 1; i < s.points.length; i++) assert.ok(s.points[i].ms > s.points[i - 1].ms)
})

test('current, peak-ahead and first-rain readings', () => {
  const s = series()
  assert.equal(PointSeries.currentMm(s), 2)
  assert.deepEqual(PointSeries.peakAhead(s), { mm: 6, minutes: 10 })
  assert.deepEqual(PointSeries.firstAtLeast(s, 5), { mm: 6, minutes: 10 })
  assert.deepEqual(PointSeries.firstAtLeast(s, 0.1), { mm: 4, minutes: 5 })
  assert.equal(PointSeries.firstAtLeast(s, 50), null)
})

test('nearest finds the point closest in time', () => {
  const s = series()
  assert.equal(PointSeries.nearest(s, Date.parse('2026-09-20T10:11:00Z')).mm, 4)
  assert.equal(PointSeries.nearest(s, Date.parse('2026-09-20T09:00:00Z')).mm, 1)
  assert.equal(PointSeries.nearest({ points: [] }, 0), null)
})

test('a pin outside the grids gives an empty series, not zeros', () => {
  const s = PointSeries.build([{ time: '2026-09-20T10:00:00Z', grid: tiny() }], [], 40, 10)
  assert.deepEqual(s.points, [])
  assert.equal(s.nowMs, null)
  assert.equal(PointSeries.currentMm(s), null)
  assert.equal(PointSeries.peakAhead(s), null)
})

test('steps without a valid timestamp are skipped', () => {
  const s = PointSeries.build([{ time: '', grid: tiny() }, { time: 'x', grid: tiny() }], [{ time: '', grid: tiny() }], 56.5, 10)
  assert.deepEqual(s.points, [])
})

test('outlook values are kept only after the nowcast ends and never below zero', () => {
  const obs = [{ time: '2026-09-20T10:00:00Z', grid: tiny() }]
  const now = [{ time: '2026-09-20T10:05:00Z', grid: tiny() }, { time: '2026-09-20T12:00:00Z', grid: tiny() }]
  const outlook = [
    { time: '2026-09-20T11:00:00Z', mm: 9 },   // inside the nowcast window: dropped
    { time: '2026-09-20T12:00:00Z', mm: 9 },   // same instant as the last step: dropped
    { time: '2026-09-20T13:00:00Z', mm: 1.5 },
    { time: '2026-09-20T14:00:00Z', mm: -0.2 },
    { time: '2026-09-20T15:00:00Z', mm: NaN }
  ]
  const s = PointSeries.build(obs, now, 56.5, 10, outlook)
  const tail = s.points.filter((p) => p.kind === 'outlook')
  assert.deepEqual(tail.map((p) => p.mm), [1.5, 0])
})

test('end to end: a shower drifting toward the pin appears in the pin series at the right time', () => {
  // A 10 mm/h shower 30 cells west of the pin moving 1 cell (~3.2 km) east per 5 min.
  const cols = 224, rows = 160, b = MapModel.bounds
  const grid = (cx) => {
    const v = new Float32Array(cols * rows)
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) v[r * cols + c] = 10 * Math.exp(-(((c - cx) / 3) ** 2 + ((r - 80) / 3) ** 2))
    return { cols, rows, bounds: b, values: v }
  }
  const a = grid(70), bgrid = grid(72) // 2 cells per 5 min
  const t0 = '2026-09-20T10:00:00Z', t1 = '2026-09-20T10:05:00Z'
  const step = Timeline.stepMinutes(t0, t1)
  const steps = Timeline.nowcastSteps(step)
  assert.equal(steps, 24)
  const seq = Interpolation.extrapolateSequence(a, bgrid, steps, 8, 6, 0.3)
  const times = Timeline.nowcastTimes(t1, step, steps)
  const nowcast = seq.map((grid, i) => ({ time: times[i], grid }))
  // pin at the centre of column 72 + 2*10 = 92 (arrives after 10 steps = 50 min), row 80
  const lat = b.north - (80 + 0.5) * (b.north - b.south) / rows
  const lon = b.west + (92 + 0.5) * (b.east - b.west) / cols
  const s = PointSeries.build([{ time: t0, grid: a }, { time: t1, grid: bgrid }], nowcast, lat, lon)
  assert.ok(PointSeries.currentMm(s) < 0.01)
  const peak = PointSeries.peakAhead(s)
  assert.ok(peak.mm > 8, 'peak ' + peak.mm)
  assert.ok(Math.abs(peak.minutes - 50) <= 5, 'minutes ' + peak.minutes)
  const first = PointSeries.firstAtLeast(s, 1)
  assert.ok(first.minutes < peak.minutes && first.minutes > 30)
})

function seriesOf(now, ahead) {
  // now: mm/h at the last scan; ahead: mm/h at +5, +10, ... minutes
  const t0 = Date.parse('2026-09-20T10:00:00Z')
  const points = [{ ms: t0 - 300000, mm: now, kind: 'observed' }, { ms: t0, mm: now, kind: 'observed' }]
  ahead.forEach((mm, i) => points.push({ ms: t0 + (i + 1) * 300000, mm, kind: 'nowcast' }))
  return { points, nowMs: t0 }
}

test('summary: dry now and staying dry', () => {
  assert.equal(PointSeries.summary(seriesOf(0, [0, 0.02, 0])), 'Dry now · none expected in the next 2 h')
})

test('summary: dry now, rain arriving', () => {
  const s = seriesOf(0, [0, 0, 0.3, 1.2, 4.5, 2])
  assert.equal(PointSeries.summary(s), 'Dry now · rain in ~15 min (up to 4.5 mm/h)')
})

test('summary: raining and building', () => {
  const s = seriesOf(1.2, [1.5, 3, 6.4, 4])
  assert.equal(PointSeries.summary(s), 'Raining · 1.2 mm/h · up to 6.4 mm/h in 15 min')
})

test('summary: raining and easing off to dry', () => {
  const s = seriesOf(2, [1, 0.4, 0, 0, 0])
  assert.equal(PointSeries.summary(s), 'Raining · 2.0 mm/h · dry within 15 min')
})

test('summary: steady rain says only what is falling', () => {
  assert.equal(PointSeries.summary(seriesOf(3, [3.2, 3.1, 2.9])), 'Raining · 3.2 mm/h'.replace('3.2', '3.0'))
})

test('summary: no reading, and long lead times', () => {
  assert.equal(PointSeries.summary({ points: [], nowMs: null }), 'No radar reading here yet')
  assert.equal(PointSeries.formatLead(90), '1 h 30 min')
  assert.equal(PointSeries.formatLead(120), '2 h')
  assert.equal(PointSeries.formatMm(12.4), '12 mm/h')
})
