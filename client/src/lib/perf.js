// Lightweight client-side performance telemetry — see performance.md for the
// full design. Events are buffered locally (IndexedDB `meta` store, same
// generic key/value pattern as syncDirty/catalogueStats) and flushed to the
// server as a best-effort, fully decoupled upload once a real data sync
// succeeds (see SyncReportScreen.svelte) - a failed/slow perf upload must
// never affect the actual sync.

import { getMeta, setMeta } from './db.js'
import { saveUsageStats } from './api.js'
import { projectToPixel } from './skymath.js'

const PERF_EVENTS_KEY = 'perfEvents'
const MAX_BUFFERED_EVENTS = 500

// Flip these during development - not user-facing settings.
export const PERF_ENABLED = true
export const PERF_LOG_CONSOLE = true

// Never throws/rejects - call sites include synchronous UI event handlers
// (pointerup, wheel, keydown) that fire this without awaiting it, and a
// broken perf buffer must never surface as an unhandled rejection there.
export async function recordPerfEvent(name, durationMs, data) {
  if (!PERF_ENABLED) return
  const event = { name, durationMs: Math.round(durationMs), ts: new Date().toISOString(), data: data || {} }
  if (PERF_LOG_CONSOLE) console.log('[perf]', event)
  try {
    const buffered = (await getMeta(PERF_EVENTS_KEY)) || []
    buffered.push(event)
    // Drop oldest first so an install that never syncs doesn't grow
    // IndexedDB unboundedly.
    const trimmed =
      buffered.length > MAX_BUFFERED_EVENTS ? buffered.slice(buffered.length - MAX_BUFFERED_EVENTS) : buffered
    await setMeta(PERF_EVENTS_KEY, trimmed)
  } catch (err) {
    if (PERF_LOG_CONSOLE) console.log('[perf] record failed', err)
  }
}

// No browser API exposes real CPU model info (privacy/fingerprinting
// reasons) - the closest thing (navigator.hardwareConcurrency, core count)
// isn't worth carrying either, so this just reduces the user-agent string
// down to a coarse OS + version, which is what's actually useful for
// distinguishing "slow on this platform" from "slow everywhere".
function detectOS(ua) {
  let m
  if ((m = /Windows NT ([\d.]+)/.exec(ua))) return `Windows NT ${m[1]}`
  if ((m = /Mac OS X ([\d_.]+)/.exec(ua))) return `macOS ${m[1].replace(/_/g, '.')}`
  if ((m = /Android ([\d.]+)/.exec(ua))) return `Android ${m[1]}`
  if ((m = /(?:iPhone|iPad|iPod).*?OS ([\d_]+)/.exec(ua))) return `iOS ${m[1].replace(/_/g, '.')}`
  if (/Linux/.test(ua)) return 'Linux'
  return 'unknown'
}

// Phase A: projectToPixel() is the single most CPU-bound thing the app
// does - called once per rendered object, every frame, in SkyCanvas's draw
// loop (spherical trig: sin/cos/atan2). Re-projects the same fixed set of
// synthetic points repeatedly for the duration, so the score reflects raw
// trig throughput the way a real draw loop repeatedly re-projects the same
// loaded catalog as the view moves.
function benchProjections(durationMs) {
  const N = 2000
  const points = []
  for (let i = 0; i < N; i++) {
    points.push([(i * 137.5) % 360, ((i * 47.3) % 180) - 90])
  }
  const t0 = performance.now()
  let ops = 0
  let ra0 = 180
  while (performance.now() - t0 < durationMs) {
    for (let i = 0; i < N; i++) {
      projectToPixel(points[i][0], points[i][1], ra0, 0, 800, 600, 60, 0)
    }
    ops += N
    ra0 = (ra0 + 0.001) % 360 // avoid trivially caching/hoisting across iterations
  }
  const elapsed = performance.now() - t0
  return Math.round((ops / elapsed) * 1000)
}

// Phase B: mimics getObjectsInArea()'s in-memory filter pass and
// visualRangePlan.js's spatial-index build - iterate a large object array,
// bounds/magnitude-check each one, allocate matches into a result array.
function benchFilter(durationMs) {
  const N = 50000
  const items = new Array(N)
  for (let i = 0; i < N; i++) {
    items[i] = { ra: (i * 0.073) % 360, dec: ((i * 0.091) % 180) - 90, mag: (i % 150) / 10 }
  }
  const t0 = performance.now()
  let ops = 0
  let magLimit = 8
  while (performance.now() - t0 < durationMs) {
    const result = []
    for (let i = 0; i < N; i++) {
      const o = items[i]
      if (o.ra >= 90 && o.ra <= 270 && o.dec >= -45 && o.dec <= 45 && o.mag <= magLimit) {
        result.push(o)
      }
    }
    ops += N
    magLimit = magLimit >= 14 ? 5 : magLimit + 0.01 // avoid trivially caching/hoisting across iterations
  }
  const elapsed = performance.now() - t0
  return Math.round((ops / elapsed) * 1000)
}

// Blocks the main thread for ~1s total (no way around that for a true
// synchronous throughput measurement without a Worker) - only ever called
// right before a sync that's actually about to upload usage stats, run
// fresh every time (not cached) so the score reflects conditions at that
// exact moment. Scores are ops/sec scaled down by 10^6 (millions of
// ops/sec), for a compact number rather than a raw 6-7 digit count.
function runCpuBenchmark() {
  return {
    projection: Math.round((benchProjections(500) / 1e6) * 100) / 100,
    filtering: Math.round((benchFilter(500) / 1e6) * 100) / 100,
  }
}

function currentClientInfo() {
  const selectedMag = localStorage.getItem('selectedMag')
  return {
    catalogueMag: selectedMag ? parseInt(selectedMag, 10) : null,
    deviceMemory: navigator.deviceMemory ?? null,
    os: detectOS(navigator.userAgent),
    cpuScores: runCpuBenchmark(),
  }
}

// Read-only count of currently buffered events, for the sync UI to show
// "N performance events will be uploaded" before the user commits - does
// not clear anything (see flushPerfEvents for the consuming read).
export async function peekBufferedPerfEventCount() {
  const buffered = (await getMeta(PERF_EVENTS_KEY)) || []
  return buffered.length
}

// Reads the buffered events, clears them locally, and returns them - the
// caller uploads them. Clearing happens optimistically before the network
// call (same trade-off the app already accepts elsewhere for dirty-tracking).
export async function flushPerfEvents() {
  const buffered = (await getMeta(PERF_EVENTS_KEY)) || []
  if (buffered.length > 0) await setMeta(PERF_EVENTS_KEY, [])
  return buffered
}

// Best-effort, fully decoupled from the real sync - call after a sync has
// already succeeded. Never throws; a broken/slow perf endpoint must never
// affect the actual data sync.
export async function flushAndUploadPerfEvents() {
  try {
    const events = await flushPerfEvents()
    if (events.length === 0) return
    await saveUsageStats({ client: currentClientInfo(), events })
  } catch (err) {
    if (PERF_LOG_CONSOLE) console.log('[perf] upload failed', err)
  }
}
