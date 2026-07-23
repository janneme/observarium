// Lists data layer — user-defined named lists of stars/DSOs (see lists.md).
// Storage follows the same flat-array-under-getMeta convention already used
// for telescopes/eyepieces (client/src/screens/TelescopesScreen.svelte),
// which is also what the generic sync adapter in sync.js expects.

import { writable } from 'svelte/store'
import { getMeta, setMeta, markDirty, getSyncDirtyTotalCount } from './db.js'
import { pendingChanges } from '../stores/ui.js'

// Set of object ids belonging to at least one active list — kept as a store
// so SkyCanvas can reactively gate its active-list marker layer without
// re-querying storage on every frame. Refreshed after every list mutation
// below; callers that mutate lists via other paths should call
// refreshActiveListObjectIds() themselves.
export const activeListObjectIds = writable(new Set())

export async function refreshActiveListObjectIds() {
  activeListObjectIds.set(await getActiveListObjectIds())
}

export function newListId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `list_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

export async function getAllLists() {
  const raw = await getMeta('lists')
  return Array.isArray(raw) ? raw : []
}

async function persistLists(lists) {
  await setMeta('lists', lists)
}

async function markListDirty(id, op) {
  await markDirty('lists', id, op)
  pendingChanges.set(await getSyncDirtyTotalCount())
}

export async function saveList(list) {
  const lists = await getAllLists()
  const stamped = { ...list, updatedAt: new Date().toISOString() }
  const idx = lists.findIndex((l) => l.id === stamped.id)
  const next = idx >= 0 ? lists.map((l, i) => (i === idx ? stamped : l)) : [...lists, stamped]
  await persistLists(next)
  await markListDirty(stamped.id, 'upsert')
  await refreshActiveListObjectIds()
  return stamped
}

export async function deleteList(id) {
  const lists = await getAllLists()
  await persistLists(lists.filter((l) => l.id !== id))
  await markListDirty(id, 'delete')
  await refreshActiveListObjectIds()
}

export async function renameList(id, name) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === id)
  if (!list) return null
  return saveList({ ...list, name })
}

export async function setListActive(id, active) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === id)
  if (!list) return null
  return saveList({ ...list, active })
}

export async function addObjectToList(listId, objectId) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === listId)
  if (!list) return null
  const objects = Array.isArray(list.objects) ? list.objects : []
  if (objects.some((o) => o.id === objectId)) return list
  return saveList({ ...list, objects: [...objects, { id: objectId, note: '', addedAt: new Date().toISOString() }] })
}

export async function removeObjectFromList(listId, objectId) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === listId)
  if (!list) return null
  const objects = (Array.isArray(list.objects) ? list.objects : []).filter((o) => o.id !== objectId)
  return saveList({ ...list, objects })
}

export async function removeObjectFromLists(listIds, objectId) {
  for (const listId of listIds) {
    // eslint-disable-next-line no-await-in-loop
    await removeObjectFromList(listId, objectId)
  }
}

export async function updateListObjectNote(listId, objectId, note) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === listId)
  if (!list) return null
  const objects = (Array.isArray(list.objects) ? list.objects : []).map((o) =>
    o.id === objectId ? { ...o, note } : o,
  )
  return saveList({ ...list, objects })
}

// Moves the object at `objectId` one position up/down within a Manual-sort
// list's own order. No-op if the list's sortType isn't 'manual' or the
// object is already at that edge.
export async function reorderListObject(listId, objectId, direction) {
  const lists = await getAllLists()
  const list = lists.find((l) => l.id === listId)
  if (!list || list.sortType !== 'manual') return null
  const objects = Array.isArray(list.objects) ? [...list.objects] : []
  const idx = objects.findIndex((o) => o.id === objectId)
  const targetIdx = idx + (direction === 'up' ? -1 : 1)
  if (idx < 0 || targetIdx < 0 || targetIdx >= objects.length) return list
  ;[objects[idx], objects[targetIdx]] = [objects[targetIdx], objects[idx]]
  return saveList({ ...list, objects })
}

export async function getListsForObject(objectId) {
  const lists = await getAllLists()
  return lists.filter((l) => (l.objects || []).some((o) => o.id === objectId))
}

// Set of object ids belonging to at least one active list — used by
// SkyCanvas to gate the active-list marker layer with a cheap lookup.
export async function getActiveListObjectIds() {
  const lists = await getAllLists()
  const ids = new Set()
  for (const list of lists) {
    if (!list.active) continue
    for (const obj of list.objects || []) ids.add(obj.id)
  }
  return ids
}
