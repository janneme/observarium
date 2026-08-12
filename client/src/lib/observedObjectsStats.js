// Per-object observation stats, kept as a store so MainScreen's sky-view
// hide filter (see observed_objects.md) can react without re-querying
// storage on every frame. Mirrors the activeListObjectIds pattern in
// lists.js. Refreshed after every observation-affecting mutation — see
// ObservationFormPanel.svelte and ObservationsScreen.svelte for call sites.
import { writable } from 'svelte/store'
import { getObservationStatsByObject } from './db.js'

export const observationStatsById = writable(new Map())

export async function refreshObservationStats() {
  observationStatsById.set(await getObservationStatsByObject())
}
