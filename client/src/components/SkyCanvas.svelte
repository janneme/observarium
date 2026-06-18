<script>
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { projectToPixel, isOnScreen } from '../lib/skymath.js'
  import { isAboveHorizon, getLST } from '../lib/horizon.js'
  import { theme } from '../stores/theme.js'
  import { getMeta } from '../lib/db.js'
  import { selectedObject } from '../stores/selectedObject.js'

  export let ra0 = 0
  export let dec0 = 0
  export let fov = 30
  export let rotation = 0
  export let objects = []
  export let lat = 51.5
  export let lon = 0
  export let time = new Date()
  export let showFovCircle = false
  export let showConstellationLines = false
  export let showConstellationNames = false
  export let showConstellationBoundaries = false
  export let showDsos = true
  export let showHorizon = true
  export let flashIds = new Set()
  export let finderMode = false

  let canvas
  let W = 0,
    H = 0
  let rafId = null
  let dirty = true
  let observer
  let currentTheme = get(theme)
  let aboveMap = new Map()
  let constellations = null

  const unsubTheme = theme.subscribe((v) => {
    currentTheme = v
    dirty = true
  })

  let currentSelectedObj = null
  const unsubSelected = selectedObject.subscribe((v) => {
    currentSelectedObj = v
    dirty = true
  })

  $: {
    ra0
    dec0
    fov
    rotation
    objects
    lat
    lon
    time
    showFovCircle
    showConstellationLines
    showConstellationNames
    showConstellationBoundaries
    showDsos
    showHorizon
    flashIds
    finderMode
    dirty = true
  }

  $: updateAboveMap(lat, lon, time, objects)

  function updateAboveMap(latV, lonV, timeV, objs) {
    const map = new Map()
    for (const o of objs) {
      if (o.pos) map.set(o.id, isAboveHorizon(o.pos[0], o.pos[1], latV, lonV, timeV))
    }
    aboveMap = map
    dirty = true
  }

  // Dynamic magnitude → pixel radius, expressed in vmin so the result is
  // independent of physical pixel density.  1 vmin = 1% of min(W, H).
  // The interpolation window is always MAG_RANGE wide, sliding with magLim:
  // faintest rendered star → MIN_R_VMIN, stars brighter than (magLim - MAG_RANGE) → MAX_R_VMIN.
  const MAG_RANGE = 6
  const MIN_R_VMIN = 0.08 // faintest visible star (at magLim), in vmin
  const MAX_R_VMIN = 0.35 // brightest star (mag ≤ magLim − MAG_RANGE), in vmin

  function starRadius(mag) {
    const m = Array.isArray(mag) ? mag[0] : mag
    const magLim = adaptiveMagLimit(fov)
    const t = Math.max(0, Math.min(1, (magLim - m) / MAG_RANGE))
    const vmin = Math.min(W, H) / 100
    return (MIN_R_VMIN + (MAX_R_VMIN - MIN_R_VMIN) * t) * vmin
  }

  // Log-linear interpolation: mag 5 at FOV_MAG5, mag 14 at FOV_MAG14.
  const FOV_MAG5 = 120 // FOV (°) where rendering depth floor is mag 5
  const FOV_MAG14 = 2 // FOV (°) where rendering depth ceiling is mag 14

  function adaptiveMagLimit(fovDeg) {
    return Math.min(14, Math.max(5, 5 + (9 * Math.log2(FOV_MAG5 / fovDeg)) / Math.log2(FOV_MAG5 / FOV_MAG14)))
  }

  // DSO angular size in arcmin → canvas pixels. Returns raw value (no min clamp) for threshold check.
  function dsoRawPx(size) {
    const arcmin = Array.isArray(size) ? size[0] : (size ?? 5)
    return (arcmin * H) / (60 * fov)
  }

  // Below this fraction of min(W,H), draw a fixed Hipparcos symbol instead of a scaled shape.
  const DSO_SYMBOL_THRESHOLD = 0.04
  const SYM_R = 8 // fixed symbol radius in px

  function drawDsoSymbol(ctx, obj, pt, above) {
    const nightly = currentTheme === 'nightly'
    const r = SYM_R
    ctx.globalAlpha = above ? 0.85 : 0.2
    ctx.strokeStyle = nightly ? '#880000' : '#99c0ff'
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
      ctx.moveTo(pt.px - r, pt.py)
      ctx.lineTo(pt.px + r, pt.py)
      ctx.moveTo(pt.px, pt.py - r)
      ctx.lineTo(pt.px, pt.py + r)
      ctx.stroke()
    } else if (type === 'planetary nebula') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      const tick = 4
      ctx.beginPath()
      ctx.moveTo(pt.px - r - tick, pt.py)
      ctx.lineTo(pt.px - r, pt.py)
      ctx.moveTo(pt.px + r, pt.py)
      ctx.lineTo(pt.px + r + tick, pt.py)
      ctx.moveTo(pt.px, pt.py - r - tick)
      ctx.lineTo(pt.px, pt.py - r)
      ctx.moveTo(pt.px, pt.py + r)
      ctx.lineTo(pt.px, pt.py + r + tick)
      ctx.stroke()
    } else if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') {
      const ang_rad = (((obj.ang ?? 0) - 90) * Math.PI) / 180
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
        else ctx.lineTo(pt.px + r * Math.cos(a), pt.py + r * Math.sin(a))
      }
      ctx.closePath()
      ctx.stroke()
    } else if (type === 'quasar' || type === 'QSO' || type === 'BL Lac') {
      const d = r * 0.75
      ctx.beginPath()
      ctx.moveTo(pt.px - d, pt.py - d)
      ctx.lineTo(pt.px + d, pt.py + d)
      ctx.moveTo(pt.px + d, pt.py - d)
      ctx.lineTo(pt.px - d, pt.py + d)
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
    let fill
    if (nightly) {
      fill = '#e00000'
    } else if (finderMode) {
      const m = Array.isArray(obj.mag) ? obj.mag[0] : (obj.mag ?? 99)
      fill = m <= 3 && obj.clr ? _blendToWhite(obj.clr, 0.72) : '#ffffff'
    } else {
      fill = obj.clr || '#ffffff'
    }
    ctx.fillStyle = fill
    ctx.fill()
    ctx.globalAlpha = 1
  }

  function _blendToWhite(hex, t) {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    const h = (v) =>
      Math.round(v + (255 - v) * t)
        .toString(16)
        .padStart(2, '0')
    return `#${h(r)}${h(g)}${h(b)}`
  }

  function _darkenHex(hex, factor) {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    const h = (v) =>
      Math.round(v * factor)
        .toString(16)
        .padStart(2, '0')
    return `#${h(r)}${h(g)}${h(b)}`
  }

  // Variable star: solid ring around the disk (Hipparcos convention, amplitude ≥ 1 mag)
  function addVariableRing(ctx, obj, pt, above) {
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    ctx.globalAlpha = above ? 0.7 : 0.15
    ctx.beginPath()
    const gap = Math.max(1.5, r * 1.5)
    const lw = Math.max(0.9, r * 1.0)
    ctx.arc(pt.px, pt.py, r + gap, 0, Math.PI * 2)
    const starColor = nightly ? '#e00000' : obj.clr || '#ffffff'
    ctx.strokeStyle = _darkenHex(starColor, 0.45)
    ctx.lineWidth = lw
    ctx.stroke()
    ctx.globalAlpha = 1
  }

  // Double star: short jutting line at 45° from the disk edge (Hipparcos convention)
  function addDoubleJut(ctx, obj, pt, above) {
    if (!above) return
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    const jut = Math.max(3, r * 1.2)
    ctx.globalAlpha = 0.65
    ctx.beginPath()
    ctx.moveTo(pt.px + Math.SQRT1_2 * r, pt.py - Math.SQRT1_2 * r)
    ctx.lineTo(pt.px + Math.SQRT1_2 * (r + jut), pt.py - Math.SQRT1_2 * (r + jut))
    ctx.strokeStyle = nightly ? '#e00000' : '#ffffff'
    ctx.lineWidth = 1.2
    ctx.stroke()
    ctx.globalAlpha = 1
  }

  const FINDER_FOV = 7.5

  function drawFovCircle(ctx) {
    const fovRad = (fov * Math.PI) / 180
    const r = (Math.tan(((FINDER_FOV / 2) * Math.PI) / 180) * H) / fovRad
    if (r > Math.min(W, H) / 2) return
    ctx.beginPath()
    ctx.arc(W / 2, H / 2, r, 0, Math.PI * 2)
    ctx.strokeStyle = currentTheme === 'nightly' ? 'rgba(224,0,0,0.4)' : 'rgba(255,255,255,0.4)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([6, 4])
    ctx.stroke()
    ctx.setLineDash([])
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
    ctx.strokeStyle = nightly ? '#880000' : '#99c0ff'
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
      ctx.moveTo(pt.px - r, pt.py)
      ctx.lineTo(pt.px + r, pt.py)
      ctx.moveTo(pt.px, pt.py - r)
      ctx.lineTo(pt.px, pt.py + r)
      ctx.stroke()
    } else if (type === 'planetary nebula') {
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.stroke()
      const tick = Math.max(2, r * 0.5)
      ctx.beginPath()
      ctx.moveTo(pt.px - r - tick, pt.py)
      ctx.lineTo(pt.px - r, pt.py)
      ctx.moveTo(pt.px + r, pt.py)
      ctx.lineTo(pt.px + r + tick, pt.py)
      ctx.moveTo(pt.px, pt.py - r - tick)
      ctx.lineTo(pt.px, pt.py - r)
      ctx.moveTo(pt.px, pt.py + r)
      ctx.lineTo(pt.px, pt.py + r + tick)
      ctx.stroke()
    } else if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') {
      // PA=0 → North (up on canvas) = canvas rotation −90°
      const ang_rad = (((obj.ang ?? 0) - 90) * Math.PI) / 180
      const major = r
      const minor = Array.isArray(obj.size) ? Math.max(2, (obj.size[1] / obj.size[0]) * major) : major * 0.4
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

  // Circular mean of boundary vertices → [ra_h, dec_d] centroid for a constellation.
  function _conCentroid(con) {
    if (!con.bounds || con.bounds.length === 0) return null
    const seen = new Set()
    let sinSum = 0,
      cosSum = 0,
      decSum = 0,
      n = 0
    for (const seg of con.bounds) {
      for (const v of seg) {
        const key = v[0] + ',' + v[1]
        if (seen.has(key)) continue
        seen.add(key)
        const ang = (v[0] / 24) * 2 * Math.PI
        sinSum += Math.sin(ang)
        cosSum += Math.cos(ang)
        decSum += v[1]
        n++
      }
    }
    if (n === 0) return null
    let ra_c = (Math.atan2(sinSum, cosSum) / (2 * Math.PI)) * 24
    if (ra_c < 0) ra_c += 24
    return [ra_c, decSum / n]
  }

  function drawConstellationBoundaries(ctx) {
    if (!constellations) return
    const nightly = currentTheme === 'nightly'
    ctx.strokeStyle = nightly ? 'rgba(136,0,0,0.45)' : 'rgba(80,100,180,0.45)'
    ctx.lineWidth = 1.0
    ctx.setLineDash([3, 6])

    // Subdivide each segment so that when one endpoint is behind the gnomonic
    // projection plane (>90° from view centre), the visible portion still draws.
    const STEPS = 8
    for (const con of Object.values(constellations)) {
      for (const seg of con.bounds) {
        const ra1h = seg[0][0],
          dec1 = seg[0][1]
        const ra2h = seg[1][0],
          dec2 = seg[1][1]
        // Shortest-path RA interpolation across the 0h/24h wrap
        let dRa = ra2h - ra1h
        if (dRa > 12) dRa -= 24
        if (dRa < -12) dRa += 24

        let inPath = false
        for (let i = 0; i <= STEPS; i++) {
          const t = i / STEPS
          const ra = ((((ra1h + t * dRa) * 15) % 360) + 360) % 360
          const dec = dec1 + t * (dec2 - dec1)
          const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
          if (pt) {
            if (!inPath) {
              ctx.beginPath()
              ctx.moveTo(pt.px, pt.py)
              inPath = true
            } else {
              ctx.lineTo(pt.px, pt.py)
            }
          } else {
            if (inPath) {
              ctx.stroke()
              inPath = false
            }
          }
        }
        if (inPath) ctx.stroke()
      }
    }
    ctx.setLineDash([])
  }

  function drawConstellationLines(ctx) {
    if (!constellations) return
    const nightly = currentTheme === 'nightly'
    const hipMap = new Map()
    for (const obj of objects) {
      if (obj.hip) hipMap.set(obj.hip, obj.pos)
    }
    ctx.strokeStyle = nightly ? 'rgba(136,0,0,0.55)' : 'rgba(100,120,220,0.5)'
    ctx.lineWidth = 1
    ctx.setLineDash([])
    for (const con of Object.values(constellations)) {
      for (const [hip_a, hip_b] of con.lines) {
        const posA = hipMap.get(hip_a)
        const posB = hipMap.get(hip_b)
        if (!posA || !posB) continue
        const ptA = projectToPixel(posA[0], posA[1], ra0, dec0, W, H, fov, rotation)
        const ptB = projectToPixel(posB[0], posB[1], ra0, dec0, W, H, fov, rotation)
        if (!ptA || !ptB) continue
        if (!isOnScreen(ptA.px, ptA.py, W, H, 40) && !isOnScreen(ptB.px, ptB.py, W, H, 40)) continue
        ctx.beginPath()
        ctx.moveTo(ptA.px, ptA.py)
        ctx.lineTo(ptB.px, ptB.py)
        ctx.stroke()
      }
    }
  }

  function drawConstellationNames(ctx) {
    if (!constellations) return
    const nightly = currentTheme === 'nightly'
    ctx.fillStyle = nightly ? 'rgba(136,0,0,0.75)' : 'rgba(160,185,230,0.8)'
    ctx.font = '11px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const con of Object.values(constellations)) {
      const c = _conCentroid(con)
      if (!c) continue
      const pt = projectToPixel(c[0] * 15, c[1], ra0, dec0, W, H, fov, rotation)
      if (!pt || !isOnScreen(pt.px, pt.py, W, H, 0)) continue
      ctx.fillText(con.name, pt.px, pt.py)
    }
  }

  // Horizon is a great circle → projects to a straight line in gnomonic.
  // Sample 72 azimuth points, sort by px, extrapolate to canvas edges, fill below.
  function drawHorizonOverlay(ctx) {
    const lst_rad = (getLST(lat, lon, time) * Math.PI) / 12
    const lat_rad = (lat * Math.PI) / 180
    const pts = []

    for (let i = 0; i < 72; i++) {
      const az_rad = (i / 72) * 2 * Math.PI
      // (az, alt=0) → equatorial: dec = arcsin(cos(φ)·cos(az))
      // HA from direction cosines: atan2(−sin(az), −sin(φ)·cos(az))
      const dec_rad = Math.asin(Math.cos(lat_rad) * Math.cos(az_rad))
      const ha_rad = Math.atan2(-Math.sin(az_rad), -Math.sin(lat_rad) * Math.cos(az_rad))
      const ra_rad = lst_rad - ha_rad
      const ra_deg = ((((ra_rad * 180) / Math.PI) % 360) + 360) % 360
      const dec_deg = (dec_rad * 180) / Math.PI
      const pt = projectToPixel(ra_deg, dec_deg, ra0, dec0, W, H, fov, rotation)
      if (pt) pts.push(pt)
    }

    if (pts.length < 2) return
    pts.sort((a, b) => a.px - b.px)

    const p0 = pts[0],
      pN = pts[pts.length - 1]
    const dx = pN.px - p0.px
    if (Math.abs(dx) < 1) return

    const slope = (pN.py - p0.py) / dx
    const pyLeft = p0.py - p0.px * slope
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
    ctx.strokeStyle = currentTheme === 'nightly' ? 'rgba(136,0,0,0.45)' : 'rgba(128,128,128,0.45)'
    ctx.lineWidth = 1
    ctx.setLineDash([6, 4])
    ctx.stroke()
    ctx.setLineDash([])
  }

  function drawSelectedMarker(ctx) {
    if (!currentSelectedObj?.pos) return
    const [ra, dec] = currentSelectedObj.pos
    const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
    if (!pt || !isOnScreen(pt.px, pt.py, W, H, 30)) return
    const gap = 9,
      len = 10
    ctx.strokeStyle = currentTheme === 'nightly' ? 'rgba(255,110,110,0.9)' : 'rgba(255,255,255,0.9)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(pt.px, pt.py - gap)
    ctx.lineTo(pt.px, pt.py - gap - len)
    ctx.moveTo(pt.px, pt.py + gap)
    ctx.lineTo(pt.px, pt.py + gap + len)
    ctx.moveTo(pt.px - gap, pt.py)
    ctx.lineTo(pt.px - gap - len, pt.py)
    ctx.moveTo(pt.px + gap, pt.py)
    ctx.lineTo(pt.px + gap + len, pt.py)
    ctx.stroke()
  }

  function draw() {
    if (!canvas || W === 0 || H === 0) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, W, H)

    if (showHorizon) drawHorizonOverlay(ctx)

    if (showConstellationBoundaries) drawConstellationBoundaries(ctx)
    if (showConstellationLines) drawConstellationLines(ctx)
    if (showConstellationNames) drawConstellationNames(ctx)

    const renderedPx = new Map()
    const magLim = adaptiveMagLimit(fov)
    // DSO limit: anchored at starMag=5→dsoMag=8, starMag=13→dsoMag=12 (linear in mag space).
    // DSOs are extended objects; their visual limit lags stars by 3 mags at naked-eye FOV,
    // converging to 1 mag below at large-aperture FOV.
    const dsoMagLim = 8 + 0.5 * (magLim - 5)

    const dbStars = objects.filter((o) => o.type === 'star' || o.type === 'double_star')
    const noMagStars = dbStars.filter((o) => o.mag == null).length
    const magPassStars = dbStars.filter((o) => (o.mag ?? 99) <= magLim).length

    const survey = {}
    function tally(label) {
      survey[label] = (survey[label] ?? 0) + 1
    }

    // Pass 1: DSOs (rendered first so stars paint on top)
    if (showDsos) {
      for (const obj of objects) {
        if (!obj.pos || obj.type !== 'dso') continue
        if ((obj.mag ?? 8) > dsoMagLim) continue
        const [ra, dec] = obj.pos
        const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
        if (!pt || !isOnScreen(pt.px, pt.py, W, H, 10)) continue
        drawDso(ctx, obj, pt, aboveMap.get(obj.id) ?? false)
        renderedPx.set(obj.id, { px: pt.px, py: pt.py })
        tally(obj.dsoType ?? 'galaxy')
      }
    }

    // Pass 2: stars and double stars (rendered on top of DSOs)
    for (const obj of objects) {
      if (!obj.pos) continue
      if (obj.type === 'star' || obj.type === 'double_star') {
        const objMag = Array.isArray(obj.mag) ? obj.mag[0] : (obj.mag ?? 99)
        if (objMag > magLim) continue
        const [ra, dec] = obj.pos
        const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
        if (!pt || !isOnScreen(pt.px, pt.py, W, H, 10)) continue
        const above = aboveMap.get(obj.id) ?? false
        const isDouble = obj.type === 'double_star'
        const isVariable = Array.isArray(obj.mag) && obj.mag[1] - obj.mag[0] >= 1
        drawStar(ctx, obj, pt, above)
        if (isVariable) addVariableRing(ctx, obj, pt, above)
        if (isDouble) addDoubleJut(ctx, obj, pt, above)
        renderedPx.set(obj.id, { px: pt.px, py: pt.py })
        tally(isDouble ? 'double_star' : 'star')
      }
    }

    if (flashIds.size > 0) {
      ctx.strokeStyle = currentTheme === 'nightly' ? '#ff0000' : '#ffff00'
      ctx.lineWidth = 2
      ctx.setLineDash([])
      for (const [id, p] of renderedPx) {
        if (flashIds.has(id)) {
          ctx.beginPath()
          ctx.arc(p.px, p.py, 15, 0, Math.PI * 2)
          ctx.stroke()
        }
      }
    }
    if (!finderMode) drawSelectedMarker(ctx)
    if (showFovCircle) drawFovCircle(ctx)

    console.log(
      `[SkyCanvas] fov=${fov}° starMagLim=${magLim.toFixed(1)} dsoMagLim=${dsoMagLim.toFixed(1)} | db:${dbStars.length} noMag:${noMagStars} magPass:${magPassStars} onScreen:`,
      survey,
    )
    dirty = false
  }

  function loop() {
    if (dirty) draw()
    rafId = requestAnimationFrame(loop)
  }

  onMount(() => {
    getMeta('constellations').then((data) => {
      if (data) {
        constellations = data
        dirty = true
      }
    })

    observer = new ResizeObserver((entries) => {
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
    unsubSelected()
  })
</script>

<canvas bind:this={canvas} style="display:block;width:100%;height:100%"></canvas>
