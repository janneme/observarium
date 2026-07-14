<script>
  import {
    insertChar,
    backspace,
    moveLeft,
    moveRight,
    moveUp,
    moveDown,
    enter,
    pressedKey,
    hwShift,
    hwCapsLock,
  } from '../stores/keyboard.js'
  import { onMount, onDestroy, tick } from 'svelte'

  let layout = 'en' // 'en' or 'cz'

  const en = {
    unshifted: [
      ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '='],
      ['q', 'w', 'e', 'r', 't', 'z', 'u', 'i', 'o', 'p', '[', ']', 'ENTER'],
      ['CAPS', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"],
      ['SHIFT', 'y', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/', 'SHIFT'],
    ],
    shifted: [
      ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '_', '+'],
      ['Q', 'W', 'E', 'R', 'T', 'Z', 'U', 'I', 'O', 'P', '{', '}', 'ENTER'],
      ['CAPS', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ':', '"'],
      ['SHIFT', 'Y', 'X', 'C', 'V', 'B', 'N', 'M', '<', '>', 'SHIFT'],
    ],
  }

  // Keep QWERTY order for both layouts; top row (number row) differs per layout
  // CZ layout: explicit unshifted and shifted rows per user specification
  const cz = {
    unshifted: [
      ['+', 'ě', 'š', 'č', 'ř', 'ž', 'ý', 'á', 'í', 'é', '=', "'"],
      ['q', 'w', 'e', 'r', 't', 'z', 'u', 'i', 'o', 'p', 'ú', ')', 'ENTER'],
      ['CAPS', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'ů', '§'],
      ['SHIFT', 'y', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '-', 'SHIFT'],
    ],
    shifted: [
      ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '%', 'ˇ'],
      ['Q', 'W', 'E', 'R', 'T', 'Z', 'U', 'I', 'O', 'P', '/', '(', 'ENTER'],
      ['CAPS', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', '"', '!'],
      ['SHIFT', 'Y', 'X', 'C', 'V', 'B', 'N', 'M', '? ', ':', '_', 'SHIFT'],
    ],
  }

  let shift = false
  let capsLock = false
  let deadActive = false
  let deadAccent = null // 'acute' | 'caron'
  let deadKeySymbol = ''
  const acuteMap = {
    a: 'á',
    e: 'é',
    i: 'í',
    o: 'ó',
    u: 'ú',
  }
  const caronMap = {
    c: 'č',
    d: 'ď',
    e: 'ě',
    n: 'ň',
    r: 'ř',
    s: 'š',
    t: 'ť',
    z: 'ž',
  }

  function displayKey(k) {
    if (k === 'SHIFT') return '⇧'
    if (k === 'ENTER') return '⏎'
    if (k === 'BACKSPACE') return '⌫'
    if (k === 'CAPS') return '⇪'
    if (k === 'LEFT') return '←'
    if (k === 'RIGHT') return '→'
    if (k === 'UP') return '↑'
    if (k === 'DOWN') return '↓'
    return k
  }

  function press(k) {
    // Handle special keys
    if (k === 'BACKSPACE') {
      backspace()
      return
    }
    if (k === 'ENTER' || k === '\n') {
      enter()
      if (shift) shift = false
      return
    }
    if (k === 'SHIFT') {
      toggleShift()
      return
    }
    if (k === 'CAPS') {
      capsLock = !capsLock
      return
    }

    // detect dead-accent key (apostrophe / caron on CZ top row)
    if (layout === 'cz' && (k === "'" || k === 'ˇ')) {
      deadActive = true
      deadAccent = k === 'ˇ' || shift ? 'caron' : 'acute'
      deadKeySymbol = k
      return
    }

    // If a dead accent is active, attempt composition for a broader set
    if (deadActive) {
      const base = k.length === 1 ? k : ''
      const lower = base.toLowerCase()
      let composedLower = null
      if (deadAccent === 'acute') composedLower = acuteMap[lower]
      else composedLower = caronMap[lower]

      const usedAccent = deadAccent
      deadActive = false
      deadAccent = null
      deadKeySymbol = ''

      if (composedLower) {
        const composed = base === lower ? composedLower : composedLower.toUpperCase()
        insertChar(composed)
        if (shift && k.length === 1) shift = false
        return
      }

      // fallback: insert the dead accent symbol then continue
      const deadSymbol = usedAccent === 'caron' ? 'ˇ' : "'"
      insertChar(deadSymbol)
      // continue to insert the current key as normal below
    }

    // For CZ use the label as provided (rows already reflect shift state when rendering)
    // For EN fallback: apply uppercase when shift or capsLock is active and key is a single letter
    let out = k
    if (layout === 'en' && (shift || capsLock) && k.length === 1) out = k.toUpperCase()

    insertChar(out)
    // one-time shift: clear after a normal key press; small delay lets :active CSS show before re-render
    if (shift && k.length === 1)
      setTimeout(() => {
        shift = false
      }, 80)
  }
  function back() {
    backspace()
  }
  function left() {
    moveLeft && moveLeft()
  }
  function right() {
    moveRight && moveRight()
  }
  function up() {
    moveUp && moveUp()
  }
  function down() {
    moveDown && moveDown()
  }

  function toggleLayout() {
    layout = layout === 'en' ? 'cz' : 'en'
  }
  function toggleShift() {
    shift = !shift
  }

  $: effectiveShift = shift || $hwShift
  $: effectiveCaps = capsLock || $hwCapsLock

  // `rows` should exclude the top (digits/diacritics) row which is rendered separately
  $: rows =
    layout === 'en'
      ? effectiveShift || effectiveCaps
        ? en.shifted.slice(1)
        : en.unshifted.slice(1)
      : effectiveShift || effectiveCaps
        ? cz.shifted.slice(1)
        : cz.unshifted.slice(1)

  // keep keyboard focus-friendly
  let mounted = false
  let kbEl
  let ro

  async function computeKeyWidths() {
    await tick()
    if (!kbEl) return
    const rows = Array.from(kbEl.querySelectorAll('.row'))
    if (!rows.length) return

    // compute container width and maximum number of non-space keys in any row
    const containerWidth = kbEl.clientWidth
    let maxCount = 0
    for (const row of rows) {
      const keys = Array.from(row.querySelectorAll('.key')).filter((k) => !k.classList.contains('space'))
      if (keys.length > maxCount) maxCount = keys.length
    }
    if (maxCount <= 0) return

    // compute gap (px) from computed style of a row
    const style = getComputedStyle(rows[0])
    const gap = parseFloat(style.gap) || 0

    // calculate per-key width so maxCount keys + gaps fill the container
    const totalGaps = gap * (maxCount - 1)
    const keyWidth = Math.floor((containerWidth - totalGaps) / maxCount)

    const fixedKeys = Array.from(kbEl.querySelectorAll('.key:not(.space)'))
    fixedKeys.forEach((k) => {
      const w = keyWidth + 'px'
      k.style.boxSizing = 'border-box'
      k.style.width = w
      k.style.minWidth = w
      k.style.maxWidth = w
      k.style.flex = '0 0 ' + w
    })
    // ensure space remains flexible
    const spaceKeys = Array.from(kbEl.querySelectorAll('.key.space'))
    spaceKeys.forEach((s) => {
      s.style.boxSizing = 'border-box'
      s.style.width = ''
      s.style.minWidth = ''
      s.style.maxWidth = ''
      s.style.flex = '1 1 0'
    })
  }

  onMount(() => {
    mounted = true
    computeKeyWidths()
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(computeKeyWidths)
      ro.observe(kbEl)
    } else {
      window.addEventListener('resize', computeKeyWidths)
    }
  })

  onDestroy(() => {
    if (ro) ro.disconnect()
    else window.removeEventListener('resize', computeKeyWidths)
  })

  // Recompute widths when layout/shift/capsLock change (rows acts as proxy for all three)
  $: if (rows && mounted) computeKeyWidths()
