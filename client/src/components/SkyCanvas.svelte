<script>
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { projectToPixel, isOnScreen } from '../lib/skymath.js'
  import { isAboveHorizon, getLST } from '../lib/horizon.js'
  import { theme } from '../stores/theme.js'

  export let ra0 = 0
  export let dec0 = 0
  export let fov = 30
  export let rotation = 0
  export let objects = []
  export let lat = 51.5
  export let lon = 0
  export let time = new Date()

  let canvas
  let W = 0, H = 0
  let rafId = null
  let dirty = true
  let observer
  let currentTheme = get(theme)
  let aboveMap = new Map()

  const unsubTheme = theme.subscribe(v => { currentTheme = v; dirty = true })

  $: { ra0; dec0; fov; rotation; objects; lat; lon; time; dirty = true }

  $: updateAboveMap(lat, lon, time, objects)

  function updateAboveMap(latV, lonV, timeV, objs) {
    const map = new Map()
    for (const o of objs) {
      if (o.pos) map.set(o.id, isAboveHorizon(o.pos[0], o.pos[1], latV, lonV, timeV))
    }
    aboveMap = map
    dirty = true
  }

  // Dynamic magnitude → pixel radius.
  // The faintest visible star (at adaptive magLim) always renders at MIN_R px.
  // The brightest star (BRIGHT_MAG) renders at maxR, which shrinks at wide FOV
  // (fewer visual clutter) and grows at narrow FOV (faint stars more visible).
  // Linear interpolation in magnitude space between the two endpoints.
  const BRIGHT_MAG = 2.0
  const MIN_R = 1.5
  const FOV_REF_SIZE = 30    // FOV at which MAX_R_AT_REF applies
  const MAX_R_AT_REF = 5

  function starRadius(mag) {
    const magLim = adaptiveMagLimit(fov)
    const fovScale = Math.sqrt(FOV_REF_SIZE / fov)
    const maxR = Math.min(MAX_R_AT_REF * fovScale, 10)
    const t = Math.max(0, Math.min(1, (magLim - mag) / (magLim - BRIGHT_MAG)))
    return MIN_R + (maxR - MIN_R) * t
  }

  // FOV (degrees) at which the magnitude limit reaches its floor of 5.
  // Each halving of FOV raises the limit by 1 mag (constant star surface density).
  // e.g. FOV_FOR_STAR_MAG_5=240: fov=120→6, fov=60→7, fov=30→8, fov=15→9.
  const FOV_FOR_STAR_MAG_5 = 120

  function adaptiveMagLimit(fovDeg) {
    return Math.min(9, Math.max(5, 5 + Math.log2(FOV_FOR_STAR_MAG_5 / fovDeg)))
  }

  // DSO angular size in arcmin → canvas pixels. Returns raw value (no min clamp) for threshold check.
  function dsoRawPx(size) {
    const arcmin = Array.isArray(size) ? size[0] : (size ?? 5)
    return arcmin * H / (60 * fov)
  }

  // Below this fraction of min(W,H), draw a fixed Hipparcos symbol instead of a scaled shape.
  const DSO_SYMBOL_THRESHOLD = 0.04
  const SYM_R = 8   // fixed symbol radius in px

  function drawDsoSymbol(ctx, obj, pt, above) {
    const nightly = currentTheme === 'nightly'
    const r = SYM_R
    ctx.globalAlpha = above ? 0.85 : 0.2
    ctx.strokeStyle = nightly ? '#d09ab8' : '#99c0ff'
    ctx.lineWidth = 1
    ctx.setLineDash([])

    const type = obj.dsoType ?? 'galaxy'

    if (type === 'open cluster') {
      ctx.beginPath()
      ctx.setLineDash([3, 3])
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      ctx.setLineDash([])

    } else if (type === 'globular cluster') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(pt.px - r, pt.py); ctx.lineTo(pt.px + r, pt.py)
      ctx.moveTo(pt.px, pt.py - r); ctx.lineTo(pt.px, pt.py + r)
      ctx.stroke()

    } else if (type === 'planetary nebula') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      const tick = 4
      ctx.beginPath()
      ctx.moveTo(pt.px - r - tick, pt.py); ctx.lineTo(pt.px - r, pt.py)
      ctx.moveTo(pt.px + r,        pt.py); ctx.lineTo(pt.px + r + tick, pt.py)
      ctx.moveTo(pt.px, pt.py - r - tick); ctx.lineTo(pt.px, pt.py - r)
      ctx.moveTo(pt.px, pt.py + r);        ctx.lineTo(pt.px, pt.py + r + tick)
      ctx.stroke()

    } else if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') {
      const ang_rad = ((obj.ang ?? 0) - 90) * Math.PI / 180
      ctx.save()
      ctx.translate(pt.px, pt.py)
      ctx.rotate(ang_rad)
      ctx.beginPath()
      ctx.ellipse(0, 0, r, Math.max(2, r * 0.4), 0, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()

    } else if (type === 'dark nebula') {
      ctx.setLineDash([3, 3])
      ctx.strokeRect(pt.px - r, pt.py - r, r * 2, r * 2)
      ctx.setLineDash([])

    } else if (type === 'galaxy cluster' || type === 'cluster of galaxies') {
      ctx.beginPath()
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * 2 * Math.PI - Math.PI / 2
        if (i === 0) ctx.moveTo(pt.px + r * Math.cos(a), pt.py + r * Math.sin(a))
        else         ctx.lineTo(pt.px + r * Math.cos(a), pt.py + r * Math.sin(a))
      }
      ctx.closePath()
      ctx.stroke()

    } else if (type === 'quasar' || type === 'QSO' || type === 'BL Lac') {
      const d = r * 0.75
      ctx.beginPath()
      ctx.moveTo(pt.px - d, pt.py - d); ctx.lineTo(pt.px + d, pt.py + d)
      ctx.moveTo(pt.px + d, pt.py - d); ctx.lineTo(pt.px - d, pt.py + d)
      ctx.stroke()

    } else {
      // emission nebula, reflection nebula → open square
      ctx.strokeRect(pt.px - r, pt.py - r, r * 2, r * 2)
    }

    ctx.globalAlpha = 1
  }

  function drawStar(ctx, obj, pt, above) {
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    ctx.globalAlpha = above ? 0.92 : 0.22
    ctx.beginPath()
    ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
    ctx.fillStyle = nightly ? '#e06a5a' : (obj.clr || '#ffffff')
    ctx.fill()
    ctx.globalAlpha = 1
  }

  function drawDoubleStar(ctx, obj, pt, above) {
    drawStar(ctx, obj, pt, above)
    if (above) {
      const nightly = currentTheme === 'nightly'
      const r = starRadius(obj.mag ?? 5) + 2.5
      ctx.globalAlpha = 0.5
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.strokeStyle = nightly ? '#e06a5a' : '#ffffff'
      ctx.lineWidth = 0.8
      ctx.stroke()
      ctx.globalAlpha = 1
    }
  }

  function drawDso(ctx, obj, pt, above) {
    const rawSz = dsoRawPx(obj.size)
    if (rawSz < DSO_SYMBOL_THRESHOLD * Math.min(W, H)) {
      drawDsoSymbol(ctx, obj, pt, above)
      return
    }

    const nightly = currentTheme === 'nightly'
    const sz = Math.max(4, Math.min(50, rawSz))
    const r = sz / 2
    ctx.globalAlpha = above ? 0.85 : 0.2
    ctx.strokeStyle = nightly ? '#d09ab8' : '#99c0ff'
    ctx.lineWidth = 1
    ctx.setLineDash([])

    const type = obj.dsoType ?? 'galaxy'

    if (type === 'open cluster') {
      ctx.beginPath()
      ctx.setLineDash([3, 3])
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      ctx.setLineDash([])

    } else if (type === 'globular cluster') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(pt.px - r, pt.py); ctx.lineTo(pt.px + r, pt.py)
      ctx.moveTo(pt.px, pt.py - r); ctx.lineTo(pt.px, pt.py + r)
      ctx.stroke()

    } else if (type === 'planetary nebula') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      const tick = Math.max(2, r * 0.5)
      ctx.beginPath()
      ctx.moveTo(pt.px - r - tick, pt.py); ctx.lineTo(pt.px - r, pt.py)
      ctx.moveTo(pt.px + r, pt.py);        ctx.lineTo(pt.px + r + tick, pt.py)
      ctx.moveTo(pt.px, pt.py - r - tick); ctx.lineTo(pt.px, pt.py - r)
      ctx.moveTo(pt.px, pt.py + r);        ctx.lineTo(pt.px, pt.py + r + tick)
      ctx.stroke()

    } else if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') {
      // PA=0 → North (up on canvas) = canvas rotation −90°
      const ang_rad = ((obj.ang ?? 0) - 90) * Math.PI / 180
      const major = r
      const minor = Array.isArray(obj.size)
        ? Math.max(2, (obj.size[1] / obj.size[0]) * major)
        : major * 0.4
      ctx.save()
      ctx.translate(pt.px, pt.py)
      ctx.rotate(ang_rad)
      ctx.beginPath()
      ctx.ellipse(0, 0, major, minor, 0, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()

    } else {
      // emission nebula, reflection nebula → dashed square
      ctx.beginPath()
      ctx.setLineDash([3, 3])
      ctx.strokeRect(pt.px - r, pt.py - r, sz, sz)
      ctx.setLineDash([])
    }

    ctx.globalAlpha = 1
  }

  // Horizon is a great circle → projects to a straight line in gnomonic.
  // Sample 72 azimuth points, sort by px, extrapolate to canvas edges, fill below.
  function drawHorizonOverlay(ctx) {
    const lst_rad = getLST(lat, lon, time) * Math.PI / 12
    const lat_rad = lat * Math.PI / 180
    const pts = []

    for (let i = 0; i < 72; i++) {
      const az_rad = (i / 72) * 2 * Math.PI
      // (az, alt=0) → equatorial: dec = arcsin(cos(φ)·cos(az))
      // HA from direction cosines: atan2(−sin(az), −sin(φ)·cos(az))
      const dec_rad = Math.asin(Math.cos(lat_rad) * Math.cos(az_rad))
      const ha_rad  = Math.atan2(-Math.sin(az_rad), -Math.sin(lat_rad) * Math.cos(az_rad))
      const ra_rad  = lst_rad - ha_rad
      const ra_deg  = ((ra_rad * 180 / Math.PI) % 360 + 360) % 360
      const dec_deg = dec_rad * 180 / Math.PI
      const pt = projectToPixel(ra_deg, dec_deg, ra0, dec0, W, H, fov, rotation)
      if (pt) pts.push(pt)
    }

    if (pts.length < 2) return
    pts.sort((a, b) => a.px - b.px)

    const p0 = pts[0], pN = pts[pts.length - 1]
    const dx = pN.px - p0.px
    if (Math.abs(dx) < 1) return

    const slope   = (pN.py - p0.py) / dx
    const pyLeft  = p0.py - p0.px * slope
    const pyRight = pN.py + (W - pN.px) * slope

    // Ground fill
    ctx.beginPath()
    ctx.moveTo(0, pyLeft)
    ctx.lineTo(W, pyRight)
    ctx.lineTo(W, H)
    ctx.lineTo(0, H)
    ctx.closePath()
    ctx.fillStyle = 'rgba(0,0,0,0.55)'
    ctx.fill()

    // Horizon line
    ctx.beginPath()
    ctx.moveTo(0, pyLeft)
    ctx.lineTo(W, pyRight)
    ctx.strokeStyle = 'rgba(128,128,128,0.45)'
    ctx.lineWidth = 1
    ctx.setLineDash([6, 4])
    ctx.stroke()
    ctx.setLineDash([])
  }

  function draw() {
    if (!canvas || W === 0 || H === 0) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, W, H)

    drawHorizonOverlay(ctx)

    const magLim = adaptiveMagLimit(fov)
    // DSO limit: anchored at starMag=5→dsoMag=8, starMag=13→dsoMag=12 (linear in mag space).
    // DSOs are extended objects; their visual limit lags stars by 3 mags at naked-eye FOV,
    // converging to 1 mag below at large-aperture FOV.
    const dsoMagLim = 8 + 0.5 * (magLim - 5)

    const dbStars = objects.filter(o => o.type === 'star' || o.type === 'double_star')
    const noMagStars = dbStars.filter(o => o.mag == null).length
    const magPassStars = dbStars.filter(o => (o.mag ?? 99) <= magLim).length

    const survey = {}
    function tally(label) { survey[label] = (survey[label] ?? 0) + 1 }

    // Pass 1: DSOs (rendered first so stars paint on top)
    for (const obj of objects) {
      if (!obj.pos || obj.type !== 'dso') continue
      if ((obj.mag ?? 8) > dsoMagLim) continue
      const [ra, dec] = obj.pos
      const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
      if (!pt || !isOnScreen(pt.px, pt.py, W, H, 10)) continue
      drawDso(ctx, obj, pt, aboveMap.get(obj.id) ?? false)
      tally(obj.dsoType ?? 'galaxy')
    }

    // Pass 2: stars and double stars (rendered on top of DSOs)
    for (const obj of objects) {
      if (!obj.pos) continue
      if (obj.type === 'star' || obj.type === 'double_star') {
        if ((obj.mag ?? 99) > magLim) continue
        const [ra, dec] = obj.pos
        const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
        if (!pt || !isOnScreen(pt.px, pt.py, W, H, 10)) continue
        const above = aboveMap.get(obj.id) ?? false
        if (obj.type === 'star') { drawStar(ctx, obj, pt, above); tally('star') }
        else { drawDoubleStar(ctx, obj, pt, above); tally('double_star') }
      }
    }

    console.log(`[SkyCanvas] fov=${fov}° starMagLim=${magLim.toFixed(1)} dsoMagLim=${dsoMagLim.toFixed(1)} | db:${dbStars.length} noMag:${noMagStars} magPass:${magPassStars} onScreen:`, survey)
    dirty = false
  }

  function loop() {
    if (dirty) draw()
    rafId = requestAnimationFrame(loop)
  }

  onMount(() => {
    observer = new ResizeObserver(entries => {
      for (const e of entries) {
        W = e.contentRect.width
        H = e.contentRect.height
        canvas.width = W
        canvas.height = H
        dirty = true
      }
    })
    observer.observe(canvas.parentElement)
    W = canvas.parentElement.clientWidth
    H = canvas.parentElement.clientHeight
    canvas.width = W
    canvas.height = H
    loop()
  })

  onDestroy(() => {
    if (rafId !== null) cancelAnimationFrame(rafId)
    if (observer) observer.disconnect()
    unsubTheme()
  })
</script>

<canvas bind:this={canvas} style="display:block;width:100%;height:100%"></canvas>
