<script>
  import { createEventDispatcher } from 'svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { setActiveServerUrl, CLOUD_SERVER_URL } from '../lib/api.js'
  import { runSync } from '../lib/sync.js'

  export let plan = { categories: [], mode: 'merge', source: 'local' }
  export let report = { localChanges: [], remoteChanges: [] }

  const dispatch = createEventDispatcher()

  let syncing = false
  let errorMsg = ''

  $: hasLocal = plan.mode !== 'overwriteServer' && report.localChanges.length > 0
  $: hasRemote = plan.mode !== 'overwriteLocal' && report.remoteChanges.length > 0
  $: hasAnyChanges = report.localChanges.length > 0 || report.remoteChanges.length > 0

  async function synchronize() {
    if (syncing) return
    errorMsg = ''
    syncing = true
    setActiveServerUrl(plan.source === 'cloud' ? CLOUD_SERVER_URL : undefined)
    try {
      await runSync(plan)
      dispatch('synced')
    } catch (err) {
      errorMsg = err?.message || 'Synchronization failed.'
    } finally {
      syncing = false
    }
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('back')} aria-label="Back">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Review Changes</span>
  </div>

  <div class="content">
    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    {#if !hasAnyChanges}
      <div class="hint">Up to date — nothing to synchronize.</div>
    {:else}
      {#if hasLocal}
        <section class="report-section">
          <div class="report-title">Local changes</div>
          <ul class="bullet-list">
            {#each report.localChanges as line}
              <li>{line}</li>
            {/each}
          </ul>
        </section>
      {/if}

      {#if hasRemote}
        <section class="report-section">
          <div class="report-title">Remote changes</div>
          <ul class="bullet-list">
            {#each report.remoteChanges as line}
              <li>{line}</li>
            {/each}
          </ul>
        </section>
      {/if}
    {/if}

    <div class="footer-actions">
      <button class="btn ghost" type="button" on:click={() => dispatch('back')} disabled={syncing}>Back</button>
      <button class="btn ghost" type="button" on:click={() => dispatch('cancel')} disabled={syncing}>Cancel</button>
      <button class="btn" type="button" on:click={synchronize} disabled={syncing || !hasAnyChanges}>
        {syncing ? 'Synchronizing…' : 'Synchronize'}
      </button>
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
    gap: 0.35rem;
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
    gap: 0.9rem;
  }

  .hint {
    color: rgba(255, 255, 255, 0.72);
    font-size: 0.85rem;
  }

  .report-section {
    border: 1px solid rgba(232, 232, 232, 0.15);
    border-radius: 8px;
    padding: 0.65rem 0.75rem;
  }

  .report-title {
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.85;
    margin-bottom: 0.4rem;
  }

  .bullet-list {
    margin: 0;
    padding-left: 1.1rem;
    font-size: 0.86rem;
    line-height: 1.5;
  }

  .footer-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .btn {
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.08);
    color: var(--fg);
    padding: 0.45rem 0.85rem;
    cursor: pointer;
    font-size: 0.86rem;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .btn.ghost {
    background: none;
  }

  .error-msg {
    border: 1px solid rgba(255, 120, 120, 0.5);
    border-radius: 6px;
    padding: 0.5rem 0.6rem;
    color: #ff9a9a;
    font-size: 0.82rem;
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .report-section {
    border-color: rgba(200, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
    background: rgba(200, 0, 0, 0.06);
  }

  :global([data-theme='nightly']) .btn.ghost {
    background: none;
  }

  :global([data-theme='nightly']) .error-msg {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff9a9a;
  }
</style>
