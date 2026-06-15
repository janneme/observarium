import { writable } from 'svelte/store'

export const showFovCircle = writable(true)
export const showConstellationLines = writable(false)
export const showConstellationBoundaries = writable(false)
export const showDsos = writable(true)
export const showHorizon = writable(true)
export const finderViewActive = writable(false)
export const pendingChanges = writable(0)
