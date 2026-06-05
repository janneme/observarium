<script>
  import { theme, toggleTheme } from './stores/theme.js'

  // Use the $store auto-subscription for Svelte reactivity
  $: current = $theme
</script>

<main>
  <header>
    <h1>Observarium</h1>
    <button on:click={toggleTheme}>Toggle Theme</button>
  </header>

  <section class="hero">
    <p>Simple client scaffold. Theme: {current}</p>
  </section>
</main>
