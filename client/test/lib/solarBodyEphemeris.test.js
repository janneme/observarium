import { describe, it, expect } from 'vitest'
import { Body } from 'astronomy-engine'
import { computeSunWindow, computeNightWindow, computeRiseSetTransit } from '../../src/lib/solarBodyEphemeris.js'

const VIENNA_LAT = 48.2
const VIENNA_LON = 16.37

describe('computeSunWindow', () => {
  it('returns an upcoming window (start/end both after now) when queried at local noon', () => {
    // 2026-01-15 12:00 UTC ~= 13:00 local (Vienna, winter, no DST) - solidly daytime.
    const noon = new Date('2026-01-15T12:00:00Z')
    const window = computeSunWindow(VIENNA_LAT, VIENNA_LON, noon, -12)
    expect(window.start.date.getTime()).toBeGreaterThan(noon.getTime())
    expect(window.end.date.getTime()).toBeGreaterThan(window.start.date.getTime())
  })

  it('returns a window bracketing now (start before, end after) when queried in the early-morning tail of an already-started night', () => {
    // Regression test: an earlier version anchored on the calendar day's
    // midday, so querying at e.g. 4am incorrectly returned *tonight's*
    // upcoming window instead of the one still in progress since last
    // evening - exactly the bug that caused Moon Map and Rise/Set Times to
    // disagree on the Moon's max altitude (each screen was silently looking
    // at a different night).
    const earlyMorning = new Date('2026-01-16T04:00:00Z') // ~05:00 local Vienna
    const window = computeSunWindow(VIENNA_LAT, VIENNA_LON, earlyMorning, -12)
    expect(window.start.date.getTime()).toBeLessThan(earlyMorning.getTime())
    expect(window.end.date.getTime()).toBeGreaterThan(earlyMorning.getTime())
  })
})

describe('computeNightWindow', () => {
  it('gives the same window regardless of whether queried from the evening or the early-morning side', () => {
    const evening = new Date('2026-01-15T20:00:00Z')
    const earlyMorning = new Date('2026-01-16T04:00:00Z')
    const fromEvening = computeNightWindow(VIENNA_LAT, VIENNA_LON, evening)
    const fromMorning = computeNightWindow(VIENNA_LAT, VIENNA_LON, earlyMorning)
    // SearchAltitude converges to within its own tolerance (~1 second), not
    // bit-for-bit, so compare with a generous slack rather than exact equality.
    expect(Math.abs(fromEvening.start.date.getTime() - fromMorning.start.date.getTime())).toBeLessThan(1000)
    expect(Math.abs(fromEvening.end.date.getTime() - fromMorning.end.date.getTime())).toBeLessThan(1000)
  })
})

describe('computeRiseSetTransit', () => {
  it('maxAltitudeAtNightDeg is never greater than the unconstrained daily transit maxAltitudeDeg', () => {
    const time = new Date('2026-01-16T04:00:00Z')
    const { maxAltitudeDeg, maxAltitudeAtNightDeg } = computeRiseSetTransit(Body.Moon, VIENNA_LAT, VIENNA_LON, time)
    if (maxAltitudeAtNightDeg != null) {
      expect(maxAltitudeAtNightDeg).toBeLessThanOrEqual(maxAltitudeDeg + 1e-6)
    }
  })

  it('reports the same maxAltitudeAtNightDeg whether queried from the evening or early-morning side of the same night', () => {
    const evening = new Date('2026-01-15T20:00:00Z')
    const earlyMorning = new Date('2026-01-16T04:00:00Z')
    const fromEvening = computeRiseSetTransit(Body.Moon, VIENNA_LAT, VIENNA_LON, evening)
    const fromMorning = computeRiseSetTransit(Body.Moon, VIENNA_LAT, VIENNA_LON, earlyMorning)
    // 10-minute altitude sampling plus search convergence tolerance means the
    // two directions won't match bit-for-bit — allow a small slack (degrees).
    expect(Math.abs(fromEvening.maxAltitudeAtNightDeg - fromMorning.maxAltitudeAtNightDeg)).toBeLessThan(0.01)
  })

  it('returns a maxAltitudeAtNightTime within the night window', () => {
    const time = new Date('2026-01-16T04:00:00Z')
    const { maxAltitudeAtNightTime } = computeRiseSetTransit(Body.Moon, VIENNA_LAT, VIENNA_LON, time)
    const night = computeNightWindow(VIENNA_LAT, VIENNA_LON, time)
    expect(maxAltitudeAtNightTime.ut).toBeGreaterThanOrEqual(night.start.ut)
    expect(maxAltitudeAtNightTime.ut).toBeLessThanOrEqual(night.end.ut)
  })
})
