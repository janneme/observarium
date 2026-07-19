<script>
  import { createEventDispatcher } from 'svelte'
  import LoginForm from '../components/LoginForm.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { keyboardActive } from '../stores/keyboard.js'

  const dispatch = createEventDispatcher()
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Log In</span>
  </div>
  <div class="content">
    <LoginForm submitLabel="Log In" on:loggedin={() => dispatch('loggedin')} />
  </div>

  {#if $keyboardActive}
    <OnScreenKeyboard />
  {/if}
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
    gap: 0.7rem;
  }
</style>
