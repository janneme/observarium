<script>
  import { onMount, onDestroy } from 'svelte'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import TopBar from '../components/TopBar.svelte'
  import MenuPanel from '../components/MenuPanel.svelte'
  import DateTimePicker from '../components/DateTimePicker.svelte'
  import AboutPanel from '../components/AboutPanel.svelte'
  import DataSyncPanel from '../components/DataSyncPanel.svelte'
  import FinderPanel from '../components/FinderPanel.svelte'
  import LoupePanel from '../components/LoupePanel.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import ObjectDetails from '../screens/ObjectDetails.svelte'
  import { getObjectsInArea } from '../lib/db.js'
  import { zenith } from '../lib/horizon.js'
  import { projectToPixel } from '../lib/skymath.js'
  import { selectedObject } from '../stores/selectedObject.js'
  import {
    showFovCircle,
    showConstellationLines,
    showConstellationNames,
    showConstellationBoundaries,
    showDsos,
    showHorizon,
    finderViewActive,
    searchViewActive,
    objectDetailsActive,
    pendingFocus,
  } from '../stores/ui.js'
  import { get } from 'svelte/store'

  let lat = 48.2 // default: Vienna
  let lon = 16.37
  let time = new Date()
  let ra0 = 0
  let dec0 = 0
  let fov = 60
  let objects = []
  let loading = true

  const FOV_STEP = 0.2 // fractional FOV change per +/- keypress
  const PAN_STEP = 0.5 // fraction of FOV to pan per arrow keypress

  let loadRa0 = 0
  let loadDec0 = 0
  let loadMargin = 0
  let loadMagLimit = 0
  let fetching = false

  const NORMAL_VIEW_MIN_FOV = 2
  const NORMAL_VIEW_MAX_FOV = 120
  const EUROPE_MIN_DEC = -35
  const TAP_THRESHOLD = 5
  const TAP_RADIUS = 20

  let screenEl
  let showLoupe = false
  let loupeRa0 = 0
  let loupeDec0 = 0
  let loupeFov = 1
  let loupeMagLim = 10
  const pointers = new Map()

  let menuOpen = false
  let showPicker = false
  let showAbout = false
  let showSync = false

  // Must stay in sync with adaptiveMagLimit in SkyCanvas (same FOV_MAG5=120, FOV_MAG14=2 anchors).
  // Ceiling ensures loaded ≥ rendered for every FOV value.
  function fovToMagLimit(f) {
    return Math.min(14, Math.ceil(Math.max(5, 5 + (9 * Math.log2(120 / f)) / Math.log2(60))))
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
    if (
      dRa > loadMargin * 0.5 ||
      dDec > loadMargin * 0.5 ||
      fov > loadMargin / 1.5 ||
      fovToMagLimit(fov) > loadMagLimit
    ) {
      loadObjects()
    }
  }

  function angSepDeg([ra1, dec1], [ra2, dec2]) {
    const r = Math.PI / 180
    return Math.acos(Math.max(-1, Math.min(1,
      Math.sin(dec1*r)*Math.sin(dec2*r) +
      Math.cos(dec1*r)*Math.cos(dec2*r)*Math.cos((ra2-ra1)*r)
    ))) / r
  }

  function adaptiveMagLimit(fovDeg) {
    return Math.min(14, Math.max(5, 5 + (9 * Math.log2(120 / fovDeg)) / Math.log2(60)))
  }

  function applyPan(dx, dy, raC, decC, W, H, fovDeg) {
    const fovRad = (fovDeg * Math.PI) / 180
    const scale = H / fovRad
    const x = -dx / scale
    const y = dy / scale
    const rho = Math.sqrt(x * x + y * y)
    if (rho < 1e-10) return { ra0: raC, dec0: decC }
    const dec0_r = (decC * Math.PI) / 180
    const c = Math.atan(rho)
    const sinC = Math.sin(c),
      cosC = Math.cos(c)
    const dec_r = Math.asin(Math.max(-1, Math.min(1, cosC * Math.sin(dec0_r) + (y * sinC * Math.cos(dec0_r)) / rho)))
    const ra_r =
      (raC * Math.PI) / 180 + Math.atan2(x * sinC, rho * Math.cos(dec0_r) * cosC - y * Math.sin(dec0_r) * sinC)
    const decMin = EUROPE_MIN_DEC + fovDeg / 2
    return {
      ra0: ((((ra_r * 180) / Math.PI) % 360) + 360) % 360,
      dec0: Math.max(decMin, Math.min(90, (dec_r * 180) / Math.PI)),
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
      ra0 = result.ra0
      dec0 = result.dec0
      maybeReload()
    } else if (pointers.size === 2) {
      const ids = [...pointers.keys()]
      const other = pointers.get(ids.find((id) => id !== e.pointerId))
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

  function handlePointerCancel(e) {
    pointers.delete(e.pointerId)
  }

  function handleTap(clientX, clientY) {
    if (!screenEl) return
    const rect = screenEl.getBoundingClientRect()
    const tapX = clientX - rect.left,
      tapY = clientY - rect.top
    const W = rect.width,
      H = rect.height
    const magLim = adaptiveMagLimit(fov)
    const dsoMagLim = 8 + 0.5 * (magLim - 5)
    let hits = []
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
    if (hits.some((h) => h.obj.type === 'star' && h.obj.dbl)) {
      hits = hits.filter((h) => h.obj.type !== 'double_star')
    }
    if (hits.length === 0) {
      selectedObject.set(null)
    } else if (hits.length === 1) {
      if (get(selectedObject)?.id === hits[0].obj.id) {
        selectedObject.set(null)
        objectDetailsActive.set(false)
      } else {
        selectedObject.set(hits[0].obj)
      }
    } else {
      const centRa  = hits.reduce((s, h) => s + h.obj.pos[0], 0) / hits.length
      const centDec = hits.reduce((s, h) => s + h.obj.pos[1], 0) / hits.length
      let minSep = Infinity
      for (let i = 0; i < hits.length; i++)
        for (let j = i + 1; j < hits.length; j++) {
          const s = angSepDeg(hits[i].obj.pos, hits[j].obj.pos)
          if (s < minSep) minSep = s
        }
      loupeFov    = Math.max(0.05, Math.min(10, minSep * window.innerWidth / (3 * TAP_RADIUS)))
      loupeRa0    = centRa
      loupeDec0   = centDec
      loupeMagLim = fovToMagLimit(fov)
      showLoupe   = true
    }
  }

  $: if ($pendingFocus) {
    ra0 = $pendingFocus.ra
    dec0 = $pendingFocus.dec
    pendingFocus.set(null)
    maybeReload()
  }

  function handleKey(e) {
    if (e.key === 'Escape') {
      if (get(objectDetailsActive)) {
        objectDetailsActive.set(false)
        e.preventDefault()
        return
      }
    }

    if (get(searchViewActive)) return

    if (e.key === 'm') {
      searchViewActive.set(false)
      objectDetailsActive.set(false)
      menuOpen = !menuOpen
      e.preventDefault()
      return
    }

    // s = sync when menu open, search when menu closed
    if (e.key === 's') {
      if (menuOpen) {
        menuOpen = false
        showSync = true
      } else {
        objectDetailsActive.set(false)
        searchViewActive.update((v) => !v)
      }
      e.preventDefault()
      return
    }

    if (e.key === 'c') { showConstellationLines.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'C') { showConstellationNames.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'b') { showConstellationBoundaries.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'd') { showDsos.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'h') { showHorizon.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'f') { finderViewActive.update((v) => !v); e.preventDefault(); return }
    if (e.key === 'o') { menuOpen = false; e.preventDefault(); return }
    if (e.key === 't') { menuOpen = false; e.preventDefault(); return }
    if (e.key === 'u') { menuOpen = false; showSync = true; e.preventDefault(); return }
    if (e.key === 'a') { menuOpen = false; showAbout = true; e.preventDefault(); return }

    if (menuOpen) return

    if (e.key === '+' || e.key === '=') {
      fov = Math.max(0.1, fov * (1 - FOV_STEP))
    } else if (e.key === '-') {
      fov = Math.min(180, fov * (1 + FOV_STEP))
    } else if (e.key === 'ArrowRight') {
      const step = (fov * PAN_STEP) / Math.cos((dec0 * Math.PI) / 180)
      ra0 = (((ra0 + step) % 360) + 360) % 360
    } else if (e.key === 'ArrowLeft') {
      const step = (fov * PAN_STEP) / Math.cos((dec0 * Math.PI) / 180)
      ra0 = (((ra0 - step) % 360) + 360) % 360
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

  function handleWheel(e) {
    // ctrlKey=true is how Chrome/Safari report trackpad pinch on desktop
    if (e.ctrlKey) {
      e.preventDefault()
      fov = Math.max(NORMAL_VIEW_MIN_FOV, Math.min(NORMAL_VIEW_MAX_FOV, fov * Math.pow(1.008, e.deltaY)))
      maybeReload()
    }
  }

  onMount(() => {
    window.addEventListener('keydown', handleKey)
    window.addEventListener('wheel', handleWheel, { passive: false })
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => init(pos.coords.latitude, pos.coords.longitude),
        () => init(lat, lon),
        { timeout: 5000 },
      )
    } else {
      init(lat, lon)
    }
  })

  onDestroy(() => {
    window.removeEventListener('keydown', handleKey)
    window.removeEventListener('wheel', handleWheel)
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
    <SkyCanvas
      {ra0}
      {dec0}
      {fov}
      {objects}
      {lat}
      {lon}
      {time}
      showFovCircle={$showFovCircle}
      showConstellationLines={$showConstellationLines}
      showConstellationNames={$showConstellationNames}
      showConstellationBoundaries={$showConstellationBoundaries}
      showDsos={$showDsos}
      showHorizon={$showHorizon}
    />
  {/if}

  <TopBar
    {time}
    {menuOpen}
    on:menutoggle={() => {
      searchViewActive.set(false)
      objectDetailsActive.set(false)
      menuOpen = !menuOpen
    }}
    on:searchtoggle={() => {
      menuOpen = false
      objectDetailsActive.set(false)
      searchViewActive.update((v) => !v)
    }}
    on:timepick={() => {
      showPicker = true
    }}
    on:objectdetails={() => {
      objectDetailsActive.set(true)
    }}
  />

  <MenuPanel
    open={menuOpen}
    on:close={() => {
      menuOpen = false
    }}
    on:about={() => {
      showAbout = true
    }}
    on:update={() => {
      showSync = true
    }}
  />

  {#if showPicker}
    <DateTimePicker
      {time}
      on:pick={(e) => {
        time = e.detail
        showPicker = false
      }}
      on:cancel={() => {
        showPicker = false
      }}
    />
  {/if}

  {#if showAbout}
    <AboutPanel
      on:close={() => {
        showAbout = false
      }}
    />
  {/if}

  {#if showSync}
    <DataSyncPanel
      on:close={() => {
        showSync = false
      }}
      on:synced={loadObjects}
    />
  {/if}

  {#if $finderViewActive}
    <FinderPanel mainRa0={ra0} mainDec0={dec0} {lat} {lon} {time} />
  {/if}

  {#if $searchViewActive}
    <SearchPanel />
  {/if}

  {#if $objectDetailsActive}
    <ObjectDetails {lat} {lon} {time} />
  {/if}

  {#if showLoupe}
    <LoupePanel
      ra0={loupeRa0}
      dec0={loupeDec0}
      fov={loupeFov}
      {objects}
      {lat} {lon} {time}
      magLimit={loupeMagLim}
      on:select={(e) => {
        showLoupe = false
        if (get(selectedObject)?.id === e.detail.obj.id) {
          selectedObject.set(null)
        } else {
          selectedObject.set(e.detail.obj)
        }
      }}
      on:close={() => { showLoupe = false }}
    />
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
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.9rem;
  }
</style>
