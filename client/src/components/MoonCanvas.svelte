<script>
  import { onMount, afterUpdate } from 'svelte'
  import { theme } from '../stores/theme.js'
  import {
    projectPoint,
    illumCos,
    terminatorProminence,
    isNearTerminator,
    LIMB_COS_CUTOFF,
    geomCorners,
  } from '../lib/moonMap.js'

  // All named features (unfiltered) — the map always shows everything
  // currently visible, not just the quiz-eligible pool; only `highlightId`
  // is special-cased.
  export let features = []
  export let subLat = 0
  export let subLon = 0
  export let sunLon = null // null = no terminator (Easy / Global scope)
  export let highlightId = null
  export let zoomEnabled = true
  // Overrides the auto-computed zoom in centerOnHighlight() when set (used
  // by the render_moon.mjs preview script's -z flag). Same units as the
  // internal `scale` (1 = full disc fills the view, 2 = half the disc's
  // diameter spans the view, etc.).
  export let forceScale = null

  let canvasEl
  let wrapEl
  let dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  let cssW = 0
  let cssH = 0

  // View transform: scale = 1 means the disc (radius 1 in normalized units)
  // fills ~90% of the shorter canvas dimension. panX/panY are normalized
  // (same units as projectPoint's x/y) offsets applied before scaling.
  let scale = 1
  let panX = 0
  let panY = 0
  const MIN_SCALE = 1
  const MAX_SCALE = 12
  // Fraction of the square view's shorter side the disc fills at scale=1 —
  // just enough margin to keep the limb stroke from getting clipped.
  const DISC_FILL_FRACTION = 0.98

  // Minimum cosC (angular distance from disc centre) for a single outline
  // vertex to still count as "on-disc" — near-zero, just enough to reject
  // genuinely far-side points. See the corner-visibility comment in draw().
  const POLY_CORNER_COS_CUTOFF = 0.02

  // Crater rim rings: fixed pixel spacing/width, independent of the
  // crater's own on-screen radius (see the "raised rim" comment in draw()).
  // Small craters use only the two outer rings (three rings that close
  // together just reads as one thick blurred border again).
  const CRATER_RING_GAP = 2.6
  const CRATER_RING_WIDTH = 1
  const CRATER_SMALL_PX2_THRESHOLD = 9

  // mare/oceanus/sinus/palus/lacus are real large regions (a big blob is
  // the *correct* depiction, mirroring how they read on real lunar maps);
  // point-like features (craters, mons, etc.) are capped much smaller so
  // they stay legible as individual rims rather than becoming blobs
  // themselves — "size" for either is only a bounding-box estimate, not a
  // true boundary, so both caps are approximate on purpose.
  const AREA_TYPES = new Set(['mare', 'oceanus', 'sinus', 'palus', 'lacus'])
  const MAX_AREA_RADIUS_FRAC = 0.6
  const MAX_POINT_RADIUS_FRAC = 0.1

  const pointers = new Map()
  let pinchStartDist = 0
  let pinchStartScale = 1
  let dragLast = null

  let prevHighlightId = undefined

  // Precomputed in normalized (pre-scale/pan) disc space, keyed by the
  // viewing/terminator conditions — independent of pan/zoom, so panning and
  // zooming (which redraw every frame) don't repeat this trig-heavy scan.
  let darkRunsKey = null
  let darkRuns = [] // [{ y0, y1, x0, x1 }] in normalized [-1,1] space
  const DARK_GRID_STEPS = 64

  function isPointDark(nx, ny) {
    // Inverse of projectPoint for a unit-radius orthographic disc: given
    // on-disc (nx, ny), recover (lat, lon) to evaluate illumination.
    const rho = Math.min(1, Math.hypot(nx, ny))
    const c = Math.asin(rho)
    if (rho < 1e-6) return illumCos(subLat, subLon, sunLon) <= 0
    const phi0 = (subLat * Math.PI) / 180
    const lat = (Math.asin(Math.cos(c) * Math.sin(phi0) + (ny * Math.sin(c) * Math.cos(phi0)) / rho) * 180) / Math.PI
    const lon =
      subLon +
      (Math.atan2(nx * Math.sin(c), rho * Math.cos(phi0) * Math.cos(c) - ny * Math.sin(phi0) * Math.sin(c)) * 180) /
        Math.PI
    return illumCos(lat, lon, sunLon) <= 0
  }

  function computeDarkRuns() {
    const key = `${subLat.toFixed(3)}|${subLon.toFixed(3)}|${sunLon == null ? 'x' : sunLon.toFixed(3)}`
    if (key === darkRunsKey) return
    darkRunsKey = key
    darkRuns = []
    if (sunLon == null) return
    const steps = DARK_GRID_STEPS
    for (let iy = 0; iy < steps; iy++) {
      const ny = -1 + (2 * (iy + 0.5)) / steps
      let runStart = null
      for (let ix = 0; ix <= steps; ix++) {
        const nx = -1 + (2 * ix) / steps
        const dist = Math.hypot(nx, ny)
        const dark = dist <= 1 && isPointDark(nx, ny)
        if (dark && runStart == null) runStart = ix
        if ((!dark || ix === steps) && runStart != null) {
          darkRuns.push({
            x0: -1 + (2 * runStart) / steps,
            x1: nx,
            yTop: ny - 1 / steps,
            h: 2 / steps,
          })
          runStart = null
        }
      }
    }
  }

  // Real "seas" are often long thin bands (Mare Frigoris spans ~80° of
  // longitude but only ~15° of latitude) — approximating every area
  // feature as a circle from a single scalar size badly misrepresents
  // them. When a feature's `geom` bounding quad is available and fully
  // on-disc, draw the actual quad instead of a circle.
  function polygonCentroid(points) {
    let x = 0
    let y = 0
    for (const p of points) {
      x += p.x
      y += p.y
    }
    return { x: x / points.length, y: y / points.length }
  }

  function insetPolygon(points, insetPx) {
    const c = polygonCentroid(points)
    return points.map((p) => {
      const dx = p.x - c.x
      const dy = p.y - c.y
      const dist = Math.hypot(dx, dy) || 1
      const shrink = Math.min(insetPx, dist * 0.9)
      const f = (dist - shrink) / dist
      return { x: c.x + dx * f, y: c.y + dy * f }
    })
  }

  function tracePolygon(ctx, points) {
    ctx.beginPath()
    ctx.moveTo(points[0].x, points[0].y)
    for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y)
    ctx.closePath()
  }

  function pointToSegmentDist(p, a, b) {
    const abx = b.x - a.x
    const aby = b.y - a.y
    const abLen2 = abx * abx + aby * aby
    let t = abLen2 > 0 ? ((p.x - a.x) * abx + (p.y - a.y) * aby) / abLen2 : 0
    t = Math.max(0, Math.min(1, t))
    return Math.hypot(p.x - (a.x + abx * t), p.y - (a.y + aby * t))
  }

  function pointInPolygon(p, points) {
    let inside = false
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const a = points[i]
      const b = points[j]
      const crosses = a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x
      if (crosses) inside = !inside
    }
    return inside
  }

  // Whether a circle (crater) touches or overlaps a polygon (sea) — used to
  // decide crater floor/rim colouring the same way circle-circle distance
  // does for circular seas.
  function circleNearPolygon(center, radius, points) {
    if (pointInPolygon(center, points)) return true
    for (let i = 0; i < points.length; i++) {
      if (pointToSegmentDist(center, points[i], points[(i + 1) % points.length]) < radius) return true
    }
    return false
  }

  function resetView() {
    scale = 1
    panX = 0
    panY = 0
  }

  export function centerOnHighlight() {
    if (!highlightId) {
      resetView()
      return
    }
    const feat = features.find((f) => f.id === highlightId)
    if (!feat) {
      resetView()
      return
    }
    const p = projectPoint(feat.lat, feat.lon, subLat, subLon)
    if (p.cosC <= LIMB_COS_CUTOFF) {
      resetView()
      return
    }
    // Zoom enough that a small feature isn't a single pixel, but not so much
    // that its immediate neighbourhood falls outside the view.
    const targetRadiusNorm = Math.max(0.01, (feat.sizeDeg * Math.PI) / 180 / 2)
    scale = forceScale ?? Math.max(MIN_SCALE, Math.min(MAX_SCALE, 0.12 / targetRadiusNorm))

    // Centering a point (px, py) at screen-space (cx, cy) requires
    // panX = -p.x, panY = +p.y — see discGeometry()/draw(): px = cx + (panX+x)*r
    // solves to panX=-x at px=cx, while py = cy + (panY-y)*r solves to
    // panY=y at py=cy (the y-axis sign flips because normalized y is
    // north-up but screen y grows downward).
    const idealPanX = -p.x
    const idealPanY = p.y

    // Clamp so a near-limb feature (legitimately close to the disc's edge,
    // e.g. Mare Orientale/Australe) doesn't pull the viewport past the disc
    // and leave empty background filling one edge of the square view — keep
    // the pan within the range that still has disc content reaching every
    // side of the frame, rather than always centering exactly.
    const halfExtent = 1 / (DISC_FILL_FRACTION * scale)
    const maxPan = Math.max(0, 1 - halfExtent)
    panX = Math.max(-maxPan, Math.min(maxPan, idealPanX))
    panY = Math.max(-maxPan, Math.min(maxPan, idealPanY))
  }

  function resizeCanvas() {
    if (!wrapEl || !canvasEl) return
    const rect = wrapEl.getBoundingClientRect()
    cssW = rect.width
    cssH = rect.height
    canvasEl.width = Math.max(1, Math.round(cssW * dpr))
    canvasEl.height = Math.max(1, Math.round(cssH * dpr))
    draw()
  }

  function discGeometry() {
    const shortSide = Math.min(cssW, cssH)
    const baseR = (shortSide / 2) * DISC_FILL_FRACTION
    const cx = cssW / 2 + panX * baseR * scale
    const cy = cssH / 2 + panY * baseR * scale
    return { cx, cy, r: baseR * scale }
  }

  function draw() {
    if (!canvasEl) return
    const ctx = canvasEl.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cssW, cssH)
    if (cssW === 0 || cssH === 0) return

    const nightly = $theme === 'nightly'
    // Two-tone schematic: highlands (everything that isn't a mare) is one
    // flat colour, maria/oceanus/sinus/palus/lacus ("seas") are another, so
    // it's obvious at a glance what's sea vs. solid ground — no elevation
    // data exists to do better than that. Craters/mons/etc. are drawn as a
    // hollow rim + shadowed floor (a schematic stand-in for a raised crater
    // wall) rather than a solid disc, so they read as "crater," not "blob."
    // Colour choices stay within the NO-GREEN rule (green channel must be
    // 00): daily uses the red/blue/magenta gamut, nightly is red-only
    // (dark-adaptation) and relies on brightness contrast instead of hue.
    const highlandsColor = nightly ? '#1a0000' : '#3a0000'
    const limbColor = nightly ? 'rgba(220,0,0,0.55)' : 'rgba(170,0,0,0.6)'
    const darkSideColor = nightly ? 'rgba(50,0,0,0.78)' : 'rgba(0,0,0,0.72)'
    // Solid, fully opaque — features overlap a lot (adjacent seas, clustered
    // craters), and any alpha baked into the fill/stroke colour themselves
    // (as opposed to ctx.globalAlpha, which is reset per-shape and doesn't
    // accumulate) stacks at the overlap into a visibly different shade.
    const mareColor = nightly ? '#600000' : '#0000b4'
    const mareEdgeColor = nightly ? '#380000' : '#000060'
    const craterRimColor = nightly ? '#c80000' : '#af0000'
    const craterRimProminentColor = nightly ? '#ff0000' : '#ff00ff'
    const highlightColor = nightly ? '#8800ff' : '#ffff00'

    const { cx, cy, r } = discGeometry()

    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.fillStyle = highlandsColor
    ctx.fill()
    ctx.lineWidth = 1.5
    ctx.strokeStyle = limbColor
    ctx.stroke()
    ctx.clip()

    // Terminator shading: darken the portion of the projected disc whose
    // sun-illumination cosine is <= 0. The dark-region scan is memoized in
    // computeDarkRuns() (normalized, pan/zoom-independent space) so panning
    // and zooming — which redraw every frame — only re-scale cached runs
    // rather than repeating the trig-heavy inverse-projection scan.
    if (sunLon != null) {
      computeDarkRuns()
      ctx.fillStyle = darkSideColor
      for (const run of darkRuns) {
        const x0 = cx + run.x0 * r
        const x1 = cx + run.x1 * r
        const yTop = cy + run.yTop * r
        ctx.fillRect(x0, yTop, x1 - x0, run.h * r)
      }
    }

    let highlightGeom = null
    const areaFeats = []
    const pointFeats = []

    for (const feat of features) {
      const p = projectPoint(feat.lat, feat.lon, subLat, subLon)
      if (p.cosC <= LIMB_COS_CUTOFF) continue
      const px = cx + p.x * r
      const py = cy - p.y * r
      const isHighlight = feat.id === highlightId
      const cos = sunLon != null ? illumCos(feat.lat, feat.lon, sunLon) : null
      const prominent = cos != null && isNearTerminator(cos)
      const prom = cos != null ? terminatorProminence(cos) : 0

      const isArea = AREA_TYPES.has(feat.type)
      const sizeNorm = Math.max(0.0025, ((feat.sizeDeg * Math.PI) / 180 / 2) * p.cosC)
      const cappedNorm = Math.min(sizeNorm, isArea ? MAX_AREA_RADIUS_FRAC : MAX_POINT_RADIUS_FRAC)
      const px2 = Math.max(1.4, cappedNorm * r)

      let polyPoints = null
      if (isArea) {
        const corners = geomCorners(feat)
        if (corners) {
          const projected = corners.map((c) => projectPoint(c.lat, c.lon, subLat, subLon))
          // LIMB_COS_CUTOFF (~81° from disc centre) exists to keep circular
          // point features from looking badly squashed near the edge — too
          // strict for an outline, which is a real boundary and can (and
          // does, e.g. Oceanus Procellarum) legitimately extend almost to
          // the true limb. Only reject a corner once it's on the far side.
          if (projected.every((cp) => cp.cosC > POLY_CORNER_COS_CUTOFF)) {
            polyPoints = projected.map((cp) => ({ x: cx + cp.x * r, y: cy - cp.y * r }))
          }
        }
      }

      if (isHighlight)
        highlightGeom = polyPoints ? { kind: 'poly', points: polyPoints } : { kind: 'circle', px, py, px2 }
      if (isArea) {
        areaFeats.push(polyPoints ? { kind: 'poly', points: polyPoints } : { kind: 'circle', px, py, px2 })
      } else {
        pointFeats.push({ px, py, px2, prominent, prom })
      }
    }

    // Seas are drawn in two passes across ALL of them rather than
    // fill+stroke per feature: a full-size "border colour" pass followed by
    // a slightly smaller "sea colour" pass on top. Where two seas overlap,
    // the second pass's fill covers the first pass's border in that region,
    // so only the true outer boundary of the merged shape ever shows a
    // border — regardless of draw order, unlike per-feature fill+stroke
    // (which made whichever sea drew last look like it sat "on top").
    const BORDER_INSET_PX = 1
    for (const a of areaFeats) {
      ctx.fillStyle = mareEdgeColor
      ctx.globalAlpha = 1
      if (a.kind === 'poly') {
        tracePolygon(ctx, a.points)
      } else {
        ctx.beginPath()
        ctx.arc(a.px, a.py, a.px2, 0, Math.PI * 2)
      }
      ctx.fill()
    }
    for (const a of areaFeats) {
      ctx.fillStyle = mareColor
      ctx.globalAlpha = 1
      if (a.kind === 'poly') {
        tracePolygon(ctx, insetPolygon(a.points, BORDER_INSET_PX))
      } else {
        ctx.beginPath()
        ctx.arc(a.px, a.py, Math.max(0, a.px2 - BORDER_INSET_PX), 0, Math.PI * 2)
      }
      ctx.fill()
    }

    for (const { px, py, px2, prominent, prom } of pointFeats) {
      // Crater etc.: a raised rim — three thin concentric rings at a fixed
      // pixel spacing, independent of the crater's own radius. A single
      // stroke whose width scales with px2 just reads as a thicker and
      // thicker blob border as craters get bigger, not a "raised boundary."
      // The floor takes on the surrounding terrain's own colour (sea if the
      // crater overlaps one, highlands otherwise) rather than a fixed shade
      // — craters don't get their own distinct background.
      const intersectsSea = areaFeats.some((a) =>
        a.kind === 'poly'
          ? circleNearPolygon({ x: px, y: py }, px2, a.points)
          : Math.hypot(a.px - px, a.py - py) < a.px2 + px2,
      )
      ctx.beginPath()
      ctx.arc(px, py, px2, 0, Math.PI * 2)
      ctx.fillStyle = intersectsSea ? mareColor : highlandsColor
      ctx.globalAlpha = 1
      ctx.fill()
      ctx.lineWidth = CRATER_RING_WIDTH
      ctx.strokeStyle = prominent ? craterRimProminentColor : intersectsSea ? mareEdgeColor : craterRimColor
      ctx.globalAlpha = prominent ? 0.7 + prom * 0.3 : 0.75
      // Two rings still sit CRATER_RING_GAP apart (same spacing as adjacent
      // rings in the three-ring case), just centred on px2 instead of one
      // of them landing exactly on it.
      const ringOffsets =
        px2 < CRATER_SMALL_PX2_THRESHOLD
          ? [-CRATER_RING_GAP / 2, CRATER_RING_GAP / 2]
          : [-CRATER_RING_GAP, 0, CRATER_RING_GAP]
      for (const dr of ringOffsets) {
        ctx.beginPath()
        ctx.arc(px, py, Math.max(0.5, px2 + dr), 0, Math.PI * 2)
        ctx.stroke()
      }
      ctx.globalAlpha = 1
    }

    // Drawn last (highest z-index within the disc) so no other feature can
    // paint over it, and sized to the object itself — not a bigger halo —
    // per its own colour/shape being left untouched above.
    if (highlightGeom) {
      if (highlightGeom.kind === 'poly') {
        tracePolygon(ctx, highlightGeom.points)
      } else {
        ctx.beginPath()
        ctx.arc(highlightGeom.px, highlightGeom.py, highlightGeom.px2, 0, Math.PI * 2)
      }
      ctx.globalAlpha = 1
      ctx.lineWidth = 1
      ctx.strokeStyle = highlightColor
      ctx.stroke()
    }

    ctx.restore()
  }

  function pointerDist() {
    const pts = [...pointers.values()]
    if (pts.length < 2) return 0
    return Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
  }

  function onPointerDown(e) {
    if (!zoomEnabled) return
    wrapEl.setPointerCapture(e.pointerId)
    const rect = wrapEl.getBoundingClientRect()
    pointers.set(e.pointerId, { x: e.clientX - rect.left, y: e.clientY - rect.top })
    if (pointers.size === 1) {
      dragLast = [...pointers.values()][0]
    } else if (pointers.size === 2) {
      pinchStartDist = pointerDist() || 1
      pinchStartScale = scale
      dragLast = null
    }
  }

  function onPointerMove(e) {
    if (!pointers.has(e.pointerId)) return
    const rect = wrapEl.getBoundingClientRect()
    pointers.set(e.pointerId, { x: e.clientX - rect.left, y: e.clientY - rect.top })

    if (pointers.size === 1 && dragLast) {
      const cur = [...pointers.values()][0]
      const { r } = discGeometry()
      panX += (cur.x - dragLast.x) / r
      panY += (cur.y - dragLast.y) / r
      dragLast = cur
      draw()
    } else if (pointers.size === 2) {
      const dist = pointerDist() || 1
      scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, pinchStartScale * (dist / pinchStartDist)))
      draw()
    }
  }

  function onPointerUp(e) {
    pointers.delete(e.pointerId)
    if (pointers.size === 1) dragLast = [...pointers.values()][0]
    else dragLast = null
  }

  function onWheel(e) {
    if (!zoomEnabled) return
    e.preventDefault()
    const factor = Math.pow(1.0015, -e.deltaY)
    scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor))
    draw()
  }

  onMount(() => {
    resizeCanvas()
    const ro = new ResizeObserver(resizeCanvas)
    ro.observe(wrapEl)
    return () => ro.disconnect()
  })

  afterUpdate(() => {
    draw()
  })

  $: if (highlightId !== prevHighlightId) {
    prevHighlightId = highlightId
    centerOnHighlight()
  }
</script>

<div
  class="moon-wrap"
  bind:this={wrapEl}
  on:pointerdown={onPointerDown}
  on:pointermove={onPointerMove}
  on:pointerup={onPointerUp}
  on:pointercancel={onPointerUp}
  on:wheel={onWheel}
>
  <canvas bind:this={canvasEl}></canvas>
</div>

<style>
  .moon-wrap {
    position: relative;
    width: 100%;
    height: 100%;
    touch-action: none;
    overflow: hidden;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }
</style>
