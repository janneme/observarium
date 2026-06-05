<script>
  import { createEventDispatcher, onDestroy } from 'svelte'
  import { register, unregister } from '../stores/keyboard.js'

  export let value = ''
  export let placeholder = ''
  export let id = ''

  const dispatch = createEventDispatcher()

  let cursor = 0

  function setValue(v) {
    value = v
    dispatch('input', value)
  }

  function setCursor(pos) {
    cursor = Math.max(0, Math.min(value.length, pos))
  }

  function insertChar(ch) {
    const before = value.slice(0, cursor)
    const after = value.slice(cursor)
    setValue(before + ch + after)
    setCursor(cursor + ch.length)
  }

  function backspace() {
    if (cursor === 0) return
    const before = value.slice(0, cursor)
    const after = value.slice(cursor)
    setValue(before.slice(0, -1) + after)
    setCursor(cursor - 1)
  }

  function moveLeft() { if (cursor > 0) setCursor(cursor - 1) }
  function moveRight() { if (cursor < value.length) setCursor(cursor + 1) }
  function moveUp() { /* no-op for single-line */ }
  function moveDown() { /* no-op for single-line */ }

  let el

  function onFocus() {
    register(api)
    setCursor(value.length)
  }

  function onBlur() {
    unregister(api)
  }

  const api = { insertChar, backspace, moveLeft, moveRight, moveUp, moveDown }

  onDestroy(() => unregister(api))

  $: if (cursor > value.length) cursor = value.length
</script>

<div
  bind:this={el}
  tabindex="0"
  class="custom-input"
  on:focus={onFocus}
  on:blur={onBlur}
  role="textbox"
  aria-label="custom input"
>
  <!-- hidden native input so <label for="..."> associates correctly -->
  {#if id}
    <input id={id} value={value} tabindex="-1" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0;border:0;padding:0;margin:0;" />
  {/if}

  {#if value.length}
    <span class="before">{value.slice(0,cursor)}</span><span class="caret" aria-hidden="true"></span><span class="after">{value.slice(cursor)}</span>
  {:else}
    <span class="placeholder">{placeholder}</span>
  {/if}
</div>

<style>
.custom-input {
  min-height: 2rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid rgba(127,127,127,0.08);
  border-radius: 4px;
  outline: none;
}
.custom-input:focus {
  box-shadow: 0 0 0 2px rgba(59,99,255,0.06);
}
.placeholder { opacity: 0.5 }
.caret { display:inline-block; width:2px; height:1em; background:var(--fg); animation: blink 0.8s steps(1) infinite; vertical-align:middle; border-radius:1px; box-shadow: 0 0 0 1px rgba(0,0,0,0.06) }
@keyframes blink { 50% { opacity: 0 } }
</style>
