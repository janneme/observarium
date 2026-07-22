<script>
  import { onMount, afterUpdate } from 'svelte'
  import { theme } from '../stores/theme.js'
  import { projectPoint, illumCos, craterFadeAlpha, LIMB_COS_CUTOFF, SEA_TYPES } from '../lib/moonMap.js'

  // The features to draw — normally everything currently visible (a future
  // general Moon-browsing screen); the Moon Quiz instead passes a
  // pre-computed fixed pool (see `fixedFeatureSet`). Only `highlightId` is
  // special-cased.
  export let features = []
  export let subLat = 0
  export let subLon = 0
  export let sunLon = null // null = no terminator (Easy / Global scope)
  export let highlightId = null
  export let zoomEnabled = true
  // Overrides the auto-computed zoom in centerOnHighlight() when set. Same
  // units as the internal `scale` (1 = full disc fills the view, 2 = half
  // the disc's diameter spans the view, etc.).
  export let forceScale = null
  // When true, `features` is treated as a fixed, pre-computed set (e.g. the
  // Moon Quiz's Hard-tier pool for the current scope): the zoom-based
  // visibility gate (MIN_VISIBLE_RADIUS_PX below) is skipped, so panning/
  // zooming never adds or removes which features are drawn — only their
  // on-screen size changes. Default false preserves the general-purpose
  // "detail appears as you zoom in" behaviour.
  export let fixedFeatureSet = false

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

  // How far outside a crater's own radius the highlight ring sits (so it
  // hugs just outside the rim rather than sitting exactly on it).
  const CRATER_HIGHLIGHT_MARGIN = 2
  // Crater floor gradient stops, as fractions of the crater's own radius
  // (0 = centre, 1 = true edge): flat darkened floor out to
  // CRATER_FLOOR_BAND_END, then a band rising to a bright rim crest at
  // CRATER_RIM_BAND_START (the inner wall catching light), then a thin
  // final band easing back down to match the surrounding terrain exactly
  // at the true edge (so there's no hard seam against it).
  const CRATER_FLOOR_BAND_END = 0.8
  const CRATER_RIM_BAND_START = 0.95

  // Which real "seas" a point feature (crater etc.) overlaps decides its
  // floor colour (see the pointFeats loop below) — a semantic distinction,
  // not a drawing-style one, so it's still checked here even though
  // FILLED/RAISED (from each feature's own `geom` layer — see moonMap.js's
  // parseGeomLayers) now drives the actual drawing method for every feature
  // type, mons included. SEA_TYPES itself is imported from moonMap.js so
  // this stays in sync with the Moon Quiz's own type-bucket definition.
  // mare/oceanus/palus/lacus/mons (FILLED style) are real large regions (a
  // big blob is the *correct* depiction, mirroring how they read on real
  // lunar maps); point-like features (crater/catena/vallis, RAISED style)
  // are capped much smaller so they stay legible as individual rims rather
  // than becoming blobs themselves — sizing for either is only an estimate,
  // not a true boundary, so both caps are approximate on purpose.
  const MAX_AREA_RADIUS_FRAC = 0.6
  const MAX_POINT_RADIUS_FRAC = 0.1

  // A point feature (crater) whose true projected size falls below this many
  // screen px is skipped entirely rather than drawn at a floor size — with
  // ~7000 small satellite-crater entries now in the catalogue, always
  // drawing a visible dot for every one would clutter a full-disc view. This
  // makes detail come and go with zoom (bigger on screen as you zoom in)
  // instead of every feature being permanently visible. The current
  // highlight is exempt so the quiz target is never hidden by this filter.
  const MIN_VISIBLE_RADIUS_PX = 1.4

  const pointers = new Map()
  let pinchStartDist = 0
  let pinchStartScale = 1
  let dragLast = null

  let prevHighlightId = undefined

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

  // The terminator (this app's simplified model: the great circle through
  // the poles at longitude sunLon +- 90 deg, i.e. the sub-solar point is
  // always treated as being on the equator — see illumCos) projects
  // orthographically to an exact ELLIPSE, not an arbitrary curve: any great
  // circle projects to an ellipse under orthographic projection. Its semi-
  // major axis always equals the disc radius (the ellipse is tangent to the
  // limb at exactly two "cusp" points); its semi-minor axis and rotation
  // depend on subLat/subLon/sunLon. This lets the phase boundary be drawn
  // as one circle arc (the lit part of the true limb) + one ellipse arc
  // (the near-hemisphere half of the terminator) — an exact shape, not a
  // pixel grid. Derivation: parametrize the terminator great circle in 3D
  // as Q(t), project it the same way projectPoint() does; Q(t) works out to
  // x(t) = -cos(d) sin(t), y(t) = cos(subLat) cos(t) + sin(subLat) sin(d)
  // sin(t) with d = subLon - sunLon — a standard "conjugate semi-diameter"
  // ellipse parametrization, whose axes/rotation follow from the 2x2
  // eigendecomposition of the matrix built from C=(0, cos(subLat))
  // (the t=0 point) and S=(-cos(d), sin(subLat)sin(d)) (the t=90 deg
  // point). Validated numerically against dense ground-truth sampling
  // (project every point of the true terminator great circle) across full,
  // quarter, thin-crescent and gibbous phases with nonzero libration —
  // residual ~0 in all cases (see moon_pipeline.md).
  //
  // All the geometry below is computed in normalized (pre-scale/pan),
  // math-standard (y-up) space; converting a normalized-space angle phi to
  // the canvas arc/ellipse APIs' own angle convention is a single
  // consistent rule applied at the end: canvasAngle = -phi (screen y is
  // flipped relative to normalized y).
  let terminatorGeomKey = null
  let terminatorGeom = null

  function angleDiff(a, b) {
    // Shortest signed a-b, wrapped to (-pi, pi].
    let d = (a - b) % (2 * Math.PI)
    if (d > Math.PI) d -= 2 * Math.PI
    if (d <= -Math.PI) d += 2 * Math.PI
    return d
  }

  function computeTerminatorGeometry() {
    const key = `${subLat.toFixed(3)}|${subLon.toFixed(3)}|${sunLon == null ? 'x' : sunLon.toFixed(3)}`
    if (key === terminatorGeomKey) return terminatorGeom
    terminatorGeomKey = key
    if (sunLon == null) {
      terminatorGeom = null
      return null
    }
    const csL = Math.cos((subLat * Math.PI) / 180)
    const sL = Math.sin((subLat * Math.PI) / 180)
    const delta = ((subLon - sunLon) * Math.PI) / 180
    const cD = Math.cos(delta)
    const sD = Math.sin(delta)

    // Conjugate semi-diameters C (at t=0), S (at t=90deg) of the projected
    // ellipse; theta/b are its rotation and semi-minor axis (semi-major is
    // always exactly 1 — proved algebraically, see moon_pipeline.md).
    const Cy = csL
    const Sx = -cD
    const Sy = sL * sD
    const m11 = Sx * Sx
    const m22 = Cy * Cy + Sy * Sy
    const m12 = Sx * Sy
    const theta = 0.5 * Math.atan2(2 * m12, m11 - m22)
    const b = Math.abs(csL * cD)

    const termPoint = (t) => ({ x: -cD * Math.sin(t), y: csL * Math.cos(t) + sL * sD * Math.sin(t) })
    const depthC = (t) => sL * Math.cos(t) - csL * sD * Math.sin(t)
    const localAngle = (x, y) => {
      const lx = x * Math.cos(theta) + y * Math.sin(theta)
      const ly = b > 1e-9 ? (-x * Math.sin(theta) + y * Math.cos(theta)) / b : 0
      return Math.atan2(ly, lx)
    }

    // Cusp: where the terminator grazes the limb (depth == 0).
    const tCusp = Math.abs(csL * sD) < 1e-12 && Math.abs(sL) < 1e-12 ? 0 : Math.atan2(sL, csL * sD)
    const cusp1 = termPoint(tCusp)
    const alphaNorm1 = Math.atan2(cusp1.y, cusp1.x) // cusp1's normalized-space angle

    // Which of the two candidate 90 deg-offset midpoints (in t) is on the
    // near/visible hemisphere (depth > 0)?
    const cMid = depthC(tCusp + Math.PI / 2)
    const nearMid = termPoint(cMid > 0 ? tCusp + Math.PI / 2 : tCusp - Math.PI / 2)
    const betaCusp1 = localAngle(cusp1.x, cusp1.y)
    const betaNearMid = localAngle(nearMid.x, nearMid.y) // always exactly betaCusp1 +- pi/2

    // Which of the two semicircles of the true limb (split by the cusp-to-
    // cusp diameter) is lit — one numeric sample suffices (see moon_pipeline.md).
    const midNormA = alphaNorm1 + Math.PI / 2
    const aLit = !isPointDark(Math.cos(midNormA), Math.sin(midNormA))

    terminatorGeom = { theta, b, alphaNorm1, aLit, betaCusp1, ellipseDir: angleDiff(betaNearMid, betaCusp1) > 0 ? 1 : -1 }
    return terminatorGeom
  }

  // Builds the phase-boundary path (circle arc + ellipse arc) in screen
  // space for the given disc geometry, using computeTerminatorGeometry()'s
  // normalized-space angles — see the canvasAngle = -phi conversion note
  // above.
  function buildPhasePath(cx, cy, r) {
    const g = computeTerminatorGeometry()
    if (!g) return null
    const path = new Path2D()
    const circleDir = g.aLit ? 1 : -1
    const circleStart = -g.alphaNorm1
    path.arc(cx, cy, r, circleStart, circleStart - circleDir * Math.PI, circleDir > 0)
    const ellipseStart = -g.betaCusp1
    path.ellipse(cx, cy, r, r * g.b, -g.theta, ellipseStart, ellipseStart - g.ellipseDir * Math.PI, g.ellipseDir > 0)
    return path
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

  // How far to cut back from each vertex along its two edges before
  // rounding, relative to the shorter of the two — real coastlines don't
  // have sharp polygon-vertex kinks, and a fixed pixel cut would look wrong
  // at different zoom levels or between a sea's long and short edges.
  const SEA_CORNER_RADIUS_RATIO = 0.3

  // Same shape as tracePolygon() but every vertex becomes a rounded corner.
  // `ratio * min(adjacent edge lengths)` is the tangent CUT LENGTH — how far
  // back from the vertex, along each edge, the rounding starts — not the
  // arc's radius. Feeding that ratio straight into ctx.arcTo() as a radius
  // (the previous approach) got these backwards: at a sharp (small) vertex
  // angle, a fixed radius demands a very long tangent length to stay
  // tangent rather than crossing the lines, so it overshot the shorter edge
  // and clamped/kinked unpredictably. Here the cut length is what's fixed,
  // and the radius is solved for from the vertex angle (r = cut *
  // tan(angle/2), the standard tangent-circle relation) — a wide-open
  // vertex angle gets a big, gentle radius, a sharp one gets a small radius
  // and stays close to its original point, and the resulting arc is always
  // < 180°. ctx.arcTo() re-derives the same tangent length from this radius
  // and draws it, so it's inherently tangent to both edges (touches, never
  // crosses) and needs no separate vertex — this radius value is exactly
  // its inverse.
  function traceRoundedPolygon(ctx, points, ratio = SEA_CORNER_RADIUS_RATIO) {
    const n = points.length
    if (n < 3 || ratio <= 0) {
      tracePolygon(ctx, points)
      return
    }
    ctx.beginPath()
    const first = points[0]
    const last = points[n - 1]
    ctx.moveTo((first.x + last.x) / 2, (first.y + last.y) / 2)
    for (let i = 0; i < n; i++) {
      const curr = points[i]
      const prev = points[(i - 1 + n) % n]
      const next = points[(i + 1) % n]
      const lenPrev = Math.hypot(curr.x - prev.x, curr.y - prev.y)
      const lenNext = Math.hypot(next.x - curr.x, next.y - curr.y)
      const cut = ratio * Math.min(lenPrev, lenNext)
      // Unit vectors from curr toward its two neighbours — the angle
      // between them is the vertex's own interior angle (0 = a folded-back
      // spike, 180 = no turn at all / a straight line).
      const ux = (prev.x - curr.x) / (lenPrev || 1)
      const uy = (prev.y - curr.y) / (lenPrev || 1)
      const vx = (next.x - curr.x) / (lenNext || 1)
      const vy = (next.y - curr.y) / (lenNext || 1)
      const cosAngle = Math.max(-1, Math.min(1, ux * vx + uy * vy))
      const halfAngle = Math.acos(cosAngle) / 2
      const radius = cut * Math.tan(halfAngle)
      ctx.arcTo(curr.x, curr.y, next.x, next.y, Number.isFinite(radius) ? radius : cut * 1e6)
    }
    ctx.closePath()
  }

  // Scales a '#rrggbb' colour's channels by factor (< 1 darkens, > 1
  // lightens, clamped) — used to derive a crater floor's gradient stops
  // from the surrounding terrain's own flat colour.
  function shadeColor(hex, factor) {
    const n = parseInt(hex.slice(1), 16)
    const r = Math.max(0, Math.min(255, Math.round(((n >> 16) & 255) * factor)))
    const g = Math.max(0, Math.min(255, Math.round(((n >> 8) & 255) * factor)))
    const b = Math.max(0, Math.min(255, Math.round((n & 255) * factor)))
    return `rgb(${r},${g},${b})`
  }

  // Parses either '#rrggbb' or 'rgb(r,g,b)' (shadeColor's own output) into
  // [r, g, b].
  function parseColorChannels(color) {
    if (color[0] === '#') {
      const n = parseInt(color.slice(1), 16)
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    }
    const m = color.match(/rgb\((\d+),(\d+),(\d+)\)/)
    return [Number(m[1]), Number(m[2]), Number(m[3])]
  }

  // Blends toward `background` by (1 - t) — t=1 returns `color` unchanged,
  // t=0 returns `background`. Used to bake a crater's terminator-distance
  // fade directly into its own paint colour (see the pointFeats loop)
  // rather than via ctx.globalAlpha, which would leave it translucent and
  // let whatever's underneath (e.g. a larger crater it's meant to
  // occlude) bleed through.
  function fadeTowardColor(color, background, t) {
    const [r1, g1, b1] = parseColorChannels(color)
    const [r2, g2, b2] = parseColorChannels(background)
    const r = Math.round(r1 * t + r2 * (1 - t))
    const g = Math.round(g1 * t + g2 * (1 - t))
    const b = Math.round(b1 * t + b2 * (1 - t))
    return `rgb(${r},${g},${b})`
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

  // Grid-sampled estimate of what fraction of a crater's own circle is
  // covered by sea (mare/oceanus/palus/lacus) — used to decide floor
  // colour. A crater merely touching a sea's edge shouldn't flip to sea
  // colour; only one mostly submerged in it should (see
  // SEA_COVERAGE_THRESHOLD below). Sampling is precise enough for a colour
  // decision and much simpler than real polygon clipping (unlike the
  // terminator boundary, this doesn't need to be pixel-exact).
  const SEA_COVERAGE_SAMPLE_GRID = 6
  const SEA_COVERAGE_THRESHOLD = 0.5

  function seaCoverageFraction(px, py, px2, seaFeats) {
    if (seaFeats.length === 0) return 0
    let total = 0
    let covered = 0
    for (let iy = 0; iy < SEA_COVERAGE_SAMPLE_GRID; iy++) {
      const sy = py - px2 + (2 * px2 * (iy + 0.5)) / SEA_COVERAGE_SAMPLE_GRID
      for (let ix = 0; ix < SEA_COVERAGE_SAMPLE_GRID; ix++) {
        const sx = px - px2 + (2 * px2 * (ix + 0.5)) / SEA_COVERAGE_SAMPLE_GRID
        if (Math.hypot(sx - px, sy - py) > px2) continue
        total++
        const inSea = seaFeats.some((a) =>
          a.shape.kind === 'poly'
            ? pointInPolygon({ x: sx, y: sy }, a.shape.points)
            : Math.hypot(a.shape.px - sx, a.shape.py - sy) <= a.shape.px2,
        )
        if (inSea) covered++
      }
    }
    return total === 0 ? 0 : covered / total
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
    // Brightness-only schematic, matching how the real Moon reads through a
    // telescope (no colour, just albedo contrast): highlands are the mid
    // background tone, maria/oceanus/palus/lacus ("seas") are distinctly
    // darker (real lunar seas have markedly lower albedo than the
    // highlands), mountain ranges are distinctly brighter (elevated terrain
    // catching more light). Craters darken their own floor rather than
    // getting a brighter rim (see the pointFeats loop below) — real rim
    // material isn't meaningfully brighter than its surroundings outside of
    // raking terminator light. Daily is true grayscale (unrestricted — the
    // NO-GREEN rule only applies to nightly); nightly stays within the red
    // channel only (green/blue == 00, dark-adaptation) and gets the same
    // brighter/darker relationships purely from R's magnitude.
    const highlandsColor = nightly ? '#900000' : '#989898'
    // Solid, fully opaque — features overlap a lot (adjacent seas, clustered
    // craters), and any alpha baked into the fill/stroke colour themselves
    // (as opposed to ctx.globalAlpha, which is reset per-shape and doesn't
    // accumulate) stacks at the overlap into a visibly different shade.
    const mareColor = nightly ? '#400000' : '#4a4a4a'
    const mareEdgeColor = nightly ? '#200000' : '#303030'
    const monsColor = nightly ? '#b00000' : '#b8b8b8'
    const monsEdgeColor = nightly ? '#900000' : '#787878'
    // Catena (crater chains) and vallis (valleys/rilles) are linear
    // depressions, not raised terrain like mons — tonally closer to maria
    // than to highlands, but not as dark as a full sea.
    const valleyColor = nightly ? '#700000' : '#686868'
    const valleyEdgeColor = nightly ? '#500000' : '#484848'
    // The quiz highlight marker is a UI affordance, not part of the lunar
    // scene, so it keeps a colour that stands out against the grayscale
    // terrain rather than going monochrome itself.
    const highlightColor = nightly ? '#8800ff' : '#ffff00'

    // FILLED-style features (see moonMap.js's parseGeomLayers) all draw with
    // the same generic two-pass edge+fill method below; only the colour
    // pair varies by feature type.
    const FILLED_COLORS = {
      mare: { edge: mareEdgeColor, fill: mareColor },
      oceanus: { edge: mareEdgeColor, fill: mareColor },
      palus: { edge: mareEdgeColor, fill: mareColor },
      lacus: { edge: mareEdgeColor, fill: mareColor },
      mons: { edge: monsEdgeColor, fill: monsColor },
      catena: { edge: valleyEdgeColor, fill: valleyColor },
      vallis: { edge: valleyEdgeColor, fill: valleyColor },
    }

    const { cx, cy, r } = discGeometry()

    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.clip()

    // Terminator: the dark side isn't drawn at all — clip everything after
    // this to the exact lit region (see buildPhasePath), so the moon's own
    // rendered silhouette is the actual lit crescent/gibbous shape.
    if (sunLon != null) {
      const phasePath = buildPhasePath(cx, cy, r)
      if (phasePath) ctx.clip(phasePath)
    }

    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.fillStyle = highlandsColor
    ctx.fill()

    let highlightGeom = null
    const filledFeats = []
    const pointFeats = []

    for (const feat of features) {
      const p = projectPoint(feat.lat, feat.lon, subLat, subLon)
      if (p.cosC <= LIMB_COS_CUTOFF) continue
      const px = cx + p.x * r
      const py = cy - p.y * r
      const isHighlight = feat.id === highlightId
      const cos = sunLon != null ? illumCos(feat.lat, feat.lon, sunLon) : null

      const layer = feat.layers && feat.layers[0]
      const isFilled = layer ? layer.style === 'FILLED' : false
      const sizeNorm = Math.max(0.0025, (feat.sizeDeg * Math.PI) / 180 / 2)
      const cappedNorm = Math.min(sizeNorm, isFilled ? MAX_AREA_RADIUS_FRAC : MAX_POINT_RADIUS_FRAC)

      let polyPoints = null
      if (isFilled && layer.points.length >= 3) {
        const projected = layer.points.map((pt) => projectPoint(pt.lat, pt.lon, subLat, subLon))
        // LIMB_COS_CUTOFF (~81° from disc centre) exists to keep circular
        // point features from looking badly squashed near the edge — too
        // strict for an outline, which is a real boundary and can (and
        // does, e.g. Oceanus Procellarum) legitimately extend almost to
        // the true limb. Only reject a vertex once it's on the far side.
        if (projected.every((cp) => cp.cosC > POLY_CORNER_COS_CUTOFF)) {
          polyPoints = projected.map((cp) => ({ x: cx + cp.x * r, y: cy - cp.y * r }))
        }
      }

      if (isFilled) {
        const px2 = Math.max(1.4, cappedNorm * p.cosC * r)
        const shape = polyPoints ? { kind: 'poly', points: polyPoints } : { kind: 'circle', px, py, px2 }
        if (isHighlight) highlightGeom = shape
        filledFeats.push({ colors: FILLED_COLORS[feat.type] || FILLED_COLORS.mare, isSea: SEA_TYPES.has(feat.type), shape })
      } else {
        // Zoom-based visibility filter (see MIN_VISIBLE_RADIUS_PX): skip
        // drawing this crater entirely once it's too small to matter at the
        // current zoom, rather than always flooring it to a visible dot.
        // Skipped entirely when `fixedFeatureSet` is set (Moon Quiz) — the
        // rendered set must not change with zoom there.
        if (!isHighlight && !fixedFeatureSet && cappedNorm * r < MIN_VISIBLE_RADIUS_PX) continue

        // Point features (craters etc.) are drawn as an ellipse, not a
        // circle — orthographic projection foreshortens a circular surface
        // feature along the radial direction (disc centre -> feature) by
        // cosC, while the tangential direction (perpendicular to that)
        // stays unforeshortened; this is the standard orthographic
        // projection distortion (Tissot's indicatrix: radial scale = cosC,
        // tangential scale = 1). A plain circle looks noticeably wrong for
        // anything away from disc centre.
        const tangentR = Math.max(MIN_VISIBLE_RADIUS_PX, cappedNorm * r)
        const radialR = Math.max(0.5, tangentR * p.cosC)
        const angle = Math.atan2(py - cy, px - cx)
        if (isHighlight) {
          highlightGeom = {
            kind: 'ellipse',
            px,
            py,
            radialR: radialR + CRATER_HIGHLIGHT_MARGIN,
            tangentR: tangentR + CRATER_HIGHLIGHT_MARGIN,
            angle,
          }
        }
        pointFeats.push({ px, py, tangentR, radialR, angle, cos, sizeDeg: feat.sizeDeg })
      }
    }

    // Draw smaller craters last (on top) so an overlap reads as "the
    // smaller crater's rim cuts into the bigger one," matching how this
    // usually looks in reality — a smaller crater is more often a younger
    // impact superimposed on an older, larger one — rather than the two
    // rims blending into a muddy merge. Sorted by real angular size
    // (sizeDeg), not projected screen radius, so the order doesn't shift
    // with zoom or limb foreshortening.
    pointFeats.sort((a, b) => b.sizeDeg - a.sizeDeg)

    // Every FILLED feature (mare/oceanus/palus/lacus/mons) is drawn in two
    // passes across ALL of them rather than fill+stroke per feature: a
    // full-size "edge colour" pass followed by a slightly smaller "fill
    // colour" pass on top. Where two features of the same colour pair
    // overlap, the second pass's fill covers the first pass's edge in that
    // region, so only the true outer boundary of the merged shape ever
    // shows an edge — regardless of draw order, unlike per-feature
    // fill+stroke (which made whichever feature drew last look "on top").
    const BORDER_INSET_PX = 1
    for (const f of filledFeats) {
      ctx.fillStyle = f.colors.edge
      ctx.globalAlpha = 1
      if (f.shape.kind === 'poly') {
        traceRoundedPolygon(ctx, f.shape.points)
      } else {
        ctx.beginPath()
        ctx.arc(f.shape.px, f.shape.py, f.shape.px2, 0, Math.PI * 2)
      }
      ctx.fill()
    }
    for (const f of filledFeats) {
      ctx.fillStyle = f.colors.fill
      ctx.globalAlpha = 1
      if (f.shape.kind === 'poly') {
        traceRoundedPolygon(ctx, insetPolygon(f.shape.points, BORDER_INSET_PX))
      } else {
        ctx.beginPath()
        ctx.arc(f.shape.px, f.shape.py, Math.max(0, f.shape.px2 - BORDER_INSET_PX), 0, Math.PI * 2)
      }
      ctx.fill()
    }

    const seaFeats = filledFeats.filter((f) => f.isSea)
    for (const { px, py, tangentR, radialR, angle, cos } of pointFeats) {
      // Crater etc.: a uniformly darkened floor for most of the disc (real
      // craters read as a fairly flat dark patch, not a smooth bowl — no
      // relief shading here to justify a gradient across the whole
      // interior), rising to a bright rim crest just inside the true edge
      // (the inner wall catching light), then easing back down to match
      // the surrounding terrain exactly at the boundary — a thin highlight
      // rather than the whole rim standing out. The floor tone still takes
      // on the surrounding terrain's own colour (sea if the crater is
      // mostly submerged in one, highlands otherwise) — craters don't get
      // their own distinct background.
      const intersectsSea = seaCoverageFraction(px, py, tangentR, seaFeats) > SEA_COVERAGE_THRESHOLD
      const floorBase = intersectsSea ? mareColor : highlandsColor
      const floorDark = shadeColor(floorBase, 0.75)
      const rimLight = shadeColor(floorBase, 1.2)
      // Fixed prominence without a terminator; fades with distance from it
      // (toward the sub-solar point) when one is active — see
      // moonMap.js's craterFadeAlpha. Baked directly into the gradient's
      // own colours (blending toward floorBase) rather than via
      // ctx.globalAlpha: with craters now drawn smaller-on-top so an
      // overlap "wins" cleanly (see the sort above pointFeats), a
      // translucent fill would let the crater underneath bleed back
      // through — painting fully opaque, already-faded colour keeps the
      // occlusion clean while still reading as faded.
      const prominence = cos == null ? 0.75 : craterFadeAlpha(cos)
      const floorDarkFaded = fadeTowardColor(floorDark, floorBase, prominence)
      const rimLightFaded = fadeTowardColor(rimLight, floorBase, prominence)
      // Drawn as a unit circle in a translated/rotated/non-uniformly-scaled
      // space (radialR along the foreshortened axis, tangentR along the
      // other) rather than passing an ellipse radius straight to a canvas
      // API, because createRadialGradient only supports circular gradients
      // — scaling the whole coordinate system first is what turns that
      // circular gradient into the correct elliptical one.
      ctx.save()
      ctx.translate(px, py)
      ctx.rotate(angle)
      ctx.scale(radialR, tangentR)
      const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
      gradient.addColorStop(0, floorDarkFaded)
      gradient.addColorStop(CRATER_FLOOR_BAND_END, floorDarkFaded)
      gradient.addColorStop(CRATER_RIM_BAND_START, rimLightFaded)
      gradient.addColorStop(1, floorBase)
      ctx.beginPath()
      ctx.arc(0, 0, 1, 0, Math.PI * 2)
      ctx.fillStyle = gradient
      ctx.globalAlpha = 1
      ctx.fill()
      ctx.restore()
    }

    // Drawn last (highest z-index within the disc) so no other feature can
    // paint over it, and sized to the object itself — not a bigger halo —
    // per its own colour/shape being left untouched above.
    if (highlightGeom) {
      if (highlightGeom.kind === 'poly') {
        traceRoundedPolygon(ctx, highlightGeom.points)
      } else if (highlightGeom.kind === 'ellipse') {
        ctx.beginPath()
        ctx.ellipse(highlightGeom.px, highlightGeom.py, highlightGeom.radialR, highlightGeom.tangentR, highlightGeom.angle, 0, Math.PI * 2)
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
