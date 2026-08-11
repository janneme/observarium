<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import { get } from 'svelte/store'
  import { getMeta } from '../lib/db.js'
  import { finderInstrument } from '../stores/ui.js'
  import CustomSelect from './CustomSelect.svelte'
  import BackIcon from '../icons/BackIcon.svelte'

  // 'Save' when opened via the Setup button; 'Telescope view' when opened
  // because the user tapped "Switch to telescope view" with nothing
  // configured yet (see finder_view.md).
  export let primaryLabel = 'Save'

  const dispatch = createEventDispatcher()

  let telescopes = []
  let eyepieces = []

  const current = get(finderInstrument)
  let selectedTelescopeId = current.telescopeId
  let selectedEyepieceId = current.eyepieceId

  $: canSave = !!selectedTelescopeId && !!selectedEyepieceId

  onMount(async () => {
    const [savedTels, savedEps] = await Promise.all([getMeta('telescopes'), getMeta('eyepieces')])
    telescopes = Array.isArray(savedTels)
      ? [...savedTels].sort((a, b) => (a.diameterInches ?? 0) - (b.diameterInches ?? 0))
      : []
    eyepieces = Array.isArray(savedEps)
      ? [...savedEps].sort((a, b) => (b.focalLengthMm ?? 0) - (a.focalLengthMm ?? 0))
      : []
  })

  function handleSave() {
    if (!canSave) return
    finderInstrument.set({ telescopeId: selectedTelescopeId, eyepieceId: selectedEyepieceId })
    dispatch('save')
  }

  function handleCancel() {
    dispatch('cancel')
  }

  function handleKey(e) {
    if (e.key === 'Escape') dispatch('cancel')
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={handleCancel} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Telescope Setup</span>
  </div>

  <div class="body">
    <div class="field-row">
      <span class="field-label">Telescope</span>
      {#if telescopes.length === 0}
        <span class="hint">No telescopes — add one under Telescopes in the menu</span>
      {:else}
        <CustomSelect
          value={selectedTelescopeId}
          options={telescopes.map((t) => ({ value: t.id, label: t.name }))}
          placeholder="Select telescope…"
          on:change={(e) => {
            selectedTelescopeId = e.detail
            selectedEyepieceId = null
          }}
        />
      {/if}
    </div>

    <div class="field-row">
      <span class="field-label">Eyepiece</span>
      {#if eyepieces.length === 0}
        <span class="hint">No eyepieces — add one under Telescopes in the menu</span>
      {:else}
        <CustomSelect
          value={selectedEyepieceId}
          options={eyepieces.map((ep) => ({ value: ep.id, label: ep.name }))}
          placeholder="Select eyepiece…"
          disabled={!selectedTelescopeId}
          on:change={(e) => {
            selectedEyepieceId = e.detail
          }}
        />
      {/if}
    </div>

    <div class="actions">
      <button class="cancel-btn" type="button" on:click={handleCancel}>Cancel</button>
      <button class="begin-btn" disabled={!canSave} on:click={handleSave}>{primaryLabel}</button>
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
    z-index: 40;
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
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .field-label {
    font-size: 0.96rem;
    min-width: 7rem;
    flex-shrink: 0;
  }

  .hint {
    font-size: 0.78rem;
    opacity: 0.5;
    font-style: italic;
  }

  .actions {
    margin-top: 0.5rem;
    display: flex;
    gap: 0.6rem;
    justify-content: center;
  }

  .cancel-btn {
    background: none;
    border: 1px solid rgba(200, 0, 0, 0.3);
    color: var(--fg);
    border-radius: 8px;
    padding: 0.7rem 1.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
  }

  .cancel-btn:hover {
    background: rgba(200, 0, 0, 0.08);
  }

  .begin-btn {
    background: var(--accent, #cc0000);
    border: none;
    color: #000000;
    border-radius: 8px;
    padding: 0.7rem 2rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 120ms;
  }

  .begin-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .begin-btn:hover:not(:disabled) {
    opacity: 0.85;
  }

  :global([data-theme='nightly']) .cancel-btn {
    color: #ff0000;
    border-color: rgba(200, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .begin-btn {
    background: rgba(200, 0, 0, 0.12);
    border: 2px solid var(--accent);
    color: var(--fg);
    font-weight: 700;
    padding: calc(0.7rem - 2px) calc(2rem - 2px);
  }
</style>
