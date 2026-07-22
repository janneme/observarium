import { describe, it, expect } from 'vitest'
import { formatDimensions, buildMoonSearchIndex, doMoonSearch } from '../../src/lib/moonMap.js'

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
  return { id: `${type}::${name}`, type, name, lat: 0, lon: 0, sizeDeg: 1, sizeKm: [10, 10], circular: true, layers: [] }
}

describe('doMoonSearch', () => {
  const features = [mkFeature('Copernicus'), mkFeature('Tycho'), mkFeature('Mare Imbrium', 'mare'), mkFeature('Mare Crisium', 'mare')]
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
