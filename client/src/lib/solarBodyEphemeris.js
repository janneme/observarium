import {
  Observer,
  AstroTime,
  SearchRiseSet,
  SearchHourAngle,
  SearchAltitude,
  Horizon,
  Illumination,
  Equator,
  Constellation,
  HelioVector,
  Body,
} from 'astronomy-engine'
import { cometPosition } from './cometPosition.js'

// "Night" = Sun at least this many degrees below the horizon, per the
// definition used for the Rise/Set Times table's observability check.
// "Astronomical Night" is the standard, stricter threshold for full darkness.
const NIGHT_SUN_ALTITUDE_DEG = -12
const ASTRONOMICAL_NIGHT_SUN_ALTITUDE_DEG = -18

export const SOLAR_BODY_NAME_MAP = {
  Mercury: Body.Mercury,
  Venus: Body.Venus,
  Mars: Body.Mars,
  Jupiter: Body.Jupiter,
  Saturn: Body.Saturn,
  Uranus: Body.Uranus,
  Neptune: Body.Neptune,
  Pluto: Body.Pluto,
  Moon: Body.Moon,
  Sun: Body.Sun,
}

function bodyAltitudeDeg(body, observer, astroTime) {
  // Horizon() needs of-date apparent equatorial coordinates, matching the
  // frame its sidereal-time-based transform expects.
  const eq = Equator(body, astroTime, observer, true, true)
  return Horizon(astroTime, observer, eq.ra, eq.dec, 'normal').altitude
}

// `target` is either an astronomy-engine Body enum (a number) or a position
// function `(astroTime) => { ra (deg), dec (deg) }` for bodies the library
// doesn't carry built-in ephemeris for (comets, computed via our own
// universal-variable propagator in cometPosition.js). Returns a function
// `(astroTime) => altitudeDeg`.
function altitudeFnFor(target, observer) {
  if (typeof target === 'function') {
    return (t) => {
      const { ra, dec } = target(t)
      return Horizon(t, observer, ra / 15, dec, 'normal').altitude
    }
  }
  return (t) => bodyAltitudeDeg(target, observer, t)
}

// Generic root-finder over an arbitrary altitude(time) function, used for
// targets astronomy-engine's own SearchRiseSet/SearchAltitude can't handle
// directly (anything not in its built-in Body enum). Samples at a fixed
// resolution across the window and bisects across the first sign change
// matching `direction` (+1 rising, -1 setting) — coarser than the library's
// own search, but comet positions/magnitudes are already rough estimates, so
// sub-minute rise/set precision isn't warranted here.
function searchAltitudeCrossing(altitudeFn, direction, startTime, limitDays, thresholdDeg = 0) {
  const SAMPLES_PER_DAY = 24
  const totalSamples = Math.max(1, Math.round(limitDays * SAMPLES_PER_DAY))
  let prevT = startTime
  let prevAlt = altitudeFn(prevT) - thresholdDeg
  for (let i = 1; i <= totalSamples; i++) {
    const t = startTime.AddDays((i * limitDays) / totalSamples)
    const alt = altitudeFn(t) - thresholdDeg
    const crossedUp = direction > 0 && prevAlt < 0 && alt >= 0
    const crossedDown = direction < 0 && prevAlt > 0 && alt <= 0
    if (crossedUp || crossedDown) {
      let lo = prevT,
        hi = t
      for (let b = 0; b < 40; b++) {
        const mid = new AstroTime((lo.ut + hi.ut) / 2)
        const midAlt = altitudeFn(mid) - thresholdDeg
        const midIsTargetSide = direction > 0 ? midAlt >= 0 : midAlt <= 0
        if (midIsTargetSide) hi = mid
        else lo = mid
      }
      return hi
    }
    prevT = t
    prevAlt = alt
  }
  return null
}

function maxAltitudeOverWindow(altitudeFn, startTime, limitDays) {
  const SAMPLES_PER_DAY = 144 // every 10 minutes
  const totalSamples = Math.max(1, Math.round(limitDays * SAMPLES_PER_DAY))
  let best = -90
  for (let i = 0; i <= totalSamples; i++) {
    const t = startTime.AddDays((i * limitDays) / totalSamples)
    const alt = altitudeFn(t)
    if (alt > best) best = alt
  }
  return best
}

// Rise/set/transit-altitude for a target over the calendar day (local
// midnight-to-midnight) containing `time`. `target` is a `Body` enum
// (astronomy-engine's built-ins, and DefineStar-registered stars/DSOs) or a
// position function (comets — see altitudeFnFor above).
export function computeRiseSetTransit(target, lat, lon, time) {
  const observer = new Observer(lat, lon, 0)
  const midnight = new Date(time)
  midnight.setHours(0, 0, 0, 0)
  const startTime = new AstroTime(midnight)

  let riseTime, setTime, maxAltitudeDeg
  if (typeof target === 'function') {
    const altitudeFn = altitudeFnFor(target, observer)
    riseTime = searchAltitudeCrossing(altitudeFn, +1, startTime, 1)
    setTime = searchAltitudeCrossing(altitudeFn, -1, startTime, 1)
    maxAltitudeDeg = maxAltitudeOverWindow(altitudeFn, startTime, 1)
  } else {
    riseTime = SearchRiseSet(target, observer, +1, startTime, 1)
    setTime = SearchRiseSet(target, observer, -1, startTime, 1)
    const transitResult = SearchHourAngle(target, observer, 0, startTime)
    maxAltitudeDeg = transitResult?.hor?.altitude ?? null
  }

  // Rise/set both absent means the body doesn't cross the horizon at all
  // that day — the transit (upper culmination) altitude's sign tells us
  // whether that's because it's circumpolar (always up) or never rises.
  let circumpolar = null
  if (!riseTime && !setTime && maxAltitudeDeg != null) {
    circumpolar = maxAltitudeDeg > 0 ? 'up' : 'down'
  }

  return { riseTime, setTime, maxAltitudeDeg, circumpolar }
}

