import { writable, get } from 'svelte/store'

// The current focused input target. It should be an object implementing
// insertChar(ch) and backspace() methods.
const _current = writable(null)

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

export function clearTarget() {
  _current.set(null)
}
// Simple single-action keyboard store. Components set an action and it is
// cleared shortly after; consumers subscribe and react to actions.
export const keyboard = writable(null)
