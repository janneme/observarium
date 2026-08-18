<script>
  import { createEventDispatcher, onDestroy } from 'svelte'
  import { register, unregister } from '../stores/keyboard.js'

  export let value = ''
  export let placeholder = ''
  export let id = ''

  const dispatch = createEventDispatcher()

  let cursor = 0
  let desiredCol = null
  let taEl
  // True between compositionstart and compositionend, i.e. while an OS-level
  // dead-key/IME sequence (e.g. Czech "Š" via a caron dead key + "s") is in
  // progress on the real native textarea below - see CustomInput.svelte,
  // which this mirrors, for the full rationale.
  let composing = false

  // Fallback path when execCommand is unsupported/fails: a plain scripted
  // .value assignment, which fires no trusted input event at all.
  function setValue(v) {
    value = v
    if (taEl && taEl.value !== v) taEl.value = v
    dispatch('input', value)
  }

  function setCursor(pos) {
    cursor = Math.max(0, Math.min(value.length, pos))
    const { col } = getLineCol(cursor)
    desiredCol = col
  }

  // Some browsers have historically restricted selectionStart/setSelectionRange
  // on certain input types (see CustomInput.svelte) - guard against a thrown
  // error there breaking typing entirely.
  function syncNativeSelection() {
    try {
      taEl?.setSelectionRange(cursor, cursor)
    } catch {
      /* ignore */
    }
  }

  // Insert/delete via execCommand rather than a direct `.value =` assignment
  // - see CustomInput.svelte's insertChar for the full rationale (trusted
  // input events for autofill/password-manager compatibility, and this is
  // also what lets dead-key/IME composition work at all: execCommand runs
  // through the browser's real text-editing pipeline on a genuinely focused
  // native element, the same element real keydowns compose into).
  function insertChar(ch) {
    if (taEl) {
      taEl.focus()
      syncNativeSelection()
      if (document.execCommand && document.execCommand('insertText', false, ch)) return
    }
    const before = value.slice(0, cursor)
    const after = value.slice(cursor)
    setValue(before + ch + after)
    setCursor(cursor + ch.length)
  }

  function backspace() {
    if (cursor === 0) return
    if (taEl) {
      taEl.focus()
      syncNativeSelection()
      if (document.execCommand && document.execCommand('delete', false)) return
    }
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

  function moveLeft() {
    if (cursor > 0) setCursor(cursor - 1)
    syncNativeSelection()
  }
  function moveRight() {
    if (cursor < value.length) setCursor(cursor + 1)
    syncNativeSelection()
  }
  function moveUp() {
    const lines = value.split('\n')
    const { lineIndex, col } = getLineCol(cursor)
    if (lineIndex === 0) {
      setCursor(0)
      syncNativeSelection()
      return
    }
    const targetLine = lines[lineIndex - 1]
    const targetCol = Math.min(desiredCol ?? col, targetLine.length)
    let pos = 0
    for (let i = 0; i < lineIndex - 1; i++) pos += lines[i].length + 1
    pos += targetCol
    setCursor(pos)
    syncNativeSelection()
  }
  function moveDown() {
    const lines = value.split('\n')
    const { lineIndex, col } = getLineCol(cursor)
    if (lineIndex >= lines.length - 1) {
      setCursor(value.length)
      syncNativeSelection()
      return
    }
    const targetLine = lines[lineIndex + 1]
    const targetCol = Math.min(desiredCol ?? col, targetLine.length)
    let pos = 0
    for (let i = 0; i <= lineIndex; i++) pos += lines[i].length + 1
    pos += targetCol
    setCursor(pos)
    syncNativeSelection()
  }

  let focused = false

  function onFocus() {
    focused = true
    register(api)
    setCursor(value.length)
  }

  function onBlur() {
    focused = false
    unregister(api)
  }

  function enter() {
    insertChar('\n')
  }

  const api = { insertChar, backspace, moveLeft, moveRight, moveUp, moveDown, enter }

  onDestroy(() => unregister(api))

  $: if (cursor > value.length) cursor = value.length

  // Real keydown is blocked *except* while composing - see CustomInput.svelte
  // for the full rationale (letting a compose sequence's keydowns through
  // unblocked is what allows the browser to actually finish composing on
  // taEl; e.key === 'Dead' also covers the dead-key press itself, before
  // `composing` flips true) - and except for native clipboard/select-all
  // shortcuts (Ctrl/Cmd+V/C/X/A), which likewise only work if the browser
  // gets to run its default action on the keydown.
  function onKeyDown(e) {
    if (composing || e.key === 'Dead') return
    if ((e.ctrlKey || e.metaKey) && ['v', 'c', 'x', 'a'].includes(e.key.toLowerCase())) return
    e.preventDefault()
  }

  function onCompositionStart() {
    composing = true
  }

  // The composed character(s) are already in taEl.value by now - the native
  // `input` event that immediately follows compositionend is handled by the
  // ordinary onNativeInput path below, same as any other real input event,
  // so nothing further is needed here beyond clearing the flag.
  function onCompositionEnd() {
    composing = false
  }

  // Real DOM `input` events on the native element — fires for
  // insertChar/backspace's own execCommand calls (see above), for a
  // completed compose sequence (see onCompositionEnd above), and for
  // browser autofill. Either way, the native element's own value/selection
  // is the source of truth here — physical keydown typing is otherwise
  // blocked (see the textarea's on:keydown below), so this never needs to
  // reconcile a real caret against a stale tracked one.
  function onNativeInput() {
    value = taEl.value
    setCursor(taEl.selectionStart ?? value.length)
    dispatch('input', value)
  }
</script>

<div class="custom-input custom-textarea">
  <!-- The real, focusable field — kept visible-sized and in-place (not
       offscreen), same rationale as CustomInput.svelte's native input.
       Real keystrokes are blocked (preventDefault on keydown) since text
       entry is meant to go through the app's own nightly-safe on-screen
       keyboard only — except while a dead-key/IME compose sequence is in
       progress, which needs the real keydowns to reach the browser to
       complete (see `composing` above) — inputmode="none" additionally
       tells mobile browsers not to pop up their own on-screen keyboard when
       this gets focus. Visually transparent; the decorative <pre> blocks
       below are what's actually seen. -->
  <textarea
    bind:this={taEl}
    {id}
    inputmode="none"
    class="native-input"
    aria-label={id ? undefined : placeholder || undefined}
    {value}
    on:focus={onFocus}
    on:blur={onBlur}
    on:input={onNativeInput}
    on:keydown={onKeyDown}
    on:compositionstart={onCompositionStart}
    on:compositionend={onCompositionEnd}
  ></textarea>

  <div class="display" aria-hidden="true">
    {#if focused}
      {#if value.length}
        <pre><span class="before">{value.slice(0, cursor)}</span><span class="caret"></span><span class="after"
            >{value.slice(cursor)}</span
          ></pre>
      {:else}
        <pre><span class="caret"></span><span class="placeholder">{placeholder}</span></pre>
      {/if}
    {:else if value.length}
      <pre>{value}</pre>
    {:else}
      <pre class="placeholder">{placeholder}</pre>
    {/if}
  </div>
</div>

<style>
  .custom-input {
    position: relative;
    padding: 0.25rem 0.5rem;
    border: 1px solid rgba(127, 127, 127, 0.08);
    border-radius: 4px;
    font-size: 1.2rem;
    font-family: monospace;
    display: flex;
    align-items: center;
  }
  .custom-input:focus-within {
    box-shadow: 0 0 0 2px rgba(59, 99, 255, 0.06);
  }
  :global([data-theme='nightly']) .custom-input:focus-within {
    box-shadow: 0 0 0 2px rgba(200, 0, 0, 0.25);
  }

  .custom-textarea {
    min-height: calc(2 * 1.25em + 0.24rem);
    padding: 0.12rem 0.5rem;
    border-radius: 6px;
    white-space: pre-wrap;
  }

  .native-input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    border: none;
    outline: none;
    background: transparent;
    color: transparent;
    caret-color: transparent;
    font: inherit;
    opacity: 0;
    resize: none;
    white-space: pre-wrap;
  }

  .display {
    position: relative;
    width: 100%;
    pointer-events: none;
  }

  .display pre {
    margin: 0;
    line-height: 1.25;
    white-space: pre-wrap;
    width: 100%;
    font: inherit;
  }

  .placeholder {
    opacity: 0.5;
  }
  .caret {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: var(--fg);
    animation: blink 0.8s steps(1) infinite;
    vertical-align: bottom;
    border-radius: 1px;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.06);
  }
  @keyframes blink {
    50% {
      opacity: 0;
    }
  }

  :global([data-theme='nightly']) .custom-textarea {
    border-color: rgba(200, 0, 0, 0.35);
    background: rgba(200, 0, 0, 0.04);
  }
</style>
