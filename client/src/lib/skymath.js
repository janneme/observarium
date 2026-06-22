const DEG = Math.PI / 180

function toRad(deg) {
  return deg * DEG
}

// Gnomonic (tangent-plane) projection.
// Returns normalised {x, y} in radians, or null when the point is on or behind
// the tangent plane (cos_c <= 0 means more than 90° from centre).
export function projectGnomonic(ra, dec, ra0, dec0) {
  const dAlpha = toRad(ra - ra0)
  const d = toRad(dec)
  const d0 = toRad(dec0)
  const cos_c = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(dAlpha)
  if (cos_c <= 0) return null
  const x = (Math.cos(d) * Math.sin(dAlpha)) / cos_c
  const y = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(dAlpha)) / cos_c
  return { x, y }
}

// Convert normalised gnomonic coords to canvas pixel coords.
// scale = H / fov_rad (pixels per radian); y-axis is flipped (y increases downward).
export function toPixel(x, y, W, H, fovDeg, rotation) {
  const scale = H / toRad(fovDeg)
  const cosR = Math.cos(rotation)
  const sinR = Math.sin(rotation)
  const xr = x * cosR - y * sinR
  const yr = x * sinR + y * cosR
  return {
    // Mirror X so sky handedness matches typical visual sky charts.
    px: W / 2 - xr * scale,
    py: H / 2 - yr * scale,
  }
}

export function projectToPixel(ra, dec, ra0, dec0, W, H, fovDeg, rotation) {
  const pt = projectGnomonic(ra, dec, ra0, dec0)
  if (!pt) return null
  return toPixel(pt.x, pt.y, W, H, fovDeg, rotation)
}

export function isOnScreen(px, py, W, H, margin = 0) {
  return px >= -margin && px <= W + margin && py >= -margin && py <= H + margin
}
