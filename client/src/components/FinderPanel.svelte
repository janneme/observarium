<script>
  import { onMount, onDestroy } from 'svelte'
  import SkyCanvas from './SkyCanvas.svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { finderViewActive } from '../stores/ui.js'
  import { getMeta, getObjectsInArea } from '../lib/db.js'

  export let mainRa0 = 0
  export let mainDec0 = 0
  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  const FINDER_FOV = 7.5
  const EUROPE_MIN_DEC = -35
  const EMPTY_SET = new Set()

  let wrapEl
  let finderRa0 = mainRa0
  let finderDec0 = mainDec0
  let objects = []
  let hasPath = false
  const pointers = new Map()

  let prevObjId = undefined
  $: {
    const obj = $selectedObject
    const id = obj?.id ?? null
    if (id !== prevObjId) {
      prevObjId = id
      if (obj?.pos) {
        finderRa0 = obj.pos[0]
        finderDec0 = obj.pos[1]
      }
      void loadObjects()
      void checkPath()
    }
  }

  async function loadObjects() {
    const margin = FINDER_FOV * 2
    objects = await getObjectsInArea(
      finderRa0 - margin, finderRa0 + margin,
      finderDec0 - margin, finderDec0 + margin,
      12
    )
  }

  async function checkPath() {
    const obj = $selectedObject
    if (!obj) { hasPath = false; return }
    try {
      const paths = await getMeta('findingPaths')
      hasPath = !!(paths && paths[obj.id] && Object.keys(paths[obj.id]).length > 0)
    } catch {
      hasPath = false
    }
  }

  function applyPan(dx, dy, raC, decC, sizePx) {
    const fovRad = FINDER_FOV * Math.PI / 180
    const scale = sizePx / fovRad
    const x = -dx / scale
    const y = dy / scale
    const rho = Math.sqrt(x * x + y * y)
    if (rho < 1e-10) return { ra0: raC, dec0: decC }
    const dec0_r = decC * Math.PI / 180
    const c = Math.atan(rho)
    const sinC = Math.sin(c), cosC = Math.cos(c)
    const dec_r = Math.asin(Math.max(-1, Math.min(1,
      cosC * Math.sin(dec0_r) + y * sinC * Math.cos(dec0_r) / rho
    )))
    const ra_r = raC * Math.PI / 180 + Math.atan2(
      x * sinC,
      rho * Math.cos(dec0_r) * cosC - y * Math.sin(dec0_r) * sinC
    )
    const decMin = EUROPE_MIN_DEC + FINDER_FOV / 2
    return {
      ra0: ((ra_r * 180 / Math.PI) % 360 + 360) % 360,
      dec0: Math.max(decMin, Math.min(90, dec_r * 180 / Math.PI))
    }
  }

  function handlePointerDown(e) {
    e.preventDefault()
    wrapEl.setPointerCapture(e.pointerId)
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  function handlePointerMove(e) {
    if (!pointers.has(e.pointerId)) return
    const prev = pointers.get(e.pointerId)
    if (pointers.size === 1) {
      const rect = wrapEl.getBoundingClientRect()
      if (rect.width > 0) {
        const result = applyPan(e.clientX - prev.x, e.clientY - prev.y, finderRa0, finderDec0, rect.width)
        finderRa0 = result.ra0
        finderDec0 = result.dec0
      }
    }
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  function handlePointerUp(e) {
    pointers.delete(e.pointerId)
    if (pointers.size === 0) void loadObjects()
  }

  function handlePointerCancel(e) { pointers.delete(e.pointerId) }

  function panStep(dRa, dDec) {
    const step = FINDER_FOV / 3
    const decMin = EUROPE_MIN_DEC + FINDER_FOV / 2
    if (dRa !== 0) {
      const raStep = step / Math.max(0.1, Math.cos(finderDec0 * Math.PI / 180))
      finderRa0 = ((finderRa0 + dRa * raStep) % 360 + 360) % 360
    }
    if (dDec !== 0) {
      finderDec0 = Math.max(decMin, Math.min(90, finderDec0 + dDec * step))
    }
    void loadObjects()
  }

  function handleKey(e) {
    const decMin = EUROPE_MIN_DEC + FINDER_FOV / 2
    const step = FINDER_FOV / 3
    if (e.key === 'ArrowRight') {
      finderRa0 = ((finderRa0 + step / Math.max(0.1, Math.cos(finderDec0 * Math.PI / 180))) % 360 + 360) % 360
    } else if (e.key === 'ArrowLeft') {
      finderRa0 = ((finderRa0 - step / Math.max(0.1, Math.cos(finderDec0 * Math.PI / 180))) % 360 + 360) % 360
    } else if (e.key === 'ArrowUp') {
      finderDec0 = Math.min(90, finderDec0 + step)
    } else if (e.key === 'ArrowDown') {
      finderDec0 = Math.max(decMin, finderDec0 - step)
    } else {
      return
    }
    e.preventDefault()
    e.stopPropagation()
    void loadObjects()
  }

  onMount(() => window.addEventListener('keydown', handleKey, true))
  onDestroy(() => window.removeEventListener('keydown', handleKey, true))

  function switchToMain() { finderViewActive.set(false) }

  function stub(label) { console.log('[FinderPanel] stub:', label) }
</script>

<div class="finder-overlay" on:pointerdown={e => e.stopPropagation()}>
  <div class="circle-container">
    <div
        class="circle-wrap"
        bind:this={wrapEl}
        on:pointerdown={handlePointerDown}
        on:pointermove={handlePointerMove}
        on:pointerup={handlePointerUp}
        on:pointercancel={handlePointerCancel}
      >
        <SkyCanvas
          ra0={finderRa0}
          dec0={finderDec0}
          fov={FINDER_FOV}
          {objects}
          {lat}
          {lon}
          {time}
          finderMode={true}
          showFovCircle={false}
          showConstellationLines={false}
          showConstellationNames={false}
          showConstellationBoundaries={false}
          showDsos={true}
          showHorizon={true}
          flashIds={EMPTY_SET}
        />
      </div>
  </div>

  <div class="scroll-area">
    <button class="finder-btn" on:click={switchToMain}>Switch to normal view</button>
    <button class="finder-btn" on:click={() => stub('search')}>Search object</button>
    {#if hasPath}
      <button class="finder-btn" on:click={() => stub('guide')}>Guide to find the object</button>
    {/if}
    <button class="finder-btn" on:click={() => stub('record')}>Record guide to find object</button>
  </div>
</div>

<style>
.finder-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: #0a0a0a;
  display: flex;
  flex-direction: column;
  user-select: none;
}

.circle-container {
  flex-shrink: 0;
  position: relative;
  width: calc(100vw - 2vh);
  aspect-ratio: 1;
  margin: 1vh 1vh 0;
}

.circle-container::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.25);
  pointer-events: none;
  z-index: 1;
  box-sizing: border-box;
}

