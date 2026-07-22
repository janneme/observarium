import { describe, it, expect } from 'vitest'
import {
  buildGlobalPools,
  buildLocalPools,
  pickDistractors,
  GLOBAL_EASY_CRATERS,
  GLOBAL_EASY_SEA,
  GLOBAL_MEDIUM_CRATERS,
  GLOBAL_MEDIUM_OTHER,
  LOCAL_MIN_POOL_SIZE,
} from '../../src/lib/moonQuizPools.js'

function mkFeature(name, type, sizeDeg, { lon = 0, lat = 0 } = {}) {
  return { id: `${type}::${name}`, type, name, lat, lon, sizeDeg, layers: [] }
}

// All at lon=0/lat=0 (sub-Earth point) so every synthetic feature is visible
// at the mean view (cosC = 1) regardless of size — keeps the global-pool
// tests focused purely on the ranking/bucketing logic.
function buildSyntheticCatalogue() {
  const craters = Array.from({ length: 25 }, (_, i) => mkFeature(`crater${i}`, 'crater', 100 - i))
  const sea = Array.from({ length: 25 }, (_, i) => mkFeature(`sea${i}`, 'mare', 75 - i))
  const ridge = Array.from({ length: 10 }, (_, i) => mkFeature(`ridge${i}`, 'mons', 50 - i))
  return [...craters, ...sea, ...ridge]
}

describe('buildGlobalPools', () => {
  const all = buildSyntheticCatalogue()

  it('easy: top craters + top sea, no ridge-like', () => {
    const { questionPool } = buildGlobalPools(all, 'easy')
    expect(questionPool).toHaveLength(GLOBAL_EASY_CRATERS + GLOBAL_EASY_SEA)
    expect(questionPool).toContain('crater::crater0') // sizeDeg 100, biggest
    expect(questionPool).toContain('crater::crater4') // sizeDeg 96, 5th biggest
    expect(questionPool).not.toContain('crater::crater5') // sizeDeg 95, 6th — excluded
    expect(questionPool).toContain('mare::sea0') // sizeDeg 75, biggest sea
    expect(questionPool).toContain('mare::sea14') // 15th biggest sea
    expect(questionPool).not.toContain('mare::sea15')
    expect(questionPool.some((id) => id.startsWith('mons::'))).toBe(false)
  })

  it('medium: top craters + top (sea ∪ ridge-like) combined', () => {
    const { questionPool } = buildGlobalPools(all, 'medium')
    expect(questionPool).toHaveLength(GLOBAL_MEDIUM_CRATERS + GLOBAL_MEDIUM_OTHER)
    expect(questionPool).toContain('crater::crater19') // 20th biggest crater
    expect(questionPool).not.toContain('crater::crater20')
    // "other" = all 25 sea (biggest 25 available) + the 5 biggest ridge-like
    // (sea sizes 51-75 all beat ridge sizes 41-50, so sea sweeps first).
    expect(questionPool.filter((id) => id.startsWith('mare::'))).toHaveLength(25)
    expect(questionPool).toContain('mons::ridge0') // sizeDeg 50, biggest ridge
    expect(questionPool).toContain('mons::ridge4') // 5th biggest ridge
    expect(questionPool).not.toContain('mons::ridge5')
  })

  it('hard: everything visible, no per-type split', () => {
    const { questionPool, renderPool } = buildGlobalPools(all, 'hard')
    expect(questionPool).toHaveLength(all.length)
    expect(renderPool).toEqual(questionPool)
  })

  it('render pool is always the Hard-tier pool, independent of difficulty', () => {
    const easy = buildGlobalPools(all, 'easy')
    const medium = buildGlobalPools(all, 'medium')
    const hard = buildGlobalPools(all, 'hard')
    expect(easy.renderPool).toEqual(hard.renderPool)
    expect(medium.renderPool).toEqual(hard.renderPool)
  })

  it('easy ⊆ medium ⊆ hard (question pools)', () => {
    const easy = buildGlobalPools(all, 'easy').questionPool
    const medium = buildGlobalPools(all, 'medium').questionPool
    const hard = buildGlobalPools(all, 'hard').questionPool
    expect(easy.every((id) => medium.includes(id))).toBe(true)
    expect(medium.every((id) => hard.includes(id))).toBe(true)
  })

  it('excludes features not visible at the mean view (limb/far side)', () => {
    const farSide = mkFeature('farside', 'crater', 200, { lon: 179 })
    const { questionPool, renderPool } = buildGlobalPools([...all, farSide], 'hard')
    expect(questionPool).not.toContain(farSide.id)
    expect(renderPool).not.toContain(farSide.id)
  })
})

