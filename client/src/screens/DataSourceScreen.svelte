<script>
  import { createEventDispatcher } from 'svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { setActiveServerUrl, CLOUD_SERVER_URL } from '../lib/api.js'

  // Which backend to fetch the star/DSO catalogue manifest from. Only
  // meaningful in dev (see MainScreen.svelte, which skips straight to the
  // magnitude picker in production) — the local dev server's magnitude sets
  // can differ from the deployed cloud one, so this has to be chosen before
  // the manifest is even fetched, not left to whatever the observation-sync
  // flow last set.
  export let source = 'local'

  const dispatch = createEventDispatcher()

  function choose(next) {
    source = next
    setActiveServerUrl(next === 'cloud' ? CLOUD_SERVER_URL : undefined)
    dispatch('selected', { source: next })
  }

  function handleKey(e) {
    if (e.key === 'Escape') {
      dispatch('close')
      e.preventDefault()
    }
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Update Data</span>
  </div>

  <div class="content">
    <p class="hint">
      The available magnitude sets can differ between backends — choose which one to check for updates against:
    </p>
    <div class="pills">
      <button class="pill" class:selected={source === 'local'} type="button" on:click={() => choose('local')}>
        Local backend
      </button>
      <button class="pill" class:selected={source === 'cloud'} type="button" on:click={() => choose('cloud')}>
        Cloud backend
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
    margin: 0;
    font-size: 0.85rem;
    opacity: 0.72;
    line-height: 1.4;
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
    padding: 0.5rem 1.1rem;
    font-size: 0.9rem;
    cursor: pointer;
  }

  .pill.selected {
    border-color: rgba(46, 119, 255, 0.85);
    background: rgba(46, 119, 255, 0.18);
    font-weight: 600;
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
</style>
