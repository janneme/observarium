#!/usr/bin/env python3
"""Renders an interactive HTML preview of the Moon Quiz's schematic map for
one feature, without the client dev server or a browser build step.

Runs the moon_features pipeline step automatically before rendering, so the
object list and geometry are always current — this is the "test Moon
features without running the full data_prep pipeline" tool.

Unlike a static image, this generates a real <canvas> page with the same
pan (drag) / zoom (wheel) interaction as the live app, so you can inspect
geometry detail at any zoom level. To get that, the page embeds a vanilla-JS
port of MoonCanvas.svelte's draw()/pointer/wheel handlers and moonMap.js's
projection math (see JS_TEMPLATE below) — deliberately duplicated rather
than built from the real client source, since there's no bundler here. Only
the drawing/interaction code is duplicated; the `geom` layers it draws are
the pipeline's real output (this script parses them the same way
moonMap.js's flattenMoonFeatures/parseGeomLayers do), so what you see always
reflects moon_features.py's actual shape construction, not a second copy of
it — see moon_pipeline.md for the split.

Usage:
    python data_prep/scripts/render_moon.py MOON_OBJECT [options]

Run with -h/--help for the full option list.
"""

# pylint: disable=duplicate-code

import json
import math
import platform
import random
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_PREP_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_DATA_PREP_DIR))

from moon_features import MoonFeaturePipeline  # noqa: E402

_SOURCES_DIR = _DATA_PREP_DIR / "sources"
_CACHE_DIR = _DATA_PREP_DIR / "cache"
_OUTPUT_DIR = _DATA_PREP_DIR / "output"
_MOON_FEATURES_PATH = _OUTPUT_DIR / "moon_features.json"

#: Written under $HOME rather than /tmp, matching render_moon.mjs's reasoning:
#: strictly-confined snap browsers can only read files under $HOME.
OUTPUT_HTML_PATH = Path.home() / "moon_view.html"

DIFFICULTY_EASY_MIN_SIZE_DEG = 15.0

# A terminator-based render places the object this many degrees into the lit
# side of the terminator when the user doesn't pin an exact number.
AUTO_OFFSET_RANGE_DEG = (5.0, 15.0)


def parse_geom_layers(geom):
    """Python port of moonMap.js's parseGeomLayers — see moon_pipeline.md
    for the "S <STYLE> M<lat>,<lon> L<dlat>,<dlon> ... Z" format."""
    layers = []
    for raw in geom or []:
        tokens = str(raw).strip().split()
        if not tokens or tokens[0] != "S":
            continue
        style = tokens[1]
        points: list[dict] = []
        lat = lon = 0.0
        for tok in tokens[2:]:
            if tok == "Z":
                break
            cmd, rest = tok[0], tok[1:]
            a, b = (float(v) for v in rest.split(","))
            if cmd == "M":
                lat, lon = a, b
            elif cmd == "L":
                lat += a
                lon += b
            else:
                continue
            points.append({"lat": lat, "lon": lon})
        layers.append({"style": style, "points": points})
    return layers


def _layer_extent_deg(points):
    if not points:
        return 0.0
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    return max(max(lats) - min(lats), max(lons) - min(lons))


def flatten_moon_features(raw):
    """Python port of moonMap.js's flattenMoonFeatures — `layers` is already
    parsed here so the generated page's JS doesn't need its own copy of
    parseGeomLayers, only the drawing code that consumes it."""
    out = []
    for ftype, by_name in (raw or {}).items():
        for name, rec in (by_name or {}).items():
            if not isinstance(rec, dict) or not isinstance(rec.get("lat"), (int, float)):
                continue
            layers = parse_geom_layers(rec.get("geom"))
            size_deg = _layer_extent_deg(layers[0]["points"]) if layers else 0.0
            out.append(
                {
                    "id": f"{ftype}::{name}",
                    "type": ftype,
                    "name": name,
                    "lat": float(rec["lat"]),
                    "lon": float(rec["lon"]),
                    "sizeDeg": size_deg,
                    "layers": layers,
                }
            )
    return out


