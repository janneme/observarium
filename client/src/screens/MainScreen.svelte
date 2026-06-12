<script>
  import { onMount, onDestroy } from 'svelte'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import { getObjectsInArea } from '../lib/db.js'
  import { zenith } from '../lib/horizon.js'

  let lat = 48.2     // default: Vienna
  let lon = 16.37
  let time = new Date()
  let ra0 = 0
  let dec0 = 0
  let fov = 60
  let objects = []
  let loading = true

  const FOV_STEP = 0.20   // fractional FOV change per +/- keypress
  const PAN_STEP = 0.50   // fraction of FOV to pan per arrow keypress

  let loadRa0 = 0
  let loadDec0 = 0
  let loadMargin = 0
  let loadMagLimit = 0
  let fetching = false

  function fovToMagLimit(f) {
    if (f >= 60) return 6
    if (f >= 30) return 7
    if (f >= 20) return 8
    if (f >= 10) return 10
    return 12
  }

  async function loadObjects() {
    if (fetching) return
    fetching = true
    const margin = fov * 1.5
    objects = await getObjectsInArea(ra0 - margin, ra0 + margin, dec0 - margin, dec0 + margin, fovToMagLimit(fov))
    loadRa0 = ra0
    loadDec0 = dec0
    loadMargin = margin
    loadMagLimit = fovToMagLimit(fov)
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
    // Reload when view centre drifts, FOV grew beyond what was loaded, or zoom-in raises mag limit
    if (dRa > loadMargin * 0.5 || dDec > loadMargin * 0.5 || fov > loadMargin / 1.5 || fovToMagLimit(fov) > loadMagLimit) {
      loadObjects()
    }
  }

  function handleKey(e) {
    if (e.key === '+' || e.key === '=') {
      fov = Math.max(5, fov * (1 - FOV_STEP))
    } else if (e.key === '-') {
      fov = Math.min(180, fov * (1 + FOV_STEP))
    } else if (e.key === 'ArrowRight') {
      const step = fov * PAN_STEP / Math.cos(dec0 * Math.PI / 180)
      ra0 = ((ra0 + step) % 360 + 360) % 360
    } else if (e.key === 'ArrowLeft') {
      const step = fov * PAN_STEP / Math.cos(dec0 * Math.PI / 180)
      ra0 = ((ra0 - step) % 360 + 360) % 360
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

  onMount(() => {
    window.addEventListener('keydown', handleKey)
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        pos => init(pos.coords.latitude, pos.coords.longitude),
        () => init(lat, lon),
        { timeout: 5000 }
      )
    } else {
      init(lat, lon)
    }
  })

  onDestroy(() => {
    window.removeEventListener('keydown', handleKey)
  })
</script>

<div class="main-screen">
  {#if loading}
    <div class="hint">Locating…</div>
  {:else}
    <SkyCanvas {ra0} {dec0} {fov} {objects} {lat} {lon} {time} />
  {/if}
</div>

<style>
.main-screen {
  width: 100vw;
  height: 100vh;
  background: #000;
  overflow: hidden;
  position: relative;
}

.hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(255,255,255,0.4);
  font-size: 0.9rem;
}
</style>
