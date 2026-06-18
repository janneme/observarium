import { writable, get, derived } from 'svelte/store'

export const pressedKey = writable(null)
let _pressedKeyTimer = null

function flashKey(label) {
  pressedKey.set(label)
  if (_pressedKeyTimer) clearTimeout(_pressedKeyTimer)
  _pressedKeyTimer = setTimeout(() => pressedKey.set(null), 150)
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
  if (!cur) return

  let handled = true
  let label = null
  if (e.key === 'Backspace') {
    cur.backspace()
    label = 'BACKSPACE'
  } else if (e.key === 'Enter') {
    if (typeof cur.enter === 'function') cur.enter()
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
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    cur.insertChar(e.key)
    label = e.key === ' ' ? 'SPACE' : e.key
  } else {
    handled = false
  }

  if (handled) {
    e.preventDefault()
    if (label) flashKey(label)
  }
}
