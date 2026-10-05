// The rain rate at one location over time: samples the observed radar grids
// and the nowcast grids at a latitude/longitude and lines the results up on
// a real time axis. Pure functions (no QML), unit-tested.
//
// Grids are {cols, rows, bounds, values}, row 0 = north, cells linear in
// longitude and latitude (see helpers/dmi-radar-to-png).

// The value of the cell containing the point (nearest-cell, so a reading is
// exactly what the map shows there); null if the point lies outside the
// grid. `raw` prefers the nowcast's unfaded field: its fade toward 30% is a
// visual confidence cue on the map, and would make a reading understate the
// prediction.
function sampleGrid(grid, latitude, longitude, raw) {
  if (!grid || !grid.bounds || !grid.cols || !grid.rows) return null
  var b = grid.bounds
  if (latitude < b.south || latitude > b.north || longitude < b.west || longitude > b.east) return null
  var col = Math.min(grid.cols - 1, Math.floor((longitude - b.west) / (b.east - b.west) * grid.cols))
  var row = Math.min(grid.rows - 1, Math.floor((b.north - latitude) / (b.north - b.south) * grid.rows))
  var values = (raw && grid.rawValues) ? grid.rawValues : grid.values
  var value = values[row * grid.cols + col]
  return isFinite(value) ? value : null
}

function timeMs(iso) {
  var t = Date.parse(String(iso || ""))
  return isFinite(t) ? t : null
}

// Series for one location: {points: [{ms, mm, kind}], nowMs}, oldest first.
//   observed  [{time, grid}]   past scans — kind "observed"
//   nowcast   [{time, grid}]   extrapolated steps — kind "nowcast"
//   outlook   [{time, mm}]     optional coarser model values (HARMONIE) —
//                              kind "outlook"; only those after the nowcast
//                              ends are kept, so the two never overlap.
// Steps with no timestamp or no reading at the point are left out.
function build(observed, nowcast, latitude, longitude, outlook) {
  var points = []
  var i, ms, mm
  var nowMs = null
  for (i = 0; i < (observed || []).length; i++) {
    ms = timeMs(observed[i].time)
    mm = sampleGrid(observed[i].grid, latitude, longitude, false)
    if (ms === null || mm === null) continue
    points.push({ ms: ms, mm: mm, kind: "observed" })
    if (nowMs === null || ms > nowMs) nowMs = ms
  }
  var nowcastEnd = nowMs
  for (i = 0; i < (nowcast || []).length; i++) {
    ms = timeMs(nowcast[i].time)
    mm = sampleGrid(nowcast[i].grid, latitude, longitude, true)
    if (ms === null || mm === null) continue
    points.push({ ms: ms, mm: mm, kind: "nowcast" })
    if (nowcastEnd === null || ms > nowcastEnd) nowcastEnd = ms
  }
  for (i = 0; i < (outlook || []).length; i++) {
    ms = timeMs(outlook[i].time)
    mm = Number(outlook[i].mm)
    if (ms === null || !isFinite(mm) || (nowcastEnd !== null && ms <= nowcastEnd)) continue
    points.push({ ms: ms, mm: Math.max(0, mm), kind: "outlook" })
  }
  points.sort(function(a, b) { return a.ms - b.ms })
  return { points: points, nowMs: nowMs }
}

// Rain rate right now: the latest observed reading, or null without one.
function currentMm(series) {
  var value = null, latest = -Infinity
  for (var i = 0; i < series.points.length; i++) {
    var p = series.points[i]
    if (p.kind === "observed" && p.ms > latest) { latest = p.ms; value = p.mm }
  }
  return value
}

// The heaviest reading still to come from the radar nowcast, and how many
// minutes from now it is expected; null when there is no nowcast.
function peakAhead(series) {
  var best = null
  for (var i = 0; i < series.points.length; i++) {
    var p = series.points[i]
    if (p.kind !== "nowcast") continue
    if (best === null || p.mm > best.mm) best = { mm: p.mm, minutes: Math.round((p.ms - series.nowMs) / 60000) }
  }
  return best
}

// The first upcoming reading at or above `threshold` mm/h ("rain starts in
// 25 min"), or null if none. Meant for a dry-now case.
function firstAtLeast(series, threshold) {
  for (var i = 0; i < series.points.length; i++) {
    var p = series.points[i]
    if (p.kind === "nowcast" && p.mm >= threshold) return { mm: p.mm, minutes: Math.round((p.ms - series.nowMs) / 60000) }
  }
  return null
}

// The point nearest in time to `ms` (for reading a value at the playback
// cursor), or null for an empty series.
function nearest(series, ms) {
  var best = null, bestGap = Infinity
  for (var i = 0; i < series.points.length; i++) {
    var gap = Math.abs(series.points[i].ms - ms)
    if (gap < bestGap) { bestGap = gap; best = series.points[i] }
  }
  return best
}

function formatMm(mm) {
  return (mm < 10 ? mm.toFixed(1) : mm.toFixed(0)) + " mm/h"
}

function formatLead(minutes) {
  if (minutes < 60) return minutes + " min"
  var h = Math.floor(minutes / 60), m = minutes % 60
  return m === 0 ? h + " h" : h + " h " + m + " min"
}

// Minutes from now after which every remaining nowcast reading is below
// drizzle (the rain has stopped for good within the horizon), or null when
// it is still raining at the horizon's end or there is no nowcast.
function dryFromMinutes(series) {
  var lastWet = null, sawNowcast = false, lastPoint = null
  for (var i = 0; i < series.points.length; i++) {
    var p = series.points[i]
    if (p.kind !== "nowcast") continue
    sawNowcast = true
    lastPoint = p
    if (p.mm >= 0.1) lastWet = p
  }
  if (!sawNowcast || (lastWet && lastWet === lastPoint)) return null
  var firstDry = null
  for (i = 0; i < series.points.length; i++) {
    p = series.points[i]
    if (p.kind === "nowcast" && p.ms > (lastWet ? lastWet.ms : series.nowMs)) { firstDry = p; break }
  }
  return firstDry ? Math.round((firstDry.ms - series.nowMs) / 60000) : null
}

// One line about the pin: what is falling now and what the nowcast expects
// over the next 2 h. Rain below 0.1 mm/h counts as dry.
function summary(series) {
  var drizzle = 0.1
  var now = currentMm(series)
  if (now === null) return "No radar reading here yet"
  var peak = peakAhead(series)
  if (now >= drizzle) {
    var text = "Raining · " + formatMm(now)
    if (peak && peak.mm >= 0.5 && peak.mm > now * 1.5 && peak.minutes > 0)
      return text + " · up to " + formatMm(peak.mm) + " in " + formatLead(peak.minutes)
    var dry = dryFromMinutes(series)
    return dry === null ? text : text + " · dry within " + formatLead(dry)
  }
  var first = firstAtLeast(series, drizzle)
  if (first) return "Dry now · rain in ~" + formatLead(first.minutes) + " (up to " + formatMm(peak.mm) + ")"
  return "Dry now · none expected in the next 2 h"
}

if (typeof module !== "undefined") module.exports = {
  summary: summary,
  formatMm: formatMm,
  formatLead: formatLead,
  sampleGrid: sampleGrid,
  build: build,
  currentMm: currentMm,
  peakAhead: peakAhead,
  firstAtLeast: firstAtLeast,
  nearest: nearest
}
