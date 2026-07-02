<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import { getMeta, getObjectsInArea } from '../lib/db.js'
  import {
    generatePlan,
    INITIAL_STAR_MAX_MAG,
    INITIAL_MAG_STEP,
    INITIAL_MAG_RANGE_START_FACTOR,
  } from '../lib/visualRangePlan.js'
  import SearchPanel from '../components/SearchPanel.svelte'
  import VisualRangeMeasureScreen from './VisualRangeMeasureScreen.svelte'

  export let lat = 0
  export let lon = 0
  export let time = new Date()

  const dispatch = createEventDispatcher()

  let selectedStar = null
  let selectedTelescopeId = null
  let selectedEyepieceId = null
  let selectedInitialMag = null
  let showSearch = false
  let telescopes = []
  let eyepieces = []
  let planning = false
  let planError = ''
  let planResult = null
  let showMeasure = false
  let _mounted = false

  const LS_KEY = 'observarium.visualRange.setup'

  function _saveState(star, telescopeId, eyepieceId, initialMag) {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ star, telescopeId, eyepieceId, initialMag }))
    } catch {}
  }

  $: _mounted && _saveState(selectedStar, selectedTelescopeId, selectedEyepieceId, selectedInitialMag)

  $: selectedTelescope = telescopes.find((t) => t.id === selectedTelescopeId) ?? null
  $: selectedEyepiece = eyepieces.find((e) => e.id === selectedEyepieceId) ?? null
  $: canBegin = !!(
    selectedStar &&
    selectedTelescope &&
    selectedEyepiece &&
    selectedInitialMag !== null &&
    !planning
  )

  $: magOptions = (() => {
    if (!selectedTelescope) return []
    const diamMm = selectedTelescope.diameterInches * 25.4
    const theoreticalMax = 2.1 + 5 * Math.log10(diamMm)
    const startRaw = INITIAL_MAG_RANGE_START_FACTOR * theoreticalMax
    const start = Math.ceil(startRaw / INITIAL_MAG_STEP) * INITIAL_MAG_STEP
    const end = Math.floor(theoreticalMax / INITIAL_MAG_STEP) * INITIAL_MAG_STEP
    const opts = []
    for (let m = start; m <= end + 0.001; m = Math.round((m + INITIAL_MAG_STEP) * 10) / 10) {
      opts.push(m)
    }
    return opts
  })()

  $: if (magOptions.length > 0 && selectedInitialMag !== null && !magOptions.includes(selectedInitialMag)) {
    selectedInitialMag = null
  }

  onMount(async () => {
    const [savedTels, savedEps] = await Promise.all([getMeta('telescopes'), getMeta('eyepieces')])
    telescopes = Array.isArray(savedTels)
      ? [...savedTels].sort((a, b) =>
          String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
        )
      : []
    eyepieces = Array.isArray(savedEps)
      ? [...savedEps].sort((a, b) =>
          String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
        )
      : []
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (raw) {
        const s = JSON.parse(raw)
        if (s.star) selectedStar = s.star
        if (s.telescopeId != null && telescopes.some((t) => t.id === s.telescopeId))
          selectedTelescopeId = s.telescopeId
        if (s.eyepieceId != null && eyepieces.some((e) => e.id === s.eyepieceId))
          selectedEyepieceId = s.eyepieceId
        if (s.initialMag != null) selectedInitialMag = s.initialMag
      }
    } catch {}
    _mounted = true
  })

  function handleKey(e) {
    if (e.key === 'Escape' && !showSearch && !showMeasure) dispatch('close')
  }

  function greekFromBayer(bayer) {
    const raw = String(bayer || '').trim()
    if (!raw) return null
    const first = raw.split(/\s+/)[0] || ''
    const cleaned = first
      .toLowerCase()
      .replace(/[0-9]+$/g, '')
      .replace(/[._-]+$/g, '')
    const greekChars = 'αβγδεζηθικλμνξοπρστυφχψω'
    if (cleaned && greekChars.includes(cleaned[0])) return cleaned[0]
    const key = cleaned.length >= 3 ? cleaned.slice(0, 3) : cleaned
    const map = {
      alf: 'α', alp: 'α', bet: 'β', gam: 'γ', del: 'δ', eps: 'ε',
      zet: 'ζ', eta: 'η', the: 'θ', iot: 'ι', kap: 'κ', lam: 'λ',
      mu: 'μ', nu: 'ν', xi: 'ξ', omi: 'ο', pi: 'π', rho: 'ρ',
      sig: 'σ', tau: 'τ', ups: 'υ', phi: 'φ', chi: 'χ', psi: 'ψ', ome: 'ω',
    }
    return map[key] || null
  }

  function preferredStarLabel(obj) {
    const rawName = String(obj?.name || '').trim()
    if (rawName) return rawName
    const rawBay = String(obj?.bay || '').trim()
    const greek = greekFromBayer(rawBay)
    if (greek && obj?.constellation) return `${greek} ${obj.constellation}`
    if (rawBay && obj?.constellation) return `${rawBay} ${obj.constellation}`
    if (obj?.hip != null) return `HIP ${obj.hip}`
    if (obj?.hd != null) return `HD ${obj.hd}`
    return String(obj?.id || 'Star')
  }

  async function handleBegin() {
    planning = true
    planError = ''
    try {
      const tel = selectedTelescope
      const ep = selectedEyepiece
      const diamMm = tel.diameterInches * 25.4
      // Fetch DSOs only (T1_MAG_LIMIT=9 skips T2 zones; DSOs are always included)
      const dsos = (await getObjectsInArea(0, 360, -90, 90, 9)).filter((o) => o.type === 'dso')
      const result = await generatePlan({
        getObjectsInArea,
        dsos,
        startStar: selectedStar,
        telescope: { focalLength: tel.focalLengthMm, diameter: diamMm },
        eyepiece: { focalLength: ep.focalLengthMm, fov: ep.fovDeg },
        initialMag: selectedInitialMag,
      })
      if (result.ok) {
        planResult = result
        showMeasure = true
      } else {
        planError = result.reason
      }
    } catch (err) {
      planError = err?.message || 'An error occurred while computing the plan.'
    } finally {
      planning = false
    }
  }