// The [start, end] window when the Sun is at or below `altitudeDeg`,
// spanning from the evening of `time`'s calendar day to the following
// morning. Returns null if no such window occurs at this latitude/season
// (e.g. high-latitude summer "white nights", where the Sun never gets that
// low).
export function computeSunWindow(lat, lon, time, altitudeDeg) {
  const observer = new Observer(lat, lon, 0)
  const midday = new Date(time)
  midday.setHours(12, 0, 0, 0)
  const middayAstro = new AstroTime(midday)

  const start = SearchAltitude(Body.Sun, observer, -1, middayAstro, 1, altitudeDeg)
  if (!start) return null
  const end = SearchAltitude(Body.Sun, observer, +1, start, 1, altitudeDeg)
  if (!end) return null
  return { start, end }
}

export function computeNightWindow(lat, lon, time) {
  return computeSunWindow(lat, lon, time, NIGHT_SUN_ALTITUDE_DEG)
}

export function computeAstronomicalNightWindow(lat, lon, time) {
  return computeSunWindow(lat, lon, time, ASTRONOMICAL_NIGHT_SUN_ALTITUDE_DEG)
}

// Whether `target` (a Body enum, or a position function — see altitudeFnFor)
// is above the horizon at any point during the night (Sun altitude <=
// NIGHT_SUN_ALTITUDE_DEG) spanning from the evening of `time`'s calendar day
// to the following morning. Returns null if no such night occurs at this
// latitude/season — callers should treat null as "can't evaluate", not "not
// observable".
function isTargetObservableAtNight(target, lat, lon, time) {
  const observer = new Observer(lat, lon, 0)

  const night = computeNightWindow(lat, lon, time)
  if (!night) return null
  const { start: nightStart, end: nightEnd } = night

  const altitudeFn = altitudeFnFor(target, observer)
  if (altitudeFn(nightStart) > 0) return true
  if (altitudeFn(nightEnd) > 0) return true

  // Down at both ends of the night doesn't rule out a rise-and-set entirely
  // within it (e.g. the Moon rising at 23:00 and setting at 02:00 during a
  // 20:00-05:00 night) — check for a rise event inside the window too.
  const nightDurationDays = nightEnd.ut - nightStart.ut
  const risesDuringNight =
    typeof target === 'function'
      ? searchAltitudeCrossing(altitudeFn, +1, nightStart, nightDurationDays)
      : SearchRiseSet(target, observer, +1, nightStart, nightDurationDays)
  return !!risesDuringNight
}

// Whether the named solar-system body is observable that night — see
// isTargetObservableAtNight.
export function isObservableAtNight(name, lat, lon, time) {
  const body = SOLAR_BODY_NAME_MAP[name]
  if (body == null) return null
  return isTargetObservableAtNight(body, lat, lon, time)
}

// Full ephemeris entry for a named solar-system body: rise/set/transit plus
// apparent magnitude, current constellation, heliocentric distance (used to
// sort the Rise/Set Times table by distance from the Sun), and whether the
// body can be observed at all during the associated night.
export function computeBodyEphemeris(name, lat, lon, time) {
  const body = SOLAR_BODY_NAME_MAP[name]
  if (body == null) return null

  const observer = new Observer(lat, lon, 0)
  const astroNow = new AstroTime(time)
  const { riseTime, setTime, maxAltitudeDeg, circumpolar } = computeRiseSetTransit(body, lat, lon, time)
  const mag = Illumination(body, astroNow).mag
  // Constellation() expects J2000 (EQJ) equatorial coordinates, so ofdate=false here.
  const eq = Equator(body, astroNow, observer, false, true)
  const constellation = Constellation(eq.ra, eq.dec)
  const distanceAu = HelioVector(body, astroNow).Length()
  const observableAtNight = isObservableAtNight(name, lat, lon, time)

  return {
    name,
    mag,
    constellationAbbr: constellation.symbol,
    constellationName: constellation.name,
    riseTime,
    setTime,
    maxAltitudeDeg,
    circumpolar,
    distanceAu,
    observableAtNight,
  }
}

// Full ephemeris entry for a comet: same shape as computeBodyEphemeris, but
// via cometPosition's universal-variable propagator instead of
// astronomy-engine's built-in ephemeris (comets aren't part of its Body
// enum). Position/magnitude are rough estimates — see cometPosition.js.
export function computeCometEphemeris(cometElem, lat, lon, time) {
  const positionFn = (astroTime) => cometPosition(cometElem, astroTime)
  const pos = positionFn(time instanceof AstroTime ? time : new AstroTime(time))
  const { riseTime, setTime, maxAltitudeDeg, circumpolar } = computeRiseSetTransit(positionFn, lat, lon, time)
  // cometPosition's ra/dec is already J2000 equatorial (no of-date rotation
  // applied), matching what Constellation() expects.
  const constellation = Constellation(pos.ra / 15, pos.dec)
  const observableAtNight = isTargetObservableAtNight(positionFn, lat, lon, time)

  return {
    name: cometElem.name,
    mag: pos.mag,
    constellationAbbr: constellation.symbol,
    constellationName: constellation.name,
    riseTime,
    setTime,
    maxAltitudeDeg,
    circumpolar,
    distanceAu: pos.distAU,
    observableAtNight,
  }
}
