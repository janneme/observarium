<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import {
    getAllObservations,
    getPendingChangesCount,
    getPendingObservationDates,
    setPendingChangesCount,
    clearPendingObservationDates,
    replaceAllObservations,
  } from '../lib/db.js'
  import { getObservations, saveObservations } from '../lib/api.js'
  import { pendingChanges } from '../stores/ui.js'

  const dispatch = createEventDispatcher()

  let pendingCount = 0
  let pendingDates = []
  let loading = true
  let syncing = false
  let status = ''
  let errorMsg = ''

  function normalizeDate(dateText) {
    const d = new Date(`${dateText}T00:00:00`)
    if (Number.isNaN(d.getTime())) return dateText
    return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`
  }

  async function loadState() {
    loading = true
    const [count, dates] = await Promise.all([getPendingChangesCount(), getPendingObservationDates()])
    pendingCount = count
    pendingDates = dates

    // Fallback for older local state where dates were not tracked yet.
    if (pendingCount > 0 && pendingDates.length === 0) {
      const all = await getAllObservations()
      pendingDates = [...new Set((all || []).map((o) => String(o?.date || '').trim()).filter(Boolean))].sort((a, b) =>
        b.localeCompare(a),
      )
    }

    loading = false
  }

  async function synchronize() {
    if (syncing) return
    syncing = true
    errorMsg = ''
    status = ''

    try {
      if (pendingCount > 0) {
        const localObservations = await getAllObservations()
        await saveObservations(localObservations)
        await setPendingChangesCount(0)
        await clearPendingObservationDates()
        pendingChanges.set(0)
        pendingCount = 0
        pendingDates = []
      }

      const serverObservations = await getObservations()
      await replaceAllObservations(Array.isArray(serverObservations) ? serverObservations : [])
      status = 'Synchronization completed.'
      dispatch('synced')
    } catch (err) {
      errorMsg = err?.message || 'Synchronization failed.'
    } finally {
      syncing = false
    }
  }

  onMount(loadState)
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')}>←</button>
    <span class="header-title">Synchronize Observation Data</span>
  </div>

  <div class="content">
    {#if loading}
      <div class="hint">Loading...</div>
    {:else}
      {#if errorMsg}
        <div class="error-msg">{errorMsg}</div>
      {/if}
      {#if status}
        <div class="ok-msg">{status}</div>
      {/if}

      {#if pendingCount <= 0}
        <div class="hint">No local unsynchronized changes. You can still pull observations from server.</div>
      {:else}
        <div class="summary">Pending changes: {pendingCount}</div>
        <div class="label">Dates to synchronize:</div>
        {#if pendingDates.length === 0}
          <div class="hint small">No tracked dates found.</div>
        {:else}
          <ul class="date-list">
            {#each pendingDates as d}
              <li>{normalizeDate(d)}</li>
            {/each}
          </ul>
        {/if}
      {/if}

      <div class="actions">
        <button class="btn ghost" type="button" on:click={() => dispatch('close')}>Back</button>
        <button class="btn" type="button" on:click={synchronize} disabled={syncing}>
          {syncing ? 'Synchronizing…' : 'Synchronize'}
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 40;
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
    gap: 0.5rem;
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

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.9rem 1rem 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }

  .summary {
    font-size: 0.9rem;
    opacity: 0.85;
  }

  .label {
    font-size: 0.82rem;
    opacity: 0.7;
  }

  .date-list {
    margin: 0;
    padding-left: 1rem;
    font-size: 0.88rem;
    line-height: 1.5;
  }

  .actions {
    display: flex;
    justify-content: flex-start;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .btn {
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.08);
    color: var(--fg);
    padding: 0.45rem 0.85rem;
    cursor: pointer;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .ghost {
    background: transparent;
  }

  .hint {
    color: rgba(255, 255, 255, 0.72);
    font-size: 0.85rem;
  }

  .hint.small {
    font-size: 0.8rem;
    opacity: 0.75;
  }

  .error-msg {
    border: 1px solid rgba(255, 120, 120, 0.5);
    border-radius: 6px;
    padding: 0.5rem 0.6rem;
    color: #ff9a9a;
    font-size: 0.82rem;
  }

  .ok-msg {
    border: 1px solid rgba(160, 180, 255, 0.45);
    border-radius: 6px;
    padding: 0.5rem 0.6rem;
    color: #d3ddff;
    font-size: 0.82rem;
  }
</style>