</script>

<svelte:window on:keydown={handleKey} />

{#if showMeasure}
  <VisualRangeMeasureScreen
    {lat}
    {lon}
    {time}
    plan={planResult}
    startStar={selectedStar}
    telescope={selectedTelescope}
    eyepiece={selectedEyepiece}
    initialMag={selectedInitialMag}
    on:close={() => {
      showMeasure = false
      dispatch('close')
    }}
  />
{:else}
  <div class="overlay" on:pointerdown|stopPropagation>
    <div class="header">
      <button class="back-btn" type="button" on:click={() => dispatch('close')}>←</button>
      <span class="header-title">Visual Range</span>
    </div>

    <div class="body">
      <div class="field-row">
        <span class="field-label">Start star</span>
        <button class="pick-btn" on:click={() => (showSearch = true)}>
          {selectedStar ? preferredStarLabel(selectedStar) : 'Pick a star…'}
        </button>
      </div>

      <div class="field-row">
        <span class="field-label">Telescope</span>
        {#if telescopes.length === 0}
          <span class="hint">No telescopes — add one under Telescopes in the menu</span>
        {:else}
          <select
            bind:value={selectedTelescopeId}
            on:change={() => {
              selectedEyepieceId = null
            }}
          >
            <option value={null} disabled>Select telescope…</option>
            {#each telescopes as tel (tel.id)}
              <option value={tel.id}>{tel.name}</option>
            {/each}
          </select>
        {/if}
      </div>

      <div class="field-row">
        <span class="field-label">Eyepiece</span>
        {#if eyepieces.length === 0}
          <span class="hint">No eyepieces — add one under Telescopes in the menu</span>
        {:else}
          <select bind:value={selectedEyepieceId} disabled={!selectedTelescopeId}>
            <option value={null} disabled>Select eyepiece…</option>
            {#each eyepieces as ep (ep.id)}
              <option value={ep.id}>{ep.name}</option>
            {/each}
          </select>
        {/if}
      </div>

      {#if selectedTelescopeId}
        <div class="field-row col">
          <span class="field-label">Initial magnitude</span>
          <div class="pills">
            {#each magOptions as m}
              <button
                class="pill"
                class:selected={selectedInitialMag === m}
                on:click={() => (selectedInitialMag = m)}
              >{m}</button>
            {/each}
          </div>
        </div>
      {/if}

      {#if planError}
        <p class="plan-error">{planError}</p>
      {/if}

      <button class="begin-btn" disabled={!canBegin} on:click={handleBegin}>
        {planning ? 'Computing…' : 'Begin'}
      </button>
    </div>
  </div>

  {#if showSearch}
    <SearchPanel
      useSearchStore={false}
      manageSelection={false}
      includeSolar={false}
      showDetailsAction={false}
      showFindingPathsAction={false}
      autoCloseOnAccept={false}
      zIndex={13}
      title="Select start star"
      resultFilter={(obj) => {
        if (obj.type !== 'star') return false
        const m =
          typeof obj.mag === 'number' ? obj.mag : Array.isArray(obj.mag) ? obj.mag[0] : Infinity
        return m <= INITIAL_STAR_MAX_MAG
      }}
      onAcceptObject={async (obj) => {
        selectedStar = obj
        showSearch = false
      }}
      on:close={() => (showSearch = false)}
    />
  {/if}
{/if}

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 12;
    background: #040404;
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
    border-bottom: 1px solid rgba(200, 0, 0, 0.15);
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .back-btn:hover {
    background: rgba(200, 0, 0, 0.08);
  }

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .body {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .field-row.col {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .field-label {
    font-size: 0.8rem;
    opacity: 0.7;
    min-width: 7rem;
    flex-shrink: 0;
  }

  .pick-btn {
    flex: 1;
    background: rgba(200, 0, 0, 0.07);
    border: 1px solid rgba(200, 0, 0, 0.25);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.4rem 0.75rem;
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
  }

  .pick-btn:hover {
    background: rgba(200, 0, 0, 0.12);
  }

  select {
    flex: 1;
    background: rgba(200, 0, 0, 0.07);
    border: 1px solid rgba(200, 0, 0, 0.25);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.4rem 0.5rem;
    font-size: 0.85rem;
  }

  select:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .hint {
    font-size: 0.78rem;
    opacity: 0.5;
    font-style: italic;
  }

  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .pill {
    background: rgba(200, 0, 0, 0.07);
    border: 1px solid rgba(200, 0, 0, 0.25);
    color: var(--fg);
    border-radius: 20px;
    padding: 0.3rem 0.65rem;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 100ms;
  }

  .pill:hover {
    background: rgba(200, 0, 0, 0.15);
  }

  .pill.selected {
    background: var(--accent, #cc0000);
    border-color: transparent;
    color: #000000;
  }

  .plan-error {
    font-size: 0.82rem;
    color: #dd0000;
    background: rgba(200, 0, 0, 0.08);
    border: 1px solid rgba(200, 0, 0, 0.25);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    margin: 0;
  }

  .begin-btn {
    margin-top: 0.5rem;
    background: var(--accent, #cc0000);
    border: none;
    color: #000000;
    border-radius: 8px;
    padding: 0.7rem 2rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    align-self: center;
    transition: opacity 120ms;
  }

  .begin-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .begin-btn:hover:not(:disabled) {
    opacity: 0.85;
  }
</style>
