<script>
  import { theme, toggleTheme } from './stores/theme.js'
  import CustomInput from './components/CustomInput.svelte'
  import CustomTextarea from './components/CustomTextarea.svelte'
  import OnScreenKeyboard from './components/OnScreenKeyboard.svelte'

  let value = ''
  let textareaValue = ''

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
    <div style="margin-top:1rem">
      <label for="custom-input">Custom input demo</label>
      <br />
      <CustomInput id="custom-input" bind:value={value} placeholder="Type with on-screen keyboard" />
    </div>
    <div style="margin-top:1rem">
      <label for="custom-textarea">Custom textarea demo</label>
      <br />
      <CustomTextarea id="custom-textarea" bind:value={textareaValue} placeholder="Multiline" />
    </div>
    <div style="margin-top:1rem">
      <OnScreenKeyboard />
    </div>
  </section>
</main>
