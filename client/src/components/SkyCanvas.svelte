<script>
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { projectToPixel, isOnScreen } from '../lib/skymath.js'
  import { isAboveHorizon, getLST } from '../lib/horizon.js'
  import { theme } from '../stores/theme.js'
  import { getMeta, getObjectImage } from '../lib/db.js'
  import { selectedObject } from '../stores/selectedObject.js'
  import { solarSystemPositions } from '../stores/ui.js'
  import {
    Equator,
    Body,
    Illumination,
    HelioVector,
    GeoVector,
    JupiterMoons,
    AstroTime,
    Observer,
  } from 'astronomy-engine'

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
  export let magLimitOverride = null
  export let finderMode = false
  export let showSolarSystem = true
  export let overlayArrows = []

  let canvas
  let W = 0,
    H = 0
  let rafId = null
  let dirty = true
  let observer
  let currentTheme = get(theme)
  let aboveMap = new Map()
  let constellations = null
  let solarSystem = null
  let solarSystemBodies = []
  let planetImages = new Map()

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
    showSolarSystem
    magLimitOverride
    finderMode
    overlayArrows
    dirty = true
  }

  $: updateAboveMap(lat, lon, time, objects)
  $: if (solarSystem) computeSolarSystemPositions(time, lat, lon)

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
  const MIN_R_VMIN = 0.12 // faintest visible star (at magLim), in vmin
  const MAX_R_VMIN = 0.5 // brightest star (mag ≤ magLim − MAG_RANGE), in vmin

  function starRadius(mag) {
    const m = Array.isArray(mag) ? mag[0] : mag
    const magLim = magLimitOverride ?? adaptiveMagLimit(minDimFov)
    const t = Math.max(0, Math.min(1, (magLim - m) / MAG_RANGE))
    const vmin = Math.min(W, H) / 100
    return (MIN_R_VMIN + (MAX_R_VMIN - MIN_R_VMIN) * t) * vmin
  }

  // Log-linear interpolation: mag 5 at FOV_MAG5, mag 14 at FOV_MAG14.
  const FOV_MAG5 = 120 // FOV (°) where rendering depth floor is mag 5
  const FOV_MAG14 = 2 // FOV (°) where rendering depth ceiling is mag 14

  // Use the shorter viewport dimension's FOV so rendering depth matches the TopBar display.
  $: minDimFov = H > 0 ? (fov * Math.min(W, H)) / H : fov

  function adaptiveMagLimit(fovDeg) {
    return Math.min(14, Math.max(5, 5 + (9 * Math.log2(FOV_MAG5 / fovDeg)) / Math.log2(FOV_MAG5 / FOV_MAG14)))
  }

  // ── Solar system ──────────────────────────────────────────────────────────────

  const PLANET_DEFS = [
    { name: 'Mercury', key: 'Mercury', symbol: '☿', color: '#A0A0A0', bodyClass: 'planet', imageId: 'mercury' },
    { name: 'Venus', key: 'Venus', symbol: '♀', color: '#FFC649', bodyClass: 'planet', imageId: 'venus' },
    { name: 'Mars', key: 'Mars', symbol: '♂', color: '#E27B58', bodyClass: 'planet', imageId: 'mars' },
    { name: 'Jupiter', key: 'Jupiter', symbol: '♃', color: '#C88B3A', bodyClass: 'planet', imageId: 'jupiter' },
    { name: 'Saturn', key: 'Saturn', symbol: '♄', color: '#FAD5A5', bodyClass: 'planet', imageId: 'saturn' },
    { name: 'Uranus', key: 'Uranus', symbol: '♅', color: '#4FD0E7', bodyClass: 'planet', imageId: 'uranus' },
    { name: 'Neptune', key: 'Neptune', symbol: '♆', color: '#4166F5', bodyClass: 'planet', imageId: 'neptune' },
    { name: 'Pluto', key: 'Pluto', symbol: '♇', color: '#A88F7B', bodyClass: 'dwarf_planet', imageId: 'pluto' },
  ]

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
  const DWARF_PLANETS = new Set(['pluto', 'ceres', 'eris', 'haumea', 'makemake'])

  function _slugifyName(name) {
    return String(name || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
  }

  const _OBL_COS = Math.cos((23.439291111 * Math.PI) / 180)
  const _OBL_SIN = Math.sin((23.439291111 * Math.PI) / 180)

  function _mpcVal(c) {
    if (c >= '1' && c <= '9') return parseInt(c)
    return c.charCodeAt(0) - 55 // 'A'→10, 'B'→11, …
  }

  function _mpcEpochToJD(packed) {
    const base = { I: 1800, J: 1900, K: 2000 }
    const year = (base[packed[0]] ?? 2000) + parseInt(packed.slice(1, 3))
    const month = _mpcVal(packed[3])
    const day = _mpcVal(packed[4])
    const a = Math.floor((14 - month) / 12)
    const y = year + 4800 - a
    const m = month + 12 * a - 3
    return (
      day +
      Math.floor((153 * m + 2) / 5) +
      365 * y +
      Math.floor(y / 4) -
      Math.floor(y / 100) +
      Math.floor(y / 400) -
      32045
    )
  }

  function _keplerE(M_rad, e) {
    let E = M_rad
    for (let i = 0; i < 50; i++) {
      const dE = (M_rad - E + e * Math.sin(E)) / (1 - e * Math.cos(E))
      E += dE
      if (Math.abs(dE) < 1e-10) break
    }
    return E
  }

  function _minorPlanetPos(elem, astroT) {
    const D = Math.PI / 180
    const jd = astroT.tt + 2451545.0
    const jdEpoch = _mpcEpochToJD(elem.epoch)
    const n = 0.9856076686 / Math.pow(elem.a, 1.5) // deg/day
    const M = (((elem.M + n * (jd - jdEpoch)) % 360) + 360) % 360
    const E = _keplerE(M * D, elem.e)
    const cosE = Math.cos(E),
      sinE = Math.sin(E)
    const nu = Math.atan2(Math.sqrt(1 - elem.e * elem.e) * sinE, cosE - elem.e)
    const r = elem.a * (1 - elem.e * cosE)
    const cO = Math.cos(elem.Omega * D),
      sO = Math.sin(elem.Omega * D)
    const co = Math.cos(elem.omega * D),
      so = Math.sin(elem.omega * D)
    const cI = Math.cos(elem.i * D),
      sI = Math.sin(elem.i * D)
    const cN = Math.cos(nu),
      sN = Math.sin(nu)
    // Heliocentric ecliptic
    const xE = r * ((cO * co - sO * so * cI) * cN + (-cO * so - sO * co * cI) * sN)
    const yE = r * ((sO * co + cO * so * cI) * cN + (-sO * so + cO * co * cI) * sN)
    const zE = r * (so * sI * cN + co * sI * sN)
    // Ecliptic → equatorial J2000
    const xQ = xE
    const yQ = _OBL_COS * yE - _OBL_SIN * zE
    const zQ = _OBL_SIN * yE + _OBL_COS * zE
    // Subtract Earth's heliocentric position
    const earth = HelioVector(Body.Earth, astroT)
    const gx = xQ - earth.x,
      gy = yQ - earth.y,
      gz = zQ - earth.z
    const gd = Math.sqrt(gx * gx + gy * gy + gz * gz)
    const ra = ((((Math.atan2(gy, gx) * 180) / Math.PI) % 360) + 360) % 360
    const dec = (Math.asin(Math.max(-1, Math.min(1, gz / gd))) * 180) / Math.PI
    const mag = elem.H + 5 * Math.log10(r * gd)
    return { ra, dec, mag }
  }

  function computeSolarSystemPositions(timeV, latV, lonV) {
    if (!solarSystem) return
    const bodies = []
    const t = new AstroTime(timeV)
    const obs = new Observer(latV, lonV, 0)

    let earthHV = null
    try {
      earthHV = HelioVector(Body.Earth, t)
    } catch {
      /* ignore */
    }

    try {
      const eq = Equator(Body.Sun, t, obs, false, true)
      const ra = eq.ra * 15,
        dec = eq.dec
      const sunDistAU = earthHV ? Math.sqrt(earthHV.x ** 2 + earthHV.y ** 2 + earthHV.z ** 2) : 1
      bodies.push({
        name: 'Sun',
        symbol: '☉',
        color: '#FFDD00',
        type: 'sun',
        bodyClass: 'star',
        imageId: 'sun',
        ra,
        dec,
        mag: -26.7,
        distAU: sunDistAU,
        above: isAboveHorizon(ra, dec, latV, lonV, timeV),
      })
    } catch {
      /* ignore */
    }

    try {
      const eq = Equator(Body.Moon, t, obs, false, true)
      const ra = eq.ra * 15,
        dec = eq.dec
      const illum = Illumination(Body.Moon, t)
      const moonGV = GeoVector(Body.Moon, t, false)
      const moonDistAU = Math.sqrt(moonGV.x ** 2 + moonGV.y ** 2 + moonGV.z ** 2)
      const sunRa = bodies[0]?.ra ?? 0
      const dRA = ((((sunRa - ra + 180) % 360) + 360) % 360) - 180
      bodies.push({
        name: 'Moon',
        symbol: '☽',
        color: '#DDDDCC',
        type: 'moon',
        bodyClass: 'moon',
        imageId: 'moon',
        ra,
        dec,
        mag: illum.mag,
        distAU: moonDistAU,
        phaseFraction: illum.phase_fraction,
        litOnRight: dRA > 0,
        above: isAboveHorizon(ra, dec, latV, lonV, timeV),
      })
    } catch {
      /* ignore */
    }

    for (const p of PLANET_DEFS) {
      try {
        const b = Body[p.key]
        const eq = Equator(b, t, obs, false, true)
        const ra = eq.ra * 15,
          dec = eq.dec
        const illum = Illumination(b, t)
        let distAU = null
        if (earthHV) {
          const bodyHV = HelioVector(b, t)
          distAU = Math.sqrt((bodyHV.x - earthHV.x) ** 2 + (bodyHV.y - earthHV.y) ** 2 + (bodyHV.z - earthHV.z) ** 2)
        }
        const isInner = p.name === 'Mercury' || p.name === 'Venus'
        let phaseFraction = null,
          litOnRight = null
        if (isInner) {
          phaseFraction = illum.phase_fraction
          const sunRa = bodies[0]?.ra ?? 0
          const dRA = ((((sunRa - ra + 180) % 360) + 360) % 360) - 180
          litOnRight = dRA > 0
        }
        bodies.push({
          ...p,
          type: 'planet',
          ra,
          dec,
          mag: illum.mag,
          distAU,
          bodyClass: p.bodyClass || 'planet',
          imageId: p.imageId || _slugifyName(p.name),
          above: isAboveHorizon(ra, dec, latV, lonV, timeV),
          ...(phaseFraction != null ? { phaseFraction, litOnRight } : {}),
        })
      } catch {
        /* ignore */
      }
    }

    try {
      const jupGV = GeoVector(Body.Jupiter, t, true)
      const moonData = JupiterMoons(t)
      const GALILEAN = [
        { key: 'io', name: 'Io', color: '#F0C040', mag: 5.0 },
        { key: 'europa', name: 'Europa', color: '#D8C8A8', mag: 5.3 },
        { key: 'ganymede', name: 'Ganymede', color: '#B8986A', mag: 4.6 },
        { key: 'callisto', name: 'Callisto', color: '#787868', mag: 5.6 },
      ]
      for (const md of GALILEAN) {
        const mv = moonData[md.key]
        const gx = jupGV.x + mv.x,
          gy = jupGV.y + mv.y,
          gz = jupGV.z + mv.z
        const gd = Math.sqrt(gx * gx + gy * gy + gz * gz)
        const ra = ((((Math.atan2(gy, gx) * 180) / Math.PI) % 360) + 360) % 360
        const dec = (Math.asin(Math.max(-1, Math.min(1, gz / gd))) * 180) / Math.PI
        bodies.push({
          name: md.name,
          color: md.color,
          symbol: '',
          type: 'jupiter_moon',
          bodyClass: 'moon',
          ra,
          dec,
          mag: md.mag,
          distAU: gd,
          above: isAboveHorizon(ra, dec, latV, lonV, timeV),
        })
      }
    } catch {
      /* ignore */
    }

    for (const mp of solarSystem.minor_planets ?? []) {
      try {
        const slug = _slugifyName(mp.name)
        if (slug === 'pluto') continue
        const pos = _minorPlanetPos(mp, t)
        bodies.push({
          name: mp.name,
          symbol: '',
          color: '#888888',
          type: 'minor_planet',
          bodyClass: DWARF_PLANETS.has(slug) ? 'dwarf_planet' : 'asteroid',
          imageId: `asteroid_${slug}`,
          ra: pos.ra,
          dec: pos.dec,
          mag: pos.mag,
          above: isAboveHorizon(pos.ra, pos.dec, latV, lonV, timeV),
        })
      } catch {
        /* ignore */
      }
    }

    solarSystemBodies = bodies
    solarSystemPositions.set(bodies)
    dirty = true
  }

  function _drawPhaseOverlay(ctx, cx, cy, r, phaseFraction, litOnRight) {
    if (phaseFraction >= 0.999) return
    ctx.fillStyle = 'rgba(0,0,0,0.85)'
    ctx.beginPath()
    if (phaseFraction <= 0.001) {
      ctx.arc(cx, cy, r, 0, 2 * Math.PI)
    } else {
      const c = 2 * phaseFraction - 1
      if (litOnRight) {
        ctx.arc(cx, cy, r, -Math.PI / 2, Math.PI / 2, true)
        if (c >= 0) ctx.ellipse(cx, cy, r * c, r, 0, Math.PI / 2, -Math.PI / 2, true)
        else ctx.ellipse(cx, cy, -r * c, r, 0, Math.PI / 2, -Math.PI / 2, false)
      } else {
        ctx.arc(cx, cy, r, -Math.PI / 2, Math.PI / 2, false)
        if (c >= 0) ctx.ellipse(cx, cy, r * c, r, 0, Math.PI / 2, -Math.PI / 2, false)
        else ctx.ellipse(cx, cy, -r * c, r, 0, Math.PI / 2, -Math.PI / 2, true)
      }
    }
    ctx.fill()
  }

  function drawSolarSystem(ctx) {
    if (!solarSystemBodies.length) return
    const nightly = currentTheme === 'nightly'
    const magLim = magLimitOverride ?? adaptiveMagLimit(minDimFov)

    for (const body of solarSystemBodies) {
      if (body.type !== 'sun' && body.type !== 'moon' && body.mag > magLim) continue
      const pt = projectToPixel(body.ra, body.dec, ra0, dec0, W, H, fov, rotation)
      if (!pt || !isOnScreen(pt.px, pt.py, W, H, 20)) continue

      ctx.globalAlpha = body.above ? 0.95 : 0.25

      if (body.type === 'jupiter_moon') {
        if (fov > 2) {
          ctx.globalAlpha = 1
          continue
        }
        ctx.beginPath()
        ctx.arc(pt.px, pt.py, 2, 0, Math.PI * 2)
        ctx.fillStyle = nightly ? '#cc6633' : body.color
        ctx.fill()
        if (fov <= 0.5 && !finderMode) {
          ctx.fillStyle = nightly ? 'rgba(204,68,0,0.85)' : 'rgba(255,255,200,0.85)'
          ctx.font = '9px system-ui, sans-serif'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          ctx.fillText(body.name, pt.px, pt.py + 4)
        }
        ctx.globalAlpha = 1
        continue
      }

      const physR = PLANET_RADII_KM[body.name]
      const imgR = physR && body.distAU ? (physR / (body.distAU * AU_KM) / ((fov * Math.PI) / 180)) * H : 0
      const img = planetImages.get(body.name.toLowerCase())
      const useImage = img && imgR >= 3

      let dotR
      if (body.type === 'sun') dotR = 10
      else if (body.type === 'moon') dotR = 7
      else if (body.type === 'planet') dotR = 5
      else dotR = 3

      const labelR = useImage ? imgR : dotR

      if (useImage) {
        ctx.save()
        ctx.beginPath()
        ctx.arc(pt.px, pt.py, imgR, 0, 2 * Math.PI)
        ctx.clip()
        ctx.drawImage(img, pt.px - imgR, pt.py - imgR, imgR * 2, imgR * 2)
        if (body.phaseFraction != null) {
          _drawPhaseOverlay(ctx, pt.px, pt.py, imgR, body.phaseFraction, body.litOnRight ?? false)
        }
        ctx.restore()
      } else {
        const color =
          body.type === 'sun'
            ? nightly
              ? '#bb3300'
              : '#ffdd00'
            : body.type === 'moon'
              ? nightly
                ? '#aa3300'
                : '#ccccbb'
              : body.type === 'planet'
                ? nightly
                  ? '#cc2200'
                  : body.color
                : nightly
                  ? '#882200'
                  : '#aaaaaa'
        ctx.beginPath()
        ctx.arc(pt.px, pt.py, dotR, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
      }

      if (!finderMode) {
        if (body.symbol) {
          ctx.fillStyle = nightly ? '#ff5500' : '#ffffff'
          ctx.font = 'bold 13px system-ui, sans-serif'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'bottom'
          ctx.fillText(body.symbol, pt.px, pt.py - labelR - 1)
        }

        ctx.fillStyle = nightly ? 'rgba(204,68,0,0.85)' : 'rgba(255,255,200,0.85)'
        ctx.font = '10px system-ui, sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(body.name, pt.px, pt.py + labelR + 2)
      }

      ctx.globalAlpha = 1
    }
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

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs) for (const c of String(p.comp || '')) if (c >= 'A' && c <= 'Z') letters.add(c)
    return letters.size
  }

  function drawStar(ctx, obj, pt) {
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    ctx.globalAlpha = 0.92
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
  function addVariableRing(ctx, obj, pt) {
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    ctx.globalAlpha = 0.7
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
  function addDoubleJut(ctx, obj, pt, above, multi = false) {
    const nightly = currentTheme === 'nightly'
    const r = starRadius(obj.mag ?? 5)
    const gap = 2
    const baseJut = Math.max(6, r * 1.5)
    // Keep the current look around 3° FOV; shorten progressively when zoomed out,
    // but stay clearly line-like around moderate FOV values such as 30°.
    const fovScale = Math.min(1, Math.pow(3 / Math.max(fov, 3), 0.25))
    const jut = Math.max(4.2, baseJut * fovScale)
    ctx.globalAlpha = 0.7
    ctx.strokeStyle = nightly ? '#e00000' : '#ffffff'
    ctx.lineWidth = 1.4
    const x0 = pt.px + Math.SQRT1_2 * (r + gap)
    const y0 = pt.py - Math.SQRT1_2 * (r + gap)
    const x1 = pt.px + Math.SQRT1_2 * (r + gap + jut)
    const y1 = pt.py - Math.SQRT1_2 * (r + gap + jut)
    if (multi) {
      const off = 1.5 * Math.SQRT1_2
      ctx.beginPath()
      ctx.moveTo(x0 - off, y0 - off)
      ctx.lineTo(x1 - off, y1 - off)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(x0 + off, y0 + off)
      ctx.lineTo(x1 + off, y1 + off)
      ctx.stroke()
    } else {
      ctx.beginPath()
      ctx.moveTo(x0, y0)
      ctx.lineTo(x1, y1)
      ctx.stroke()
    }
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
    if (currentSelectedObj.type === 'solar_system_body') {
      const body = solarSystemBodies.find((b) => b.name.toLowerCase() === currentSelectedObj.name?.toLowerCase())
      if (body) {
        const physR = PLANET_RADII_KM[body.name]
        const imgR = physR && body.distAU ? (physR / (body.distAU * AU_KM) / ((fov * Math.PI) / 180)) * H : 0
        if (planetImages.has(body.name.toLowerCase()) && imgR >= 3) return
      }
    }
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
    const magLim = magLimitOverride ?? adaptiveMagLimit(minDimFov)
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

    // Pass 0: overlay arrows (behind DSOs and stars)
    if (overlayArrows.length) {
      const nightly = currentTheme === 'nightly'
      const arrowColor = nightly ? 'rgba(204,68,0,0.55)' : 'rgba(255,255,255,0.45)'
      const labelColor = nightly ? 'rgba(204,68,0,0.65)' : 'rgba(255,255,255,0.55)'
      ctx.save()
      ctx.strokeStyle = arrowColor
      ctx.lineWidth = 1.5
      for (const arr of overlayArrows) {
        const from = projectToPixel(arr.fromRa, arr.fromDec, ra0, dec0, W, H, fov, rotation)
        const to = projectToPixel(arr.toRa, arr.toDec, ra0, dec0, W, H, fov, rotation)
        if (!from || !to) continue
        const dx = to.px - from.px
        const dy = to.py - from.py
        const len = Math.hypot(dx, dy)
        if (len < 2) continue
        const ux = dx / len
        const uy = dy / len
        // shorten line end so chevron tip sits exactly at toRa/toDec
        const tipX = to.px
        const tipY = to.py
        ctx.beginPath()
        ctx.moveTo(from.px, from.py)
        ctx.lineTo(tipX, tipY)
        ctx.stroke()
        // open chevron head
        const hw = 8
        ctx.beginPath()
        ctx.moveTo(tipX - ux * hw + uy * hw * 0.5, tipY - uy * hw - ux * hw * 0.5)
        ctx.lineTo(tipX, tipY)
        ctx.lineTo(tipX - ux * hw - uy * hw * 0.5, tipY - uy * hw + ux * hw * 0.5)
        ctx.stroke()
        if (arr.label) {
          ctx.fillStyle = labelColor
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          const mx = (from.px + tipX) / 2
          const my = (from.py + tipY) / 2
          ctx.fillText(arr.label, mx - uy * 11, my + ux * 11)
        }
      }
      ctx.restore()
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
        const isDouble = obj.type === 'double_star' || !!obj.dbl
        const isMulti = (obj.type === 'double_star' && dsLetterCount(obj.pairs) > 2) || obj.dbl === 'm'
        const isVariable = Array.isArray(obj.mag) && obj.mag[1] - obj.mag[0] >= 1
        drawStar(ctx, obj, pt, above)
        if (isVariable) addVariableRing(ctx, obj, pt, above)
        if (isDouble) addDoubleJut(ctx, obj, pt, above, isMulti)
        renderedPx.set(obj.id, { px: pt.px, py: pt.py })
        tally(isDouble ? 'double_star' : 'star')
      }
    }

    // Pass 3: solar system bodies (on top of stars)
    if (showSolarSystem) drawSolarSystem(ctx)

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
    getMeta('solar_system').then((data) => {
      if (data) {
        solarSystem = data
      }
    })

    const PLANET_NAMES = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto']
    Promise.all(
      PLANET_NAMES.map(async (name) => {
        try {
          const rec = await getObjectImage(`planet_${name}`)
          if (rec?.blob) {
            const url = URL.createObjectURL(rec.blob)
            const img = new Image()
            img.onload = () => {
              planetImages.set(name, img)
              URL.revokeObjectURL(url)
              dirty = true
            }
            img.src = url
          }
        } catch {
          /* no image stored yet */
        }
      }),
    )

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
