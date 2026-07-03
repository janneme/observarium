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
  import { objectDetailsActive, solarSystemPositions } from '../stores/ui.js'
  import { getTodayObservation, getObjectImage, getDoubleStarNear } from '../lib/db.js'
  import { applyDsPatch } from '../lib/customObjects.js'
  import ObservationFormPanel from '../components/ObservationFormPanel.svelte'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'

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
  let showObservationForm = false

  $: obj = $selectedObject

  function raHours(o) {
    return (o?.pos?.[0] ?? 0) / 15
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

  function solarApparentMag(o) {
    if (o?.type !== 'solar_system_body') return null
    const oid = String(o.id || '').toLowerCase()
    const oname = String(o.name || '').toLowerCase()
    const body = $solarSystemPositions.find((b) => {
      const bname = String(b.name || '').toLowerCase()
      const bid = `solar_${String(b.imageId || bname).toLowerCase()}`
      return bid === oid || bname === oname
    })
    if (!body || body.mag == null || Number.isNaN(Number(body.mag))) return null
    return Number(body.mag)
  }

  function formatApparentMag(m) {
    if (m == null) return null
    return m.toFixed(2)
  }

  function catNumbers(o) {
    const parts = []
    if (o.bay) parts.push(o.constellation ? `${o.bay} ${o.constellation}` : o.bay)
    if (o.flam != null) parts.push(o.constellation ? `${o.flam} ${o.constellation}` : String(o.flam))
    if (o.hd != null) parts.push(`HD ${o.hd}`)
    if (o.hip != null) parts.push(`HIP ${o.hip}`)
    if (o.m != null) parts.push(`M ${o.m}`)
    if (o.ngc != null) parts.push(`NGC ${o.ngc}`)
    if (o.ic != null) parts.push(`IC ${o.ic}`)
    if (o.caldwell != null) parts.push(`C ${o.caldwell}`)
    if (o.wds != null) parts.push(`WDS ${o.wds}`)
    return parts.length ? parts : null
  }

  function dblPairs(o, ds = null) {
    if (o.type === 'double_star') return o.pairs || []
    if (Array.isArray(o.dbl)) return o.dbl.flatMap((entry) => entry.pairs || [])
    if (o.dbl && ds) return ds.pairs || []
    return []
  }

  function isDouble(o) {
    return o.type === 'double_star' || (o.type === 'star' && !!o.dbl)
  }

  function dblMainPair(o, ds = null) {
    const pairs = dblPairs(o, ds)
    return pairs.find((p) => p.comp === 'AB') || pairs[0] || null
  }

  function formatSep(sep) {
    if (sep == null) return null
    if (Array.isArray(sep)) return `${sep[0]}″–${sep[1]}″`
    return `${sep}″`
  }

  const VAR_TYPE_LABELS = {
    DCEP: 'Cepheid',
    DCEPS: 'Cepheid (short-period)',
    CEP: 'Cepheid',
    CW: 'W Virginis variable',
    CWA: 'W Virginis variable',
    CWB: 'W Virginis variable',
    M: 'Mira variable',
    SR: 'Semi-regular variable',
    SRA: 'Semi-regular variable',
    SRB: 'Semi-regular variable',
    SRC: 'Semi-regular variable',
    SRD: 'Semi-regular variable',
    L: 'Irregular variable',
    LB: 'Irregular variable',
    LC: 'Irregular variable',
    RR: 'RR Lyrae variable',
    RRAB: 'RR Lyrae variable',
    RRC: 'RR Lyrae variable',
    EA: 'Eclipsing binary (Algol type)',
    EB: 'Eclipsing binary (β Lyræ type)',
    EW: 'Eclipsing binary (W UMa type)',
    BCEP: 'β Cephei variable',
    DSCT: 'δ Scuti variable',
    GDOR: 'γ Doradus variable',
    RCB: 'R Coronae Borealis variable',
    UV: 'Flare star',
  }

  function varTypeLabel(o) {
    if (!Array.isArray(o.mag) || !o.varType) return null
    const label = VAR_TYPE_LABELS[o.varType]
    return label ? `Variable star (${label})` : 'Variable star'
  }

  function typeLabels(o, ds = null) {
    if (o.dsoType) return [o.dsoType]
    if (o.type === 'solar_system_body') {
      const cls = String(o.bodyClass || '').toLowerCase()
      if (cls === 'planet') return ['Planet']
      if (cls === 'dwarf_planet') return ['Dwarf planet']
      if (cls === 'asteroid') return ['Asteroid']
      if (cls === 'moon') return ['Moon']
      if (cls === 'star') return ['Star']
      const name = String(o.name || '').toLowerCase()
      if (['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune'].includes(name)) return ['Planet']
      if (['pluto', 'ceres', 'eris', 'haumea', 'makemake'].includes(name)) return ['Dwarf planet']
      if (name === 'moon') return ['Moon']
      if (name === 'sun') return ['Star']
      return ['Solar system body']
    }
    const labels = []
    if (isDouble(o)) {
      const pairs = dblPairs(o, ds)
      const physComps = pairs.filter((p) => !!p.phys).map((p) => p.comp)
      if (physComps.length > 0) labels.push(`Double star (physical ${physComps.join(', ')})`)
      else if (o.dbl === 'p') labels.push('Double star (physical)')
      else if (o.dbl === 'a' || pairs.some((p) => p.vis)) labels.push('Double star (apparent)')
      else labels.push('Double star')
    }
    const vl = varTypeLabel(o)
    if (vl) labels.push(vl)
    if (labels.length === 0) labels.push(o.type)
    return labels
  }

  function formatMagRow(o, ds = null) {
    if (!isDouble(o)) return formatMag(o.mag)
    const pairs = dblPairs(o, ds)
    const compMags = new Map()
    for (const pair of pairs) {
      if (!pair?.comp || !Array.isArray(pair.mag)) continue
      const comp = String(pair.comp).trim().toUpperCase()
      if (comp.length !== 2 || pair.mag.length < 2) continue
      const [c1, c2] = comp.split('')
      const [m1, m2] = pair.mag
      if (m1 != null && !compMags.has(c1)) compMags.set(c1, m1)
      if (m2 != null && !compMags.has(c2)) compMags.set(c2, m2)
    }
    if (compMags.size >= 2) {
      const compStr = [...compMags.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([, mag]) => mag)
        .join(' / ')
      return o.mag != null ? `${formatMag(o.mag)} (${compStr})` : compStr
    }
    const pair = dblMainPair(o, ds)
    if (pair?.mag && Array.isArray(pair.mag)) {
      const [m1, m2] = pair.mag
      const compStr = `${m1} / ${m2}`
      return o.mag != null ? `${formatMag(o.mag)} (${compStr})` : compStr
    }
    return formatMag(o.mag)
  }

  function formatSpect(o, ds = null) {
    const linkedSpect = isDouble(o) ? ds?.spect : null
    const embeddedSpect = isDouble(o)
      ? Array.isArray(o.dbl)
        ? o.dbl.find((entry) => typeof entry?.spect === 'string' && entry.spect.trim())?.spect
        : null
      : null
    const normalize = (s) =>
      typeof s === 'string'
        ? s
            .replace(/\+/g, '/')
            .replace(/\s*\/\s*/g, ' / ')
            .replace(/\s+/g, ' ')
            .split(' / ')
            .map((part) => part.replace(/\s+/g, ''))
            .join(' / ')
            .trim()
        : ''
    const linkedNorm = normalize(linkedSpect)
    const embeddedNorm = normalize(embeddedSpect)
    const hasComposite = (s) => s.includes(' / ')
    const dblSpect = isDouble(o)
      ? hasComposite(embeddedNorm) && !hasComposite(linkedNorm)
        ? embeddedNorm
        : hasComposite(linkedNorm) && !hasComposite(embeddedNorm)
          ? linkedNorm
          : embeddedNorm.length > linkedNorm.length
            ? embeddedNorm
            : linkedNorm
      : null
    const effectiveSpect = isDouble(o) ? dblSpect || o.spect : o.spect
    if (!effectiveSpect) return null
    if (isDouble(o)) {
      return normalize(effectiveSpect)
    }
    return effectiveSpect
  }

  function spectralColor(s) {
    const m = { O: '#92b5ff', B: '#b2c5ff', A: '#cad8ff', F: '#f8f7ff', G: '#fff4e8', K: '#ffd2a1', M: '#ff8f6b' }
    return m[s?.trim()[0]?.toUpperCase()] ?? null
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
          Pluto: Body.Pluto,
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

  function openObservedForm() {
    if (!obj) return
    showObservationForm = true
  }

  function shouldIgnoreShortcutTarget(target) {
    if (!target || !(target instanceof Element)) return false
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
    return !!target.closest('[contenteditable="true"]')
  }

  function onGlobalKeyDown(event) {
    if (!$objectDetailsActive || showObservationForm || !obj) return
    if (event.defaultPrevented || event.repeat) return
    if (event.altKey || event.ctrlKey || event.metaKey) return
    if (shouldIgnoreShortcutTarget(event.target)) return
    const isShortcutKey = String(event.key).toLowerCase() === 'o' || event.code === 'KeyO'
    if (!isShortcutKey) return
    event.preventDefault()
    event.stopImmediatePropagation()
    openObservedForm()
  }

  function close() {
    objectDetailsActive.set(false)
  }

  function objLabel(obj) {
    if (!obj) return '—'
    if (obj.name) return obj.name
    if (obj.bay && obj.constellation) return `${obj.bay} ${obj.constellation}`
    if (obj.flam && obj.constellation) return `${obj.flam} ${obj.constellation}`
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    const id = String(obj.id || '')
    if (id.startsWith('dso_M')) return `M ${Number(id.slice(5))}`
    if (id.startsWith('dso_NGC')) return `NGC ${Number(id.slice(7))}`
    if (id.startsWith('dso_IC')) return `IC ${Number(id.slice(6))}`
    if (id.startsWith('dso_C')) return `C ${Number(id.slice(5))}`
    if (id.startsWith('solar_')) {
      const name = id.slice(6).replace(/_/g, ' ').trim()
      if (name) return name[0].toUpperCase() + name.slice(1)
    }
    if (id.startsWith('star_t2_')) return 'Unnamed'
    return id.replace(/^star_([A-Za-z]+)(\d+)$/, '$1 $2') || '—'
  }

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs) for (const c of String(p.comp || '')) if (c >= 'A' && c <= 'Z') letters.add(c)
    return letters.size
  }

  function objectSymbolKind(obj) {
    if (!obj) return 'generic'
    if (obj.type === 'double_star') return dsLetterCount(obj.pairs) > 2 ? 'double_star_multi' : 'double_star'
    if (obj.type === 'star') {
      if (obj.dbl === 'm') return 'double_star_multi'
      if (obj.dbl) return 'double_star'
      if (Array.isArray(obj.mag) && obj.mag[1] - obj.mag[0] >= 1) return 'variable_star'
      return 'star'
    }
    if (obj.type === 'solar_system_body') return String(obj.name || '').toLowerCase() || 'generic'
    const type = String(obj.dsoType || '').toLowerCase()
    if (type === 'open cluster') return 'open_cluster'
    if (type === 'globular cluster') return 'globular_cluster'
    if (type === 'planetary nebula') return 'planetary_nebula'
    if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') return 'galaxy'
    if (type === 'dark nebula') return 'dark_nebula'
    if (type === 'galaxy cluster' || type === 'cluster of galaxies') return 'galaxy_cluster'
    if (type === 'quasar' || type === 'qso' || type === 'bl lac') return 'quasar'
    if (type.includes('nebula')) return 'nebula'
    return 'generic'
  }

  onMount(() => {
    if (obj) loadData(obj)
    window.addEventListener('keydown', onGlobalKeyDown, true)
  })

  onDestroy(() => {
    window.removeEventListener('keydown', onGlobalKeyDown, true)
    if (blobUrlToRevoke) URL.revokeObjectURL(blobUrlToRevoke)
  })

  $: if (obj) loadData(obj)

  $: if (obj?.type === 'star' && obj.dbl) {
    linkedDs = null
    getDoubleStarNear(obj.pos[0], obj.pos[1]).then((ds) => {
      linkedDs = applyDsPatch(ds)
    })
  } else {
    linkedDs = null
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" on:click={close}>←</button>
    <span class="type-symbol"><ObservationObjectSymbol kind={objectSymbolKind(obj)} /></span>
    <span class="header-title">{objLabel(obj)}</span>
    <button
      class="observed-btn"
      class:observed={isObservedToday}
      on:click={openObservedForm}
      title={isObservedToday ? 'Edit observation' : 'Create observation'}
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512" aria-hidden="true">
        <path
          d="M288 32c-80.8 0-145.5 36.8-192.6 80.6-46.8 43.5-78.1 95.4-93 131.1-3.3 7.9-3.3 16.7 0 24.6 14.9 35.7 46.2 87.7 93 131.1 47.1 43.7 111.8 80.6 192.6 80.6s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1 3.3-7.9 3.3-16.7 0-24.6-14.9-35.7-46.2-87.7-93-131.1-47.1-43.7-111.8-80.6-192.6-80.6zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64-11.5 0-22.3-3-31.7-8.4-1 10.9-.1 22.1 2.9 33.2 13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-12.2-45.7-55.5-74.8-101.1-70.8 5.3 9.3 8.4 20.1 8.4 31.7z"
        />
      </svg>
    </button>
  </div>

  <svg style="display:none" aria-hidden="true">
    <defs>
      <filter id="nightly-red-scale" color-interpolation-filters="sRGB">
        <feColorMatrix
          type="matrix"
          values="0.2126 0.7152 0.0722 0 0
                  0      0      0      0 0
                  0      0      0      0 0
                  0      0      0      1 0"
        />
      </filter>
    </defs>
  </svg>

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
          <div class="row cat-row">
            <span class="label">Catalogue</span>
            <span class="cat-value">
              {#each catNumbers(obj) as item}
                <span class="cat-item">{item}</span>
              {/each}
            </span>
          </div>
        {/if}
        {#if obj.type}
          {@const tLabels = typeLabels(obj, linkedDs)}
          <div class="row cat-row">
            <span class="label">Type</span>
            <span class="cat-value">
              {#each tLabels as label}
                <span class="cat-item">{label}</span>
              {/each}
            </span>
          </div>
        {/if}
        {#if obj.varPeriod}
          <div class="row"><span class="label">Period</span><span class="value">{obj.varPeriod} days</span></div>
        {/if}
        {#if isDouble(obj)}
          {@const sepPairs = dblPairs(obj, linkedDs).filter((p) => p.sep != null)}
          {#if sepPairs.length === 1}
            <div class="row">
              <span class="label">Separation</span><span class="value">{formatSep(sepPairs[0].sep)}</span>
            </div>
          {:else if sepPairs.length > 1}
            <div class="row sep-row">
              <span class="label">Separation</span>
              <span class="value sep-value">
                {#each sepPairs as p}
                  <span class="sep-item"><span class="sep-comp">{p.comp}</span>{formatSep(p.sep)}</span>
                {/each}
              </span>
            </div>
          {/if}
        {/if}
        {#if obj.pos}
          <div class="row"><span class="label">RA</span><span class="value mono">{formatRA(raHours(obj))}</span></div>
          <div class="row"><span class="label">Dec</span><span class="value mono">{formatDec(decDeg(obj))}</span></div>
          {#if obj.type === 'solar_system_body' && solarApparentMag(obj) != null}
            <div class="row">
              <span class="label">Apparent mag</span><span class="value"
                >{formatApparentMag(solarApparentMag(obj))}</span
              >
            </div>
          {/if}
        {/if}
        {#if obj.constellation}
          <div class="row"><span class="label">Constellation</span><span class="value">{obj.constellation}</span></div>
        {/if}
        {#if obj.mag != null || isDouble(obj)}
          <div class="row">
            <span class="label">Magnitude</span><span class="value"
              >{isDouble(obj) ? formatMagRow(obj, linkedDs) : formatMag(obj.mag)}</span
            >
          </div>
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
        {#if formatSpect(obj, linkedDs)}
          {@const spParts = formatSpect(obj, linkedDs).split(' / ')}
          <div class="row">
            <span class="label">Spectral type</span>
            <span class="value">
              {#each spParts as part, i}
                {#if i > 0}<span class="spect-sep">{' '}/{' '}</span>{/if}
                <span class="spect-color" style="color: {spectralColor(part) ?? 'inherit'}">{part}</span>
              {/each}
            </span>
          </div>
        {/if}
        {#if obj.cstar_mag != null}
          <div class="row"><span class="label">Central star mag</span><span class="value">{obj.cstar_mag}</span></div>
        {/if}
      </section>

      <section class="info-section">
        <div class="section-title">Visibility today</div>
        <div class="row"><span class="label">Rise</span><span class="value mono">{formatTime(riseTime)}</span></div>
        <div class="row">
          <span class="label">Transit</span><span class="value mono">{formatTime(transitTime)}</span>
        </div>
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
        {@const planetPhaseDeg = (Math.acos(1 - 2 * planetPhaseFraction) * 180) / Math.PI}
        <section class="info-section moon-section">
          <div class="section-title">Phase</div>
          <div class="moon-row">
            <svg viewBox="0 0 100 100" width="64" height="64" class="moon-svg">
              <circle cx="50" cy="50" r="45" class="moon-dark" />
              {#if moonPath(planetPhaseDeg)}
                <path d={moonPath(planetPhaseDeg)} class="moon-lit" />
              {/if}
            </svg>
            <span class="value">{Math.round(planetPhaseFraction * 100)}% illuminated</span>
          </div>
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

  {#if showObservationForm && obj}
    <ObservationFormPanel
      objectId={obj.id}
      on:saved={async () => {
        showObservationForm = false
        await loadData(obj)
      }}
      on:cancel={() => {
        showObservationForm = false
      }}
    />
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
    color: var(--fg);
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
    color: var(--fg);
    font-size: 1.3rem;
    cursor: pointer;
    padding: 0 0.5rem;
    border-radius: 4px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    line-height: 0;
  }

  .back-btn:hover {
    background: rgba(200, 0, 0, 0.1);
  }

  .type-symbol {
    font-size: 0.95rem;
    opacity: 0.7;
    flex-shrink: 0;
    line-height: 1;
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
    border: none;
    color: var(--fg);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    padding: 0.25rem;
    border-radius: 4px;
  }

  .observed-btn svg {
    width: 1.4rem;
    height: 1.4rem;
    fill: currentColor;
  }

  .observed-btn.observed {
    color: #cc0000;
  }

  .observed-btn:hover {
    background: rgba(200, 0, 0, 0.1);
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
    background: #000;
  }

  .object-image {
    width: auto;
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
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

  .cat-row {
    align-items: flex-start;
  }

  .cat-value {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.15rem;
  }

  .cat-item {
    font-size: 0.8rem;
    text-align: right;
  }

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

  .sep-row {
    align-items: flex-start;
  }

  .sep-value {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    text-align: right;
  }

  .sep-item {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
    font-family: monospace;
    font-size: 0.85rem;
  }

  .sep-comp {
    opacity: 0.6;
    font-weight: 600;
  }

  .spect-sep {
    opacity: 0.5;
  }

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

  /* Nightly theme */
  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }
  :global([data-theme='nightly']) .back-btn:hover {
    background: rgba(200, 0, 0, 0.08);
  }
  :global([data-theme='nightly']) .observed-btn:hover {
    background: rgba(200, 0, 0, 0.1);
  }
  :global([data-theme='nightly']) .info-section {
    border-bottom-color: rgba(200, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .moon-dark {
    fill: #110000;
    stroke: rgba(200, 0, 0, 0.3);
  }
  :global([data-theme='nightly']) .moon-lit {
    fill: #cc0000;
  }
  :global([data-theme='nightly']) .object-image {
    filter: url(#nightly-red-scale);
  }
  :global([data-theme='nightly']) .spect-color {
    color: inherit !important;
  }
</style>
