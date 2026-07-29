import { AstroTime, HelioVector, Body } from 'astronomy-engine'

// Standard gravitational parameter of the Sun (k^2, k = Gaussian
// gravitational constant), in AU^3/day^2.
const GM_SUN = 0.00029591220828559104

const OBL_COS = Math.cos((23.439291111 * Math.PI) / 180)
const OBL_SIN = Math.sin((23.439291111 * Math.PI) / 180)

// Stumpff functions C(z)/S(z), used by the universal-variable Kepler solver
// so the same propagator works for elliptical, parabolic, and hyperbolic
// orbits alike — comets, unlike asteroids, are often near-parabolic (e≈1)
// or hyperbolic (e>1), where a mean-anomaly-based elliptical solver doesn't
// apply.
function stumpffC(z) {
  if (z > 1e-6) return (1 - Math.cos(Math.sqrt(z))) / z
  if (z < -1e-6) {
    const s = Math.sqrt(-z)
    return (Math.cosh(s) - 1) / -z
  }
  return 0.5 - z / 24 + (z * z) / 720
}

function stumpffS(z) {
  if (z > 1e-6) {
    const s = Math.sqrt(z)
    return (s - Math.sin(s)) / (s * s * s)
  }
  if (z < -1e-6) {
    const s = Math.sqrt(-z)
    return (Math.sinh(s) - s) / (s * s * s)
  }
  return 1 / 6 - z / 120 + (z * z) / 5040
}

// Comet position via a universal-variable propagator, starting from the
// known state at perihelion passage (r0 = q, radial velocity = 0 — comet
// elements are given as q/Tp rather than semi-major-axis/mean-anomaly,
// since neither is well-defined near e=1). Handles e<1, e=1, and e>1
// uniformly.
//
// `elem` fields: q, e, argOfPeriDeg, ascNodeDeg, inclDeg, tpJd, H, slopeN
// (matching data_prep/comets.py's output). `time` may be a Date or an
// astronomy-engine AstroTime.
//
// Returns { ra (deg), dec (deg), mag, distAU } — geocentric equatorial J2000
// position, apparent magnitude (via the comet brightening law, a rough
// estimate not a reliable prediction), and heliocentric distance.
export function cometPosition(elem, time) {
  const astroT = time instanceof AstroTime ? time : new AstroTime(time)
  const D = Math.PI / 180
  const jd = astroT.tt + 2451545.0
  const { q, e } = elem
  const alpha = (1 - e) / q // 1/a: >0 elliptical, 0 parabolic, <0 hyperbolic

  let dt = jd - elem.tpJd
  if (alpha > 1e-10) {
    // Elliptical: motion is periodic — fold dt into [-period/2, period/2] so
    // the Newton solve starts from a small, well-conditioned anomaly
    // regardless of how long ago/far off the epoch's Tp is.
    const a = 1 / alpha
    const period = 2 * Math.PI * Math.sqrt((a * a * a) / GM_SUN)
    dt = (((dt % period) + period * 1.5) % period) - period / 2
  }

  const sqrtMu = Math.sqrt(GM_SUN)
  const r0 = q

  // Universal Kepler's equation from periapsis (vr0 = 0 there):
  //   sqrt(mu)*dt = (1 - alpha*r0)*chi^3*S(z) + r0*chi,  z = alpha*chi^2
  let chi = (sqrtMu * dt) / Math.max(r0, 1e-6)
  for (let iter = 0; iter < 100; iter++) {
    const z = alpha * chi * chi
    const C = stumpffC(z)
    const S = stumpffS(z)
    const F = r0 * chi + (1 - alpha * r0) * chi * chi * chi * S - sqrtMu * dt
    const dF = r0 + (1 - alpha * r0) * chi * chi * C
    const dchi = dF !== 0 ? F / dF : 0
    chi -= dchi
    if (Math.abs(dchi) < 1e-7) break
  }

  const z = alpha * chi * chi
  const C = stumpffC(z)
  const S = stumpffS(z)
  const f = 1 - (chi * chi * C) / r0
  const g = dt - (chi * chi * chi * S) / sqrtMu

  // Perifocal frame at periapsis: r0_vec = [q, 0, 0], v0_vec = [0, vPeri, 0].
  const vPeri = Math.sqrt((GM_SUN * (1 + e)) / q)
  const cO = Math.cos(elem.ascNodeDeg * D),
    sO = Math.sin(elem.ascNodeDeg * D)
  const co = Math.cos(elem.argOfPeriDeg * D),
    so = Math.sin(elem.argOfPeriDeg * D)
  const cI = Math.cos(elem.inclDeg * D),
    sI = Math.sin(elem.inclDeg * D)
  // Perifocal basis vectors (periapsis direction P, in-plane perpendicular Q),
  // expressed in the ecliptic frame.
  const Px = cO * co - sO * so * cI,
    Py = sO * co + cO * so * cI,
    Pz = so * sI
  const Qx = -cO * so - sO * co * cI,
    Qy = -sO * so + cO * co * cI,
    Qz = co * sI

  const xE = f * q * Px + g * vPeri * Qx
  const yE = f * q * Py + g * vPeri * Qy
  const zE = f * q * Pz + g * vPeri * Qz
  const r = Math.sqrt(xE * xE + yE * yE + zE * zE)

  // Ecliptic → equatorial J2000
  const xQ = xE
  const yQ = OBL_COS * yE - OBL_SIN * zE
  const zQ = OBL_SIN * yE + OBL_COS * zE
  // Subtract Earth's heliocentric position
  const earth = HelioVector(Body.Earth, astroT)
  const gx = xQ - earth.x,
    gy = yQ - earth.y,
    gz = zQ - earth.z
  const gd = Math.sqrt(gx * gx + gy * gy + gz * gz)
  const ra = ((((Math.atan2(gy, gx) * 180) / Math.PI) % 360) + 360) % 360
  const dec = (Math.asin(Math.max(-1, Math.min(1, gz / gd))) * 180) / Math.PI
  // Comet magnitude law (brightens faster than a fixed-H asteroid as it
  // nears the Sun) — this is a rough estimate, not a reliable prediction.
  const mag = elem.H + 5 * Math.log10(gd) + 2.5 * elem.slopeN * Math.log10(Math.max(r, 1e-6))
  return { ra, dec, mag, distAU: r }
}
