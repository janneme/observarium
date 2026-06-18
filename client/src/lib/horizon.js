import { Observer, AstroTime, Horizon as AstroHorizon, SiderealTime } from 'astronomy-engine'

export function getLST(lat, lon, time) {
  const t = new AstroTime(time)
  const lst = SiderealTime(t) + lon / 15
  return ((lst % 24) + 24) % 24 // local sidereal time in hours
}

// Returns altitude in degrees (negative = below horizon).
export function getAltitude(ra_deg, dec_deg, lat, lon, time) {
  const obs = new Observer(lat, lon, 0)
  const t = new AstroTime(time)
  const hor = AstroHorizon(t, obs, ra_deg / 15, dec_deg, 'normal')
  return hor.altitude
}

export function isAboveHorizon(ra_deg, dec_deg, lat, lon, time) {
  return getAltitude(ra_deg, dec_deg, lat, lon, time) >= 0
}

// Zenith point: RA = local sidereal time, Dec = observer latitude.
export function zenith(lat, lon, time) {
  const t = new AstroTime(time)
  const lst = SiderealTime(t) + lon / 15
  const ra_deg = (((lst % 24) + 24) % 24) * 15
  return { ra: ra_deg, dec: lat }
}
