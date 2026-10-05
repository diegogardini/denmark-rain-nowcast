// A local equirectangular map, longitude scaled at 56 degrees north (near
// Denmark's mid-latitude). Drawing, the radar PNG warp, the nowcast grid
// and DMI's radar API query all share `bounds`, so the raster and the
// vector coastlines line up without any per-frame reprojection.
//
// The domain is deliberately much larger than Denmark: it takes in the
// North Sea to the west (weather arrives from there, so rain has to be
// in-frame *before* it reaches the coast for the nowcast to carry it in),
// the Skagerrak/Kattegat/Baltic, and the neighbouring countries for context.
// helpers/dmi-radar-to-png keeps its own copy of these numbers (bash can't
// import this) — tests/maprange.test.cjs fails if they drift apart.
var bounds = { west: 5.0, east: 16.5, south: 53.9, north: 58.5 }
var longitudeScale = Math.cos(56 * Math.PI / 180)

// Width / height of `bounds` as drawn (longitude scaled). RadarMap sizes its
// canvas from this so the map fills the panel instead of letterboxing.
var aspect = (bounds.east - bounds.west) * longitudeScale / (bounds.north - bounds.south)

// HARMONIE is fetched for a smaller box than the map: its cube endpoint
// returns one JSON feature per ~2km cell with no way to ask for coarser
// data, so payload scales with area, and that endpoint is the one DMI
// throttles hardest. Its frames simply cover this sub-rectangle of the map.
// Also the "Denmark region" the bar icon's peak rain rate is taken over.
var harmonieBounds = { west: 8, east: 15.3, south: 54.3, north: 58 }

// "west,south,east,north" — the exact form DMI's STAC/EDR APIs expect for
// bbox query parameters (verified against opendataapi.dmi.dk on 2026-09-17).
function bboxString(b) { return b.west + "," + b.south + "," + b.east + "," + b.north }
var dmiBbox = bboxString(bounds)
var harmonieBbox = bboxString(harmonieBounds)

function viewport(width, height) {
  var scale = Math.max(0, Math.min(
    (width - 16) / ((bounds.east - bounds.west) * longitudeScale),
    (height - 16) / (bounds.north - bounds.south)))
  return {
    scale: scale,
    x: (width - (bounds.east - bounds.west) * longitudeScale * scale) / 2,
    y: (height - (bounds.north - bounds.south) * scale) / 2
  }
}

function project(latitude, longitude, width, height) {
  var vp = viewport(width, height)
  return {
    x: vp.x + (longitude - bounds.west) * longitudeScale * vp.scale,
    y: vp.y + (bounds.north - latitude) * vp.scale
  }
}

// Inverse of project(): a pixel in a width x height map view back to
// {latitude, longitude}. Used to turn a click into a pin.
function unproject(x, y, width, height) {
  var vp = viewport(width, height)
  if (vp.scale <= 0) return null
  return {
    latitude: bounds.north - (y - vp.y) / vp.scale,
    longitude: bounds.west + (x - vp.x) / (longitudeScale * vp.scale)
  }
}

// Whether a point falls inside the map window (the area radar data covers).
function contains(latitude, longitude) {
  return latitude >= bounds.south && latitude <= bounds.north &&
    longitude >= bounds.west && longitude <= bounds.east
}

// Highest value among the cells of `grid` ({cols, rows, bounds, values})
// whose centers fall inside `region`. Grids here may cover more than the
// region (the map-wide nowcast grid) or exactly it (HARMONIE's).
function regionPeak(grid, region) {
  if (!grid || !grid.values || !grid.bounds) return 0
  var cellLon = (grid.bounds.east - grid.bounds.west) / grid.cols
  var cellLat = (grid.bounds.north - grid.bounds.south) / grid.rows
  var max = 0
  for (var row = 0; row < grid.rows; row++) {
    var lat = grid.bounds.north - (row + 0.5) * cellLat
    if (lat < region.south || lat > region.north) continue
    for (var col = 0; col < grid.cols; col++) {
      var lon = grid.bounds.west + (col + 0.5) * cellLon
      if (lon < region.west || lon > region.east) continue
      var v = grid.values[row * grid.cols + col]
      if (v > max) max = v
    }
  }
  return max
}

if (typeof module !== "undefined") module.exports = {
  bounds: bounds,
  longitudeScale: longitudeScale,
  aspect: aspect,
  harmonieBounds: harmonieBounds,
  dmiBbox: dmiBbox,
  harmonieBbox: harmonieBbox,
  viewport: viewport,
  project: project,
  unproject: unproject,
  contains: contains,
  regionPeak: regionPeak
}
