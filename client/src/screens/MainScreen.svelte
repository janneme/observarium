<script>
  import { onMount, onDestroy } from 'svelte'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import TopBar from '../components/TopBar.svelte'
  import MenuPanel from '../components/MenuPanel.svelte'
  import DateTimePicker from '../components/DateTimePicker.svelte'
  import AboutPanel from '../components/AboutPanel.svelte'
  import DataSyncPanel from '../components/DataSyncPanel.svelte'
  import SyncSetupScreen from './SyncSetupScreen.svelte'
  import SyncReportScreen from './SyncReportScreen.svelte'
  import FinderPanel from '../components/FinderPanel.svelte'
  import LoupePanel from '../components/LoupePanel.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import FindingPathsScreen from './FindingPathsScreen.svelte'
  import FindingPathsListScreen from './FindingPathsListScreen.svelte'
  import ObjectDetails from '../screens/ObjectDetails.svelte'
  import TelescopesScreen from '../screens/TelescopesScreen.svelte'
  import VisualRangeSetupScreen from './VisualRangeSetupScreen.svelte'
  import StarQuizScreen from './StarQuizScreen.svelte'
  import ConstellationIdQuizScreen from './ConstellationIdQuizScreen.svelte'
  import MoonQuizScreen from './MoonQuizScreen.svelte'
  import MoonMapScreen from './MoonMapScreen.svelte'
  import ObservationsScreen from './ObservationsScreen.svelte'
  import LoginScreen from './LoginScreen.svelte'
  import { getObjectsInArea, migrateLegacyPendingToSyncDirty, getSyncDirtyTotalCount } from '../lib/db.js'
  import { getTokenStatus } from '../lib/auth.js'
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
    showSolarSystem,
    solarSystemPositions,
    finderViewActive,
    searchViewActive,
    objectDetailsActive,
    pendingFocus,
    pendingChanges,
  } from '../stores/ui.js'
  import { get } from 'svelte/store'
  import { toggleTheme } from '../stores/theme.js'

  let lat = 48.2 // default: Vienna
  let lon = 16.37
  let time = new Date()
  let skyTime = new Date()
  let clockInterval = null
  let usingCustomTime = false // true once the user picks a date other than today; pauses the live clock
  let ra0 = 0
  let dec0 = 0
  let fov = 60
  let objects = []
  let loading = true
  let viewportW = 0
  let viewportH = 0

  const FOV_STEP = 0.2 // fractional FOV change per +/- keypress
  const PAN_STEP = 0.5 // fraction of FOV to pan per arrow keypress

  let loadRa0 = 0
  let loadDec0 = 0
  let loadMargin = 0
  let loadRaMargin = 0
  let loadMagLimit = 0
  let fetching = false

  const NORMAL_VIEW_MIN_FOV = 0.001
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
  let showSyncSetup = false
  let showSyncReport = false
  let syncCategories = { observations: true, findingPaths: true, telescopes: true, eyepieces: true }
  let syncMode = 'merge'
  let syncSource = 'local'
  let syncPlan = null
  let syncReport = null
  let showObservationSyncLogin = false
  let showTelescopes = false
  let showObservations = false
  let showFindingPaths = false
  let findingPathsObject = null
  let findingPathsFromFinder = false
  let findingPathsStateVersion = 0
  let findingPathsStartHip = null
  let findingPathsEditHip = null
  let returnToObservationsFromObjectDetails = false
  let showFindingPathsList = false
  let findingPathsListTargetChip = null
  let showVisualRange = false
  let showStarQuiz = false
  let showConstellationIdQuiz = false
  let showMoonQuiz = false
  let showMoonMap = false
  let findingPathsListStartChip = null
  let returnToFindingPathsListFromFinder = false
  let returnToFindingPathsListFromAbout = false

  // Must stay in sync with adaptiveMagLimit in SkyCanvas (same FOV_MAG5=120, FOV_MAG14=2 anchors).
  // Ceiling ensures loaded ≥ rendered for every FOV value.
  function fovToMagLimit(f) {
    return Math.min(14, Math.ceil(Math.max(5, 5 + (9 * Math.log2(120 / f)) / Math.log2(60))))
  }

  function adaptiveMagLimit(f) {
    return Math.min(14, Math.max(5, 5 + (9 * Math.log2(120 / f)) / Math.log2(60)))
  }

  function computeViewportMagRange(objs, magLimit, centerRa, centerDec, hFovDeg, vFovDeg) {
    let min = Infinity,
      max = -Infinity
    const cosDec = Math.cos((centerDec * Math.PI) / 180)
    for (const obj of objs) {
      if (obj.type !== 'star' && obj.type !== 'double_star') continue
      const m = Array.isArray(obj.mag) ? obj.mag[0] : obj.mag
      if (m == null || m > magLimit) continue
      const [ra, dec] = obj.pos
      if (Math.abs(dec - centerDec) > vFovDeg / 2) continue
      let dRa = Math.abs(ra - centerRa)
      if (dRa > 180) dRa = 360 - dRa
      if (dRa * cosDec > hFovDeg / 2) continue
      if (m < min) min = m
      if (m > max) max = m
    }
    return { min: min === Infinity ? null : min, max: max === -Infinity ? null : max }
  }

  async function loadObjects() {
    if (fetching) return
    fetching = true
    const margin = fov * 1.5
    // Near the celestial poles, cos(dec) → 0, so a fixed RA margin covers an
    // ever-shrinking sliver of the actual visible sky — stars just outside
    // that narrow RA window get excluded even though they're angularly close
    // to the view centre. Scale the RA margin by 1/cos(dec) to compensate.
    const cosDec = Math.max(0.05, Math.cos((dec0 * Math.PI) / 180))
    const raMargin = Math.min(180, margin / cosDec)
    objects = await getObjectsInArea(
      ra0 - raMargin,
      ra0 + raMargin,
      dec0 - margin,
      dec0 + margin,
      fovToMagLimit(minDimFov),
    )
    loadRa0 = ra0
    loadDec0 = dec0
    loadMargin = margin
    loadRaMargin = raMargin
    loadMagLimit = fovToMagLimit(minDimFov)
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
    // dRa is compared against loadRaMargin (already cos(dec)-scaled), not
    // loadMargin — a raw RA-degree drift near the pole can be huge while the
    // view has barely moved on the sky, and vice versa near the equator.
    if (
      dRa > loadRaMargin * 0.5 ||
      dDec > loadMargin * 0.5 ||
      fov > loadMargin / 1.5 ||
      fovToMagLimit(minDimFov) > loadMagLimit
    ) {
      loadObjects()
    }
  }

  function angSepDeg([ra1, dec1], [ra2, dec2]) {
    const r = Math.PI / 180
    return (
      Math.acos(
        Math.max(
          -1,
          Math.min(
            1,
            Math.sin(dec1 * r) * Math.sin(dec2 * r) +
              Math.cos(dec1 * r) * Math.cos(dec2 * r) * Math.cos((ra2 - ra1) * r),
          ),
        ),
      ) / r
    )
  }

  function applyPan(dx, dy, raC, decC, W, H, fovDeg) {
    const fovRad = (fovDeg * Math.PI) / 180
    const scale = H / fovRad
    const x = dx / scale
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
    const magLim = adaptiveMagLimit(minDimFov)
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
    if (get(showSolarSystem)) {
      const PLANET_RADII_KM = {
        Sun: 696000,
        Moon: 1737,
        Mercury: 2440,
        Venus: 6052,
        Mars: 3397,
        Jupiter: 71492,
        Saturn: 60268,
        Uranus: 25559,
        Neptune: 24766,
        Pluto: 1188,
      }
      const AU_KM = 149597870.7
      for (const body of get(solarSystemPositions)) {
        const pt = projectToPixel(body.ra, body.dec, ra0, dec0, W, H, fov, 0)
        if (!pt) continue
        const physR = PLANET_RADII_KM[body.name]
        const imgR = physR && body.distAU ? (physR / (body.distAU * AU_KM) / ((fov * Math.PI) / 180)) * H : 0
        const hitR = Math.max(TAP_RADIUS, imgR)
        const dist = Math.hypot(pt.px - tapX, pt.py - tapY)
        if (dist <= hitR) {
          hits.push({
            obj: {
              id: `solar_${body.imageId || body.name.toLowerCase()}`,
              name: body.name,
              pos: [body.ra, body.dec],
              type: 'solar_system_body',
              bodyClass: body.bodyClass,
            },
            dist,
          })
        }
      }
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
      const centRa = hits.reduce((s, h) => s + h.obj.pos[0], 0) / hits.length
      const centDec = hits.reduce((s, h) => s + h.obj.pos[1], 0) / hits.length
      let minSep = Infinity
      for (let i = 0; i < hits.length; i++)
        for (let j = i + 1; j < hits.length; j++) {
          const s = angSepDeg(hits[i].obj.pos, hits[j].obj.pos)
          if (s < minSep) minSep = s
        }
      loupeFov = fov / 5
      loupeRa0 = centRa
      loupeDec0 = centDec
      loupeMagLim = fovToMagLimit(fov)
      showLoupe = true
    }
  }

  $: if ($pendingFocus) {
    ra0 = $pendingFocus.ra
    dec0 = $pendingFocus.dec
    pendingFocus.set(null)
    maybeReload()
  }

  $: if (!$objectDetailsActive && returnToObservationsFromObjectDetails) {
    returnToObservationsFromObjectDetails = false
    showObservations = true
  }

  $: if (!$objectDetailsActive && returnToFindingPathsListFromAbout) {
    returnToFindingPathsListFromAbout = false
    showFindingPathsList = true
  }

  function openObservationSync() {
    const { valid, nearExpiry } = getTokenStatus()
    if (!valid || nearExpiry) {
      showObservationSyncLogin = true
    } else {
      showSyncSetup = true
    }
  }

  function handleKey(e) {
    if (e.key === 'Escape') {
      if (showObservationSyncLogin) {
        showObservationSyncLogin = false
        e.preventDefault()
        return
      }
      if (showSyncReport) {
        showSyncReport = false
        e.preventDefault()
        return
      }
      if (showSyncSetup) {
        showSyncSetup = false
        e.preventDefault()
        return
      }
      if (showFindingPathsList) {
        showFindingPathsList = false
        e.preventDefault()
        return
      }
      if (showStarQuiz) {
        showStarQuiz = false
        e.preventDefault()
        return
      }
      if (showConstellationIdQuiz) {
        showConstellationIdQuiz = false
        e.preventDefault()
        return
      }
      if (showMoonQuiz) {
        showMoonQuiz = false
        e.preventDefault()
        return
      }
      if (showMoonMap) {
        showMoonMap = false
        e.preventDefault()
        return
      }
      if (showFindingPaths) {
        showFindingPaths = false
        findingPathsObject = null
        findingPathsFromFinder = false
        findingPathsStartHip = null
        findingPathsEditHip = null
        findingPathsStateVersion += 1
        if (returnToFindingPathsListFromFinder) {
          returnToFindingPathsListFromFinder = false
          showFindingPathsList = true
        }
        e.preventDefault()
        return
      }
      if (menuOpen) {
        menuOpen = false
        e.preventDefault()
        return
      }
      if (showObservations) {
        showObservations = false
        e.preventDefault()
        return
      }
      if (get(objectDetailsActive)) {
        objectDetailsActive.set(false)
        e.preventDefault()
        return
      }
      if (get(finderViewActive)) {
        finderViewActive.set(false)
        e.preventDefault()
        return
      }
    }

    if (e.key === 'n') {
      toggleTheme()
      e.preventDefault()
      return
    }

    // Finder has its own keymap; do not let global shortcuts interfere.
    if (get(finderViewActive)) return

    if (get(searchViewActive)) return
    if (showFindingPathsList) return
    if (showFindingPaths) return
    if (showVisualRange) return
    if (showStarQuiz) return
    if (showConstellationIdQuiz) return
    if (showMoonQuiz) return
    if (showMoonMap) return

    if ((e.key === 'i' || e.key === 'Enter') && get(selectedObject)) {
      objectDetailsActive.set(true)
      e.preventDefault()
      return
    }

    if (e.key === 'm') {
      searchViewActive.set(false)
      objectDetailsActive.set(false)
      showObservations = false
      menuOpen = !menuOpen
      e.preventDefault()
      return
    }

    if (e.key === 'S') {
      menuOpen = false
      openObservationSync()
      e.preventDefault()
      return
    }
    if (e.key === 's') {
      showSolarSystem.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'f') {
      menuOpen = false
      showObservations = false
      objectDetailsActive.set(false)
      searchViewActive.update((v) => !v)
      e.preventDefault()
      return
    }

    if (e.key === 'c') {
      showConstellationLines.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'C') {
      showConstellationNames.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'b') {
      showConstellationBoundaries.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'd') {
      showDsos.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'h') {
      showHorizon.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'F') {
      showObservations = false
      finderViewActive.update((v) => !v)
      e.preventDefault()
      return
    }
    if (e.key === 'o') {
      menuOpen = false
      showObservations = true
      e.preventDefault()
      return
    }
    if (e.key === 'p') {
      menuOpen = false
      showFindingPathsList = true
      e.preventDefault()
      return
    }
    if (e.key === 'r') {
      menuOpen = false
      showVisualRange = true
      e.preventDefault()
      return
    }
    if (e.key === 't') {
      menuOpen = false
      showTelescopes = true
      e.preventDefault()
      return
    }
    if (e.key === 'u') {
      menuOpen = false
      showSync = true
      e.preventDefault()
      return
    }
    if (e.key === 'a') {
      menuOpen = false
      showAbout = true
      e.preventDefault()
      return
    }

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
    migrateLegacyPendingToSyncDirty()
      .then(() => getSyncDirtyTotalCount())
      .then((count) => pendingChanges.set(count))
    window.addEventListener('keydown', handleKey)
    window.addEventListener('wheel', handleWheel, { passive: false })
    clockInterval = setInterval(() => {
      if (usingCustomTime) return
      time = new Date()
      if (time.getMinutes() !== skyTime.getMinutes()) skyTime = time
    }, 1000)
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
    clearInterval(clockInterval)
  })

  $: minDimFov = viewportH > 0 ? (fov * Math.min(viewportW, viewportH)) / viewportH : fov
  $: _vpRange = computeViewportMagRange(
    objects,
    Math.min(adaptiveMagLimit(minDimFov), parseFloat(localStorage.getItem('selectedMag') || '14')),
    ra0,
    dec0,
    viewportH > 0 ? (fov * viewportW) / viewportH : fov,
    fov,
  )
  $: displayMagMin = _vpRange.min
  $: displayMagMax = _vpRange.max