describe('buildLocalPools', () => {
  // subLat=0, subLon=0 fixed; illumCos(lat=0, lon, sunLon) = cos((lon-sunLon)*D2R).
  // Solve for lon given a desired illumCos value c, staying on the branch
  // that keeps cosC = cos(lon) comfortably above LIMB_COS_CUTOFF (0.15).
  const SUN_LON = 45
  const D2R = Math.PI / 180
  function lonForIllumCos(c) {
    return SUN_LON - Math.acos(c) / D2R
  }
  const viewing = { subLat: 0, subLon: 0, sunLon: SUN_LON }

  it('takes top 30%/100% by size from the terminator-near subset', () => {
    // 20 features comfortably within the default near-terminator band
    // (illumCos spread across (0, 0.3)) — enough to avoid widening.
    const near = Array.from({ length: LOCAL_MIN_POOL_SIZE }, (_, i) =>
      mkFeature(`near${i}`, 'crater', 100 - i, { lon: lonForIllumCos((0.29 * (i + 1)) / LOCAL_MIN_POOL_SIZE) })
    )
    const { questionPool, renderPool } = buildLocalPools(near, 'medium', viewing)
    expect(renderPool).toHaveLength(LOCAL_MIN_POOL_SIZE)
    expect(questionPool).toHaveLength(Math.round(LOCAL_MIN_POOL_SIZE * 0.3))
    // Medium's question pool must be the biggest-by-size subset of renderPool.
    expect(questionPool).toContain('crater::near0') // sizeDeg 100, biggest
  })

  it('hard uses the entire terminator-near set (100%)', () => {
    const near = Array.from({ length: LOCAL_MIN_POOL_SIZE }, (_, i) =>
      mkFeature(`near${i}`, 'crater', 100 - i, { lon: lonForIllumCos((0.29 * (i + 1)) / LOCAL_MIN_POOL_SIZE) })
    )
    const { questionPool, renderPool } = buildLocalPools(near, 'hard', viewing)
    expect(questionPool).toEqual(renderPool)
    expect(questionPool).toHaveLength(LOCAL_MIN_POOL_SIZE)
  })

  it('widens the terminator-proximity threshold when too few features qualify', () => {
    // Only 3 candidates, all just outside the default 0.3 threshold — none
    // would qualify without widening.
    const borderline = Array.from({ length: 3 }, (_, i) => mkFeature(`b${i}`, 'crater', 10, { lon: lonForIllumCos(0.35 + i * 0.01) }))
    const { renderPool } = buildLocalPools(borderline, 'hard', viewing)
    expect(renderPool).toHaveLength(3)
  })

  it('does not widen once the base terminator-near set is already big enough', () => {
    const near = Array.from({ length: LOCAL_MIN_POOL_SIZE }, (_, i) =>
      mkFeature(`near${i}`, 'crater', 100 - i, { lon: lonForIllumCos((0.29 * (i + 1)) / LOCAL_MIN_POOL_SIZE) })
    )
    const tooFarFromTerminator = mkFeature('toolit', 'crater', 999, { lon: lonForIllumCos(0.4) })
    const { renderPool } = buildLocalPools([...near, tooFarFromTerminator], 'hard', viewing)
    expect(renderPool).not.toContain(tooFarFromTerminator.id)
    expect(renderPool).toHaveLength(LOCAL_MIN_POOL_SIZE)
  })
})

describe('pickDistractors', () => {
  it('only picks distractors sharing the target broad type bucket', () => {
    const target = mkFeature('target', 'crater', 50)
    const otherCrater = mkFeature('other-crater', 'crater', 40)
    const sea = mkFeature('sea', 'mare', 60)
    const ridge = mkFeature('ridge', 'mons', 30)
    const pool = [target.id, otherCrater.id, sea.id, ridge.id]
    const featuresById = new Map([target, otherCrater, sea, ridge].map((f) => [f.id, f]))

    const distractors = pickDistractors(target, pool, pool, featuresById, 3)
    expect(distractors).toEqual([otherCrater.id])
  })

  it('treats mons/catena/vallis as one ridge-like bucket', () => {
    const target = mkFeature('target', 'mons', 50)
    const catena = mkFeature('c', 'catena', 40)
    const vallis = mkFeature('v', 'vallis', 30)
    const crater = mkFeature('cr', 'crater', 20)
    const pool = [target.id, catena.id, vallis.id, crater.id]
    const featuresById = new Map([target, catena, vallis, crater].map((f) => [f.id, f]))

    const distractors = pickDistractors(target, pool, pool, featuresById, 3)
    expect(distractors.sort()).toEqual([catena.id, vallis.id].sort())
  })

  it('falls back to the render pool when the question pool bucket is thin', () => {
    const target = mkFeature('target', 'crater', 50)
    const onlyDistractorInQuestionPool = mkFeature('qp-crater', 'crater', 40)
    const renderOnlyCraters = [mkFeature('r1', 'crater', 39), mkFeature('r2', 'crater', 38)]
    const sea = mkFeature('sea', 'mare', 60)

    const questionPool = [target.id, onlyDistractorInQuestionPool.id, sea.id]
    const renderPool = [...questionPool, ...renderOnlyCraters.map((f) => f.id)]
    const featuresById = new Map(
      [target, onlyDistractorInQuestionPool, sea, ...renderOnlyCraters].map((f) => [f.id, f])
    )

    const distractors = pickDistractors(target, questionPool, renderPool, featuresById, 3)
    expect(distractors).toHaveLength(3)
    expect(distractors).toContain(onlyDistractorInQuestionPool.id)
    for (const id of distractors) {
      expect(featuresById.get(id).type).toBe('crater')
    }
  })
})
