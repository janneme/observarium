import { describe, it, expect } from 'vitest'
import {
  dsoDifficulty,
  doubleStarDifficulty,
  starDifficulty,
  difficultyCategory,
  dblPairs,
  percentileRank,
  computeListDifficultyOrder,
} from '../../src/lib/listDifficulty.js'

describe('dsoDifficulty', () => {
  it('ranks a small bright galaxy as easier than a large galaxy of the same magnitude', () => {
    const small = { type: 'dso', mag: 9, size: [8, 8] }
    const large = { type: 'dso', mag: 9, size: [70, 40] }
    expect(dsoDifficulty(small)).toBeLessThan(dsoDifficulty(large))
  })

  it('floors near-point-like sizes so tiny objects are not skewed to be trivially easy', () => {
    const pointLike = { type: 'dso', mag: 9, size: [0.1, 0.1] }
    expect(dsoDifficulty(pointLike)).toBeCloseTo(9, 5)
  })
})

describe('doubleStarDifficulty', () => {
  it('ranks a tighter separation as harder than a wider one at the same magnitudes', () => {
    const tight = { type: 'double_star', pairs: [{ mag: [5, 6], sep: 1 }] }
    const wide = { type: 'double_star', pairs: [{ mag: [5, 6], sep: 20 }] }
    expect(doubleStarDifficulty(tight)).toBeGreaterThan(doubleStarDifficulty(wide))
  })

  it('handles a [min,max] separation range by using the latest (last) value', () => {
    const obj = { type: 'double_star', pairs: [{ mag: [5, 6], sep: [3, 5] }] }
    expect(doubleStarDifficulty(obj)).toBe(
      doubleStarDifficulty({ type: 'double_star', pairs: [{ mag: [5, 6], sep: 5 }] }),
    )
  })

  it('picks the AB pair rather than pairs[0] when the AB pair is not listed first', () => {
    const obj = {
      type: 'double_star',
      pairs: [
        { comp: 'AC', mag: [5, 12], sep: 60 },
        { comp: 'AB', mag: [5, 6], sep: 1 },
      ],
    }
    // Should score like the tight AB pair (sep 1), not the wide AC one (sep 60).
    expect(doubleStarDifficulty(obj)).toBe(
      doubleStarDifficulty({ type: 'double_star', pairs: [{ mag: [5, 6], sep: 1 }] }),
    )
  })

  it('resolves pairs from a linked double_star record for a star-type primary (obj.dbl truthy)', () => {
    const star = { type: 'star', mag: 3.19, dbl: 'a' }
    const ds = { type: 'double_star', pairs: [{ comp: 'AB', mag: [3.19, 4.68], sep: 34.5 }] }
    expect(doubleStarDifficulty(star, ds)).toBe(
      doubleStarDifficulty({ type: 'double_star', pairs: [{ mag: [3.19, 4.68], sep: 34.5 }] }),
    )
  })

  it('resolves pairs embedded directly on obj.dbl when it is an array, without needing ds', () => {
    const star = { type: 'star', mag: 5, dbl: [{ pairs: [{ comp: 'AB', mag: [5, 7], sep: 2 }] }] }
    expect(doubleStarDifficulty(star)).toBe(
      doubleStarDifficulty({ type: 'double_star', pairs: [{ mag: [5, 7], sep: 2 }] }),
    )
  })
})

describe('dblPairs', () => {
  it('returns [] for a plain star with no dbl flag', () => {
    expect(dblPairs({ type: 'star', mag: 3 })).toEqual([])
  })

  it('prefers the double_star record over a missing/undefined ds', () => {
    expect(dblPairs({ type: 'star', dbl: 'p' }, null)).toEqual([])
  })
})

describe('starDifficulty', () => {
  it('uses the scalar magnitude directly', () => {
    expect(starDifficulty({ type: 'star', mag: 4.2 })).toBe(4.2)
  })

  it('uses the first value for a variable-star magnitude range', () => {
    expect(starDifficulty({ type: 'star', mag: [3, 5] })).toBe(3)
  })
})

