const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ForecastModel = require('../ForecastModel.js')
const MapModel = require('../MapModel.js')

test('buildCubeUrl matches the real DMI EDR endpoint shape (verified live on 2026-09-17)', () => {
  // The bbox is deliberately the literal original Denmark box, not the (much
  // larger) map domain: this endpoint's payload scales with area and it is
  // the one DMI throttles, so growing it should be a conscious change.
  const url = ForecastModel.buildCubeUrl(MapModel.harmonieBbox, '2026-09-17T13:00:00Z')
  assert.equal(url,
    'https://opendataapi.dmi.dk/v1/forecastedr/collections/harmonie_dini_sf/cube' +
    '?bbox=8%2C54.3%2C15.3%2C58&crs=crs84&parameter-name=rain-precipitation-rate' +
    '&datetime=2026-09-17T13%3A00%3A00Z&f=GeoJSON')
})

test('parseCubeToGrid bins a real captured DMI cube response into a coarse grid', () => {
  const raw = fs.readFileSync(path.join(__dirname, 'fixtures', 'harmonie-cube.json'), 'utf8')
  const grid = ForecastModel.parseCubeToGrid(raw, MapModel.harmonieBounds, 20, 14)
  assert.equal(grid.cols, 20)
  assert.equal(grid.rows, 14)
  assert.equal(grid.values.length, 20 * 14)
  assert.equal(grid.step, '2026-09-17T13:00:00.000Z')
  assert.ok(grid.values.some((v) => v > 0), 'at least one cell should have picked up a real rain value')
  assert.ok(grid.values.every((v) => v >= 0 && isFinite(v)))
})

test('parseCubeToGrid tolerates malformed input, returning an all-zero grid', () => {
  const grid = ForecastModel.parseCubeToGrid('not json', MapModel.harmonieBounds, 4, 3)
  assert.equal(grid.values.length, 12)
  assert.ok(grid.values.every((v) => v === 0))
})

test('parseCubeToGrid drops points outside the given bounds', () => {
  const raw = JSON.stringify({
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: { 'rain-precipitation-rate': 99 } },
      { type: 'Feature', geometry: { type: 'Point', coordinates: [10, 55] }, properties: { 'rain-precipitation-rate': 3 } }
    ]
  })
  const grid = ForecastModel.parseCubeToGrid(raw, MapModel.harmonieBounds, 4, 3)
  assert.ok(grid.values.every((v) => v < 99))
  assert.ok(grid.values.some((v) => v > 0))
})
