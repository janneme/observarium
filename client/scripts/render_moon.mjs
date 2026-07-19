#!/usr/bin/env node
// Renders a static preview of the Moon Quiz's schematic map for one feature,
// reusing the real app code (MoonCanvas.svelte + lib/moonMap.js) so any
// change made there — colours, terminator prominence, feature sizing, pan/
// zoom clamping, etc. — is automatically reflected here too, with no
// separate test harness to keep in sync. Not part of the client build (only
// referenced by this script), dev-tool only.
//
// Usage:
//   node client/scripts/render_moon.mjs MOON_OBJECT [options]
//
// Run with -h/--help for the full option list.

import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs/promises'
import os from 'node:os'
import { spawn } from 'node:child_process'
import { build } from 'vite'

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const CLIENT_DIR = path.resolve(SCRIPT_DIR, '..')
const REPO_ROOT = path.resolve(CLIENT_DIR, '..')
const VITE_CONFIG_PATH = path.join(CLIENT_DIR, 'vite.config.mjs')
const MOON_FEATURES_PATH = path.join(REPO_ROOT, 'data_prep', 'output', 'moon_features.json')
const MOON_CANVAS_PATH = path.join(CLIENT_DIR, 'src', 'components', 'MoonCanvas.svelte')
const THEME_STORE_PATH = path.join(CLIENT_DIR, 'src', 'stores', 'theme.js')
const MOON_MAP_LIB_PATH = path.join(CLIENT_DIR, 'src', 'lib', 'moonMap.js')
// Written under $HOME rather than /tmp: strictly-confined snap browsers
// (e.g. snap Chromium/Firefox, common on Ubuntu) can only read files under
// $HOME (plus removable media) — file://tmp/... fails there with
// "Your file couldn't be accessed".
const OUTPUT_HTML_PATH = path.join(os.homedir(), 'moon_view.html')

// A terminator-based render places the object this many degrees into the
// lit side of the terminator when the user doesn't pin an exact number —
// enough to be clearly in the "long shadows" zone (see TERMINATOR_ABS_COS
// in moonMap.js) without sitting exactly on the line.
const AUTO_OFFSET_RANGE_DEG = [5, 15]

function printHelp() {
  console.log(`Usage: node client/scripts/render_moon.mjs MOON_OBJECT [options]

Renders a static preview of how the Moon Quiz would display MOON_OBJECT
(matched case-insensitively against moon_features.json feature names) to
~/moon_view.html and opens it in your default browser. (Written under
$HOME rather than /tmp so strictly-confined snap browsers can read it.)

Options:
  -z ZOOM       Override the zoom level. Same convention as the app: 1 =
                full disc fills the square view, 2 = half the disc's
                diameter spans the view, etc. Default: auto, sized to the
                object (small objects zoom in further).
  -p PHASE      Where the terminator sits relative to the object, in
                degrees, signed:
                  - a number, e.g. "-p 10": object sits 10° into the lit
                    side of the terminator (negative = into the dark side).
                    The sign also picks which of the two symmetric
                    terminator crossings (east/west of the object) is used.
                  - "+" or "-": auto-pick a plausible magnitude but respect
                    the given sign.
                Passing -p at all forces a terminator render even for
                objects large enough to default to a full-disc view.
                Without -p: objects >= the quiz's "Easy" size threshold
                (15° selenographic) render as a full disc with no
                terminator (matching what Easy difficulty would show);
                smaller objects get an automatically placed terminator with
                a random offset and side.
  -n            Nightly color scheme (default: daily).
  -h, --help    Show this help.

Examples:
  node client/scripts/render_moon.mjs Copernicus
  node client/scripts/render_moon.mjs "Mare Imbrium" -n
  node client/scripts/render_moon.mjs Plato -p +12 -z 6
`)
}

function parseArgs(argv) {
  const opts = { object: null, zoom: null, phase: null, nightly: false, help: false }
  const rest = []
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '-h' || a === '--help') {
      opts.help = true
    } else if (a === '-n') {
      opts.nightly = true
    } else if (a === '-z') {
      opts.zoom = argv[++i]
    } else if (a === '-p') {
      opts.phase = argv[++i]
    } else {
      rest.push(a)
    }
  }
  opts.object = rest.join(' ').trim() || null
  return opts
}

