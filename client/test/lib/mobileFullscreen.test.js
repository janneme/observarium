import { describe, it, expect, vi } from 'vitest'
import { MobileFullscreenStarter } from '../../src/lib/mobileFullscreen.js'

function createDoc() {
  const listeners = new Map()
  return {
    fullscreenEnabled: true,
    fullscreenElement: null,
    documentElement: {
      requestFullscreen: vi.fn().mockResolvedValue(undefined),
    },
    addEventListener: vi.fn((event, handler) => {
      listeners.set(event, handler)
    }),
    removeEventListener: vi.fn((event) => {
      listeners.delete(event)
    }),
    listeners,
  }
}

describe('MobileFullscreenStarter', () => {
  it('skips fullscreen on non-mobile context', async () => {
    const doc = createDoc()
    const starter = new MobileFullscreenStarter({
      doc,
      win: {
        innerWidth: 1440,
        innerHeight: 900,
        matchMedia: vi.fn((query) => ({ matches: query === '(pointer: coarse)' ? false : false })),
      },
      nav: { maxTouchPoints: 0 },
      target: doc.documentElement,
    })

    const started = await starter.start()

    expect(started).toBe(false)
    expect(doc.documentElement.requestFullscreen).not.toHaveBeenCalled()
  })

  it('attempts fullscreen immediately on mobile context', async () => {
    const doc = createDoc()
    const starter = new MobileFullscreenStarter({
      doc,
      win: {
        innerWidth: 390,
        innerHeight: 844,
        matchMedia: vi.fn((query) => ({ matches: query === '(pointer: coarse)' || query === '(hover: none)' })),
      },
      nav: { maxTouchPoints: 5 },
      target: doc.documentElement,
    })

    const started = await starter.start()

    expect(started).toBe(true)
    expect(doc.documentElement.requestFullscreen).toHaveBeenCalledTimes(1)
  })

  it('installs gesture fallback when immediate fullscreen fails', async () => {
    const doc = createDoc()
    doc.documentElement.requestFullscreen = vi.fn().mockRejectedValue(new Error('gesture required'))

    const starter = new MobileFullscreenStarter({
      doc,
      win: {
        innerWidth: 393,
        innerHeight: 852,
        matchMedia: vi.fn((query) => ({ matches: query === '(pointer: coarse)' || query === '(hover: none)' })),
      },
      nav: { maxTouchPoints: 5 },
      target: doc.documentElement,
    })

    const started = await starter.start()

    expect(started).toBe(false)
    expect(doc.addEventListener).toHaveBeenCalledWith('pointerup', expect.any(Function), { passive: true })
    expect(doc.addEventListener).toHaveBeenCalledWith('touchend', expect.any(Function), { passive: true })
    expect(doc.addEventListener).toHaveBeenCalledWith('click', expect.any(Function), { passive: true })
  })
})
