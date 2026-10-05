// DMI Forecast Data EDR API (HARMONIE DINI model) client logic — pure
// functions, no Process/IO (that lives in DataService.qml).
//
// Verified live against opendataapi.dmi.dk on 2026-09-17:
//   GET /v1/forecastedr/collections/harmonie_dini_sf/cube
//     ?bbox=<west,south,east,north>&crs=crs84
//     &parameter-name=rain-precipitation-rate&datetime=<ISO step>&f=GeoJSON
// returns a FeatureCollection of Point features, one per native ~2-3km grid
// cell (about 46,500 points for the Denmark bbox — far denser than a small
// widget canvas needs), each with properties.step and
// properties["rain-precipitation-rate"].
//
// Unit note: the collection's parameter metadata labels this "Kg pr. square
// metres / s" (i.e. kg/m^2/s, equivalent to mm/s), but the raw values
// observed live are O(1-5) — treating them as mm/s would imply tens of
// thousands of mm/h, physically impossible. The values match a plausible
// mm/h reading directly, so this client treats the raw number as mm/h
// as-is. This is an empirical assumption (recorded here deliberately, not
// silently), worth re-verifying if DMI changes the API.
//
// `crs=crs84` only works for /position queries per the live API's own error
// message for /cube with crs84 when unpaired — but succeeds for /cube when
// used as both the query and (implicitly) the bbox CRS with f=GeoJSON, which
// is what this client relies on; f=CoverageJSON requires crs=native instead
// and is not used here.

var API_ROOT = "https://opendataapi.dmi.dk/v1/forecastedr/collections/harmonie_dini_sf"
var PARAMETER = "rain-precipitation-rate"

function buildCubeUrl(bbox, isoStep) {
  return API_ROOT + "/cube"
    + "?bbox=" + encodeURIComponent(bbox)
    + "&crs=crs84"
    + "&parameter-name=" + encodeURIComponent(PARAMETER)
    + "&datetime=" + encodeURIComponent(isoStep)
    + "&f=GeoJSON"
}

// Bins the ~46k native-resolution points down into a coarse cols x rows
// grid over `bounds` ({west,east,south,north}), averaging any points that
// land in the same cell. This is plenty of detail for a small Canvas (each
// cell ends up several pixels wide) and keeps per-frame rendering cheap.
function parseCubeToGrid(raw, bounds, cols, rows) {
  var sums = new Float64Array(cols * rows)
  var counts = new Int32Array(cols * rows)
  var step = null
  try {
    var data = JSON.parse(String(raw || "{}"))
    var features = Array.isArray(data.features) ? data.features : []
    var dLon = bounds.east - bounds.west
    var dLat = bounds.north - bounds.south
    for (var i = 0; i < features.length; i++) {
      var f = features[i] || {}
      var coords = f.geometry && f.geometry.coordinates
      var props = f.properties || {}
      var value = props[PARAMETER]
      if (!Array.isArray(coords) || typeof value !== "number" || !isFinite(value)) continue
      var lon = coords[0], lat = coords[1]
      if (lon < bounds.west || lon > bounds.east || lat < bounds.south || lat > bounds.north) continue
      if (!step && props.step) step = String(props.step)
      var col = Math.min(cols - 1, Math.floor((lon - bounds.west) / dLon * cols))
      var row = Math.min(rows - 1, Math.floor((bounds.north - lat) / dLat * rows))
      var idx = row * cols + col
      sums[idx] += Math.max(0, value)
      counts[idx] += 1
    }
  } catch (e) {
    // fall through, returns an all-empty grid
  }
  var values = new Float32Array(cols * rows)
  for (var j = 0; j < values.length; j++) values[j] = counts[j] > 0 ? sums[j] / counts[j] : 0
  return { cols: cols, rows: rows, bounds: bounds, step: step, values: values }
}

if (typeof module !== "undefined") module.exports = {
  buildCubeUrl: buildCubeUrl,
  parseCubeToGrid: parseCubeToGrid
}