describe('difficultyCategory', () => {
  it('classifies dso/double_star/star types', () => {
    expect(difficultyCategory({ type: 'dso' })).toBe('dso')
    expect(difficultyCategory({ type: 'double_star' })).toBe('doubleStar')
    expect(difficultyCategory({ type: 'star' })).toBe('star')
  })

  it('classifies a star that is a cataloged double star primary as doubleStar, not star', () => {
    expect(difficultyCategory({ type: 'star', dbl: 'a' })).toBe('doubleStar')
    expect(difficultyCategory({ type: 'star', dbl: 'p' })).toBe('doubleStar')
    expect(difficultyCategory({ type: 'star', dbl: 'm' })).toBe('doubleStar')
  })
})

describe('percentileRank', () => {
  it('maps the easiest value to 0 and hardest to 100', () => {
    const ranks = percentileRank([3, 1, 2])
    expect(ranks[1]).toBe(0)
    expect(ranks[2]).toBe(50)
    expect(ranks[0]).toBe(100)
  })

  it('returns 0 for a single-element or empty list', () => {
    expect(percentileRank([5])).toEqual([0])
    expect(percentileRank([])).toEqual([])
  })
})

describe('computeListDifficultyOrder', () => {
  it('normalizes each category independently before ordering easiest-first', () => {
    const objects = [
      { id: 'a', type: 'star', mag: 10 }, // hardest star
      { id: 'b', type: 'star', mag: 2 }, // easiest star
      { id: 'c', type: 'dso', mag: 15, size: [1, 1] }, // hardest dso
      { id: 'd', type: 'dso', mag: 2, size: [1, 1] }, // easiest dso
    ]
    const order = computeListDifficultyOrder(objects).map((o) => o.id)
    // Each category's easiest (percentile 0) member should precede its hardest (percentile 100).
    expect(order.indexOf('b')).toBeLessThan(order.indexOf('a'))
    expect(order.indexOf('d')).toBeLessThan(order.indexOf('c'))
  })

  it('scores double-star-primary stars by split difficulty (via dsById), not point-source magnitude', () => {
    // Mirrors the real Albireo/Algieba bug: a wide, easy-to-split pair whose
    // primary is fainter than a tight, hard-to-split pair's brighter primary.
    // Sorted by magnitude alone, Algieba (brighter) would wrongly come first.
    const albireo = { id: 'star_HIP95947', type: 'star', mag: 3.05, dbl: 'a', pos: [0, 0] }
    const algieba = { id: 'star_HIP50583', type: 'star', mag: 2.01, dbl: 'a', pos: [0, 0] }
    const dsById = new Map([
      ['star_HIP95947', { type: 'double_star', pairs: [{ comp: 'AB', mag: [3.19, 4.68], sep: 34.5 }] }],
      ['star_HIP50583', { type: 'double_star', pairs: [{ comp: 'AB', mag: [2.37, 3.64], sep: 4.2 }] }],
    ])
    const order = computeListDifficultyOrder([algieba, albireo], dsById).map((o) => o.id)
    expect(order).toEqual(['star_HIP95947', 'star_HIP50583']) // Albireo (easy, wide) before Algieba (tight)
  })

  it('without dsById, still classifies double-star-primary stars in their own category (not mixed with plain stars)', () => {
    const dblStar = { id: 'a', type: 'star', mag: 2, dbl: 'a' }
    const plainStar = { id: 'b', type: 'star', mag: 10 }
    // No dsById passed: dblPairs finds no pairs, so doubleStarDifficulty falls back to its
    // default (pair === null) rather than accidentally being scored as a plain point source.
    expect(difficultyCategory(dblStar)).toBe('doubleStar')
    expect(difficultyCategory(plainStar)).toBe('star')
    expect(() => computeListDifficultyOrder([dblStar, plainStar])).not.toThrow()
  })
})
