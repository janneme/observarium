import { describe, it, expect } from 'vitest'
import {
  formatDimensions,
  buildMoonSearchIndex,
  doMoonSearch,
  terminatorEllipseGeometry,
} from '../../src/lib/moonMap.js'

describe('formatDimensions', () => {
  it('shows a single diameter for circular features', () => {
    expect(formatDimensions({ sizeKm: [96.07, 96.08], circular: true })).toBe('⌀96 km')
  })

  it('shows both axes for elongated features', () => {
    expect(formatDimensions({ sizeKm: [12.3, 47.8], circular: false })).toBe('12×48 km')
  })

  it('rounds to 2 significant figures', () => {
    expect(formatDimensions({ sizeKm: [1169.32, 1098.59], circular: false })).toBe('1200×1100 km')
  })

  it('returns empty string when sizeKm is missing', () => {
    expect(formatDimensions({ sizeKm: null, circular: true })).toBe('')
    expect(formatDimensions({})).toBe('')
  })
})

function mkFeature(name, type = 'crater') {
  return {
    id: `${type}::${name}`,
    type,
    name,
    lat: 0,
    lon: 0,
    sizeDeg: 1,
    sizeKm: [10, 10],
    circular: true,
    layers: [],
  }
}

describe('doMoonSearch', () => {
  const features = [
    mkFeature('Copernicus'),
    mkFeature('Tycho'),
    mkFeature('Mare Imbrium', 'mare'),
    mkFeature('Mare Crisium', 'mare'),
  ]
  const index = buildMoonSearchIndex(features)

  it('matches a substring anywhere in the name', () => {
    const results = doMoonSearch('imbrium', index)
    expect(results).toHaveLength(1)
    expect(results[0].obj.name).toBe('Mare Imbrium')
  })

  it('is case-insensitive', () => {
    const results = doMoonSearch('TYCHO', index)
    expect(results.map((r) => r.obj.name)).toEqual(['Tycho'])
  })

  it('sorts results alphabetically, not by match position', () => {
    const results = doMoonSearch('mare', index)
    expect(results.map((r) => r.obj.name)).toEqual(['Mare Crisium', 'Mare Imbrium'])
  })

  it('highlights the matching substring', () => {
    const results = doMoonSearch('coper', index)
    expect(results[0].spans).toEqual([
      { text: 'Coper', hl: true },
      { text: 'nicus', hl: false },
    ])
  })

  it('returns nothing for an empty query', () => {
    expect(doMoonSearch('', index)).toEqual([])
    expect(doMoonSearch('   ', index)).toEqual([])
  })
})

describe('terminatorEllipseGeometry', () => {
  // Reproduces exactly the path MoonCanvas.svelte's buildPhasePath() draws
  // (circle arc + ellipse arc, sampled instead of built as a Path2D — not
  // available outside a browser) and measures its enclosed area via the
  // shoelace formula, to check it actually matches the real illumination
  // fraction for the given phase. This is the regression test for a real
  // bug: an earlier version started the ellipse arc at cusp1's own
  // parameter instead of cusp2's (where the circle arc actually leaves off),
  // and with the untouched sweep direction — either mistake alone silently
  // produces a closed shape whose enclosed area is a completely different
  // (in one case, exactly complementary: e.g. 74% instead of 26%) fraction
  // of the disc, while every individual geometry value (b, theta, aLit...)
  // still looks individually plausible.
  function illumFractionFromPath(subLat, subLon, sunLon) {
    const g = terminatorEllipseGeometry(subLat, subLon, sunLon)
    const circleDir = g.aLit ? 1 : -1
    const circleStart = -g.alphaNorm1
    const circleEnd = circleStart - circleDir * Math.PI
    const ellipseStart = -(g.betaCusp1 + Math.PI)
    const ellipseDir = -g.ellipseDir
    const ellipseEnd = ellipseStart - ellipseDir * Math.PI
    const rotation = -g.theta

    const N = 200
    const pts = []
    for (let i = 0; i <= N; i++) {
      const t = circleStart + ((circleEnd - circleStart) * i) / N
      pts.push([Math.cos(t), Math.sin(t)])
    }
    for (let i = 0; i <= N; i++) {
      const t = ellipseStart + ((ellipseEnd - ellipseStart) * i) / N
      pts.push([
        Math.cos(t) * Math.cos(rotation) - g.b * Math.sin(t) * Math.sin(rotation),
        Math.cos(t) * Math.sin(rotation) + g.b * Math.sin(t) * Math.cos(rotation),
      ])
    }

    let area = 0
    for (let i = 0; i < pts.length; i++) {
      const [x1, y1] = pts[i]
      const [x2, y2] = pts[(i + 1) % pts.length]
      area += x1 * y2 - x2 * y1
    }
    area = Math.abs(area) / 2 / Math.PI // normalize by unit-disc area (pi)
    return g.aLit ? area : 1 - area
  }

  function sunLonForPhase(phaseDeg, subLonDeg) {
    return (((subLonDeg + 180 - phaseDeg) % 360) + 360) % 360
  }

  const cases = [
    ['waxing crescent', 60],
    ['waning crescent', 300],
    ['waxing gibbous', 160],
    ['waning gibbous', 200],
  ]

  for (const [label, phaseDeg] of cases) {
    it(`encloses the correct illuminated area for a ${label} phase (${phaseDeg}deg)`, () => {
      const subLat = -6.5
      const subLon = -2.5
      const sunLon = sunLonForPhase(phaseDeg, subLon)
      const expected = (1 - Math.cos((phaseDeg * Math.PI) / 180)) / 2
      expect(illumFractionFromPath(subLat, subLon, sunLon)).toBeCloseTo(expected, 2)
    })
  }

  it('returns null when sunLon is null (full-disc / no-terminator view)', () => {
    expect(terminatorEllipseGeometry(0, 0, null)).toBeNull()
  })
})