def find_feature(features, query):
    """Python port of render_moon.mjs's findFeature — exact/partial name
    matching, including TYPE::NAME disambiguation."""
    q = query.strip().lower()
    if "::" in q:
        exact_id = [f for f in features if f["id"].lower() == q]
        if exact_id:
            return exact_id[0]
    exact_name = [f for f in features if f["name"].lower() == q]
    if len(exact_name) == 1:
        return exact_name[0]
    if len(exact_name) > 1:
        ids = ", ".join(f["id"] for f in exact_name)
        raise SystemExit(f'"{query}" matches multiple feature types: {ids}. Use TYPE::NAME to disambiguate.')
    partial = [f for f in features if q in f["name"].lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = ", ".join(f["name"] for f in partial[:15])
        suffix = ", ..." if len(partial) > 15 else ""
        raise SystemExit(f'No exact match for "{query}". Did you mean: {names}{suffix}?')
    raise SystemExit(f'No Moon feature matching "{query}" found in moon_features.json.')


def terminator_sun_lon_for_object(lat_deg, lon_deg, signed_offset_deg):
    """Sun selenographic longitude placing an object `offset_deg` from the
    terminator (positive = into the lit side). Python port of moonMap.js's
    former terminatorSunLonForObject (a preview-tool-only helper, kept here
    rather than in the client since nothing in the app itself needs it)."""
    lat_rad = math.radians(lat_deg)
    offset_rad = math.radians(abs(signed_offset_deg))
    ratio = max(-1.0, min(1.0, math.sin(offset_rad) / math.cos(lat_rad)))
    delta_lon_deg = math.degrees(math.acos(ratio))
    sign = -1.0 if signed_offset_deg < 0 else 1.0
    return lon_deg - sign * delta_lon_deg


# --- HTML/JS page -----------------------------------------------------------
#
# A vanilla-JS port of MoonCanvas.svelte's draw()/pointer/wheel handlers and
# moonMap.js's projection math — see the module docstring for why this is a
# deliberate duplication rather than a build step. PARAMS (features already
# flattened+parsed, subLat/subLon/sunLon/highlightId/forceScale/nightly) is
# injected as JSON in place of __PARAMS_JSON__.

_JS_TEMPLATE = r"""
const PARAMS = __PARAMS_JSON__
const { features, subLat, subLon, sunLon, highlightId, forceScale, nightly } = PARAMS

// --- ported from client/src/lib/moonMap.js ---
const LIMB_COS_CUTOFF = 0.15
const D2R = Math.PI / 180

function projectPoint(latDeg, lonDeg, subLatDeg, subLonDeg) {
  const phi = latDeg * D2R
  const phi0 = subLatDeg * D2R
  const lambda = (lonDeg - subLonDeg) * D2R
  const cosC = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(lambda)
  const x = Math.cos(phi) * Math.sin(lambda)
  const y = Math.sin(phi) * Math.cos(phi0) - Math.cos(phi) * Math.sin(phi0) * Math.cos(lambda)
  return { x, y, cosC }
}

function illumCos(latDeg, lonDeg, sunLonDeg) {
  const phi = latDeg * D2R
  const lambda = (lonDeg - sunLonDeg) * D2R
  return Math.cos(phi) * Math.cos(lambda)
}

// Point features (craters etc.) fade out with distance from the terminator
// — 1 (fully visible) right at the terminator, dropping toward
// CRATER_FADE_MIN_ALPHA well before the sub-solar point. Only meaningful in
// terminator views. CRATER_FADE_POWER > 1 makes the drop-off front-loaded
// (steep near the terminator, tapering as it nears the floor).
const CRATER_FADE_MIN_ALPHA = 0.12
const CRATER_FADE_POWER = 3

function craterFadeAlpha(cos) {
  const t = Math.max(0, Math.min(1, cos))
  return CRATER_FADE_MIN_ALPHA + (1 - CRATER_FADE_MIN_ALPHA) * Math.pow(1 - t, CRATER_FADE_POWER)
}

// --- ported from client/src/components/MoonCanvas.svelte ---
let canvasEl, wrapEl
let dpr = window.devicePixelRatio || 1
let cssW = 0
let cssH = 0

let scale = 1
let panX = 0
let panY = 0
const MIN_SCALE = 1
const MAX_SCALE = 12
const DISC_FILL_FRACTION = 0.98
const POLY_CORNER_COS_CUTOFF = 0.02
const CRATER_HIGHLIGHT_MARGIN = 2
const CRATER_FLOOR_BAND_END = 0.8
const CRATER_RIM_BAND_START = 0.95
const SEA_TYPES = new Set(['mare', 'oceanus', 'palus', 'lacus'])
const MAX_AREA_RADIUS_FRAC = 0.6
const MAX_POINT_RADIUS_FRAC = 0.1
const MIN_VISIBLE_RADIUS_PX = 1.4
const SEA_CORNER_RADIUS_RATIO = 0.3
const BORDER_INSET_PX = 1

const pointers = new Map()
let pinchStartDist = 0
let pinchStartScale = 1
let dragLast = null

function isPointDark(nx, ny) {
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

// The terminator projects orthographically to an exact ellipse (any great
// circle does), tangent to the limb at two "cusp" points — see
// MoonCanvas.svelte's computeTerminatorGeometry for the full derivation
// (validated numerically against dense ground-truth sampling). All angles
// here are normalized (y-up) space; canvas angle = -normalizedAngle is
// applied once, in buildPhasePath.
let terminatorGeomKey = null
let terminatorGeom = null

function angleDiff(a, b) {
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

  const tCusp = Math.abs(csL * sD) < 1e-12 && Math.abs(sL) < 1e-12 ? 0 : Math.atan2(sL, csL * sD)
  const cusp1 = termPoint(tCusp)
  const alphaNorm1 = Math.atan2(cusp1.y, cusp1.x)

  const cMid = depthC(tCusp + Math.PI / 2)
  const nearMid = termPoint(cMid > 0 ? tCusp + Math.PI / 2 : tCusp - Math.PI / 2)
  const betaCusp1 = localAngle(cusp1.x, cusp1.y)
  const betaNearMid = localAngle(nearMid.x, nearMid.y)

  const midNormA = alphaNorm1 + Math.PI / 2
  const aLit = !isPointDark(Math.cos(midNormA), Math.sin(midNormA))

  terminatorGeom = { theta, b, alphaNorm1, aLit, betaCusp1, ellipseDir: angleDiff(betaNearMid, betaCusp1) > 0 ? 1 : -1 }
  return terminatorGeom
}

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

function shadeColor(hex, factor) {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.max(0, Math.min(255, Math.round(((n >> 16) & 255) * factor)))
  const g = Math.max(0, Math.min(255, Math.round(((n >> 8) & 255) * factor)))
  const b = Math.max(0, Math.min(255, Math.round((n & 255) * factor)))
  return `rgb(${r},${g},${b})`
}

function parseColorChannels(color) {
  if (color[0] === '#') {
    const n = parseInt(color.slice(1), 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const m = color.match(/rgb\((\d+),(\d+),(\d+)\)/)
  return [Number(m[1]), Number(m[2]), Number(m[3])]
}

// Blends toward `background` by (1 - t) — see MoonCanvas.svelte's
// fadeTowardColor for why this replaces ctx.globalAlpha for craters.
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

function centerOnHighlight() {
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
  const targetRadiusNorm = Math.max(0.01, (feat.sizeDeg * Math.PI) / 180 / 2)
  scale = forceScale ?? Math.max(MIN_SCALE, Math.min(MAX_SCALE, 0.12 / targetRadiusNorm))
  const idealPanX = -p.x
  const idealPanY = p.y
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

  // Brightness-only, matching how the real Moon reads through a telescope —
  // see MoonCanvas.svelte's draw() for the full palette rationale.
  const highlandsColor = nightly ? '#900000' : '#989898'
  const mareColor = nightly ? '#400000' : '#4a4a4a'
  const mareEdgeColor = nightly ? '#200000' : '#303030'
  const monsColor = nightly ? '#b00000' : '#b8b8b8'
  const monsEdgeColor = nightly ? '#900000' : '#787878'
  const valleyColor = nightly ? '#700000' : '#686868'
  const valleyEdgeColor = nightly ? '#500000' : '#484848'
  const highlightColor = nightly ? '#8800ff' : '#ffff00'

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
      // Zoom-based visibility filter: skip drawing this crater entirely
      // once it's too small to matter at the current zoom, rather than
      // always flooring it to a visible dot (see MIN_VISIBLE_RADIUS_PX).
      if (!isHighlight && cappedNorm * r < MIN_VISIBLE_RADIUS_PX) continue

      // Point features (craters etc.) are drawn as an ellipse, not a
      // circle — orthographic projection foreshortens a circular surface
      // feature along the radial direction (disc centre -> feature) by
      // cosC, while the tangential direction stays unforeshortened
      // (Tissot's indicatrix for orthographic projection: radial scale =
      // cosC, tangential scale = 1).
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

  // Draw smaller craters last (on top) so an overlap reads as "the smaller
  // crater's rim cuts into the bigger one" rather than a muddy merge — see
  // MoonCanvas.svelte's draw() for the full rationale. Sorted by real
  // angular size (sizeDeg), not projected screen radius.
  pointFeats.sort((a, b) => b.sizeDeg - a.sizeDeg)

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
    const intersectsSea = seaCoverageFraction(px, py, tangentR, seaFeats) > SEA_COVERAGE_THRESHOLD
    const floorBase = intersectsSea ? mareColor : highlandsColor
    const floorDark = shadeColor(floorBase, 0.75)
    const rimLight = shadeColor(floorBase, 1.2)
    // Prominence baked into the gradient's own colours (blended toward
    // floorBase) rather than ctx.globalAlpha — with craters drawn
    // smaller-on-top so an overlap "wins" cleanly, a translucent fill
    // would let the crater underneath bleed back through.
    const prominence = cos == null ? 0.75 : craterFadeAlpha(cos)
    const floorDarkFaded = fadeTowardColor(floorDark, floorBase, prominence)
    const rimLightFaded = fadeTowardColor(rimLight, floorBase, prominence)
    // Drawn as a unit circle in a translated/rotated/non-uniformly-scaled
    // space (radialR along the foreshortened axis, tangentR along the
    // other) — createRadialGradient only supports circular gradients, so
    // scaling the coordinate system first is what turns it elliptical.
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
  e.preventDefault()
  const factor = Math.pow(1.0015, -e.deltaY)
  scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor))
  draw()
}

function init() {
  wrapEl = document.getElementById('wrap')
  canvasEl = document.getElementById('canvas')
  centerOnHighlight()
  resizeCanvas()
  new ResizeObserver(resizeCanvas).observe(wrapEl)
  wrapEl.addEventListener('pointerdown', onPointerDown)
  wrapEl.addEventListener('pointermove', onPointerMove)
  wrapEl.addEventListener('pointerup', onPointerUp)
  wrapEl.addEventListener('pointercancel', onPointerUp)
  wrapEl.addEventListener('wheel', onWheel, { passive: false })
}

window.addEventListener('DOMContentLoaded', init)
"""


def _build_html(params: dict) -> str:
    js = _JS_TEMPLATE.replace("__PARAMS_JSON__", json.dumps(params))
    info_lines = (
        params["title"]
        + ("\\n" + "full disc" if params["sunLon"] is None else "\\n" + "terminator view")
        + ("\\n" + f"zoom {params['forceScale']}x" if params["forceScale"] else "\\n" + "zoom auto")
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Moon preview: {params["title"]}</title>
<style>
html,body{{margin:0;padding:0;background:#000;height:100%;overflow:hidden}}
body{{display:flex;align-items:stretch;justify-content:flex-start;box-sizing:border-box;
  padding:4px;gap:10px;height:100vh}}
#wrap{{position:relative;height:100%;aspect-ratio:1/1;flex-shrink:0;
  border:2px solid rgba(180,0,0,0.6);border-radius:10px;overflow:hidden;touch-action:none}}
canvas{{width:100%;height:100%;display:block}}
.info{{align-self:flex-start;color:#ccc;font:13px monospace;white-space:pre-line;
  background:rgba(0,0,0,0.55);padding:0.5rem 0.7rem;border-radius:4px;max-width:320px}}
.info b{{color:#fff}}
</style>
</head>
<body>
<div id="wrap"><canvas id="canvas"></canvas></div>
<div class="info">{info_lines}

Drag to pan, wheel to zoom.
</div>
<script>
{js}
</script>
</body>
</html>
"""


# --- CLI ---------------------------------------------------------------


def _print_help():
    print(
        """Usage: python data_prep/scripts/render_moon.py MOON_OBJECT [options]

Renders an interactive preview of how the Moon Quiz would display
MOON_OBJECT (matched case-insensitively against moon_features.json feature
names) to ~/moon_view.html and opens it in your default browser. Drag to
pan, wheel to zoom — same interaction as the live app.

Options:
  -z ZOOM       Override the zoom level. Same convention as the app: 1 =
                full disc fills the square view, 2 = half the disc's
                diameter spans the view, etc. Default: auto, sized to the
                object (small objects zoom in further).
  -p PHASE      Where the terminator sits relative to the object, in
                degrees, signed:
                  - a number, e.g. "-p 10": object sits 10 degrees into the
                    lit side of the terminator (negative = into the dark
                    side). The sign also picks which of the two symmetric
                    terminator crossings (east/west of the object) is used.
                  - "+" or "-": auto-pick a plausible magnitude but respect
                    the given sign.
                Passing -p at all forces a terminator render even for
                objects large enough to default to a full-disc view, and
                even with an explicit -z.
                Without -p and without -z: objects >= the quiz's "Easy"
                size threshold (15 degrees selenographic) render as a full
                disc with no terminator; smaller objects get an
                automatically placed terminator with a random offset and
                side. An explicit -z (without -p) always renders full disc,
                no terminator — you're already choosing the framing
                yourself, so the size-based auto-terminator is skipped.
  -n            Nightly color scheme (default: daily).
  -h, --help    Show this help.

Examples:
  python data_prep/scripts/render_moon.py Copernicus
  python data_prep/scripts/render_moon.py "Mare Imbrium" -n
  python data_prep/scripts/render_moon.py Plato -p +12 -z 6
"""
    )


def parse_args(argv):
    """Manual parser mirroring render_moon.mjs's parseArgs exactly (rather
    than argparse) so "-p -5"/"-p -"/multi-word object names behave
    identically to the script this replaces."""
    opts = {"object": None, "zoom": None, "phase": None, "nightly": False, "help": False}
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            opts["help"] = True
        elif a == "-n":
            opts["nightly"] = True
        elif a == "-z":
            i += 1
            opts["zoom"] = argv[i] if i < len(argv) else None
        elif a == "-p":
            i += 1
            opts["phase"] = argv[i] if i < len(argv) else None
        else:
            rest.append(a)
        i += 1
    opts["object"] = " ".join(rest).strip() or None
    return opts


def _resolve_phase_offset(phase_arg):
    if phase_arg is None:
        return None
    if phase_arg == "+":
        return random.uniform(*AUTO_OFFSET_RANGE_DEG)
    if phase_arg == "-":
        return -random.uniform(*AUTO_OFFSET_RANGE_DEG)
    try:
        return float(phase_arg)
    except ValueError as exc:
        raise SystemExit(f'-p expects a number, "+", or "-" (got "{phase_arg}")') from exc


def _resolve_zoom(zoom_arg):
    if zoom_arg is None:
        return None
    try:
        value = float(zoom_arg)
    except ValueError as exc:
        raise SystemExit(f'-z expects a positive number (got "{zoom_arg}")') from exc
    if value <= 0:
        raise SystemExit(f'-z expects a positive number (got "{zoom_arg}")')
    return value


def _open_in_browser(path):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        print(f"Could not open a browser automatically ({exc}); open {path} manually.")


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(sys.argv[1:] if argv is None else argv)
    if opts["help"] or not opts["object"]:
        _print_help()
        return 0 if opts["help"] else 1

    print("Running moon_features pipeline step...")
    MoonFeaturePipeline(_SOURCES_DIR, _OUTPUT_DIR, cache_dir=_CACHE_DIR).run()

    raw = json.loads(_MOON_FEATURES_PATH.read_text(encoding="utf-8"))
    all_features = flatten_moon_features(raw)
    feature = find_feature(all_features, opts["object"])

    forced_offset = _resolve_phase_offset(opts["phase"])
    force_scale = _resolve_zoom(opts["zoom"])

    # An explicit -z already means the user is manually controlling the
    # framing — don't second-guess that with an auto-terminator triggered
    # by the object's size; only -p (an explicit phase request) still forces
    # one on top of an explicit zoom.
    use_terminator = forced_offset is not None or (
        force_scale is None and feature["sizeDeg"] < DIFFICULTY_EASY_MIN_SIZE_DEG
    )
    sun_lon = None
    if use_terminator:
        offset_deg = (
            forced_offset
            if forced_offset is not None
            else (1.0 if random.random() < 0.5 else -1.0) * random.uniform(*AUTO_OFFSET_RANGE_DEG)
        )
        sun_lon = terminator_sun_lon_for_object(feature["lat"], feature["lon"], offset_deg)

    term_desc = f"terminator view, sunLon={sun_lon:.2f}°" if use_terminator else "full-disc view (no terminator)"
    zoom_desc = f", zoom={force_scale}x" if force_scale else ", zoom=auto"
    theme_desc = "nightly" if opts["nightly"] else "daily"
    print(
        f"Rendering {feature['type']}::{feature['name']} (size {feature['sizeDeg']:.2f}°) — "
        f"{term_desc}{zoom_desc}, {theme_desc}"
    )

    params = {
        "features": all_features,
        "subLat": 0,
        "subLon": 0,
        "sunLon": sun_lon,
        "highlightId": feature["id"],
        "forceScale": force_scale,
        "nightly": opts["nightly"],
        "title": f"{feature['name']} ({feature['type']})",
    }

    OUTPUT_HTML_PATH.write_text(_build_html(params), encoding="utf-8")
    print(f"Wrote {OUTPUT_HTML_PATH}")
    _open_in_browser(OUTPUT_HTML_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
