import { describe, it, expect } from 'vitest'
import {
  buildEligiblePool,
  pickPositionDistractors,
  pickImageDistractors,
  pickNameDistractors,
  subtypeBucket,
  EASY_POOL_SIZE,
  MEDIUM_NGC_POOL_SIZE,
  HARD_NGC_POOL_SIZE,
} from '../../src/lib/deepSkyQuizPool.js'

function mkDso(id, dsoType, mag, { m, pos = [0, 0] } = {}) {
  return { id, type: 'dso', dsoType, mag, m, pos }
}

describe('buildEligiblePool', () => {
  it('easy: top 30 brightest Messier objects, no NGC', () => {
    const messier = Array.from({ length: 40 }, (_, i) => mkDso(`m${i}`, 'spiral galaxy', i, { m: i + 1 }))
    const ngc = Array.from({ length: 10 }, (_, i) => mkDso(`ngc${i}`, 'spiral galaxy', i))
    const pool = buildEligiblePool([...messier, ...ngc], 'easy', () => true)
    expect(pool).toHaveLength(EASY_POOL_SIZE)
    expect(pool).toContain('m0')
    expect(pool).toContain('m29')
    expect(pool).not.toContain('m30')
    expect(pool.some((id) => id.startsWith('ngc'))).toBe(false)
  })

  it('medium: all Messier + top 30 brightest non-Messier NGC', () => {
    const messier = Array.from({ length: 10 }, (_, i) => mkDso(`m${i}`, 'globular cluster', 20, { m: i + 1 }))
    const ngc = Array.from({ length: 40 }, (_, i) => mkDso(`ngc${i}`, 'spiral galaxy', i))
    const pool = buildEligiblePool([...messier, ...ngc], 'medium', () => true)
    expect(pool).toHaveLength(10 + MEDIUM_NGC_POOL_SIZE)
    for (const m of messier) expect(pool).toContain(m.id)
    expect(pool).toContain('ngc0')
    expect(pool).toContain('ngc29')
    expect(pool).not.toContain('ngc30')
  })

  it('hard: all Messier + top 200 brightest non-Messier NGC', () => {
    const messier = [mkDso('m1', 'globular cluster', 5, { m: 1 })]
    const ngc = Array.from({ length: 250 }, (_, i) => mkDso(`ngc${i}`, 'spiral galaxy', i))
    const pool = buildEligiblePool([...messier, ...ngc], 'hard', () => true)
    expect(pool).toHaveLength(1 + HARD_NGC_POOL_SIZE)
    expect(pool).toContain('ngc199')
    expect(pool).not.toContain('ngc200')
  })

  it('excludes non-Messier open clusters without an image, in medium/hard', () => {
    const withImage = mkDso('oc_img', 'open cluster', 1)
    const withoutImage = mkDso('oc_noimg', 'open cluster', 0.5)
    const messierOc = mkDso('oc_m', 'open cluster', 2, { m: 44 })
    const hasImage = (id) => id === 'oc_img'

    const mediumPool = buildEligiblePool([withImage, withoutImage, messierOc], 'medium', hasImage)
    expect(mediumPool).toContain('oc_img')
    expect(mediumPool).toContain('oc_m')
    expect(mediumPool).not.toContain('oc_noimg')

    const hardPool = buildEligiblePool([withImage, withoutImage, messierOc], 'hard', hasImage)
    expect(hardPool).not.toContain('oc_noimg')
  })

  it('easy tier is Messier-only regardless of image availability', () => {
    const withImage = mkDso('oc_img', 'open cluster', 1)
    const messierOc = mkDso('oc_m', 'open cluster', 2, { m: 44 })
    const hasImage = (id) => id === 'oc_img'

    const easyPool = buildEligiblePool([withImage, messierOc], 'easy', hasImage)
    expect(easyPool).toContain('oc_m')
    expect(easyPool).not.toContain('oc_img')
  })
})

describe('subtypeBucket', () => {
  it('splits galaxies into spiral / elliptical / plain (no irregular subtype in the data)', () => {
    expect(subtypeBucket('spiral galaxy')).toBe('spiral galaxy')
    expect(subtypeBucket('elliptical galaxy')).toBe('elliptical galaxy')
    expect(subtypeBucket('galaxy')).toBe('galaxy')
  })

  it('splits clusters into globular / open', () => {
    expect(subtypeBucket('globular cluster')).toBe('globular cluster')
    expect(subtypeBucket('open cluster')).toBe('open cluster')
  })

  it('groups all nebula types into one bucket', () => {
    expect(subtypeBucket('emission nebula')).toBe('nebula')
    expect(subtypeBucket('reflection nebula')).toBe('nebula')
    expect(subtypeBucket('planetary nebula')).toBe('nebula')
  })
})

describe('pickPositionDistractors', () => {
  it('excludes candidates within minSepDeg of the target (e.g. M81/M82)', () => {
    const m81 = mkDso('m81', 'spiral galaxy', 6.9, { pos: [148.9, 69.1] })
    const m82 = mkDso('m82', 'galaxy', 8.4, { pos: [148.97, 69.68] }) // ~0.6deg from M81
    const far = mkDso('far', 'spiral galaxy', 9, { pos: [200, 40] })
    const dsosById = new Map([
      [m81.id, m81],
      [m82.id, m82],
      [far.id, far],
    ])
    const pool = [m81.id, m82.id, far.id]
    const distractors = pickPositionDistractors('m81', pool, dsosById, 2, 3)
    expect(distractors).not.toContain('m82')
    expect(distractors).toContain('far')
  })
})

describe('pickImageDistractors', () => {
  it('requires an image and excludes the same subtype bucket', () => {
    const target = mkDso('spiral1', 'spiral galaxy', 8)
    const sameBucketNoImage = mkDso('spiral2', 'spiral galaxy', 9)
    const otherBucket = mkDso('ell1', 'elliptical galaxy', 9)
    const otherBucketNoImage = mkDso('ell2', 'elliptical galaxy', 9)
    const dsosById = new Map([target, sameBucketNoImage, otherBucket, otherBucketNoImage].map((d) => [d.id, d]))
    const pool = [...dsosById.keys()]
    const hasImageSet = new Set(['spiral1', 'ell1'])

    const distractors = pickImageDistractors('spiral1', pool, dsosById, hasImageSet, 3)
    expect(distractors).toEqual(['ell1'])
  })

  it('exempts nebulae from the subtype-bucket restriction', () => {
    const target = mkDso('neb1', 'emission nebula', 6)
    const neb2 = mkDso('neb2', 'reflection nebula', 7)
    const neb3 = mkDso('neb3', 'planetary nebula', 8)
    const dsosById = new Map([target, neb2, neb3].map((d) => [d.id, d]))
    const pool = [...dsosById.keys()]
    const hasImageSet = new Set(['neb1', 'neb2', 'neb3'])

    const distractors = pickImageDistractors('neb1', pool, dsosById, hasImageSet, 3)
    expect(distractors.sort()).toEqual(['neb2', 'neb3'])
  })
})

describe('pickNameDistractors', () => {
  it('excludes only the target, no other restriction', () => {
    const pool = ['a', 'b', 'c', 'd']
    const distractors = pickNameDistractors('a', pool, 3)
    expect(distractors).not.toContain('a')
    expect(distractors.sort()).toEqual(['b', 'c', 'd'])
  })
})
