import { writable, get, derived } from 'svelte/store'

export const pressedKey = writable(null)
let _pressedKeyTimer = null

function flashKey(label) {
  pressedKey.set(label)
  if (_pressedKeyTimer) clearTimeout(_pressedKeyTimer)
  _pressedKeyTimer = setTimeout(() => pressedKey.set(null), 150)
}

// Hardware modifier key state — used by OnScreenKeyboard to mirror HW Shift/CapsLock
export const hwShift = writable(false)
export const hwCapsLock = writable(false)

export function handleKeyUp(e) {
  if (e.key === 'Shift') hwShift.set(false)
}

// The current focused input target. It should be an object implementing
// insertChar(ch) and backspace() methods.
const _current = writable(null)

// True when any input has keyboard focus — use to show/hide OnScreenKeyboard.
export const keyboardActive = derived(_current, ($c) => $c !== null)

export function register(target) {
  _current.set(target)
}

export function unregister(target) {
  // clear only if the same target
  const cur = get(_current)
  if (cur === target) _current.set(null)
}

export function insertChar(ch) {
  const cur = get(_current)
  if (cur && typeof cur.insertChar === 'function') cur.insertChar(ch)
}

export function backspace() {
  const cur = get(_current)
  if (cur && typeof cur.backspace === 'function') cur.backspace()
}

export function moveLeft() {
  const cur = get(_current)
  if (cur && typeof cur.moveLeft === 'function') cur.moveLeft()
}

export function moveRight() {
  const cur = get(_current)
  if (cur && typeof cur.moveRight === 'function') cur.moveRight()
}

export function moveUp() {
  const cur = get(_current)
  if (cur && typeof cur.moveUp === 'function') cur.moveUp()
}

export function moveDown() {
  const cur = get(_current)
  if (cur && typeof cur.moveDown === 'function') cur.moveDown()
}

export function enter() {
  const cur = get(_current)
  if (!cur) return
  if (typeof cur.enter === 'function') cur.enter()
  else if (typeof cur.insertChar === 'function') cur.insertChar('\n')
}

export function clearTarget() {
  _current.set(null)
}

export function handleKeyDown(e) {
  const cur = get(_current)

  // Global rule: when custom keyboard is active, consume all key strokes here.
  // Esc closes the keyboard only.
  if (cur) {
    // Let an OS-level dead-key/IME compose sequence run its course (e.g.
    // Czech "Š" via a caron dead key + "s") - a composing keydown's e.key is
    // only the not-yet-composed base character, so intercepting it here and
    // then blocking the event (as below) would insert the wrong plain
    // letter and kill the sequence before the real character is produced.
    // Do nothing at all - no preventDefault, no insertChar - so the event
    // reaches the focused element and the browser can finish composing;
    // the final character arrives via a native compositionend/input event
    // instead (see CustomInput.svelte). Checked both ways since browsers
    // differ on when isComposing actually flips true: e.key === 'Dead'
    // covers the dead-key press itself (before composition is reported as
    // started), isComposing covers every keystroke once it has.
    if (e.isComposing || e.key === 'Dead') return

    // Let native clipboard/select-all shortcuts through unblocked, same
    // reasoning as composition above: paste/copy/cut/select-all are browser
    // default actions tied to the keydown itself (Ctrl/Cmd+V only actually
    // pastes if the browser gets to run its default handling), so
    // intercepting and preventDefault-ing them here - as every other key is
    // below - would silently break them. The resulting paste still lands as
    // a normal native `input` event, handled by CustomInput.svelte's
    // existing onNativeInput the same as typing/composition/autofill.
    if ((e.ctrlKey || e.metaKey) && ['v', 'c', 'x', 'a'].includes(e.key.toLowerCase())) return

    if (e.key === 'Escape') {
      clearTarget()
      e.preventDefault()
      e.stopImmediatePropagation()
      return
    }

    // Track hardware modifiers while keyboard is active.
    if (e.key === 'Shift') {
      hwShift.set(true)
      flashKey('SHIFT')
      e.preventDefault()
      e.stopImmediatePropagation()
      return
    }
    if (e.key === 'CapsLock') {
      hwCapsLock.update((v) => !v)
      flashKey('CAPS')
      e.preventDefault()
      e.stopImmediatePropagation()
      return
    }

    if (e.getModifierState) hwCapsLock.set(e.getModifierState('CapsLock'))

    let handled = true
    let label = null
    if (e.key === 'Backspace') {
      cur.backspace()
      label = 'BACKSPACE'
    } else if (e.key === 'Enter') {
      if (e.shiftKey && typeof cur.shiftEnter === 'function') cur.shiftEnter()
      else if (typeof cur.enter === 'function') cur.enter()
      else cur.insertChar('\n')
      label = 'ENTER'
    } else if (e.key === 'ArrowLeft') {
      cur.moveLeft()
      label = 'LEFT'
    } else if (e.key === 'ArrowRight') {
      cur.moveRight()
      label = 'RIGHT'
    } else if (e.key === 'ArrowUp') {
      cur.moveUp()
      label = 'UP'
    } else if (e.key === 'ArrowDown') {
      cur.moveDown()
      label = 'DOWN'
    } else if (e.key === 'Tab') {
      if (e.shiftKey && typeof cur.shiftTab === 'function') cur.shiftTab()
      else if (typeof cur.tab === 'function') cur.tab()
      label = 'TAB'
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      cur.insertChar(e.key)
      label = e.key === ' ' ? 'SPACE' : e.key
    } else {
      handled = false
    }

    // Even unhandled keys must not leak to app shortcuts while keyboard is active.
    e.preventDefault()
    e.stopImmediatePropagation()
    if (handled && label) flashKey(label)
    return
  }

  // Track hardware Shift immediately (before checking for a focused input)
  if (e.key === 'Shift') {
    hwShift.set(true)
    flashKey('SHIFT')
    return
  }
  if (e.key === 'CapsLock') {
    hwCapsLock.update((v) => !v)
    flashKey('CAPS')
    return
  }
  // Keep CapsLock in sync with the browser's actual state on every other key
  if (e.getModifierState) hwCapsLock.set(e.getModifierState('CapsLock'))

  const cur2 = get(_current)
  if (!cur2) return

  let handled = true
  let label = null
  if (e.key === 'Backspace') {
    cur2.backspace()
    label = 'BACKSPACE'
  } else if (e.key === 'Enter') {
    if (e.shiftKey && typeof cur2.shiftEnter === 'function') cur2.shiftEnter()
    else if (typeof cur2.enter === 'function') cur2.enter()
    else cur2.insertChar('\n')
    label = 'ENTER'
  } else if (e.key === 'ArrowLeft') {
    cur2.moveLeft()
    label = 'LEFT'
  } else if (e.key === 'ArrowRight') {
    cur2.moveRight()
    label = 'RIGHT'
  } else if (e.key === 'ArrowUp') {
    cur2.moveUp()
    label = 'UP'
  } else if (e.key === 'ArrowDown') {
    cur2.moveDown()
    label = 'DOWN'
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    cur2.insertChar(e.key)
    label = e.key === ' ' ? 'SPACE' : e.key
  } else {
    handled = false
  }

  if (handled) {
    e.preventDefault()
    e.stopImmediatePropagation()
    if (label) flashKey(label)
  }
}
