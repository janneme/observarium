<script>
  import { createEventDispatcher, onDestroy } from 'svelte'
  import { register, unregister } from '../stores/keyboard.js'

  export let value = ''
  export let placeholder = ''
  export let id = ''

  const dispatch = createEventDispatcher()

  function setValue(v) {
    value = v
    dispatch('input', value)
  }

  let cursor = 0
  let desiredCol = null

  function setCursor(pos) {
    cursor = Math.max(0, Math.min(value.length, pos))
    const { lineIndex, col } = getLineCol(cursor)
    desiredCol = col
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

  function getLineCol(pos) {
    const up = value.slice(0, pos)
    const lines = up.split('\n')
    const lineIndex = lines.length - 1
    const col = lines[lines.length - 1].length
    return { lineIndex, col }
  }

  function moveLeft() { if (cursor > 0) setCursor(cursor - 1) }
  function moveRight() { if (cursor < value.length) setCursor(cursor + 1) }
  function moveUp() {
    const lines = value.split('\n')
    const { lineIndex, col } = getLineCol(cursor)
    if (lineIndex === 0) { setCursor(0); return }
    const targetLine = lines[lineIndex - 1]
    const targetCol = Math.min(desiredCol ?? col, targetLine.length)
    let pos = 0
    for (let i = 0; i < lineIndex - 1; i++) pos += lines[i].length + 1
    pos += targetCol
    setCursor(pos)
  }
  function moveDown() {
    const lines = value.split('\n')
    const { lineIndex, col } = getLineCol(cursor)
    if (lineIndex >= lines.length - 1) { setCursor(value.length); return }
    const targetLine = lines[lineIndex + 1]
    const targetCol = Math.min(desiredCol ?? col, targetLine.length)
    let pos = 0
    for (let i = 0; i <= lineIndex; i++) pos += lines[i].length + 1
    pos += targetCol
    setCursor(pos)
  }

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
  class="custom-textarea"
  on:focus={onFocus}
  on:blur={onBlur}
  role="textbox"
  aria-label="custom textarea"
>
  {#if id}
    <textarea id={id} tabindex="-1" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0;border:0;padding:0;margin:0;">{value}</textarea>
  {/if}

  {#if value.length}
    <pre><span class="before">{value.slice(0,cursor)}</span><span class="caret" aria-hidden="true"></span><span class="after">{value.slice(cursor)}</span></pre>
  {:else}
    <pre class="placeholder">{placeholder}</pre>
  {/if}
</div>

<style>
.custom-textarea {
  min-height: 4rem;
  padding: 0.5rem;
  border: 1px solid rgba(127,127,127,0.08);
  border-radius: 6px;
  white-space: pre-wrap;
  position:relative;
}
.placeholder { opacity: 0.5 }
.caret { display:inline-block; width:2px; height:1em; background:var(--fg); animation: blink 0.8s steps(1) infinite; vertical-align:bottom; border-radius:1px; box-shadow: 0 0 0 1px rgba(0,0,0,0.06) }
@keyframes blink { 50% { opacity: 0 } }
</style>
