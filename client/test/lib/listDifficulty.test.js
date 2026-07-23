import { describe, it, expect } from 'vitest'
import {
  dsoDifficulty,
  doubleStarDifficulty,
  starDifficulty,
  difficultyCategory,
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
    expect(doubleStarDifficulty(obj)).toBe(doubleStarDifficulty({ type: 'double_star', pairs: [{ mag: [5, 6], sep: 5 }] }))
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
})
