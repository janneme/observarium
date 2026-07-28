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

// Rise/set/transit-altitude for any astronomy-engine body, over the calendar
// day (local midnight-to-midnight) containing `time`. Works the same for
// solar-system bodies and DefineStar-registered stars/DSOs.
export function computeRiseSetTransit(body, lat, lon, time) {
  const observer = new Observer(lat, lon, 0)
  const midnight = new Date(time)
  midnight.setHours(0, 0, 0, 0)
  const startTime = new AstroTime(midnight)

  const riseTime = SearchRiseSet(body, observer, +1, startTime, 1)
  const setTime = SearchRiseSet(body, observer, -1, startTime, 1)
  const transitResult = SearchHourAngle(body, observer, 0, startTime)
  const maxAltitudeDeg = transitResult?.hor?.altitude ?? null

  // Rise/set both absent means the body doesn't cross the horizon at all
  // that day — the transit (upper culmination) altitude's sign tells us
  // whether that's because it's circumpolar (always up) or never rises.
  let circumpolar = null
  if (!riseTime && !setTime && maxAltitudeDeg != null) {
    circumpolar = maxAltitudeDeg > 0 ? 'up' : 'down'
  }

  return { riseTime, setTime, maxAltitudeDeg, circumpolar }
}

function bodyAltitudeDeg(body, observer, astroTime) {
  // Horizon() needs of-date apparent equatorial coordinates, matching the
  // frame its sidereal-time-based transform expects.
  const eq = Equator(body, astroTime, observer, true, true)
  return Horizon(astroTime, observer, eq.ra, eq.dec, 'normal').altitude
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

// Whether `body` is above the horizon at any point during the night (Sun
// altitude <= NIGHT_SUN_ALTITUDE_DEG) spanning from the evening of `time`'s
// calendar day to the following morning. Returns null if no such night
// occurs at this latitude/season — callers should treat null as "can't
// evaluate", not "not observable".
export function isObservableAtNight(name, lat, lon, time) {
  const body = SOLAR_BODY_NAME_MAP[name]
  if (body == null) return null
  const observer = new Observer(lat, lon, 0)

  const night = computeNightWindow(lat, lon, time)
  if (!night) return null
  const { start: nightStart, end: nightEnd } = night

  if (bodyAltitudeDeg(body, observer, nightStart) > 0) return true
  if (bodyAltitudeDeg(body, observer, nightEnd) > 0) return true

  // Down at both ends of the night doesn't rule out a rise-and-set entirely
  // within it (e.g. the Moon rising at 23:00 and setting at 02:00 during a
  // 20:00-05:00 night) — check for a rise event inside the window too.
  const nightDurationDays = nightEnd.ut - nightStart.ut
  const risesDuringNight = SearchRiseSet(body, observer, +1, nightStart, nightDurationDays)
  return !!risesDuringNight
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
