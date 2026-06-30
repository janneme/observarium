<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { get } from 'svelte/store'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import MultiplierSelect from '../components/MultiplierSelect.svelte'
  import {
    getFindingPathsForObject,
    saveFindingPathForObject,
    deleteFindingPathForObject,
    incrementFindingPathsChanges,
    getObjectsInArea,
    getSearchIndex,
  } from '../lib/db.js'
  import { pendingChanges } from '../stores/ui.js'
  import { projectToPixel } from '../lib/skymath.js'
  import { toggleTheme } from '../stores/theme.js'
  import DeleteIcon from '../icons/DeleteIcon.svelte'

  export let contextObject = null
  export let initialSelectStart = false
  export let initialStartHip = null
  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  const dispatch = createEventDispatcher()

  const FINDER_FOV = 7.5
  const PATH_START_MAX_MAG = 4
  const EUROPE_MIN_DEC = -35
  const SNAP_RADIUS = 15

  let wrapEl
  let finderRa0 = 0
  let finderDec0 = 0
  let finderFov = FINDER_FOV
  let objects = []
  let overlays = []
  let pointers = new Map()
  let finderWheelTimer = null

  let objectCtx = null
  let pathsByStart = {}
  let pathEntryList = []
  let expandedStartHip = null
  let activeStepIndex = null
  let statusMsg = ''

  let starsByHip = new Map()
  let labelById = new Map()

  let pendingPoint = null

  let confirmOpen = false
  let confirmMessage = ''
  let confirmAction = null

  let startSearchOpen = false
  let recordingStartHip = null

  function clonePoint(point) {
    return point && typeof point === 'object' ? { ...point } : null
  }

  function normalizeMultiplier(value) {
    const n = Number(value)
    if (!Number.isFinite(n)) return 1
    return Math.max(0.5, Math.round(n * 2) / 2)
  }

  function pointLabel(point) {
    if (!point) return 'Unset'
    if (point.objectId && labelById.has(point.objectId)) return labelById.get(point.objectId)
    if (point.hip && starsByHip.has(String(point.hip))) {
      return starsByHip.get(String(point.hip)).label
    }
    if (Number.isFinite(point.ra) && Number.isFinite(point.dec)) {
      return `${point.ra.toFixed(2)}°, ${point.dec.toFixed(2)}°`
    }
    return 'Unnamed point'
  }

  function objectLabel(obj) {
    if (!obj) return 'Object finding paths'
    if (obj.type === 'star') return preferredStarLabel(obj)
    if (obj.name) return obj.name
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    return String(obj.id || 'Object')
  }

  function objectFullLabel(obj) {
    if (!obj) return 'Object finding paths'
    if (obj.type === 'star') return preferredStarLabel(obj)
    let cat = null
    if (obj.m != null) cat = `M ${obj.m}`
    else if (obj.ngc != null) cat = `NGC ${obj.ngc}`
    else if (obj.ic != null) cat = `IC ${obj.ic}`
    else if (obj.caldwell != null) cat = `C ${obj.caldwell}`
    if (cat && obj.name) return `${cat} (${obj.name})`
    return cat || obj.name || String(obj.id || 'Object')
  }

  function greekFromBayer(bayer) {
    const raw = String(bayer || '').trim()
    if (!raw) return null
    const first = raw.split(/\s+/)[0] || ''
    const cleaned = first
      .toLowerCase()
      .replace(/[0-9]+$/g, '')
      .replace(/[._-]+$/g, '')
    const greekChars = 'αβγδεζηθικλμνξοπρστυφχψω'
    if (cleaned && greekChars.includes(cleaned[0])) return cleaned[0]
    const key = cleaned.length >= 3 ? cleaned.slice(0, 3) : cleaned
    const map = {
      alf: 'α',
      alp: 'α',
      bet: 'β',
      gam: 'γ',
      del: 'δ',
      eps: 'ε',
      zet: 'ζ',
      eta: 'η',
      the: 'θ',
      iot: 'ι',
      kap: 'κ',
      lam: 'λ',
      mu: 'μ',
      nu: 'ν',
      xi: 'ξ',
      omi: 'ο',
      pi: 'π',
      rho: 'ρ',
      sig: 'σ',
      tau: 'τ',
      ups: 'υ',
      phi: 'φ',
      chi: 'χ',
      psi: 'ψ',
      ome: 'ω',
    }
    return map[key] || null
  }

  function preferredStarLabel(obj) {
    const rawName = String(obj?.name || '').trim()
    if (rawName) return rawName
    const rawBay = String(obj?.bay || '').trim()
    const greek = greekFromBayer(rawBay)
    if (greek && obj?.constellation) return `${greek} ${obj.constellation}`
    if (rawBay && obj?.constellation) return `${rawBay} ${obj.constellation}`
    if (obj?.hip != null) return `HIP ${obj.hip}`
    if (obj?.hd != null) return `HD ${obj.hd}`
    if (obj?.sao != null) return `SAO ${obj.sao}`
    if (obj?.flam != null && obj?.constellation) return `${obj.flam} ${obj.constellation}`
    return String(obj?.id || 'Star')
  }

  function centerOn(point) {
    if (!point) return
    if (Number.isFinite(point.ra) && Number.isFinite(point.dec)) {
      finderRa0 = ((point.ra % 360) + 360) % 360
      const decMin = EUROPE_MIN_DEC + finderFov / 2
      finderDec0 = Math.max(decMin, Math.min(90, point.dec))
    }
  }

  async function loadFinderObjects() {
    const margin = Math.max(finderFov * 2, FINDER_FOV * 2)
    objects = await getObjectsInArea(
      finderRa0 - margin,
      finderRa0 + margin,
      finderDec0 - margin,
      finderDec0 + margin,
      12,
    )
  }

  async function loadLabels() {
    const index = await getSearchIndex()
    const nextStarsByHip = new Map()
    const nextLabels = new Map()
    for (const obj of index) {
      const label = objectLabel(obj)
      nextLabels.set(obj.id, label)
      if (obj.type === 'star' && obj.hip != null) {
        // Prefer canonical star labels (name/Bayer) over double-star aliases for path headers.
        nextStarsByHip.set(String(obj.hip), {
          id: obj.id,
          label,
          point: { ra: obj.pos?.[0], dec: obj.pos?.[1], objectId: obj.id, hip: obj.hip },
        })
      } else if (obj.type === 'double_star' && obj.hip != null && !nextStarsByHip.has(String(obj.hip))) {
        nextStarsByHip.set(String(obj.hip), {
          id: obj.id,
          label,
          point: { ra: obj.pos?.[0], dec: obj.pos?.[1], objectId: obj.id, hip: obj.hip },
        })
      }
    }
    starsByHip = nextStarsByHip
    labelById = nextLabels
  }

  function pathEntries() {
    return Object.entries(pathsByStart)
      .map(([startHip, path]) => ({
        startHip,
        path,
        label: starsByHip.get(String(startHip))?.label || `HIP ${startHip}`,
      }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }

  function ensureExpandedPath() {
    if (expandedStartHip && pathsByStart[expandedStartHip]) return
    const entries = pathEntries()
    expandedStartHip = entries.length ? entries[0].startHip : null
    activeStepIndex = null
  }

  async function loadPaths() {
    if (!objectCtx) return
    pathsByStart = await getFindingPathsForObject(objectCtx.id)
    ensureExpandedPath()
  }

  async function init() {
    objectCtx = contextObject || get(selectedObject)
    if (!objectCtx?.id || !objectCtx?.pos) {
      statusMsg = 'Select an object first.'
      return
    }
    finderRa0 = objectCtx.pos[0]
    finderDec0 = objectCtx.pos[1]
    await Promise.all([loadLabels(), loadPaths()])
    if (initialStartHip != null) {
      const hip = String(initialStartHip)
      if (pathsByStart[hip]) {
        expandedStartHip = hip
        const path = pathsByStart[hip]
        if (path?.steps?.length) {
          activeStepIndex = 0
          centerOn(stepAnchor(path, 0))
        }
      }
    }
    await loadFinderObjects()
  }

  $: pathEntryList = pathEntries()
  $: recordingPath = recordingStartHip ? pathsByStart[recordingStartHip] || null : null
  $: recordingStartLabel = recordingStartHip
    ? starsByHip.get(String(recordingStartHip))?.label || `HIP ${recordingStartHip}`
    : null
  $: expandedStartLabel = expandedStartHip
    ? starsByHip.get(String(expandedStartHip))?.label || `HIP ${expandedStartHip}`
    : null
  $: guideMode = initialStartHip != null

  function pathStartPoint(startHip) {
    const star = starsByHip.get(String(startHip))
    if (star?.point) return clonePoint(star.point)
    return null
  }

  function getExpandedPath() {
    if (!expandedStartHip) return null
    return pathsByStart[expandedStartHip] || null
  }

  function isStarSnapCandidate(obj) {
    if (!obj?.pos) return false
    return obj.type === 'star' || obj.type === 'double_star'
  }

  function screenToSky(clientX, clientY) {
    const rect = wrapEl?.getBoundingClientRect()
    if (!rect || rect.width <= 0 || rect.height <= 0) return null
    const W = rect.width
    const H = rect.height
    const px = clientX - rect.left
    const py = clientY - rect.top
    const fovRad = (finderFov * Math.PI) / 180
    const scale = H / fovRad
    const x = (W / 2 - px) / scale
    const y = (H / 2 - py) / scale
    const rho = Math.sqrt(x * x + y * y)
    if (rho < 1e-12) return { ra: finderRa0, dec: finderDec0 }
    const c = Math.atan(rho)
    const sinC = Math.sin(c)
    const cosC = Math.cos(c)
    const dec0 = (finderDec0 * Math.PI) / 180
    const dec = Math.asin(cosC * Math.sin(dec0) + (y * sinC * Math.cos(dec0)) / rho)
    const ra =
      (finderRa0 * Math.PI) / 180 + Math.atan2(x * sinC, rho * Math.cos(dec0) * cosC - y * Math.sin(dec0) * sinC)
    return {
      ra: ((((ra * 180) / Math.PI) % 360) + 360) % 360,
      dec: (dec * 180) / Math.PI,
    }
  }

  function pickPoint(clientX, clientY) {
    if (!wrapEl) return null
    const rect = wrapEl.getBoundingClientRect()
    const W = rect.width
    const H = rect.height
    let best = null
    let bestDist = Infinity
    for (const obj of objects) {
      if (!isStarSnapCandidate(obj)) continue
      const pt = projectToPixel(obj.pos[0], obj.pos[1], finderRa0, finderDec0, W, H, finderFov, 0)
      if (!pt) continue
      const dist = Math.hypot(pt.px - (clientX - rect.left), pt.py - (clientY - rect.top))
      if (dist <= SNAP_RADIUS && dist < bestDist) {
        bestDist = dist
        best = obj
      }
    }
    if (best) {
      return {
        ra: best.pos[0],
        dec: best.pos[1],
        objectId: best.id,
        hip: best.hip ?? null,
      }
    }
    return screenToSky(clientX, clientY)
  }

  function startPathSelection() {
    startSearchOpen = true
    statusMsg = ''
  }

  function clearPending() {
    pendingPoint = null
    finderFov = FINDER_FOV
  }

  async function setStart(idx) {
    if (!pendingPoint?.hip) return
    const startHip = expandedStartHip
    const path = getExpandedPath()
    if (!startHip || !path) return
    const steps = path.steps
      .slice(0, idx + 1)
      .map((s, i) => (i === idx ? { ...s, startPoint: clonePoint(pendingPoint) } : s))
    await savePath(startHip, { steps })
    if (activeStepIndex != null && activeStepIndex >= steps.length) activeStepIndex = steps.length - 1
    clearPending()
  }

  async function setEnd(idx) {
    if (!pendingPoint) return
    const startHip = expandedStartHip
    const path = getExpandedPath()
    if (!startHip || !path) return
    const steps = path.steps
      .slice(0, idx + 1)
      .map((s, i) => (i === idx ? { ...s, endPoint: clonePoint(pendingPoint) } : s))
    await savePath(startHip, { steps })
    if (activeStepIndex != null && activeStepIndex >= steps.length) activeStepIndex = steps.length - 1
    clearPending()
  }

  async function setFinal(idx) {
    if (!objectCtx?.pos) return
    const startHip = expandedStartHip
    const path = getExpandedPath()
    if (!startHip || !path) return
    const targetPoint = { ra: objectCtx.pos[0], dec: objectCtx.pos[1], objectId: objectCtx.id }
    const steps = path.steps
      .slice(0, idx + 1)
      .map((s, i) => (i === idx ? { ...s, endPoint: targetPoint, final: true } : s))
    await savePath(startHip, { steps })
    clearPending()
    activeStepIndex = idx
  }

  function closeStartSearch() {
    startSearchOpen = false
  }

  function startSearchFilter(obj) {
    if (!obj || obj.type !== 'star' || obj.hip == null) return false
    const baseMag = Array.isArray(obj.mag) ? obj.mag[0] : Number(obj.mag)
    return Number.isFinite(baseMag) && baseMag <= PATH_START_MAX_MAG
  }

  async function createPathForStartHip(startHip) {
    if (!startHip) return
    if (pathsByStart[startHip]) {
      expandedStartHip = startHip
      activeStepIndex = null
      focusPath(startHip)
      return
    }
    const path = { steps: [] }
    await savePath(startHip, path)
    expandedStartHip = startHip
    activeStepIndex = null
    const start = pathStartPoint(startHip)
    centerOn(start)
    await loadFinderObjects()
    await addStep()
  }

  async function handleStartSearchAcceptObject(obj) {
    if (!obj || obj.hip == null) return
    const hip = String(obj.hip)
    await createPathForStartHip(hip)
    if (initialSelectStart) recordingStartHip = hip
    closeStartSearch()
    return false
  }

  async function savePath(startHip, path) {
    await saveFindingPathForObject(objectCtx.id, startHip, path)
    pathsByStart = { ...pathsByStart, [startHip]: path }
    const steps = path?.steps
    if (Array.isArray(steps) && steps.length > 0 && steps[steps.length - 1]?.final === true) {
      await incrementFindingPathsChanges()
      pendingChanges.update((n) => n + 1)
    }
  }

  function applyPan(dx, dy, raC, decC, sizePx, fov) {
    const fovRad = (fov * Math.PI) / 180
    const scale = sizePx / fovRad
    const x = dx / scale
    const y = dy / scale
    const rho = Math.sqrt(x * x + y * y)
    if (rho < 1e-10) return { ra0: raC, dec0: decC }
    const dec0_r = (decC * Math.PI) / 180
    const c = Math.atan(rho)
    const sinC = Math.sin(c)
    const cosC = Math.cos(c)
    const dec_r = Math.asin(Math.max(-1, Math.min(1, cosC * Math.sin(dec0_r) + (y * sinC * Math.cos(dec0_r)) / rho)))
    const ra_r =
      (raC * Math.PI) / 180 + Math.atan2(x * sinC, rho * Math.cos(dec0_r) * cosC - y * Math.sin(dec0_r) * sinC)
    const decMin = EUROPE_MIN_DEC + fov / 2
    return {
      ra0: ((((ra_r * 180) / Math.PI) % 360) + 360) % 360,
      dec0: Math.max(decMin, Math.min(90, (dec_r * 180) / Math.PI)),
    }
  }

  function handlePointerDown(e) {
    if (guideMode) return
    e.preventDefault()
    e.stopPropagation()
    wrapEl.setPointerCapture(e.pointerId)
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY })
  }

  function handlePointerMove(e) {
    if (!pointers.has(e.pointerId)) return
    const prev = pointers.get(e.pointerId)
    if (pointers.size === 1) {
      const rect = wrapEl.getBoundingClientRect()
      const next = applyPan(e.clientX - prev.x, e.clientY - prev.y, finderRa0, finderDec0, rect.width, finderFov)
      finderRa0 = next.ra0
      finderDec0 = next.dec0
    } else if (pointers.size === 2) {
      const ids = [...pointers.keys()]
      const other = pointers.get(ids.find((id) => id !== e.pointerId))
      const prevDist = Math.hypot(prev.x - other.x, prev.y - other.y)
      const currDist = Math.hypot(e.clientX - other.x, e.clientY - other.y)
      if (prevDist > 1) {
        const nextFov = finderFov / (currDist / prevDist)
        finderFov = Math.max(1.5, Math.min(20, nextFov))
      }
    }
    pointers.set(e.pointerId, { ...prev, x: e.clientX, y: e.clientY })
  }

  function handleFinderWheel(e) {
    e.stopPropagation()
    if (!e.ctrlKey || guideMode) return
    e.preventDefault()
    const nextFov = finderFov * Math.pow(1.008, e.deltaY)
    finderFov = Math.max(1.5, Math.min(20, nextFov))
    clearTimeout(finderWheelTimer)
    finderWheelTimer = setTimeout(loadFinderObjects, 300)
  }

  function handlePointerUp(e) {
    const prev = pointers.get(e.pointerId)
    if (activeStepIndex != null && prev && Math.hypot(e.clientX - prev.startX, e.clientY - prev.startY) < 8) {
      pendingPoint = pickPoint(e.clientX, e.clientY)
    }
    pointers.delete(e.pointerId)
    if (pointers.size === 0) {
      loadFinderObjects()
    }
  }

  function handlePointerCancel(e) {
    pointers.delete(e.pointerId)
  }

  function focusPath(startHip) {
    expandedStartHip = startHip
    pendingPoint = null
    finderFov = FINDER_FOV
    const path = pathsByStart[startHip]
    activeStepIndex = path?.steps?.length ? 0 : null
    const start = pathStartPoint(startHip)
    centerOn(start)
    loadFinderObjects()
  }

  function effectiveStepEnd(step, resolvedStart) {
    if (!step?.startPoint && !step?.endPoint) return null
    if (!step.endPoint) return step.startPoint ? clonePoint(step.startPoint) : null
    const m = normalizeMultiplier(step.multiplier)
    const s = step.startPoint || resolvedStart
    if (m === 1 || !s) return clonePoint(step.endPoint)
    const e = step.endPoint
    let dRa = e.ra - s.ra
    if (dRa > 180) dRa -= 360
    if (dRa < -180) dRa += 360
    return {
      ra: (((s.ra + dRa * m) % 360) + 360) % 360,
      dec: Math.max(-90, Math.min(90, s.dec + (e.dec - s.dec) * m)),
    }
  }

  function stepAnchor(path, idx) {
    if (!path || idx < 0) return pathStartPoint(expandedStartHip)
    const prev = path.steps[idx - 1]
    if (!prev) return pathStartPoint(expandedStartHip)
    const resolvedStart = prev.startPoint || stepAnchor(path, idx - 1)
    return effectiveStepEnd(prev, resolvedStart) || clonePoint(resolvedStart)
  }

  function selectStep(idx) {
    const path = getExpandedPath()
    const anchor = stepAnchor(path, idx)
    activeStepIndex = idx
    pendingPoint = null
    finderFov = FINDER_FOV
    centerOn(anchor)
    loadFinderObjects()
  }

  async function addStep() {
    const startHip = expandedStartHip
    const path = getExpandedPath()
    if (!startHip || !path) return
    const steps = [...(path.steps || [])]
    const last = steps[steps.length - 1]
    const startPoint =
      last?.endPoint?.hip != null && normalizeMultiplier(last?.multiplier) === 1 ? clonePoint(last.endPoint) : null
    steps.push({ startPoint, endPoint: null, multiplier: 1 })
    await savePath(startHip, { steps })
    activeStepIndex = steps.length - 1
    pendingPoint = null
    finderFov = FINDER_FOV
    const anchor = stepAnchor({ steps }, steps.length - 1)
    if (anchor) centerOn(anchor)
    await loadFinderObjects()
  }

  function angularSepDeg(a, b) {
    if (!a || !b) return 0
    const r = Math.PI / 180
    return (
      Math.acos(
        Math.max(
          -1,
          Math.min(
            1,
            Math.sin(a.dec * r) * Math.sin(b.dec * r) +
              Math.cos(a.dec * r) * Math.cos(b.dec * r) * Math.cos((b.ra - a.ra) * r),
          ),
        ),
      ) / r
    )
  }

  function multiplierOptions(step, resolvedFrom) {
    const from = resolvedFrom || step?.startPoint
    const to = step?.endPoint
    if (!from || !to) return [1]
    const vectorLen = angularSepDeg(from, to)
    if (vectorLen < 0.05) return [1]
    const maxMul = Math.max(1, Math.floor(((2 * FINDER_FOV) / vectorLen) * 2) / 2)
    const values = []
    for (let v = 1; v <= maxMul + 1e-9; v += 0.5) {
      values.push(Math.round(v * 2) / 2)
      if (values.length >= 30) break
    }
    return values
  }

  async function setMultiplierForStep(idx, value) {
    const startHip = expandedStartHip
    const path = getExpandedPath()
    if (!startHip || !path || idx == null || !path.steps?.[idx]) return
    const steps = path.steps.slice(0, idx + 1)
    steps[idx] = { ...steps[idx], multiplier: normalizeMultiplier(value) }
    await savePath(startHip, { steps })
    if (activeStepIndex != null && activeStepIndex >= steps.length) activeStepIndex = steps.length - 1
  }

  async function deleteStep(stepIndex) {
    const path = getExpandedPath()
    const startHip = expandedStartHip
    if (!startHip || !path) return
    const steps = path.steps.slice(0, stepIndex)
    await savePath(startHip, { steps })
    if (activeStepIndex != null && activeStepIndex >= steps.length) activeStepIndex = steps.length - 1
  }

  function askDeletePath(startHip) {
    const label = starsByHip.get(String(startHip))?.label || `HIP ${startHip}`
    confirmMessage = `Delete path from ${label}?`
    confirmAction = async () => {
      const deletedSteps = pathsByStart[startHip]?.steps
      const wasFinal =
        Array.isArray(deletedSteps) && deletedSteps.length > 0 && deletedSteps[deletedSteps.length - 1]?.final === true
      await deleteFindingPathForObject(objectCtx.id, startHip)
      const next = { ...pathsByStart }
      delete next[startHip]
      pathsByStart = next
      if (wasFinal) {
        await incrementFindingPathsChanges()
        pendingChanges.update((n) => n + 1)
      }
      if (guideMode) {
        dispatch('close')
      } else {
        ensureExpandedPath()
      }
    }
    confirmOpen = true
  }

  function closeConfirm() {
    confirmOpen = false
    confirmAction = null
    confirmMessage = ''
  }

  async function onConfirm() {
    const fn = confirmAction
    closeConfirm()
    if (typeof fn === 'function') await fn()
  }

  function placeLabel(point) {
    if (!point) return '?'
    if (point.hip) {
      const star = starsByHip.get(String(point.hip))
      if (star) return star.label
    }
    if (point.objectId && labelById.has(point.objectId)) return labelById.get(point.objectId)
    return '•'
  }

  function stepTitleParts(step, idx, path) {
    const resolvedStart = step?.startPoint || stepAnchor(path, idx)
    const m = normalizeMultiplier(step?.multiplier)
    return {
      prefix: `${idx + 1}. `,
      from: placeLabel(resolvedStart),
      to: placeLabel(step?.endPoint),
      mx: m !== 1 ? ` (${m}x)` : null,
    }
  }

  function overlayGeometry() {
    const path = getExpandedPath()
    if (!path?.steps) return []
    const result = []
    path.steps.forEach((step, idx) => {
      if (step.final) return
      const startPt = step.startPoint || stepAnchor(path, idx)
      if (!startPt || !step.endPoint) return
      const m = normalizeMultiplier(step.multiplier)
      result.push({
        fromRa: startPt.ra,
        fromDec: startPt.dec,
        toRa: step.endPoint.ra,
        toDec: step.endPoint.dec,
        label: m !== 1 ? `${m}x` : '',
      })
    })
    return result
  }

  $: {
    pathsByStart
    expandedStartHip
    starsByHip
    overlays = overlayGeometry()
  }

  $: targetInView = (() => {
    if (!objectCtx?.pos || activeStepIndex == null) return false
    const path = getExpandedPath()
    const anchor = stepAnchor(path, activeStepIndex)
    if (!anchor) return false
    const target = { ra: objectCtx.pos[0], dec: objectCtx.pos[1] }
    return angularSepDeg(anchor, target) <= FINDER_FOV / 2
  })()

  $: pathIsComplete = (() => {
    const steps = (expandedStartHip ? pathsByStart[expandedStartHip] : null)?.steps || []
    if (!steps.length) return false
    return steps[steps.length - 1]?.final === true
  })()

  function handleKey(e) {
    if (e.key === 'n') {
      toggleTheme()
      e.preventDefault()
    }
  }

  onMount(async () => {
    window.addEventListener('keydown', handleKey)
    await init()
    if (initialSelectStart) startPathSelection()
  })

  onDestroy(() => {
    window.removeEventListener('keydown', handleKey)
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation on:wheel={handleFinderWheel}>
  <div class="header">
    <button class="back-btn" on:click={() => dispatch('close')} aria-label="Back">←</button>
    <div class="title">
      {#if recordingStartHip && recordingStartLabel}
        Path {recordingStartLabel} ⇒ {objectFullLabel(objectCtx)}
      {:else if initialSelectStart}
        Select start (bright star)
      {:else if guideMode && expandedStartLabel}
        {expandedStartLabel}<span class="title-arrow">→</span>{objectFullLabel(objectCtx)}
      {:else}
        Finding Paths · {objectLabel(objectCtx)}
      {/if}
    </div>
    {#if guideMode}
      <button class="btn danger" on:click={() => askDeletePath(expandedStartHip)}>Delete</button>
    {:else if !recordingStartHip}
      <button class="btn" on:click={startPathSelection}>＋ Path</button>
    {/if}
  </div>

  <div class="finder-sticky">
    <div
      class="finder-wrap"
      bind:this={wrapEl}
      on:pointerdown={handlePointerDown}
      on:pointermove={handlePointerMove}
      on:pointerup={handlePointerUp}
      on:pointercancel={handlePointerCancel}
    >
      <SkyCanvas
        ra0={finderRa0}
        dec0={finderDec0}
        fov={finderFov}
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
        showSolarSystem={true}
        overlayArrows={overlays}
      />

      {#if pendingPoint}
        {@const rect = wrapEl?.getBoundingClientRect()}
        {@const mark = rect
          ? projectToPixel(
              pendingPoint.ra,
              pendingPoint.dec,
              finderRa0,
              finderDec0,
              rect.width,
              rect.height,
              finderFov,
              0,
            )
          : null}
        {#if mark}
          <div class="pick-mark" style={`left:${mark.px}px; top:${mark.py}px`}>
            <span class="cross"></span>
          </div>
        {/if}
      {/if}
    </div>

    {#if activeStepIndex != null && !guideMode}
      <div class="edit-bar">
        <div class="edit-label">{pendingPoint ? pointLabel(pendingPoint) : 'Tap finder to place a point'}</div>
        {#if pendingPoint}
          <div class="edit-actions">
            <button class="btn small" on:click={clearPending}>Clear</button>
          </div>
        {/if}
      </div>
    {/if}
    {#if guideMode && activeStepIndex != null}
      {@const _gp = pathsByStart[expandedStartHip]}
      {@const _gs = _gp?.steps || []}
      {@const _navP = stepTitleParts(_gs[activeStepIndex], activeStepIndex, _gp)}
      <div class="step-nav">
        <button class="nav-btn" disabled={activeStepIndex === 0} on:click={() => selectStep(activeStepIndex - 1)}
          >‹</button
        >
        <span class="step-nav-label">
          {activeStepIndex + 1}/{_gs.length}
          <strong class="step-nav-name"
            >{_navP.from}<span class="step-arrow">→</span>{_navP.to}{#if _navP.mx}<span class="step-mx">{_navP.mx}</span
              >{/if}</strong
          >
        </span>
        <button
          class="nav-btn"
          disabled={activeStepIndex === _gs.length - 1}
          on:click={() => selectStep(activeStepIndex + 1)}>›</button
        >
      </div>
    {/if}
  </div>

  <div class="list-wrap">
    {#if statusMsg}
      <div class="status">{statusMsg}</div>
    {/if}

    {#if recordingStartHip}
      <!-- Recording mode: show only the steps of the path being recorded -->
      {#if recordingPath}
        <div class="steps">
          {#if !(recordingPath.steps || []).length}
            <div class="empty-step">No steps yet.</div>
          {/if}

          {#each recordingPath.steps || [] as step, idx}
            {@const p = stepTitleParts(step, idx, recordingPath)}
            <div class="step-row" class:active={activeStepIndex === idx}>
              <button class="step-main" on:click={() => selectStep(idx)}>
                {p.prefix}{p.from}<span class="step-arrow">→</span>{p.to}{#if p.mx}<span class="step-mx">{p.mx}</span
                  >{/if}
              </button>
              {#if activeStepIndex === idx}
                <div class="step-actions">
                  {#if step.final}
                    <button class="mini" on:click={() => deleteStep(idx)}>Delete</button>
                  {:else}
                    {#if idx > 0}
                      <button class="mini" on:click={() => deleteStep(idx)}>Delete</button>
                    {/if}
                    <button
                      class="mini"
                      class:set={step.startPoint != null}
                      disabled={!pendingPoint?.hip}
                      on:click={() => setStart(idx)}>Set start</button
                    >
                    <button
                      class="mini"
                      class:set={step.endPoint != null}
                      disabled={!pendingPoint}
                      on:click={() => setEnd(idx)}>Set end</button
                    >
                    {#if targetInView}
                      <button class="mini" on:click={() => setFinal(idx)}>Set Final</button>
                    {/if}
                    <MultiplierSelect
                      value={normalizeMultiplier(step.multiplier)}
                      options={multiplierOptions(step, step.startPoint || stepAnchor(recordingPath, idx))}
                      on:change={(e) => setMultiplierForStep(idx, e.detail)}
                    />
                  {/if}
                </div>
              {/if}
            </div>
          {/each}

          {#if !pathIsComplete}
            <button class="add-step" on:click={addStep}>Add</button>
          {/if}
        </div>
      {/if}
    {:else}
      <!-- Normal mode: show full path list -->
      {#if pathEntryList.length === 0 && !guideMode}
        <div class="empty">No paths defined for this object.</div>
      {/if}

      {#each pathEntryList as entry (entry.startHip)}
        <section class="path-card">
          <div class="path-head">
            <button class="path-toggle" on:click={() => focusPath(entry.startHip)}>
              from <strong>{entry.label}</strong>
            </button>
            <button
              class="icon-btn danger"
              on:click={() => askDeletePath(entry.startHip)}
              aria-label="Delete path"
              title="Delete path"
            >
              <DeleteIcon size="0.9rem" aria-hidden="true" />
            </button>
          </div>

          {#if expandedStartHip === entry.startHip}
            <div class="steps">
              {#if !(entry.path.steps || []).length}
                <div class="empty-step">No steps yet.</div>
              {/if}

              {#each entry.path.steps || [] as step, idx}
                {@const p = stepTitleParts(step, idx, entry.path)}
                <div class="step-row" class:active={activeStepIndex === idx}>
                  <button class="step-main" on:click={() => selectStep(idx)}>
                    {p.prefix}{p.from}<span class="step-arrow">→</span>{p.to}{#if p.mx}<span class="step-mx"
                        >{p.mx}</span
                      >{/if}
                  </button>
                  {#if activeStepIndex === idx}
                    <div class="step-actions">
                      {#if step.final}
                        <button class="mini" on:click={() => deleteStep(idx)}>Delete</button>
                      {:else}
                        {#if idx > 0}
                          <button class="mini" on:click={() => deleteStep(idx)}>Delete</button>
                        {/if}
                        <button
                          class="mini"
                          class:set={step.startPoint != null}
                          disabled={!pendingPoint?.hip}
                          on:click={() => setStart(idx)}>Set start</button
                        >
                        <button
                          class="mini"
                          class:set={step.endPoint != null}
                          disabled={!pendingPoint}
                          on:click={() => setEnd(idx)}>Set end</button
                        >
                        {#if targetInView}
                          <button class="mini" on:click={() => setFinal(idx)}>Set Final</button>
                        {/if}
                        <MultiplierSelect
                          value={normalizeMultiplier(step.multiplier)}
                          options={multiplierOptions(step, step.startPoint || stepAnchor(entry.path, idx))}
                          on:change={(e) => setMultiplierForStep(idx, e.detail)}
                        />
                      {/if}
                    </div>
                  {/if}
                </div>
              {/each}

              {#if !pathIsComplete}
                <button class="add-step" on:click={addStep}>Add</button>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    {/if}
  </div>

  <ConfirmDialog
    open={confirmOpen}
    title="Confirm"
    message={confirmMessage}
    confirmLabel="Delete"
    cancelLabel="Cancel"
    on:cancel={closeConfirm}
    on:confirm={onConfirm}
  />

  {#if startSearchOpen}
    <SearchPanel
      placeholder="Start star"
      emptyHint="Type a bright star name"
      noResultsHint="No bright stars found"
      useSearchStore={false}
      manageSelection={false}
      includeSolar={false}
      showDetailsAction={false}
      showFindingPathsAction={false}
      autoCloseOnAccept={false}
      topOffset="5.35rem"
      zIndex={13}
      resultFilter={startSearchFilter}
      onAcceptObject={handleStartSearchAcceptObject}
      on:close={closeStartSearch}
    />
  {/if}
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 12;
    background: #040404;
    color: var(--fg);
    display: flex;
    flex-direction: column;
  }

  .header {
    height: 2.6rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 0.65rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.15);
    flex-shrink: 0;
  }

  .title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.92rem;
    font-weight: 600;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    padding: 0.25rem 0.15rem 0.25rem 0.5rem;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .back-btn:hover {
    background: rgba(232, 232, 232, 0.1);
  }

  .btn {
    border: 1px solid rgba(232, 232, 232, 0.3);
    background: rgba(255, 255, 255, 0.05);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.3rem 0.55rem;
    font-size: 0.78rem;
    cursor: pointer;
  }

  .btn.small {
    padding: 0.25rem 0.5rem;
    font-size: 0.74rem;
  }

  .finder-sticky {
    position: sticky;
    top: 0;
    z-index: 1;
    background: #050505;
    padding: 0.55rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.12);
  }

  .finder-wrap {
    width: 100%;
    aspect-ratio: 1;
    position: relative;
    clip-path: circle(50%);
    border-radius: 50%;
    overflow: hidden;
    touch-action: none;
    border: 1px solid rgba(232, 232, 232, 0.2);
  }

  .pick-mark {
    position: absolute;
    width: 22px;
    height: 22px;
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .cross {
    position: absolute;
    inset: 0;
  }

  .cross::before,
  .cross::after {
    content: '';
    position: absolute;
  }

  .cross::before {
    width: 1.5px;
    left: 50%;
    top: 0;
    bottom: 0;
    transform: translateX(-50%);
    background: linear-gradient(
      to bottom,
      rgba(160, 200, 255, 0.65) calc(50% - 3px),
      transparent calc(50% - 3px),
      transparent calc(50% + 3px),
      rgba(160, 200, 255, 0.65) calc(50% + 3px)
    );
  }

  .cross::after {
    height: 1.5px;
    top: 50%;
    left: 0;
    right: 0;
    transform: translateY(-50%);
    background: linear-gradient(
      to right,
      rgba(160, 200, 255, 0.65) calc(50% - 3px),
      transparent calc(50% - 3px),
      transparent calc(50% + 3px),
      rgba(160, 200, 255, 0.65) calc(50% + 3px)
    );
  }

  .edit-bar {
    margin-top: 0.5rem;
    border: 1px solid rgba(122, 175, 255, 0.4);
    border-radius: 8px;
    padding: 0.45rem;
    background: rgba(80, 120, 180, 0.12);
  }

  .edit-label {
    font-size: 0.8rem;
    margin-bottom: 0.4rem;
  }

  .edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
  }

  .list-wrap {
    flex: 1;
    overflow-y: auto;
    padding: 0.65rem;
  }

  .status {
    font-size: 0.8rem;
    opacity: 0.85;
    margin-bottom: 0.5rem;
  }

  .empty {
    font-size: 0.85rem;
    opacity: 0.7;
    padding: 0.75rem 0.2rem;
  }

  .path-card {
    border: 1px solid rgba(232, 232, 232, 0.18);
    border-radius: 8px;
    margin-bottom: 0.6rem;
    overflow: hidden;
  }

  .path-head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(255, 255, 255, 0.04);
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
    padding: 0.35rem;
  }

  .path-toggle {
    flex: 1;
    text-align: left;
    background: none;
    border: none;
    color: var(--fg);
    font-size: 0.85rem;
    cursor: pointer;
    padding: 0.25rem;
  }

  .path-toggle strong {
    font-weight: 700;
  }

  .icon-btn {
    width: 1.75rem;
    height: 1.75rem;
    border: 1px solid rgba(232, 232, 232, 0.35);
    border-radius: 6px;
    background: none;
    cursor: pointer;
    color: var(--fg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .icon-btn.danger {
    border-color: rgba(255, 120, 120, 0.5);
    color: #ff9a9a;
  }

  .steps {
    padding: 0.5rem;
  }

  .empty-step {
    font-size: 0.78rem;
    opacity: 0.7;
    padding: 0.35rem;
  }

  .step-row {
    border: 1px solid rgba(232, 232, 232, 0.12);
    border-radius: 6px;
    margin-bottom: 0.45rem;
    overflow: hidden;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
  }

  .step-row.active {
    border-color: rgba(120, 180, 255, 0.9);
    background: rgba(80, 130, 220, 0.1);
  }

  .step-row.active .step-main {
    color: rgba(170, 210, 255, 1);
  }

  .step-main {
    flex: 1;
    min-width: 0;
    border: none;
    background: rgba(255, 255, 255, 0.03);
    color: var(--fg);
    text-align: left;
    padding: 0.45rem;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .step-actions {
    flex-shrink: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    padding: 0.25rem 0.4rem;
  }

  .mini {
    border: 1px solid rgba(232, 232, 232, 0.26);
    background: rgba(255, 255, 255, 0.04);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.2rem 0.45rem;
    font-size: 0.7rem;
    cursor: pointer;
  }

  .mini:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .mini.set {
    border-color: rgba(100, 200, 130, 0.6);
    color: #9dda9d;
  }

  .add-step {
    width: 100%;
    border: 1px dashed rgba(232, 232, 232, 0.35);
    background: rgba(255, 255, 255, 0.03);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.4rem;
    font-size: 0.78rem;
    cursor: pointer;
  }

  :global([data-theme='nightly']) .overlay {
    background: #110000;
  }

  :global([data-theme='nightly']) .header,
  :global([data-theme='nightly']) .finder-sticky,
  :global([data-theme='nightly']) .path-head {
    border-color: rgba(180, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .finder-wrap {
    border-color: rgba(180, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .edit-bar {
    border-color: rgba(204, 68, 0, 0.45);
    background: rgba(160, 40, 0, 0.12);
  }

  :global([data-theme='nightly']) .btn,
  :global([data-theme='nightly']) .mini,
  :global([data-theme='nightly']) .add-step,
  :global([data-theme='nightly']) .path-card,
  :global([data-theme='nightly']) .step-row {
    border-color: rgba(180, 0, 0, 0.35);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .mini.set {
    border-color: rgba(200, 100, 80, 0.6);
    color: #cc8070;
  }

  :global([data-theme='nightly']) .btn,
  :global([data-theme='nightly']) .mini,
  :global([data-theme='nightly']) .add-step {
    background: rgba(180, 0, 0, 0.08);
  }

  :global([data-theme='nightly']) .step-row.active {
    border-color: rgba(204, 68, 0, 0.85);
    background: rgba(160, 40, 0, 0.12);
  }

  :global([data-theme='nightly']) .step-row.active .step-main {
    color: #ff0000;
  }

  :global([data-theme='nightly']) .cross::before {
    background: linear-gradient(
      to bottom,
      rgba(204, 68, 0, 0.65) calc(50% - 3px),
      transparent calc(50% - 3px),
      transparent calc(50% + 3px),
      rgba(204, 68, 0, 0.65) calc(50% + 3px)
    );
  }

  :global([data-theme='nightly']) .cross::after {
    background: linear-gradient(
      to right,
      rgba(204, 68, 0, 0.65) calc(50% - 3px),
      transparent calc(50% - 3px),
      transparent calc(50% + 3px),
      rgba(204, 68, 0, 0.65) calc(50% + 3px)
    );
  }

  :global([data-theme='nightly']) .icon-btn {
    border-color: rgba(200, 0, 0, 0.5);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .icon-btn.danger {
    border-color: rgba(200, 0, 0, 0.65);
    color: #cc0000;
  }

  .step-arrow,
  .title-arrow {
    font-size: 1.15em;
    vertical-align: 0.05em;
    margin: 0 0.2em;
  }

  .step-mx {
    font-weight: normal;
    opacity: 0.75;
  }

  .btn.danger {
    border-color: rgba(255, 120, 120, 0.5);
    color: #ff9a9a;
  }

  .step-nav {
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
  }

  .step-nav-label {
    font-size: 0.85rem;
    text-align: center;
    flex: 1;
    min-width: 0;
  }

  .step-nav-name {
    margin-left: 0.4em;
    font-weight: 700;
  }

  .nav-btn {
    border: 1px solid rgba(232, 232, 232, 0.3);
    background: rgba(255, 255, 255, 0.05);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.3rem 0.6rem;
    font-size: 1rem;
    cursor: pointer;
    line-height: 1;
  }

  .nav-btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  :global([data-theme='nightly']) .btn.danger {
    border-color: rgba(200, 0, 0, 0.5);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .nav-btn {
    border-color: rgba(180, 0, 0, 0.35);
    color: #cc0000;
    background: rgba(180, 0, 0, 0.08);
  }
</style>
