<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import {
    computeBodyEphemeris,
    computeCometEphemeris,
    computeNightWindow,
    computeAstronomicalNightWindow,
  } from '../lib/solarBodyEphemeris.js'
  import { getMeta } from '../lib/db.js'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import RiseIcon from '../icons/RiseIcon.svelte'
  import SetIcon from '../icons/SetIcon.svelte'
  import MaxHeightIcon from '../icons/MaxHeightIcon.svelte'
  import AlwaysUpIcon from '../icons/AlwaysUpIcon.svelte'
  import AlwaysDownIcon from '../icons/AlwaysDownIcon.svelte'

  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  const dispatch = createEventDispatcher()

  const PLANET_NAMES = ['Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']

  let comets = []
  onMount(async () => {
    const solarSystem = await getMeta('solar_system')
    comets = solarSystem?.comets ?? []
  })

  function formatTime(astroTime) {
    if (!astroTime) return '—'
    return astroTime.date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  }

  function formatMag(m) {
    return m == null ? '—' : m.toFixed(1)
  }

  function formatAltitude(a) {
    return a == null ? '—' : `${a.toFixed(0)}°`
  }

  function formatHM(astroTime) {
    const d = astroTime.date
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  function formatWindow(w) {
    return w ? `${formatHM(w.start)}-${formatHM(w.end)}` : '—'
  }

  // Recomputed whenever the received `time` (or the loaded comet list)
  // changes — no timer, since this is a snapshot for a given observing date,
  // not a live clock display.
  $: rows = (() => {
    const moon = computeBodyEphemeris('Moon', lat, lon, time)
    const planets = PLANET_NAMES.map((name) => computeBodyEphemeris(name, lat, lon, time)).sort(
      (a, b) => a.distanceAu - b.distanceAu,
    )
    // Comet brightness/visibility predictions are rough estimates — only
    // list ones currently observable that night and currently brighter than
    // mag 9 (the catalog's peak-magnitude cutoff doesn't guarantee that —
    // a comet can be included for its perihelion peak but much fainter now).
    const cometRows = comets
      .map((c) => ({ ...computeCometEphemeris(c, lat, lon, time), isComet: true }))
      .filter((r) => r.observableAtNight !== false && r.mag <= 9.0)
      .sort((a, b) => a.distanceAu - b.distanceAu)
    return [moon, ...planets, ...cometRows]
  })()

  $: headerDate = `Rise/Set Times for ${time.getDate()}. ${time.getMonth() + 1}. ${time.getFullYear()}`
  $: nightWindow = computeNightWindow(lat, lon, time)
  $: astronomicalNightWindow = computeAstronomicalNightWindow(lat, lon, time)

  function handleKey(e) {
    if (e.key === 'Escape') dispatch('close')
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">{headerDate}</span>
  </div>

  <div class="body">
    <div class="night-table">
      <div class="night-row night-head">
        <span>Night</span>
        <span>Astronomical Night</span>
      </div>
      <div class="night-row">
        <span>{formatWindow(nightWindow)}</span>
        <span>{formatWindow(astronomicalNightWindow)}</span>
      </div>
    </div>

    <div class="table">
      <div class="table-row table-head">
        <span class="col-object">Object</span>
        <span class="col-const">Const.</span>
        <span class="col-mag">Mag.</span>
        <span class="col-icon"><RiseIcon size="1.2rem" aria-hidden="true" /></span>
        <span class="col-icon"><SetIcon size="1.2rem" aria-hidden="true" /></span>
        <span class="col-icon"><MaxHeightIcon size="1.2rem" aria-hidden="true" /></span>
      </div>
      {#each rows as row (row.name)}
        <div class="table-row" class:row-faint={row.observableAtNight === false}>
          <span class="col-object">
            <span class="obj-icon">
              <ObservationObjectSymbol kind={row.isComet ? 'comet' : row.name.toLowerCase()} />
            </span>
            {row.name}
          </span>
          <span class="col-const">{row.constellationAbbr}</span>
          <span class="col-mag">{formatMag(row.mag)}</span>
          <span class="col-icon">
            {#if row.circumpolar === 'up'}
              <AlwaysUpIcon size="1.2rem" />
            {:else if row.circumpolar === 'down'}
              <AlwaysDownIcon size="1.2rem" />
            {:else}
              {formatTime(row.riseTime)}
            {/if}
          </span>
          <span class="col-icon">
            {#if row.circumpolar === 'up'}
              <AlwaysUpIcon size="1.2rem" />
            {:else if row.circumpolar === 'down'}
              <AlwaysDownIcon size="1.2rem" />
            {:else}
              {formatTime(row.setTime)}
            {/if}
          </span>
          <span class="col-icon max-alt-cell">
            {#if row.observableAtNight === false}
              <span>—</span>
            {:else}
              <span>{formatAltitude(row.maxAltitudeAtNightDeg)}</span>
              {#if row.maxAltitudeAtNightTime}
                <span class="max-alt-time">{formatHM(row.maxAltitudeAtNightTime)}</span>
              {/if}
            {/if}
          </span>
        </div>
      {/each}
    </div>
  </div>
</div>

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
    gap: 0.35rem;
    flex-shrink: 0;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    padding: 0.25rem 0.15rem 0.25rem 0.5rem;
    border-radius: 4px;
    display: flex;
    align-items: center;
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
  }

  .night-table {
    display: flex;
    flex-direction: column;
    width: 100%;
    margin-bottom: 1.25rem;
  }

  .night-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    text-align: center;
    gap: 0.5rem;
    padding: 0.55rem 0.4rem;
    border-bottom: 1px solid rgba(127, 127, 127, 0.12);
  }

  .night-head {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    opacity: 0.6;
    border-bottom: 1px solid rgba(200, 0, 0, 0.25);
  }

  .table {
    display: flex;
    flex-direction: column;
    width: 100%;
  }

  .table-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr;
    align-items: center;
    gap: 0.5rem;
    padding: 0.55rem 0.4rem;
    border-bottom: 1px solid rgba(127, 127, 127, 0.12);
  }

  /* Not observable that night (never above the horizon while the Sun is
     below NIGHT_SUN_ALTITUDE_DEG) — de-emphasize rather than hide, since the
     object is still a real, correctly-computed row. */
  .row-faint {
    opacity: 0.4;
  }

  .table-head {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    opacity: 0.6;
    border-bottom: 1px solid rgba(200, 0, 0, 0.25);
  }

  /* .col-object sets its own font-size for data rows — override it back down
     in the header row so all header labels render at the same size. */
  .table-head .col-object {
    font-size: 0.8rem;
  }

  .col-const,
  .col-mag,
  .col-icon,
  .table-head .col-icon {
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .col-object {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 1rem;
  }

  .max-alt-cell {
    flex-direction: column;
    gap: 0.05rem;
  }

  .max-alt-time {
    font-size: 0.72em;
    opacity: 0.7;
  }

  .obj-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
  }

  .obj-icon :global(.symbol) {
    transform: scale(2);
  }
</style>
