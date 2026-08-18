<script>
  import { createEventDispatcher, onDestroy } from 'svelte'
  import { register, unregister } from '../stores/keyboard.js'

  export let value = ''
  export let placeholder = ''
  export let id = ''
  export let mask = false
  export let outlined = false
  // Real <input> attributes. Only the login form sets these meaningfully
  // (type="password"/autocomplete="current-password" etc.) — every other
  // caller (search boxes, list/telescope names, ...) is fine with the
  // text/off defaults, which keep the browser from offering unrelated
  // autofill suggestions on them.
  export let type = 'text'
  export let name = ''
  export let autocomplete = 'off'

  const dispatch = createEventDispatcher()

  let cursor = 0
  let inputEl
  // True between compositionstart and compositionend, i.e. while an OS-level
  // dead-key/IME sequence (e.g. Czech "Š" via a caron dead key + "s") is in
  // progress on the real native input below. Real keydown is normally
  // blocked entirely (see on:keydown below) since typing goes through
  // insertChar/execCommand instead, but a composing keydown's e.key is only
  // the not-yet-composed base character - blocking it there would insert the
  // wrong plain letter and prevent the compose sequence from ever
  // completing. While composing, keydown is left alone so the browser's
  // native composition can finish on inputEl; the result arrives via the
  // ordinary on:input handler below once compositionend fires.
  let composing = false

  // Fallback path when execCommand is unsupported/fails: a plain scripted
  // .value assignment, which fires no trusted input event at all.
  function setValue(v) {
    value = v
    if (inputEl && inputEl.value !== v) inputEl.value = v
    dispatch('input', value)
  }

  function setCursor(pos) {
    cursor = Math.max(0, Math.min(value.length, pos))
  }

  // Some browsers have historically restricted selectionStart/setSelectionRange
  // on type="password" inputs (a security-motivated quirk, since relaxed in
  // most engines but not worth relying on) — guard against a thrown error
  // there breaking typing entirely.
  function syncNativeSelection() {
    try {
      inputEl?.setSelectionRange(cursor, cursor)
    } catch {
      /* ignore */
    }
  }

  // Insert/delete via execCommand rather than a direct `.value =`
  // assignment — the latter is a silent scripted mutation that fires no
  // input event at all (or, if dispatched manually, only an untrusted one),
  // which browsers' save-password heuristics specifically distrust: it
  // looks identical to a page quietly prefilling the field rather than the
  // user actually typing. execCommand runs through the browser's real
  // text-editing pipeline instead, producing a genuine trusted `input`
  // event — the standard trick custom/virtual-keyboard widgets use to stay
  // compatible with autofill and "save this password?" prompts. Native
  // selection is synced to our own tracked `cursor` first since real
  // keydown is blocked (see the input's on:keydown below), so the browser's
  // own selection state can otherwise drift from ours.
  function insertChar(ch) {
    if (inputEl) {
      inputEl.focus()
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
    if (inputEl) {
      inputEl.focus()
      syncNativeSelection()
      if (document.execCommand && document.execCommand('delete', false)) return
    }
    const before = value.slice(0, cursor)
    const after = value.slice(cursor)
    setValue(before.slice(0, -1) + after)
    setCursor(cursor - 1)
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
    /* no-op for single-line */
  }
  function moveDown() {
    /* no-op for single-line */
  }

  let focused = false

  export function focus() {
    inputEl?.focus()
  }

  function onFocus() {
    focused = true
    register(api)
    setCursor(value.length)
  }

  function onBlur() {
    focused = false
    unregister(api)
  }

  // Real keydown is blocked *except* while composing (see `composing`
  // above) - letting a compose sequence's keydowns through unblocked is
  // what allows the browser to actually finish composing on inputEl.
  // e.key === 'Dead' also covers the dead-key press itself, before
  // `composing` flips true. Native clipboard/select-all shortcuts
  // (Ctrl/Cmd+V/C/X/A) are exempted too - paste in particular only works if
  // the browser gets to run its default action on this keydown; the result
  // lands via the ordinary onNativeInput path below either way. Mirrors
  // stores/keyboard.js's global handler, which exempts the same keys.
  function onKeyDown(e) {
    if (composing || e.key === 'Dead') return
    if ((e.ctrlKey || e.metaKey) && ['v', 'c', 'x', 'a'].includes(e.key.toLowerCase())) return
    e.preventDefault()
  }

  function onCompositionStart() {
    composing = true
  }

  // The composed character(s) are already in inputEl.value by now - the
  // native `input` event that immediately follows compositionend is handled
  // by the ordinary onNativeInput path below, same as any other real input
  // event, so nothing further is needed here beyond clearing the flag.
  function onCompositionEnd() {
    composing = false
  }

  // Real DOM `input` events on the native element — fires for
  // insertChar/backspace's own execCommand calls (see above), for a
  // completed compose sequence (see onCompositionEnd above), and for
  // browser/password-manager autofill, which sets .value directly. Either
  // way, the native element's own value/selection is the source of truth
  // here (autofill has no notion of our tracked `cursor` to preserve, and
  // execCommand/composition already moved the real caret to the right
  // place) — physical keydown typing is otherwise blocked (see the input's
  // on:keydown below), so this never needs to reconcile a real caret
  // against a stale tracked one.
  function onNativeInput() {
    value = inputEl.value
    setCursor(inputEl.selectionStart ?? value.length)
    dispatch('input', value)
  }

  function enter() {
    dispatch('enter')
    inputEl.blur()
  }

  function shiftEnter() {
    dispatch('shiftEnter')
    inputEl.blur()
  }

  function tab() {
    dispatch('tab')
  }

  function shiftTab() {
    dispatch('shiftTab')
  }

  const api = { insertChar, backspace, moveLeft, moveRight, moveUp, moveDown, enter, shiftEnter, tab, shiftTab }

  onDestroy(() => unregister(api))

  $: if (cursor > value.length) cursor = value.length
</script>

<div class="custom-input" class:outlined>
  <!-- The real, focusable field — kept visible-sized and in-place (not
       offscreen) so browsers treat it as a genuine input worth autofilling
       or offering to save (this is what didn't work before: a hidden,
       off-screen input that browsers/password managers ignore). Real
       keystrokes are blocked (preventDefault on keydown) since text entry
       is meant to go through the app's own nightly-safe on-screen keyboard
       only — except while a dead-key/IME compose sequence is in progress,
       which needs the real keydowns to reach the browser to complete (see
       `composing` above) — inputmode="none" additionally tells mobile
       browsers not to pop up their own on-screen keyboard when this gets
       focus. Visually transparent; the decorative spans below are what's
       actually seen. -->
  <input
    bind:this={inputEl}
    {id}
    {type}
    {name}
    {autocomplete}
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
  />

  <div class="display" aria-hidden="true">
    {#if focused}
      {#if value.length}
        {#if mask}
          <span class="before">{'•'.repeat(cursor)}</span><span class="caret"></span><span class="after"
            >{'•'.repeat(value.length - cursor)}</span
          >
        {:else}
          <span class="before">{value.slice(0, cursor)}</span><span class="caret"></span><span class="after"
            >{value.slice(cursor)}</span
          >
        {/if}
      {:else}
        <span class="caret"></span><span class="placeholder">{placeholder}</span>
      {/if}
    {:else if value.length}
      <span>{mask ? '•'.repeat(value.length) : value}</span>
    {:else}
      <span class="placeholder">{placeholder}</span>
    {/if}
  </div>
</div>

<style>
  .custom-input {
    position: relative;
    min-height: 2rem;
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
  .custom-input.outlined {
    border-color: rgba(127, 127, 127, 0.45);
  }
  .custom-input.outlined:focus-within {
    border-color: rgba(127, 127, 127, 0.65);
    box-shadow: 0 0 0 2px rgba(59, 99, 255, 0.25);
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
  }

  .display {
    position: relative;
    width: 100%;
    pointer-events: none;
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
    vertical-align: middle;
    border-radius: 1px;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.06);
  }
  @keyframes blink {
    50% {
      opacity: 0;
    }
  }
</style>
