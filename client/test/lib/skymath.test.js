import { describe, it, expect } from 'vitest'
import { projectGnomonic, toPixel, projectToPixel, isOnScreen } from '../../src/lib/skymath.js'

const W = 800,
  H = 600,
  fov = 30,
  rot = 0

describe('projectGnomonic', () => {
  it('centre projects to (0, 0)', () => {
    const pt = projectGnomonic(45, 20, 45, 20)
    expect(pt).not.toBeNull()
    expect(pt.x).toBeCloseTo(0)
    expect(pt.y).toBeCloseTo(0)
  })

  it('returns null for point directly behind (cos_c <= 0)', () => {
    // antipodal point: dec0=45, opposite is dec=-45 at ra+180
    const pt = projectGnomonic(225, -45, 45, 45)
    expect(pt).toBeNull()
  })

  it('RA wrap-around: RA=359 with centre RA=1 same offset as RA=-1', () => {
    const pt1 = projectGnomonic(359, 0, 1, 0)
    const pt2 = projectGnomonic(-1, 0, 1, 0)
    expect(pt1).not.toBeNull()
    expect(pt2).not.toBeNull()
    expect(pt1.x).toBeCloseTo(pt2.x, 10)
    expect(pt1.y).toBeCloseTo(pt2.y, 10)
  })
})

describe('toPixel', () => {
  it('centre (0,0) maps to (W/2, H/2)', () => {
    const { px, py } = toPixel(0, 0, W, H, fov, 0)
    expect(px).toBeCloseTo(W / 2)
    expect(py).toBeCloseTo(H / 2)
  })

  it('rotation=PI/2 swaps x/y contribution', () => {
    // A purely-x offset at rot=0 should become a purely-y offset at rot=PI/2
    const { px: px0, py: py0 } = toPixel(1, 0, W, H, fov, 0)
    const { px: pxR, py: pyR } = toPixel(1, 0, W, H, fov, Math.PI / 2)
    // At rot=0: mirrored projection means +x is left of centre.
    expect(px0).toBeLessThan(W / 2)
    expect(py0).toBeCloseTo(H / 2)
    // At rot=PI/2: x contribution rotates into y axis
    expect(pxR).toBeCloseTo(W / 2, 5)
    expect(pyR).not.toBeCloseTo(H / 2)
  })
})

describe('projectToPixel', () => {
  it('centre projects to (W/2, H/2)', () => {
    const pt = projectToPixel(45, 20, 45, 20, W, H, fov, rot)
    expect(pt).not.toBeNull()
    expect(pt.px).toBeCloseTo(W / 2)
    expect(pt.py).toBeCloseTo(H / 2)
  })

  it('object at dec0+fov/2 projects near top edge', () => {
    // Gnomonic maps angular offset θ to tan(θ)·scale, so dec0+fov/2 lands just
    // above the top edge (py slightly negative) — confirm it's close to 0.
    const pt = projectToPixel(45, 35, 45, 20, W, H, fov, rot)
    expect(pt).not.toBeNull()
    const scale = H / ((fov * Math.PI) / 180)
    const expected_py = H / 2 - Math.tan(((fov / 2) * Math.PI) / 180) * scale
    expect(pt.py).toBeCloseTo(expected_py, 3)
  })

  it('behind-plane object returns null', () => {
    expect(projectToPixel(225, -45, 45, 45, W, H, fov, rot)).toBeNull()
  })
})

describe('isOnScreen', () => {
  it('centre is on screen', () => {
    expect(isOnScreen(W / 2, H / 2, W, H)).toBe(true)
  })

  it('outside bounds is off screen', () => {
    expect(isOnScreen(-1, H / 2, W, H)).toBe(false)
    expect(isOnScreen(W + 1, H / 2, W, H)).toBe(false)
  })

  it('margin extends bounds', () => {
    expect(isOnScreen(-5, H / 2, W, H, 10)).toBe(true)
  })
})