</script>

<svelte:window bind:innerWidth={viewportW} bind:innerHeight={viewportH} />

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
      time={skyTime}
      showFovCircle={$showFovCircle}
      showConstellationLines={$showConstellationLines}
      showConstellationNames={$showConstellationNames}
      showConstellationBoundaries={$showConstellationBoundaries}
      showDsos={$showDsos}
      showHorizon={$showHorizon}
      showSolarSystem={$showSolarSystem}
    />
  {/if}

  <TopBar
    {time}
    {menuOpen}
    finderMode={$finderViewActive}
    fov={showMoonMap ? null : minDimFov}
    magMin={showMoonMap ? null : displayMagMin}
    magMax={showMoonMap ? null : displayMagMax}
    on:menutoggle={() => {
      searchViewActive.set(false)
      objectDetailsActive.set(false)
      showObservations = false
      menuOpen = !menuOpen
    }}
    on:searchtoggle={() => {
      menuOpen = false
      objectDetailsActive.set(false)
      searchViewActive.update((v) => !v)
    }}
    on:timepick={() => {
      showPicker = !showPicker
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
    on:telescopes={() => {
      showTelescopes = true
    }}
    on:observations={() => {
      showObservations = true
    }}
    on:findingpathslist={() => {
      showFindingPathsList = true
    }}
    on:visualrange={() => {
      showVisualRange = true
    }}
    on:sync={() => {
      openObservationSync()
    }}
    on:starquiz={() => {
      showStarQuiz = true
    }}
    on:constellationquiz={() => {
      showConstellationIdQuiz = true
    }}
    on:moonquiz={() => {
      showMoonQuiz = true
    }}
    on:moonmap={() => {
      showMoonMap = true
    }}
  />

  {#if showPicker}
    <DateTimePicker
      {time}
      on:pick={(e) => {
        time = e.detail
        skyTime = e.detail
        usingCustomTime = e.detail.toDateString() !== new Date().toDateString()
      }}
      on:resumeLive={() => {
        usingCustomTime = false
      }}
      on:done={() => {
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

  {#if showTelescopes}
    <TelescopesScreen
      onClose={() => {
        showTelescopes = false
      }}
    />
  {/if}

  {#if showObservationSyncLogin}
    <LoginScreen
      on:loggedin={() => {
        showObservationSyncLogin = false
        showSyncSetup = true
      }}
      on:close={() => {
        showObservationSyncLogin = false
      }}
    />
  {/if}

  {#if showSyncSetup}
    <SyncSetupScreen
      bind:categories={syncCategories}
      bind:mode={syncMode}
      bind:source={syncSource}
      on:close={() => {
        showSyncSetup = false
      }}
      on:analyzed={(e) => {
        syncPlan = { categories: e.detail.categories, mode: e.detail.mode, source: e.detail.source }
        syncReport = e.detail.report
        showSyncSetup = false
        showSyncReport = true
      }}
    />
  {/if}

  {#if showSyncReport}
    <SyncReportScreen
      plan={syncPlan}
      report={syncReport}
      on:back={() => {
        showSyncReport = false
        showSyncSetup = true
      }}
      on:cancel={() => {
        showSyncReport = false
      }}
      on:synced={async () => {
        showSyncReport = false
        pendingChanges.set(await getSyncDirtyTotalCount())
      }}
    />
  {/if}

  {#if showObservations}
    <ObservationsScreen
      {time}
      onClose={() => {
        showObservations = false
        returnToObservationsFromObjectDetails = false
      }}
      onOpenObject={(obj) => {
        returnToObservationsFromObjectDetails = true
        showObservations = false
        selectedObject.set(obj)
        objectDetailsActive.set(true)
      }}
    />
  {/if}

  {#if $finderViewActive}
    <FinderPanel
      mainRa0={ra0}
      mainDec0={dec0}
      {lat}
      {lon}
      time={skyTime}
      pathStateVersion={findingPathsStateVersion}
      on:recordpath={(e) => {
        findingPathsObject = e.detail?.object || get(selectedObject)
        if (!findingPathsObject) return
        findingPathsFromFinder = true
        showFindingPaths = true
      }}
      on:guidepath={(e) => {
        findingPathsObject = e.detail?.object || get(selectedObject)
        if (!findingPathsObject) return
        findingPathsFromFinder = false
        findingPathsStartHip = e.detail?.startHip ?? null
        showFindingPaths = true
      }}
    />
  {/if}

  {#if $searchViewActive}
    <SearchPanel
      on:findingpaths={(e) => {
        findingPathsObject = e.detail?.object
        if (!findingPathsObject) return
        selectedObject.set(findingPathsObject)
        searchViewActive.set(false)
        findingPathsFromFinder = false
        showFindingPaths = true
      }}
    />
  {/if}

  {#if showFindingPathsList}
    <FindingPathsListScreen
      initialTargetChip={findingPathsListTargetChip}
      initialStartChip={findingPathsListStartChip}
      on:close={() => {
        showFindingPathsList = false
        findingPathsListTargetChip = null
        findingPathsListStartChip = null
      }}
      on:openpath={(e) => {
        findingPathsListTargetChip = e.detail.targetChip
        findingPathsListStartChip = e.detail.startChip
        showFindingPathsList = false
        findingPathsObject = e.detail.contextObject
        findingPathsFromFinder = e.detail.initialSelectStart
        findingPathsStartHip = e.detail.initialStartHip
        findingPathsEditHip = e.detail.initialEditHip ?? null
        returnToFindingPathsListFromFinder = true
        showFindingPaths = true
      }}
      on:openabout={(e) => {
        findingPathsListTargetChip = e.detail.targetChip
        findingPathsListStartChip = e.detail.startChip
        showFindingPathsList = false
        selectedObject.set(e.detail.obj)
        objectDetailsActive.set(true)
        returnToFindingPathsListFromAbout = true
      }}
    />
  {/if}

  {#if showFindingPaths}
    <FindingPathsScreen
      contextObject={findingPathsObject}
      initialSelectStart={findingPathsFromFinder}
      initialStartHip={findingPathsStartHip}
      initialEditHip={findingPathsEditHip}
      {lat}
      {lon}
      time={skyTime}
      on:close={() => {
        showFindingPaths = false
        findingPathsObject = null
        findingPathsFromFinder = false
        findingPathsStartHip = null
        findingPathsEditHip = null
        findingPathsStateVersion += 1
        if (returnToFindingPathsListFromFinder) {
          returnToFindingPathsListFromFinder = false
          showFindingPathsList = true
        }
      }}
    />
  {/if}

  {#if showVisualRange}
    <VisualRangeSetupScreen
      {lat}
      {lon}
      time={skyTime}
      on:close={() => {
        showVisualRange = false
      }}
    />
  {/if}

  {#if showStarQuiz}
    <StarQuizScreen
      {lat}
      {lon}
      time={skyTime}
      viewRa0={ra0}
      viewDec0={dec0}
      viewFov={minDimFov}
      on:close={() => {
        showStarQuiz = false
      }}
    />
  {/if}

  {#if showConstellationIdQuiz}
    <ConstellationIdQuizScreen
      {lat}
      {lon}
      time={skyTime}
      on:close={() => {
        showConstellationIdQuiz = false
      }}
    />
  {/if}

  {#if showMoonQuiz}
    <MoonQuizScreen
      time={skyTime}
      on:close={() => {
        showMoonQuiz = false
      }}
    />
  {/if}

  {#if showMoonMap}
    <MoonMapScreen
      time={skyTime}
      on:close={() => {
        showMoonMap = false
      }}
    />
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
      {lat}
      {lon}
      time={skyTime}
      magLimit={loupeMagLim}
      on:select={(e) => {
        showLoupe = false
        if (get(selectedObject)?.id === e.detail.obj.id) {
          selectedObject.set(null)
        } else {
          selectedObject.set(e.detail.obj)
        }
      }}
      on:close={() => {
        showLoupe = false
      }}
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
