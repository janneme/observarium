<script>
  import { createEventDispatcher } from 'svelte'
  import SkyCanvas from './SkyCanvas.svelte'
  import { projectToPixel } from '../lib/skymath.js'

  export let ra0 = 0
  export let dec0 = 0
  export let fov = 1
  export let objects = []
  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()
  export let magLimit = 10

  const dispatch = createEventDispatcher()
  const TAP_THRESHOLD = 5

  let wrapEl
  const pointers = new Map()

  function handlePointerDown(e) {
    e.preventDefault()
    wrapEl.setPointerCapture(e.pointerId)
    pointers.set(e.pointerId, { startX: e.clientX, startY: e.clientY })
  }

  function handlePointerUp(e) {
    const ptr = pointers.get(e.pointerId)
    if (ptr && Math.hypot(e.clientX - ptr.startX, e.clientY - ptr.startY) < TAP_THRESHOLD) {
      handleTap(e.clientX, e.clientY)
    }
    pointers.delete(e.pointerId)
  }

  function handleTap(clientX, clientY) {
    if (!wrapEl) return
    const rect = wrapEl.getBoundingClientRect()
    const tapX = clientX - rect.left
    const tapY = clientY - rect.top
    const W = rect.width
    const H = rect.height
    const dsoMagLim = 8 + 0.5 * (magLimit - 5)
    let closest = null
    let closestDist = Infinity
    for (const obj of objects) {
      if (!obj.pos) continue
      if (obj.type === 'star' || obj.type === 'double_star') {
        const m = Array.isArray(obj.mag) ? obj.mag[0] : (obj.mag ?? 99)
        if (m > magLimit) continue
      } else if (obj.type === 'dso') {
        if ((obj.mag ?? 8) > dsoMagLim) continue
      } else {
        continue
      }
      const [ra, dec] = obj.pos
      const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, 0)
      if (!pt) continue
      const dist = Math.hypot(pt.px - tapX, pt.py - tapY)
      if (dist < closestDist) {
        closestDist = dist
        closest = obj
      }
    }
    if (closest) dispatch('select', { obj: closest })
  }
</script>

<div class="loupe-overlay" on:pointerdown|stopPropagation>
  <div class="square-container">
    <div class="canvas-wrap" bind:this={wrapEl} on:pointerdown={handlePointerDown} on:pointerup={handlePointerUp}>
      <SkyCanvas
        {ra0}
        {dec0}
        {fov}
        {objects}
        {lat}
        {lon}
        {time}
        magLimitOverride={magLimit}
        starRadiusScale={2}
        finderMode={false}
        showFovCircle={false}
        showConstellationLines={false}
        showConstellationNames={false}
        showConstellationBoundaries={false}
        showDsos={true}
        showHorizon={false}
      />
    </div>
    <button class="close-btn" on:click={() => dispatch('close')} aria-label="Close">✕</button>
  </div>
  <p class="hint">Tap an object to select</p>
</div>

<style>
  .loupe-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    user-select: none;
  }

  .square-container {
    position: relative;
    flex-shrink: 0;
    width: calc(100vw - 2vh);
    aspect-ratio: 1;
    margin: 1vh 1vh 0;
  }

  .square-container::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.35);
    pointer-events: none;
    z-index: 1;
    box-sizing: border-box;
  }

  .canvas-wrap {
    position: absolute;
    inset: 0;
    border-radius: 12px;
    overflow: hidden;
    touch-action: none;
    cursor: crosshair;
  }

  .close-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 1;
    background: rgba(0, 0, 0, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: rgba(255, 255, 255, 0.8);
    border-radius: 6px;
    font-size: 1rem;
    line-height: 1;
    padding: 5px 8px;
    cursor: pointer;
    transition: opacity 120ms;
  }

  .close-btn:hover {
    opacity: 0.75;
  }

  .hint {
    margin: 1.2vh 1vh 0;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.45);
    text-align: center;
  }

  :global([data-theme='nightly']) .loupe-overlay {
    background: #110000;
  }

  :global([data-theme='nightly']) .square-container::after {
    border-color: rgba(180, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .close-btn {
    border-color: rgba(180, 0, 0, 0.3);
    color: rgba(255, 128, 128, 0.8);
  }

  :global([data-theme='nightly']) .hint {
    color: rgba(255, 128, 128, 0.4);
  }
</style>
