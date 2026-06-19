<script>
  import { onMount, onDestroy } from 'svelte'
  import {
    Observer,
    AstroTime,
    SearchRiseSet,
    SearchHourAngle,
    MoonPhase,
    Illumination,
    Body,
    DefineStar,
  } from 'astronomy-engine'
  import { selectedObject } from '../stores/selectedObject.js'
  import { objectDetailsActive } from '../stores/ui.js'
  import { getTodayObservation, toggleObjectObserved, getObjectImage, getDoubleStarNear } from '../lib/db.js'

  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  let obj = null
  let linkedDs = null
  let isObservedToday = false
  let imageUrl = null
  let blobUrlToRevoke = null
  let riseTime = null
  let transitTime = null
  let setTime = null
  let moonPhaseDeg = null
  let moonIllumination = null
  let planetPhaseFraction = null

  $: obj = $selectedObject

  function raHours(o) {
    if (!o?.pos) return 0
    // stars: pos[0] in hours; DSOs and double stars: pos[0] in degrees
    return o.type === 'star' ? o.pos[0] : o.pos[0] / 15
  }

  function decDeg(o) {
    return o?.pos?.[1] ?? 0
  }

  function formatRA(h) {
    const hh = Math.floor(h)
    const mTotal = (h - hh) * 60
    const mm = Math.floor(mTotal)
    const ss = ((mTotal - mm) * 60).toFixed(1)
    return `${hh}h ${String(mm).padStart(2, '0')}m ${ss}s`
  }

  function formatDec(d) {
    const sign = d >= 0 ? '+' : '−'
    const abs = Math.abs(d)
    const dd = Math.floor(abs)
    const mTotal = (abs - dd) * 60
    const mm = Math.floor(mTotal)
    const ss = Math.round((mTotal - mm) * 60)
    return `${sign}${dd}° ${String(mm).padStart(2, '0')}′ ${String(ss).padStart(2, '0')}″`
  }

  function formatTime(astroTime) {
    if (!astroTime) return '—'
    return astroTime.date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  function formatSize(s) {
    if (s == null) return null
    if (Array.isArray(s)) return `${s[0]}′ × ${s[1]}′`
    return `${s}′`
  }

  function formatMag(m) {
    if (m == null) return null
    if (Array.isArray(m)) return `${m[0]}–${m[1]}`
    return String(m)
  }

  function catNumbers(o) {
    const parts = []
    if (o.m != null) parts.push(`M ${o.m}`)
    if (o.ngc != null) parts.push(`NGC ${o.ngc}`)
    if (o.ic != null) parts.push(`IC ${o.ic}`)
    if (o.caldwell != null) parts.push(`C ${o.caldwell}`)
    if (o.hip != null) parts.push(`HIP ${o.hip}`)
    if (o.hd != null) parts.push(`HD ${o.hd}`)
    if (o.wds != null) parts.push(`WDS ${o.wds}`)
    if (o.bay) parts.push(o.bay)
    if (o.flam != null) parts.push(String(o.flam))
    return parts.join('  ·  ') || null
  }

  function dblPairs(o) {
    if (o.type === 'double_star') return o.pairs || []
    if (Array.isArray(o.dbl)) return o.dbl.flatMap((entry) => entry.pairs || [])
    if (o.dbl && linkedDs) return linkedDs.pairs || []
    return []
  }

  function isDouble(o) {
    return o.type === 'double_star' || (o.type === 'star' && !!o.dbl)
  }

  function dblMainPair(o) {
    const pairs = dblPairs(o)
    return pairs.find((p) => p.comp === 'AB') || pairs[0] || null
  }

  function formatSep(sep) {
    if (sep == null) return null
    if (Array.isArray(sep)) return `${sep[0]}″–${sep[1]}″`
    return `${sep}″`
  }

  function typeLabel(o) {
    if (o.dsoType) return o.dsoType
    if (isDouble(o)) {
      const hasPhys = dblPairs(o).some((p) => p.phys)
      return hasPhys ? 'Physical double star' : 'Double star'
    }
    return o.type
  }

  function formatMagRow(o) {
    if (!isDouble(o)) return formatMag(o.mag)
    const pair = dblMainPair(o)
    if (pair?.mag && Array.isArray(pair.mag)) {
      const [m1, m2] = pair.mag
      const compStr = `${m1} / ${m2}`
      return o.mag != null ? `${formatMag(o.mag)} (${compStr})` : compStr
    }
    return formatMag(o.mag)
  }

  function formatSpect(o) {
    if (!o.spect) return null
    if (isDouble(o) && o.spect.includes('+')) return o.spect.split('+').join(' / ')
    return o.spect
  }

  function moonPath(phaseDeg) {
    const r = 45
    const cx = 50
    const cy = 50
    const p = ((phaseDeg % 360) + 360) % 360
    if (p < 0.5) return ''
    if (p > 179.5 && p < 180.5) {
      return `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`
    }
    const cosP = Math.cos((p * Math.PI) / 180)
    const ex = Math.abs(cosP) * r
    if (p < 180) {
      const ts = cosP >= 0 ? 0 : 1
      return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${ex} ${r} 0 0 ${ts} ${cx} ${cy - r} Z`
    } else {
      const ts = cosP <= 0 ? 1 : 0
      return `M ${cx} ${cy - r} A ${r} ${r} 0 1 0 ${cx} ${cy + r} A ${ex} ${r} 0 0 ${ts} ${cx} ${cy - r} Z`
    }
  }

  async function loadData(o) {
    if (!o) return

    // Observation status
    const todayObs = await getTodayObservation()
    isObservedToday = todayObs?.objects?.some((x) => x.id === o.id) ?? false

    // Image
    const imgRecord = await getObjectImage(o.id)
    if (imgRecord?.blob) {
      if (blobUrlToRevoke) URL.revokeObjectURL(blobUrlToRevoke)
      blobUrlToRevoke = URL.createObjectURL(imgRecord.blob)
      imageUrl = blobUrlToRevoke
    } else {
      imageUrl = null
    }

    // Rise/transit/set
    riseTime = null
    transitTime = null
    setTime = null
    moonPhaseDeg = null
    moonIllumination = null
    planetPhaseFraction = null

    try {
      const observer = new Observer(lat, lon, 0)
      const midnight = new Date(time)
      midnight.setHours(0, 0, 0, 0)
      const startTime = new AstroTime(midnight)
      const astroNow = new AstroTime(time)

      let body
      if (o.type === 'star' || o.type === 'dso' || o.type === 'double_star') {
        const distLy = o.dist ? o.dist * 3.26156 : 1000
        DefineStar(Body.Star1, raHours(o), decDeg(o), distLy)
        body = Body.Star1
      } else {
        // solar system fallback
        const nameMap = {
          Mercury: Body.Mercury,
          Venus: Body.Venus,
          Mars: Body.Mars,
          Jupiter: Body.Jupiter,
          Saturn: Body.Saturn,
          Uranus: Body.Uranus,
          Neptune: Body.Neptune,
          Moon: Body.Moon,
          Sun: Body.Sun,
        }
        body = nameMap[o.name] ?? Body.Sun
      }

      riseTime = SearchRiseSet(body, observer, +1, startTime, 1)
      setTime = SearchRiseSet(body, observer, -1, startTime, 1)
      const transitResult = SearchHourAngle(body, observer, 0, startTime)
      transitTime = transitResult?.time ?? null

      // Moon phase
      if (o.name === 'Moon' || body === Body.Moon) {
        moonPhaseDeg = MoonPhase(astroNow)
        moonIllumination = (1 - Math.cos((moonPhaseDeg * Math.PI) / 180)) / 2
      }

      // Inner planet phase
      if (o.inner || body === Body.Mercury || body === Body.Venus) {
        const illum = Illumination(body, astroNow)
        planetPhaseFraction = illum.phase_fraction
      }
    } catch (err) {
      console.warn('[ObjectDetails] astronomy computation failed:', err)
    }
  }

  async function toggleObserved() {
    if (!obj) return
    isObservedToday = await toggleObjectObserved(obj.id)
  }

  function close() {
    objectDetailsActive.set(false)
  }

  onMount(() => {
    if (obj) loadData(obj)
  })

  onDestroy(() => {
    if (blobUrlToRevoke) URL.revokeObjectURL(blobUrlToRevoke)
  })

  $: if (obj) loadData(obj)

  $: if (obj?.type === 'star' && obj.dbl) {
    linkedDs = null
    getDoubleStarNear(obj.pos[0], obj.pos[1]).then((ds) => {
      linkedDs = ds
    })
  } else {
    linkedDs = null
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" on:click={close}>← Back</button>
    <span class="header-title">{obj?.name || obj?.id || '—'}</span>
    <button
      class="observed-btn"
      class:observed={isObservedToday}
      on:click={toggleObserved}
      title={isObservedToday ? 'Mark as not observed' : 'Mark as observed tonight'}
    >{isObservedToday ? '★' : '☆'}</button>
  </div>

  {#if obj}
    <div class="content">
      {#if imageUrl}
        <div class="image-wrap">
          <img src={imageUrl} alt={obj.name || obj.id} class="object-image" />
        </div>
      {/if}

      <section class="info-section">
        {#if obj.name}
          <div class="row"><span class="label">Name</span><span class="value">{obj.name}</span></div>
        {/if}
        {#if catNumbers(obj)}
          <div class="row"><span class="label">Catalogue</span><span class="value cat">{catNumbers(obj)}</span></div>
        {/if}
        {#if obj.type}
          <div class="row"><span class="label">Type</span><span class="value">{typeLabel(obj)}</span></div>
        {/if}
        {#if isDouble(obj)}
          {@const sep = dblMainPair(obj)?.sep}
          {#if sep != null}
            <div class="row"><span class="label">Separation</span><span class="value">{formatSep(sep)}</span></div>
          {/if}
        {/if}
        {#if obj.pos}
          <div class="row"><span class="label">RA</span><span class="value mono">{formatRA(raHours(obj))}</span></div>
          <div class="row"><span class="label">Dec</span><span class="value mono">{formatDec(decDeg(obj))}</span></div>
        {/if}
        {#if obj.constellation}
          <div class="row"><span class="label">Constellation</span><span class="value">{obj.constellation}</span></div>
        {/if}
        {#if obj.mag != null || isDouble(obj)}
          <div class="row"><span class="label">Magnitude</span><span class="value">{isDouble(obj) ? formatMagRow(obj) : formatMag(obj.mag)}</span></div>
        {/if}
        {#if obj.size != null}
          <div class="row"><span class="label">Size</span><span class="value">{formatSize(obj.size)}</span></div>
        {/if}
        {#if obj.ang != null}
          <div class="row"><span class="label">Orientation</span><span class="value">{obj.ang}°</span></div>
        {/if}
        {#if obj.dist != null}
          <div class="row"><span class="label">Distance</span><span class="value">{obj.dist} ly</span></div>
        {/if}
        {#if formatSpect(obj)}
          <div class="row"><span class="label">Spectral type</span><span class="value">{formatSpect(obj)}</span></div>
        {/if}
        {#if obj.cstar_mag != null}
          <div class="row"><span class="label">Central star</span><span class="value">mag {obj.cstar_mag}</span></div>
        {/if}
      </section>

      {#if isDouble(obj) && dblPairs(obj).length > 0}
        {@const disc = obj.type === 'double_star' ? obj.disc : linkedDs?.disc}
        <section class="info-section">
          <div class="section-title">Double star</div>
          {#if disc}
            <div class="row"><span class="label">Discoverer</span><span class="value">{disc}</span></div>
          {/if}
          {#each dblPairs(obj) as pair}
            <div class="dbl-pair">
              <span class="pair-comp">{pair.comp}</span>
              {#if pair.mag != null}
                <span class="pair-mag">{Array.isArray(pair.mag) ? `${pair.mag[0]} / ${pair.mag[1]}` : pair.mag}</span>
              {/if}
              {#if pair.sep != null}
                <span class="pair-sep">{formatSep(pair.sep)}</span>
              {/if}
              {#if pair.period != null}
                <span class="pair-period">{pair.period} yr</span>
              {/if}
            </div>
          {/each}
        </section>
      {/if}

      <section class="info-section">
        <div class="section-title">Visibility today</div>
        <div class="row"><span class="label">Rise</span><span class="value mono">{formatTime(riseTime)}</span></div>
        <div class="row"><span class="label">Transit</span><span class="value mono">{formatTime(transitTime)}</span></div>
        <div class="row"><span class="label">Set</span><span class="value mono">{formatTime(setTime)}</span></div>
      </section>

      {#if moonPhaseDeg !== null}
        <section class="info-section moon-section">
          <div class="section-title">Moon phase</div>
          <div class="moon-row">
            <svg viewBox="0 0 100 100" width="64" height="64" class="moon-svg">
              <circle cx="50" cy="50" r="45" class="moon-dark" />
              {#if moonPath(moonPhaseDeg)}
                <path d={moonPath(moonPhaseDeg)} class="moon-lit" />
              {/if}
            </svg>
            <span class="value">{Math.round((moonIllumination ?? 0) * 100)}% illuminated</span>
          </div>
        </section>
      {/if}

      {#if planetPhaseFraction !== null}
        <section class="info-section">
          <div class="section-title">Phase</div>
          <div class="row"><span class="label">Illumination</span><span class="value">{Math.round(planetPhaseFraction * 100)}%</span></div>
        </section>
      {/if}

      {#if obj.note || obj.smr}
        <section class="info-section note-section">
          <div class="section-title">Notes</div>
          {#if obj.smr}
            <p class="note-text smr">{obj.smr}</p>
          {/if}
          {#if obj.note}
            <p class="note-text">{obj.note}</p>
          {/if}
        </section>
      {/if}
    </div>
  {/if}
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 11;
    background: #000;
    color: #e8e8e8;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.15);
    flex-shrink: 0;
    gap: 0.5rem;
  }

  .back-btn {
    background: none;
    border: none;
    color: #e8e8e8;
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .back-btn:hover {
    background: rgba(232, 232, 232, 0.1);
  }

  .header-title {
    flex: 1;
    font-size: 1rem;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .observed-btn {
    background: none;
    border: 1px solid rgba(232, 232, 232, 0.35);
    color: #e8e8e8;
    font-size: 1.25rem;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    line-height: 1;
  }

  .observed-btn.observed {
    background: rgba(220, 80, 80, 0.18);
    border-color: #dc5050;
    color: #dc5050;
  }

  .observed-btn:hover {
    background: rgba(232, 232, 232, 0.12);
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem 1rem 2rem;
    -webkit-overflow-scrolling: touch;
  }

  .image-wrap {
    margin-bottom: 1rem;
    border-radius: 6px;
    overflow: hidden;
    max-height: 220px;
    background: #000;
  }

  .object-image {
    width: 100%;
    height: 220px;
    object-fit: cover;
    display: block;
  }

  .info-section {
    margin-bottom: 1rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
    padding-bottom: 0.75rem;
  }

  .info-section:last-child {
    border-bottom: none;
  }

  .section-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.55;
    margin-bottom: 0.5rem;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.2rem 0;
    gap: 0.5rem;
  }

  .label {
    font-size: 0.8rem;
    opacity: 0.6;
    flex-shrink: 0;
  }

  .value {
    font-size: 0.9rem;
    text-align: right;
  }

  .value.mono {
    font-family: monospace;
    font-size: 0.85rem;
  }

  .value.cat {
    font-size: 0.8rem;
    text-align: right;
  }

  .moon-section {}

  .moon-row {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .moon-svg {
    flex-shrink: 0;
  }

  .moon-dark {
    fill: #1a1a1a;
    stroke: rgba(232, 232, 232, 0.25);
    stroke-width: 1.5;
  }

  .moon-lit {
    fill: #e8e8e8;
  }

  .dbl-pair {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.2rem 0;
    font-size: 0.85rem;
  }

  .pair-comp {
    font-weight: 600;
    flex-shrink: 0;
    min-width: 2rem;
    opacity: 0.9;
  }

  .pair-mag {
    flex: 1;
  }

  .pair-sep {
    opacity: 0.85;
    font-family: monospace;
    font-size: 0.8rem;
  }

  .pair-period {
    opacity: 0.55;
    font-size: 0.8rem;
    flex-shrink: 0;
  }

  .note-section {}

  .note-text {
    font-size: 0.85rem;
    line-height: 1.5;
    opacity: 0.85;
    margin: 0 0 0.5rem;
  }

  .note-text.smr {
    font-weight: 600;
    opacity: 1;
    margin-bottom: 0.4rem;
  }
</style>