function randomInRange([lo, hi]) {
  return lo + Math.random() * (hi - lo)
}

// Resolves -p into a signed offset-from-terminator in degrees, or null if
// no terminator should be forced by this flag (leaving the size-based
// default decision in place).
function resolvePhaseOffset(phaseArg) {
  if (phaseArg == null) return null
  if (phaseArg === '+') return randomInRange(AUTO_OFFSET_RANGE_DEG)
  if (phaseArg === '-') return -randomInRange(AUTO_OFFSET_RANGE_DEG)
  const n = Number(phaseArg)
  if (!Number.isFinite(n)) {
    throw new Error(`-p expects a number, "+", or "-" (got "${phaseArg}")`)
  }
  return n
}

function resolveZoom(zoomArg) {
  if (zoomArg == null) return null
  const n = Number(zoomArg)
  if (!Number.isFinite(n) || n <= 0) {
    throw new Error(`-z expects a positive number (got "${zoomArg}")`)
  }
  return n
}

function findFeature(allFeatures, query) {
  const q = query.trim().toLowerCase()
  if (q.includes('::')) {
    const exact = allFeatures.find((f) => f.id.toLowerCase() === q)
    if (exact) return exact
  }
  const exactName = allFeatures.filter((f) => f.name.toLowerCase() === q)
  if (exactName.length === 1) return exactName[0]
  if (exactName.length > 1) {
    const list = exactName.map((f) => f.id).join(', ')
    throw new Error(`"${query}" matches multiple feature types: ${list}. Use TYPE::NAME to disambiguate.`)
  }
  const partial = allFeatures.filter((f) => f.name.toLowerCase().includes(q))
  if (partial.length === 1) return partial[0]
  if (partial.length > 1) {
    const list = partial
      .slice(0, 15)
      .map((f) => f.name)
      .join(', ')
    throw new Error(`No exact match for "${query}". Did you mean: ${list}${partial.length > 15 ? ', ...' : ''}?`)
  }
  throw new Error(`No Moon feature matching "${query}" found in moon_features.json.`)
}

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  if (opts.help || !opts.object) {
    printHelp()
    process.exitCode = opts.help ? 0 : 1
    return
  }

  const { flattenMoonFeatures, DIFFICULTY_MIN_SIZE_DEG, terminatorSunLonForObject } = await import(MOON_MAP_LIB_PATH)

  const raw = JSON.parse(await fs.readFile(MOON_FEATURES_PATH, 'utf-8'))
  const allFeatures = flattenMoonFeatures(raw)
  const feature = findFeature(allFeatures, opts.object)

  const forcedOffset = resolvePhaseOffset(opts.phase)
  const forceScale = resolveZoom(opts.zoom)

  const useTerminator = forcedOffset != null || feature.sizeDeg < DIFFICULTY_MIN_SIZE_DEG.easy
  let sunLon = null
  if (useTerminator) {
    const offsetDeg = forcedOffset ?? (Math.random() < 0.5 ? 1 : -1) * randomInRange(AUTO_OFFSET_RANGE_DEG)
    sunLon = terminatorSunLonForObject(feature.lat, feature.lon, offsetDeg)
  }

  console.log(
    `Rendering ${feature.type}::${feature.name} (size ${feature.sizeDeg.toFixed(2)}°) — ` +
      (useTerminator ? `terminator view, sunLon=${sunLon.toFixed(2)}°` : 'full-disc view (no terminator)') +
      (forceScale ? `, zoom=${forceScale}x` : ', zoom=auto') +
      (opts.nightly ? ', nightly' : ', daily'),
  )

  const params = {
    features: allFeatures,
    subLat: 0,
    subLon: 0,
    sunLon,
    highlightId: feature.id,
    forceScale,
    nightly: opts.nightly,
    title: `${feature.name} (${feature.type})`,
  }

  const workDir = await fs.mkdtemp(path.join(os.tmpdir(), 'observarium-moon-preview-'))
  try {
    const html = await buildPreviewHtml(workDir, params)
    await fs.writeFile(OUTPUT_HTML_PATH, html, 'utf-8')
    console.log(`Wrote ${OUTPUT_HTML_PATH}`)
    openInBrowser(OUTPUT_HTML_PATH)
  } finally {
    await fs.rm(workDir, { recursive: true, force: true })
  }
}

