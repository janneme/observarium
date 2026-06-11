<script>
  import { onMount } from 'svelte'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import { getObjectsInArea } from '../lib/db.js'
  import { zenith } from '../lib/horizon.js'

  let lat = 48.2     // default: Vienna
  let lon = 16.37
  let time = new Date()
  let ra0 = 0
  let dec0 = 0
  let fov = 30
  let objects = []
  let loading = true

  async function init(latitude, longitude) {
    lat = latitude
    lon = longitude
    time = new Date()
    const z = zenith(lat, lon, time)
    ra0 = z.ra
    dec0 = z.dec
    const margin = fov * 1.5
    objects = await getObjectsInArea(ra0 - margin, ra0 + margin, dec0 - margin, dec0 + margin)
    loading = false
  }

  onMount(() => {
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
