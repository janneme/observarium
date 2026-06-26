<script>
  import Router, { push } from 'svelte-spa-router'
  import { onMount } from 'svelte'
  import WelcomeScreen from './screens/WelcomeScreen.svelte'
  import MainScreen from './screens/MainScreen.svelte'
  import { hasData } from './lib/db.js'
  import './stores/theme.js'
  import { handleKeyDown, handleKeyUp } from './stores/keyboard.js'

  const routes = {
    '/': WelcomeScreen,
    '/main': MainScreen,
  }

  onMount(async () => {
    const loaded = await hasData()
    if (loaded) {
      push('/main')
    } else {
      push('/')
    }
  })
</script>

<svelte:window on:keydown|capture={handleKeyDown} on:keyup|capture={handleKeyUp} />
<Router {routes} />
