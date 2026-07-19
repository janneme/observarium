<script>
  import { createEventDispatcher } from 'svelte'
  import CustomCheckbox from '../components/CustomCheckbox.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { setActiveServerUrl, CLOUD_SERVER_URL } from '../lib/api.js'
  import { analyzeSync } from '../lib/sync.js'

  export let categories = { observations: true, findingPaths: true, telescopes: true, eyepieces: true }
  export let mode = 'merge'
  export let source = 'local'

  const dispatch = createEventDispatcher()

  const isDev = import.meta.env.DEV

  const CATEGORY_FIELDS = [
    { key: 'observations', label: 'Observations' },
    { key: 'findingPaths', label: 'Finding paths' },
    { key: 'telescopes', label: 'Telescopes' },
    { key: 'eyepieces', label: 'Eyepieces' },
  ]

  const MODE_OPTIONS = [
    { key: 'merge', label: 'Merge' },
    { key: 'overwriteLocal', label: 'Overwrite local' },
    { key: 'overwriteServer', label: 'Overwrite server' },
  ]

  let analyzing = false
  let errorMsg = ''

  function selectedCategoryList() {
    return CATEGORY_FIELDS.filter((f) => categories[f.key]).map((f) => f.key)
  }

  async function analyze() {
    if (analyzing) return
    const list = selectedCategoryList()
    if (list.length === 0) {
      errorMsg = 'Select at least one category to synchronize.'
      return
    }
    errorMsg = ''
    analyzing = true
    setActiveServerUrl(source === 'cloud' ? CLOUD_SERVER_URL : undefined)
    try {
      const report = await analyzeSync({ categories: list, mode })
      dispatch('analyzed', { categories: list, mode, source, report })
    } catch (err) {
      errorMsg = err?.message || 'Could not analyze changes.'
    } finally {
      analyzing = false
    }
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Synchronize</span>
  </div>

  <div class="content">
    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    <section class="section">
      <div class="section-title">Objects to synchronize</div>
      <div class="category-list">
        {#each CATEGORY_FIELDS as field}
          <CustomCheckbox
            label={field.label}
            checked={categories[field.key]}
            on:change={(e) => (categories = { ...categories, [field.key]: e.detail })}
          />
        {/each}
      </div>
    </section>

    <section class="section">
      <div class="section-title">Synchronization mode</div>
      <div class="pills">
        {#each MODE_OPTIONS as opt}
          <button class="pill" class:selected={mode === opt.key} type="button" on:click={() => (mode = opt.key)}>
            {opt.label}
          </button>
        {/each}
      </div>
    </section>

    {#if isDev}
      <section class="section">
        <div class="section-title">Synchronization source</div>
        <div class="pills">
          <button class="pill" class:selected={source === 'local'} type="button" on:click={() => (source = 'local')}>
            Local backend
          </button>
          <button class="pill" class:selected={source === 'cloud'} type="button" on:click={() => (source = 'cloud')}>
            Cloud backend
          </button>
        </div>
      </section>
    {/if}

    <div class="footer-actions">
      <button class="btn ghost" type="button" on:click={() => dispatch('close')}>Cancel</button>
      <button class="btn" type="button" on:click={analyze} disabled={analyzing}>
        {analyzing ? 'Analyzing…' : 'Analyze Changes'}
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

  .section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .section-title {
    font-size: 0.8rem;
    opacity: 0.72;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .category-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .pill {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 999px;
    padding: 0.35rem 0.85rem;
    font-size: 0.82rem;
    cursor: pointer;
  }

  .pill.selected {
    border-color: rgba(46, 119, 255, 0.85);
    background: rgba(46, 119, 255, 0.18);
    font-weight: 600;
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

  :global([data-theme='nightly']) .pill {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .pill.selected {
    border-color: #ff0000;
    background: rgba(200, 0, 0, 0.2);
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
