// A fixed, bounded scale with a gentler, almost linear response near zero.
// 1 mm/h is one third up, 2.5 mm/h is 56%, and 10 mm/h is 83%.
// The 2 mm/h knee compresses heavy showers without amplifying tiny changes.
function heightFraction(mm) {
  var value = Number(mm)
  if (!isFinite(value) || value <= 0) return 0
  return value / (2 + value)
}

function yFor(mm, top, bottom) {
  return bottom - heightFraction(mm) * (bottom - top)
}

// Shape-preserving cubic tangents. Harmonic means and the segment limiter
// prevent ringing at dry intervals or overshooting an isolated shower peak.
function tangents(points) {
  if (points.length < 2) return [0]
  var slopes = [], result = []
  for (var i = 0; i < points.length - 1; i++)
    slopes.push((points[i + 1].y - points[i].y) / (points[i + 1].x - points[i].x))
  result[0] = slopes[0]
  for (i = 1; i < points.length - 1; i++) {
    var a = slopes[i - 1], b = slopes[i]
    result[i] = a * b <= 0 ? 0 : 2 * a * b / (a + b)
  }
  result[points.length - 1] = slopes[slopes.length - 1]
  for (i = 0; i < slopes.length; i++) {
    if (slopes[i] === 0) { result[i] = 0; result[i + 1] = 0; continue }
    var alpha = result[i] / slopes[i], beta = result[i + 1] / slopes[i]
    var magnitude = alpha * alpha + beta * beta
    if (magnitude > 9) {
      var factor = 3 / Math.sqrt(magnitude)
      result[i] = factor * alpha * slopes[i]
      result[i + 1] = factor * beta * slopes[i]
    }
  }
  return result
}

if (typeof module !== "undefined") module.exports = { heightFraction: heightFraction, yFor: yFor, tangents: tangents }