</script>

<div
  bind:this={kbEl}
  class="kb"
  class:caps={capsLock}
  class:shift
  aria-hidden="false"
  role="application"
  aria-label="On-screen keyboard"
>
  <div class="row digits">
    {#if layout === 'en'}
      {#each effectiveShift || effectiveCaps ? en.shifted[0] : en.unshifted[0] as d}
        <button
          class="key flex"
          data-key={d}
          type="button"
          class:dead-active={deadKeySymbol === d}
          class:hw-active={$pressedKey === d}
          on:pointerdown|preventDefault={() => press(d)}>{displayKey(d)}</button
        >
      {/each}
    {:else}
      {#each effectiveShift || effectiveCaps ? cz.shifted[0] : cz.unshifted[0] as d}
        <button
          class="key flex"
          data-key={d}
          type="button"
          class:dead-active={deadKeySymbol === d}
          class:hw-active={$pressedKey === d}
          on:pointerdown|preventDefault={() => press(d)}>{displayKey(d)}</button
        >
      {/each}
    {/if}
    <button
      class="key flex"
      data-key="BACKSPACE"
      type="button"
      class:dead-active={deadKeySymbol === 'BACKSPACE'}
      class:hw-active={$pressedKey === 'BACKSPACE'}
      on:pointerdown|preventDefault={back}>{displayKey('BACKSPACE')}</button
    >
  </div>

  {#each rows as r}
    <div class="row">
      {#each r as k}
        <button
          class="key flex"
          data-key={k}
          type="button"
          class:dead-active={deadKeySymbol === k}
          class:hw-active={$pressedKey === k}
          class:key-toggled={(k === 'SHIFT' && effectiveShift) || (k === 'CAPS' && effectiveCaps)}
          on:pointerdown|preventDefault={() => press(k)}>{displayKey(k)}</button
        >
      {/each}
    </div>
  {/each}

  <div class="row bottom">
    <button
      class="key small lang"
      data-key="LANG"
      type="button"
      class:dead-active={deadKeySymbol === 'LANG'}
      on:pointerdown|preventDefault={toggleLayout}
      aria-label="Language">{layout.toUpperCase()}</button
    >
    <button
      class="key small"
      data-key="LEFT"
      type="button"
      class:dead-active={deadKeySymbol === 'LEFT'}
      class:hw-active={$pressedKey === 'LEFT'}
      on:pointerdown|preventDefault={left}>{displayKey('LEFT')}</button
    >
    <button
      class="key small"
      data-key="UP"
      type="button"
      class:dead-active={deadKeySymbol === 'UP'}
      class:hw-active={$pressedKey === 'UP'}
      on:pointerdown|preventDefault={up}>{displayKey('UP')}</button
    >
    <button
      class="key space"
      data-key="SPACE"
      type="button"
      class:dead-active={deadKeySymbol === 'SPACE'}
      class:hw-active={$pressedKey === 'SPACE'}
      on:pointerdown|preventDefault={() => press(' ')}
      aria-label="Space"
    ></button>
    <button
      class="key small"
      data-key="DOWN"
      type="button"
      class:dead-active={deadKeySymbol === 'DOWN'}
      class:hw-active={$pressedKey === 'DOWN'}
      on:pointerdown|preventDefault={down}>{displayKey('DOWN')}</button
    >
    <button
      class="key small"
      data-key="RIGHT"
      type="button"
      class:dead-active={deadKeySymbol === 'RIGHT'}
      class:hw-active={$pressedKey === 'RIGHT'}
      on:pointerdown|preventDefault={right}>{displayKey('RIGHT')}</button
    >
  </div>
</div>

<style>
  .kb {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    width: 100%;
    margin: 0 auto;
    box-sizing: border-box;
  }
  .row {
    display: flex;
    gap: 0.35rem;
    justify-content: stretch;
    align-items: center;
  }
  .digits {
    justify-content: flex-start;
  }
  .key {
    padding: 0.45rem 0.65rem;
    background: var(--key-bg, rgba(255, 255, 255, 0.02));
    border-radius: 6px;
    color: var(--fg);
    border: 1px solid rgba(127, 127, 127, 0.18);
    box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
    min-width: 36px;
    text-align: center;
    box-sizing: border-box;
  }
  .key {
    padding: 0.28rem 0.5rem;
    background: var(--key-bg, rgba(255, 255, 255, 0.02));
    border-radius: 6px;
    color: var(--fg);
    border: 1px solid var(--fg);
    box-shadow: 0 2px 0 rgba(0, 0, 0, 0.08);
    min-width: 36px;
    text-align: center;
    box-sizing: border-box;
    transition:
      transform 80ms ease,
      filter 120ms ease;
    display: flex;
    align-items: center;
    justify-content: center;
    height: clamp(36px, 6vw, 56px);
    font-size: 1.05rem;
  }
  .key:active,
  .key.hw-active {
    transform: translateY(1px) scale(0.995);
    background: var(--fg);
    color: var(--bg);
    border-color: var(--bg);
  }
  .key.small {
    padding: 0.28rem 0.5rem;
    min-width: 36px;
    flex: 1 1 0;
    max-width: 64px;
    font-size: 1.05rem;
  }
  /* use a clamped height so keys remain visually balanced; flex distributes width evenly */
  .key.flex {
    flex: 1 1 0;
    min-width: 0;
  }
  .key.space {
    flex: 3 1 0;
    min-width: 0;
  }
  /* persistent highlight for SHIFT (when active) and CAPS (when locked) */
  .key.key-toggled {
    background: var(--fg);
    color: var(--bg);
    border-color: var(--bg);
  }
  .key.key-toggled:active {
    background: var(--bg);
    color: var(--fg);
    border-color: var(--fg);
  }
  .key.dead-active {
    background: var(--fg);
    color: var(--bg);
    border-color: var(--bg);
  }
  .key.dead-active:active {
    background: var(--bg);
    color: var(--fg);
    border-color: var(--fg);
  }
  /* bottom row sizing: allow space to expand, other keys use .small */
  /* slightly larger borders on hover for clarity */
  .key:hover {
    border-color: var(--fg);
  }
  /* ensure keys don't become too tall on narrow screens */
  @media (max-width: 520px) {
    .key.flex {
      aspect-ratio: 1.4;
    }
    .key.small {
      padding: 0.18rem 0.28rem;
    }
  }

  :global([data-theme='nightly']) .key {
    color: #ff0000;
    border-color: rgba(200, 0, 0, 0.5);
    background: rgba(80, 0, 0, 0.55);
  }
  :global([data-theme='nightly']) .key:hover {
    border-color: #ff0000;
  }
  :global([data-theme='nightly']) .key:active,
  :global([data-theme='nightly']) .key.hw-active {
    background: #880000;
    color: #000;
    border-color: #000;
  }
  :global([data-theme='nightly']) .key.key-toggled {
    background: #880000;
    color: #000;
    border-color: #000;
  }
  :global([data-theme='nightly']) .key.key-toggled:active {
    background: rgba(80, 0, 0, 0.55);
    color: #ff0000;
    border-color: rgba(200, 0, 0, 0.5);
  }
  :global([data-theme='nightly']) .key.dead-active {
    background: #880000;
    color: #000;
    border-color: #000;
  }
  :global([data-theme='nightly']) .key.dead-active:active {
    background: rgba(80, 0, 0, 0.55);
    color: #ff0000;
    border-color: rgba(200, 0, 0, 0.5);
  }
</style>
