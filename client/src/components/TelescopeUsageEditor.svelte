<script>
  export let telescopes = []
  export let eyepieces = []
  export let telescopeStates = []
  export let telescopeNeedsEyepiece = () => false
  export let onToggleTelescope = () => {}
  export let onToggleEyepiece = () => {}
  export let emptyTelescopesHint = 'No telescopes defined yet.'
  export let emptyEyepiecesHint = 'No options defined. Add options in the Telescopes screen.'
  let stateByTelescopeId = new Map()

  $: stateByTelescopeId = new Map(
    (Array.isArray(telescopeStates) ? telescopeStates : []).map((s) => [s.telescopeId, s]),
  )

  function stateFor(telescopeId) {
    return stateByTelescopeId.get(telescopeId) || null
  }

  function onTelescopePress(telescopeId, event) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
    onToggleTelescope(telescopeId)
  }

  function onEyepiecePress(telescopeId, eyepieceId, event) {
    event?.preventDefault?.()
    event?.stopPropagation?.()
    onToggleEyepiece(telescopeId, eyepieceId)
  }

  function onTelescopeClick(telescopeId, event) {
    if ((event?.detail || 0) > 0) return
    onTelescopePress(telescopeId, event)
  }

  function onEyepieceClick(telescopeId, eyepieceId, event) {
    if ((event?.detail || 0) > 0) return
    onEyepiecePress(telescopeId, eyepieceId, event)
  }

  function shouldShowEyepieces(telescope) {
    const state = stateFor(telescope.id)
    return telescopeNeedsEyepiece(telescope) && state?.seen === true
  }
</script>

{#if telescopes.length === 0}
  <div class="hint">{emptyTelescopesHint}</div>
{:else}
  <div class="telescope-list">
    {#each telescopes as telescope}
      {@const state = stateFor(telescope.id)}
      <button
        class="chip telescope-chip"
        class:active={state?.seen === true}
        type="button"
        aria-pressed={state?.seen === true}
        on:pointerup={(e) => onTelescopePress(telescope.id, e)}
        on:click={(e) => onTelescopeClick(telescope.id, e)}
        title="Toggle telescope usage"
      >
        <div class="name">{telescope.name}</div>
        <div class="meta">{telescope.focalLengthMm} mm · {telescope.diameterInches}"</div>
      </button>
      {#if shouldShowEyepieces(telescope)}
        <div class="eyepieces">
          {#if eyepieces.length === 0}
            <div class="hint small">{emptyEyepiecesHint}</div>
          {:else}
            {#each eyepieces as eyepiece}
              <button
                class="chip"
                class:active={state.eyepieceIds?.includes(eyepiece.id)}
                type="button"
                on:pointerup={(e) => onEyepiecePress(telescope.id, eyepiece.id, e)}
                on:click={(e) => onEyepieceClick(telescope.id, eyepiece.id, e)}
              >
                {eyepiece.name}
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .telescope-list {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .name {
    font-size: 0.8rem;
    font-weight: 600;
  }

  .meta {
    font-size: 0.72rem;
    opacity: 0.7;
  }

  .eyepieces {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-top: 0.1rem;
    margin-bottom: 0.15rem;
  }

  .chip {
    border: 1px solid rgba(232, 232, 232, 0.35);
    border-radius: 999px;
    background: none;
    color: var(--fg);
    font-size: 0.74rem;
    padding: 0.18rem 0.48rem;
    cursor: pointer;
    -webkit-tap-highlight-color: rgba(80, 150, 255, 0.2);
  }

  .chip.active {
    border-color: rgba(80, 150, 255, 0.75);
    background: rgba(80, 150, 255, 0.14);
  }

  .chip.telescope-chip {
    width: 100%;
    text-align: left;
    border-radius: 0;
  }

  .chip:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px rgba(80, 150, 255, 0.35);
  }

  .hint {
    font-size: 0.82rem;
    opacity: 0.7;
  }

  .hint.small {
    font-size: 0.78rem;
  }

  :global([data-theme='nightly']) .chip {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .chip.active {
    border-color: #ff0000;
    background: rgba(200, 0, 0, 0.2);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .chip:focus-visible {
    box-shadow: 0 0 0 2px rgba(200, 0, 0, 0.35);
  }
</style>