async function buildPreviewHtml(workDir, params) {
  const entryPath = path.join(workDir, 'entry.mjs')
  const outDir = path.join(workDir, 'out')

  // Absolute file:// import specifiers so this entry can live outside
  // client/src and still resolve the real app modules unambiguously.
  const moonCanvasSpecifier = toImportSpecifier(MOON_CANVAS_PATH)
  const themeSpecifier = toImportSpecifier(THEME_STORE_PATH)

  const entrySource = `import MoonCanvas from ${JSON.stringify(moonCanvasSpecifier)}
import { theme } from ${JSON.stringify(themeSpecifier)}

const params = ${JSON.stringify(params)}

theme.set(params.nightly ? 'nightly' : 'daily')
document.title = 'Moon preview: ' + params.title

// Square render area (mirroring MoonQuizScreen.svelte's .moon-wrap) sized
// to fill the viewport height, with the info text as a sidebar to its
// right rather than an overlay — so the image itself gets the whole
// viewport height instead of sharing it with a text row above.
const style = document.createElement('style')
style.textContent =
  'html,body{margin:0;padding:0;background:#000;height:100%;overflow:hidden}' +
  'body{display:flex;align-items:stretch;justify-content:flex-start;box-sizing:border-box;' +
  'padding:4px;gap:10px;height:100vh}' +
  '#app{position:relative;height:100%;aspect-ratio:1/1;flex-shrink:0;' +
  'border:2px solid rgba(180,0,0,0.6);border-radius:10px;overflow:hidden}' +
  '.info{align-self:flex-start;color:#ccc;font:13px monospace;white-space:pre-line;' +
  'background:rgba(0,0,0,0.55);padding:0.5rem 0.7rem;border-radius:4px;max-width:260px}'
document.head.appendChild(style)

const root = document.createElement('div')
root.id = 'app'
document.body.appendChild(root)

const info = document.createElement('div')
info.className = 'info'
info.textContent = params.title + (params.sunLon == null ? ' — full disc' : ' — terminator view') +
  (params.forceScale ? ' — zoom ' + params.forceScale + 'x' : ' — zoom auto')
document.body.appendChild(info)

window.addEventListener('wheel', (e) => { if (e.ctrlKey) e.preventDefault() }, { passive: false })

new MoonCanvas({
  target: root,
  props: {
    features: params.features,
    subLat: params.subLat,
    subLon: params.subLon,
    sunLon: params.sunLon,
    highlightId: params.highlightId,
    forceScale: params.forceScale,
  },
})
`
  await fs.writeFile(entryPath, entrySource, 'utf-8')

  await build({
    root: CLIENT_DIR,
    configFile: VITE_CONFIG_PATH,
    logLevel: 'warn',
    cacheDir: path.join(workDir, '.vite-cache'),
    publicDir: false,
    build: {
      outDir,
      emptyOutDir: true,
      minify: false,
      rollupOptions: {
        input: entryPath,
        output: { entryFileNames: 'moon-preview.js' },
      },
    },
  })

  const outFiles = await fs.readdir(outDir, { recursive: true })
  const jsFile = outFiles.find((f) => f.endsWith('.js'))
  const cssFile = outFiles.find((f) => f.endsWith('.css'))
  if (!jsFile) throw new Error('Build did not produce a JS bundle — see Vite output above.')

  const js = await fs.readFile(path.join(outDir, jsFile), 'utf-8')
  const css = cssFile ? await fs.readFile(path.join(outDir, cssFile), 'utf-8') : ''

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Moon preview</title>
<style>${css}</style>
</head>
<body>
<script>
${js}
</script>
</body>
</html>
`
}

function toImportSpecifier(absPath) {
  // A plain absolute filesystem path works as a Rollup/Vite import
  // specifier on POSIX; Windows needs a file:// URL instead.
  return process.platform === 'win32' ? new URL(`file://${absPath.replace(/\\/g, '/')}`).href : absPath
}

function openInBrowser(filePath) {
  const url = 'file://' + filePath
  if (process.platform === 'darwin') {
    spawn('open', [url], { detached: true, stdio: 'ignore' }).unref()
  } else if (process.platform === 'win32') {
    spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref()
  } else {
    spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref()
  }
}

main().catch((err) => {
  console.error('Error:', err.message || err)
  process.exitCode = 1
})
