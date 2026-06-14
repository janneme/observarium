<script>
  import { onMount, onDestroy } from 'svelte'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import { getObjectsInArea } from '../lib/db.js'
  import { zenith } from '../lib/horizon.js'
  import { projectToPixel } from '../lib/skymath.js'
  import { selectedObject } from '../stores/selectedObject.js'
  import { showFovCircle } from '../stores/ui.js'

  let lat = 48.2     // default: Vienna
  let lon = 16.37
  let time = new Date()
  let ra0 = 0
  let dec0 = 0
  let fov = 60
  let objects = []
  let loading = true

  const FOV_STEP = 0.20   // fractional FOV change per +/- keypress
  const PAN_STEP = 0.50   // fraction of FOV to pan per arrow keypress

  let loadRa0 = 0
  let loadDec0 = 0
  let loadMargin = 0
  let loadMagLimit = 0
  let fetching = false

  const NORMAL_VIEW_MIN_FOV = 2
  const NORMAL_VIEW_MAX_FOV = 60
  const EUROPE_MIN_DEC = -35
  const TAP_THRESHOLD = 5
  const TAP_RADIUS = 20

  let screenEl
  let flashIds = new Set()
  let flashTimer = null
  const pointers = new Map()

  // Must stay in sync with adaptiveMagLimit in SkyCanvas (same FOV_MAG5=120, FOV_MAG14=2 anchors).
  // Ceiling ensures loaded ≥ rendered for every FOV value.
  function fovToMagLimit(f) {
    return Math.min(14, Math.ceil(Math.max(5, 5 + 9 * Math.log2(120 / f) / Math.log2(60))))
  }

  async function loadObjects() {
    if (fetching) return
    fetching = true
    const margin = fov * 1.5
    objects = await getObjectsInArea(ra0 - margin, ra0 + margin, dec0 - margin, dec0 + margin, fovToMagLimit(fov))
    loadRa0 = ra0
    loadDec0 = dec0
    loadMargin = margin
    loadMagLimit = fovToMagLimit(fov)
    fetching = false
  }

  async function init(latitude, longitude) {
    lat = latitude
    lon = longitude
    time = new Date()
    const z = zenith(lat, lon, time)
    ra0 = z.ra
    dec0 = z.dec
    await loadObjects()
    loading = false
  }

  function maybeReload() {
    if (fetching) return
    const rawDRa = Math.abs(ra0 - loadRa0)
    const dRa = Math.min(rawDRa, 360 - rawDRa)
    const dDec = Math.abs(dec0 - loadDec0)
    // Reload when view centre drifts, FOV grew beyond what was loaded, or zoom-in raises mag limit
    if (dRa > loadMargin * 0.5 || dDec > loadMargin * 0.5 || fov > loadMargin / 1.5 || fovToMagLimit(fov) > loadMagLimit) {
      loadObjects()
    }
  }

  function adaptiveMagLimit(fovDeg) {
    return Math.min(14, Math.max(5, 5 + 9 * Math.log2(120 / fovDeg) / Math.log2(60)))
  }

  function applyPan(dx, dy, raC, decC, W, H, fovDeg) {
    const fovRad = fovDeg * Math.PI / 180
    const scale = H / fovRad
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
    const decMin = EUROPE_MIN_DEC + fovDeg / 2
    return {
      ra0: ((ra_r * 180 / Math.PI) % 360 + 360) % 360,
      dec0: Math.max(decMin, Math.min(90, dec_r * 180 / Math.PI))
    }
  }

  function handlePointerDown(e) {
    e.preventDefault()
    screenEl.setPointerCapture(e.pointerId)
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY })
  }

  function handlePointerMove(e) {
    if (!pointers.has(e.pointerId)) return
    const prev = pointers.get(e.pointerId)
    if (pointers.size === 1) {
      const rect = screenEl.getBoundingClientRect()
      const result = applyPan(e.clientX - prev.x, e.clientY - prev.y, ra0, dec0, rect.width, rect.height, fov)
      ra0 = result.ra0; dec0 = result.dec0
      maybeReload()
    } else if (pointers.size === 2) {
      const ids = [...pointers.keys()]
      const other = pointers.get(ids.find(id => id !== e.pointerId))
      const prevDist = Math.hypot(prev.x - other.x, prev.y - other.y)
      const currDist = Math.hypot(e.clientX - other.x, e.clientY - other.y)
      if (prevDist > 1) {
        fov = Math.max(NORMAL_VIEW_MIN_FOV, Math.min(NORMAL_VIEW_MAX_FOV, fov / (currDist / prevDist)))
        maybeReload()
      }
    }
    pointers.set(e.pointerId, { ...prev, x: e.clientX, y: e.clientY })
  }

  function handlePointerUp(e) {
    const ptr = pointers.get(e.pointerId)
    if (ptr && Math.hypot(e.clientX - ptr.startX, e.clientY - ptr.startY) < TAP_THRESHOLD) {
      handleTap(e.clientX, e.clientY)
    }
    pointers.delete(e.pointerId)
  }

  function handlePointerCancel(e) { pointers.delete(e.pointerId) }

  function handleTap(clientX, clientY) {
    if (!screenEl) return
    const rect = screenEl.getBoundingClientRect()
    const tapX = clientX - rect.left, tapY = clientY - rect.top
    const W = rect.width, H = rect.height
    const magLim = adaptiveMagLimit(fov)
    const dsoMagLim = 8 + 0.5 * (magLim - 5)
    const hits = []
    for (const obj of objects) {
      if (!obj.pos) continue
      if (obj.type === 'star' || obj.type === 'double_star') {
        const m = Array.isArray(obj.mag) ? obj.mag[0] : (obj.mag ?? 99)
        if (m > magLim) continue
      } else if (obj.type === 'dso') {
        if ((obj.mag ?? 8) > dsoMagLim) continue
      } else {
        continue
      }
      const [ra, dec] = obj.pos
      const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, 0)
      if (!pt) continue
      const dist = Math.hypot(pt.px - tapX, pt.py - tapY)
      if (dist <= TAP_RADIUS) hits.push({ obj, dist })
    }
    if (hits.length === 0) {
      selectedObject.set(null)
    } else if (hits.length === 1) {
      selectedObject.set(hits[0].obj)
    } else {
      flashIds = new Set(hits.map(h => h.obj.id))
      if (flashTimer) clearTimeout(flashTimer)
      flashTimer = setTimeout(() => { flashIds = new Set(); flashTimer = null }, 200)
    }
  }

  function handleKey(e) {
    if (e.key === '+' || e.key === '=') {
      fov = Math.max(0.1, fov * (1 - FOV_STEP))
    } else if (e.key === '-') {
      fov = Math.min(180, fov * (1 + FOV_STEP))
    } else if (e.key === 'ArrowRight') {
      const step = fov * PAN_STEP / Math.cos(dec0 * Math.PI / 180)
      ra0 = ((ra0 + step) % 360 + 360) % 360
    } else if (e.key === 'ArrowLeft') {
      const step = fov * PAN_STEP / Math.cos(dec0 * Math.PI / 180)
      ra0 = ((ra0 - step) % 360 + 360) % 360
    } else if (e.key === 'ArrowUp') {
      dec0 = Math.min(90, dec0 + fov * PAN_STEP)
    } else if (e.key === 'ArrowDown') {
      dec0 = Math.max(-90, dec0 - fov * PAN_STEP)
    } else {
      return
    }
    e.preventDefault()
    maybeReload()
  }

  onMount(() => {
    window.addEventListener('keydown', handleKey)
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        pos => init(pos.coords.latitude, pos.coords.longitude),
        () => init(lat, lon),
        { timeout: 5000 }
      )
    } else {
      init(lat, lon)
    }
  })

  onDestroy(() => {
    window.removeEventListener('keydown', handleKey)
    if (flashTimer) clearTimeout(flashTimer)
  })
</script>

<div
  class="main-screen"
  bind:this={screenEl}
  on:pointerdown={handlePointerDown}
  on:pointermove={handlePointerMove}
  on:pointerup={handlePointerUp}
  on:pointercancel={handlePointerCancel}
>
  {#if loading}
    <div class="hint">Locating…</div>
  {:else}
    <SkyCanvas {ra0} {dec0} {fov} {objects} {lat} {lon} {time} showFovCircle={$showFovCircle} {flashIds} />
  {/if}
</div>

<style>
.main-screen {
  width: 100vw;
  height: 100vh;
  background: #000;
  overflow: hidden;
  position: relative;
  touch-action: none;
  user-select: none;
}

.hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(255,255,255,0.4);
  font-size: 0.9rem;
}
</style>