.circle-wrap {
  position: absolute;
  inset: 0;
  clip-path: circle(50%);
  touch-action: none;
  cursor: grab;
}

.circle-wrap:active { cursor: grabbing; }

.scroll-area {
  flex: 1;
  overflow-y: auto;
  padding: 1vh 2vh 3vh;
  display: flex;
  flex-direction: column;
  gap: 1.2vh;
}

.finder-btn {
  width: 100%;
  padding: 1.7vh 2vh;
  background: rgba(255,255,255,0.07);
  color: var(--surface-fg, #fff);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 1.2vh;
  font-size: 1.8vh;
  font-family: inherit;
  text-align: center;
  cursor: pointer;
  transition: background 150ms;
  flex-shrink: 0;
}

.finder-btn:hover,
.finder-btn:focus-visible {
  background: rgba(255,255,255,0.13);
  outline: none;
}

:global([data-theme='nightly']) .finder-overlay { background: #110000; }

:global([data-theme='nightly']) .circle-container::after { border-color: rgba(180,0,0,0.3); }

:global([data-theme='nightly']) .finder-btn {
  color: #ff8080;
  border-color: rgba(180,0,0,0.25);
  background: rgba(180,0,0,0.08);
}

:global([data-theme='nightly']) .finder-btn:hover { background: rgba(180,0,0,0.14); }
</style>
