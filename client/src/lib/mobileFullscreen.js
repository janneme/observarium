class MobileFullscreenStarter {
  constructor({ doc = document, win = window, nav = navigator, target } = {}) {
    this.doc = doc
    this.win = win
    this.nav = nav
    this.target = target || doc.documentElement
    this.boundGestureHandler = this.onUserGesture.bind(this)
    this.gestureHooksInstalled = false
  }

  isMobileBrowser() {
    if (!this.win || !this.nav) return false

    const coarsePointer = typeof this.win.matchMedia === 'function' && this.win.matchMedia('(pointer: coarse)').matches
    const noHover = typeof this.win.matchMedia === 'function' && this.win.matchMedia('(hover: none)').matches
    const hasTouch = (this.nav.maxTouchPoints || 0) > 0
    const smallViewport = Math.min(this.win.innerWidth || 0, this.win.innerHeight || 0) <= 1024

    return (coarsePointer || hasTouch) && (noHover || smallViewport)
  }

  isFullscreenAvailable() {
    return Boolean(this.doc?.fullscreenEnabled && typeof this.target?.requestFullscreen === 'function')
  }

  async enterFullscreen() {
    if (this.doc?.fullscreenElement) return true
    if (!this.isFullscreenAvailable()) return false

    try {
      await this.target.requestFullscreen({ navigationUI: 'hide' })
      this.removeGestureHooks()
      return true
    } catch {
      this.installGestureHooks()
      return false
    }
  }

  installGestureHooks() {
    if (this.gestureHooksInstalled) return
    this.gestureHooksInstalled = true

    this.doc.addEventListener('pointerup', this.boundGestureHandler, { passive: true })
    this.doc.addEventListener('touchend', this.boundGestureHandler, { passive: true })
    this.doc.addEventListener('click', this.boundGestureHandler, { passive: true })
  }

  removeGestureHooks() {
    if (!this.gestureHooksInstalled) return
    this.gestureHooksInstalled = false

    this.doc.removeEventListener('pointerup', this.boundGestureHandler)
    this.doc.removeEventListener('touchend', this.boundGestureHandler)
    this.doc.removeEventListener('click', this.boundGestureHandler)
  }

  async onUserGesture() {
    await this.enterFullscreen()
  }

  async start() {
    if (!this.isMobileBrowser()) return false
    return this.enterFullscreen()
  }
}

export function startMobileFullscreen() {
  const starter = new MobileFullscreenStarter()
  void starter.start()
  return starter
}

export { MobileFullscreenStarter }
