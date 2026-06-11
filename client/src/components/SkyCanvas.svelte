<script>
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { projectToPixel, isOnScreen } from '../lib/skymath.js'
  import { isAboveHorizon } from '../lib/horizon.js'
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

  const unsubTheme = theme.subscribe(v => { currentTheme = v; dirty = true })

  $: { ra0; dec0; fov; rotation; objects; lat; lon; time; dirty = true }

  function starRadius(mag) {
    return Math.max(0.5, Math.min(5, 4.5 - mag * 0.45))
  }

  function draw() {
    if (!canvas || W === 0 || H === 0) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, W, H)

    const nightly = currentTheme === 'nightly'

    for (const obj of objects) {
      if (!obj.pos) continue
      const [ra, dec] = obj.pos
      const pt = projectToPixel(ra, dec, ra0, dec0, W, H, fov, rotation)
      if (!pt || !isOnScreen(pt.px, pt.py, W, H, 4)) continue
      const above = isAboveHorizon(ra, dec, lat, lon, time)
      const r = starRadius(obj.mag ?? 5)
      ctx.beginPath()
      ctx.arc(pt.px, pt.py, r, 0, Math.PI * 2)
      ctx.fillStyle = nightly
        ? (above ? 'rgba(224,106,90,0.95)' : 'rgba(224,106,90,0.25)')
        : (above ? 'rgba(255,255,255,0.9)'  : 'rgba(255,255,255,0.2)')
      ctx.fill()
    }
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
