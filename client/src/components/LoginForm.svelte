<script>
  import { createEventDispatcher } from 'svelte'
  import CustomInput from './CustomInput.svelte'
  import { login } from '../lib/api.js'

  export let submitLabel = 'Log In'

  const dispatch = createEventDispatcher()

  let username = ''
  let password = ''
  let loading = false
  let errorMsg = ''

  async function handleSubmit() {
    if (!username || !password) {
      errorMsg = 'Enter username and password'
      return
    }
    loading = true
    errorMsg = ''
    try {
      await login(username, password)
      dispatch('loggedin')
    } catch (err) {
      errorMsg = err.message || 'Login failed'
    } finally {
      loading = false
    }
  }
</script>

<div class="login-form">
  <label for="lf-username">Username</label>
  <CustomInput id="lf-username" bind:value={username} placeholder="username" />

  <label for="lf-password">Password</label>
  <CustomInput id="lf-password" bind:value={password} placeholder="password" mask={true} />

  {#if errorMsg}
    <div class="error-msg">{errorMsg}</div>
  {/if}

  <button class="submit-btn" type="button" on:click={handleSubmit} disabled={loading}>
    {loading ? 'Logging in…' : submitLabel}
  </button>
</div>

<style>
  .login-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  label {
    font-size: 0.8rem;
    opacity: 0.7;
    margin-bottom: -0.25rem;
  }

  .error-msg {
    font-size: 0.82rem;
    color: #ff9a9a;
    padding: 0.15rem 0;
  }

  .submit-btn {
    margin-top: 0.25rem;
    padding: 0.45rem 0.85rem;
    font-size: 0.9rem;
    cursor: pointer;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.25);
    background: rgba(255, 255, 255, 0.08);
    color: var(--fg);
    align-self: flex-start;
  }

  .submit-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
