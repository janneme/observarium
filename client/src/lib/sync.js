// Sync analysis/execution — see SYNC_ENHANCEMENT.md for the full design.
//
// A "category" is one of the four independently syncable data sets
// (observations, findingPaths, telescopes, eyepieces). Each has an adapter
// below that knows how to read/write its local + remote representation and
// flatten it into a Map<key, item> for diffing, regardless of whether the
// underlying storage shape is a flat array (observations, telescopes,
// eyepieces) or a nested object (finding paths).

import {
  getAllObservations,
  replaceAllObservations,
  getAllFindingPaths,
  replaceAllFindingPaths,
  getMeta,
  setMeta,
  getSyncDirty,
  clearSyncDirtyKeys,
  getSearchIndex,
  SYNC_EPOCH_ISO,
} from './db.js'
import {
  getObservations,
  saveObservations,
  mergeObservations,
  getFindingPaths,
  saveFindingPaths,
  mergeFindingPaths,
  getTelescopes,
  saveTelescopes,
  mergeTelescopes,
  getEyepieces,
  saveEyepieces,
  mergeEyepieces,
  getLists,
  saveLists,
  mergeLists,
} from './api.js'

export const SYNC_MODES = ['merge', 'overwriteLocal', 'overwriteServer']
export const SYNC_CATEGORY_LIST = ['observations', 'findingPaths', 'telescopes', 'eyepieces', 'lists']

function fmtDateLabel(dateKey) {
  const d = new Date(`${dateKey}T00:00:00`)
  if (Number.isNaN(d.getTime())) return dateKey
  return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`
}

function fallbackLabelFromId(id) {
  const raw = String(id || '')
  if (raw.startsWith('dso_M')) return `M ${Number(raw.slice(5))}`
  if (raw.startsWith('dso_NGC')) return `NGC ${Number(raw.slice(7))}`
  if (raw.startsWith('dso_IC')) return `IC ${Number(raw.slice(6))}`
  return raw || 'Unknown object'
}

function objectLabel(obj) {
  if (!obj) return 'Unknown object'
  if (obj.type === 'dso') {
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
  }
  if (obj.name) return obj.name
  if (obj.bay && obj.constellation) return `${obj.bay} ${obj.constellation}`
  if (obj.flam && obj.constellation) return `${obj.flam} ${obj.constellation}`
  return fallbackLabelFromId(obj.id)
}

function isFinalPath(path) {
  const steps = path?.steps
  return Array.isArray(steps) && steps.length > 0 && steps[steps.length - 1]?.final === true
}

function flattenFindingPaths(raw) {
  // Only final (completed) paths ever sync — matches the long-standing
  // upload rule (draft/in-progress paths never leave the device).
  const map = new Map()
  for (const [objectId, byStart] of Object.entries(raw || {})) {
    for (const [startHip, path] of Object.entries(byStart || {})) {
      if (isFinalPath(path)) {
        map.set(`${objectId}::${startHip}`, {
          objectId,
          startHip,
          steps: path.steps,
          updatedAt: path.updatedAt || SYNC_EPOCH_ISO,
        })
      }
    }
  }
  return map
}

// Inverse of flattenFindingPaths — reconstructs the nested
// {objectId: {startHip: {steps, updatedAt}}} storage shape from a flat
// Map<"objectId::startHip", {objectId, startHip, steps, updatedAt}>.
function unflattenFindingPaths(map) {
  const result = {}
  for (const item of map.values()) {
    const byStart = result[item.objectId] || (result[item.objectId] = {})
    byStart[item.startHip] = { steps: item.steps, updatedAt: item.updatedAt }
  }
  return result
}

// Used specifically before an overwrite-server push, so draft/in-progress
// paths (present in the raw local blob but never meant to leave the device)
// don't get written to the server's finding-paths storage.
function filterFinalPathsRaw(raw) {
  const result = {}
  for (const [objectId, byStart] of Object.entries(raw || {})) {
    const finalByStart = {}
    for (const [startHip, path] of Object.entries(byStart || {})) {
      if (isFinalPath(path)) finalByStart[startHip] = path
    }
    if (Object.keys(finalByStart).length > 0) result[objectId] = finalByStart
  }
  return result
}

async function buildFindingPathLabelResolver() {
  const searchIndex = await getSearchIndex()
  const objectById = new Map(searchIndex.map((o) => [o.id, o]))
  const starByHip = new Map(
    searchIndex.filter((o) => o.type === 'star' && o.hip != null).map((o) => [String(o.hip), o]),
  )
  return (key) => {
    const [objectId, startHip] = key.split('::')
    const startLabel =
      objectLabel(starByHip.get(String(startHip))) !== 'Unknown object'
        ? objectLabel(starByHip.get(String(startHip)))
        : `HIP ${startHip}`
    const targetLabel =
      objectLabel(objectById.get(objectId)) !== 'Unknown object'
        ? objectLabel(objectById.get(objectId))
        : fallbackLabelFromId(objectId)
    return `${startLabel} ⇒ ${targetLabel}`
  }
}

// --------------------------------------------------------------------------
// Category adapters
// --------------------------------------------------------------------------

async function makeAdapters() {
  const findingPathLabel = await buildFindingPathLabelResolver()
  return {
    observations: {
      noun: { singular: 'observation', plural: 'observations' },
      getLocalRaw: () => getAllObservations(),
      getRemoteRaw: () => getObservations(),
      toMap: (raw) => new Map((raw || []).map((o) => [o.date, o])),
      fromMap: (map) => Array.from(map.values()),
      replaceLocalRaw: (raw) => replaceAllObservations(raw),
      saveServerRaw: (raw) => saveObservations(raw),
      formatLabel: fmtDateLabel,
      mergePush: (upserts, deletes) => mergeObservations(upserts, deletes),
    },
    findingPaths: {
      noun: { singular: 'finding path', plural: 'finding paths' },
      getLocalRaw: () => getAllFindingPaths(),
      getRemoteRaw: () => getFindingPaths(),
      toMap: flattenFindingPaths,
      fromMap: unflattenFindingPaths,
      replaceLocalRaw: (raw) => replaceAllFindingPaths(raw),
      saveServerRaw: (raw) => saveFindingPaths(filterFinalPathsRaw(raw)),
      formatLabel: findingPathLabel,
      mergePush: (upserts, deletes) => mergeFindingPaths(upserts, deletes),
    },
    telescopes: {
      noun: { singular: 'telescope', plural: 'telescopes' },
      getLocalRaw: async () => (await getMeta('telescopes')) || [],
      getRemoteRaw: () => getTelescopes(),
      toMap: (raw) => new Map((raw || []).map((t) => [t.id, t])),
      fromMap: (map) => Array.from(map.values()),
      replaceLocalRaw: (raw) => setMeta('telescopes', raw),
      saveServerRaw: (raw) => saveTelescopes(raw),
      formatLabel: (key, map) => map.get(key)?.name || key,
      mergePush: (upserts, deletes) => mergeTelescopes(upserts, deletes),
    },
    eyepieces: {
      noun: { singular: 'eyepiece', plural: 'eyepieces' },
      getLocalRaw: async () => (await getMeta('eyepieces')) || [],
      getRemoteRaw: () => getEyepieces(),
      toMap: (raw) => new Map((raw || []).map((e) => [e.id, e])),
      fromMap: (map) => Array.from(map.values()),
      replaceLocalRaw: (raw) => setMeta('eyepieces', raw),
      saveServerRaw: (raw) => saveEyepieces(raw),
      formatLabel: (key, map) => map.get(key)?.name || key,
      mergePush: (upserts, deletes) => mergeEyepieces(upserts, deletes),
    },
    lists: {
      noun: { singular: 'list', plural: 'lists' },
      getLocalRaw: async () => (await getMeta('lists')) || [],
      getRemoteRaw: () => getLists(),
      toMap: (raw) => new Map((raw || []).map((l) => [l.id, l])),
      fromMap: (map) => Array.from(map.values()),
      replaceLocalRaw: (raw) => setMeta('lists', raw),
      saveServerRaw: (raw) => saveLists(raw),
      formatLabel: (key, map) => map.get(key)?.name || key,
      mergePush: (upserts, deletes) => mergeLists(upserts, deletes),
    },
  }
}

function itemsEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b)
}

// Diff two Map<key,item> snapshots: what changes if `from` becomes `to`.
function diffMaps(fromMap, toMap) {
  const added = []
  const updated = []
  const removed = []
  for (const [key, toItem] of toMap) {
    if (!fromMap.has(key)) added.push(key)
    else if (!itemsEqual(fromMap.get(key), toItem)) updated.push(key)
  }
  for (const key of fromMap.keys()) {
    if (!toMap.has(key)) removed.push(key)
  }
  return { added, updated, removed }
}

// Predicts the server-side merge-apply result (§8.1) purely in memory, so
// "Analyze Changes" can preview it without writing anything.
function simulateMerge(localMap, remoteMap, dirtyEntries) {
  const predicted = new Map(remoteMap)
  const remoteAdd = []
  const remoteUpdate = []
  const remoteDelete = []
  const conflictLost = []

  for (const [key, entry] of dirtyEntries) {
    if (entry.op === 'delete') {
      if (predicted.has(key)) {
        predicted.delete(key)
        remoteDelete.push(key)
      }
      continue
    }
    const localItem = localMap.get(key)
    if (!localItem) continue // dirty but no longer present locally — nothing to push
    const remoteItem = remoteMap.get(key)
    const localUpdatedAt = localItem.updatedAt || SYNC_EPOCH_ISO
    const remoteUpdatedAt = remoteItem?.updatedAt || SYNC_EPOCH_ISO
    if (!remoteItem) {
      predicted.set(key, localItem)
      remoteAdd.push(key)
    } else if (localUpdatedAt >= remoteUpdatedAt) {
      predicted.set(key, localItem)
      remoteUpdate.push(key)
    } else {
      conflictLost.push(key)
    }
  }

  return { predictedMap: predicted, remoteAdd, remoteUpdate, remoteDelete, conflictLost }
}

// Merge mode must never delete local data — a server that lacks some item
// is indistinguishable from "this device never pushed it yet" (true for
// any not-yet-dirty local item, and always true on a brand-new category's
// first sync). The only way an item is ever removed locally is if it was
// already deleted locally beforehand (so it's simply absent from
// `localMap` to begin with) — deletion only ever flows local -> server,
// never the reverse. So this is a non-destructive union: local keeps
// everything it has, and only gains items that are new or newer on the
// server side.
function mergeLocalUnion(localMap, serverMap) {
  const next = new Map(localMap)
  for (const [key, remoteItem] of serverMap) {
    const localItem = next.get(key)
    const remoteUpdatedAt = remoteItem.updatedAt || SYNC_EPOCH_ISO
    const localUpdatedAt = localItem?.updatedAt || SYNC_EPOCH_ISO
    if (!localItem || remoteUpdatedAt > localUpdatedAt) {
      next.set(key, remoteItem)
    }
  }
  return next
}

function formatBulletGroup(verb, noun, keys, formatLabel, map) {
  if (keys.length === 0) return null
  const nounText = keys.length === 1 ? noun.singular : noun.plural
  const labels = keys.map((k) => formatLabel(k, map)).join(', ')
  return `${verb} ${nounText} ${labels}`
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

// Returns { localChanges: string[], remoteChanges: string[] } — already
// human-readable bullet lines (without the leading "- "), grouped by
// (category, operation), singular/plural handled per SYNC_ENHANCEMENT.md §9.
export async function analyzeSync({ categories, mode }) {
  const adapters = await makeAdapters()
  const dirty = await getSyncDirty()
  const localLines = []
  const remoteLines = []

  for (const category of categories) {
    const adapter = adapters[category]
    const [localRaw, remoteRaw] = await Promise.all([adapter.getLocalRaw(), adapter.getRemoteRaw()])
    const localMap = adapter.toMap(localRaw)
    const remoteMap = adapter.toMap(remoteRaw)

    if (mode === 'overwriteLocal') {
      const diff = diffMaps(localMap, remoteMap)
      const combinedMap = new Map([...localMap, ...remoteMap])
      localLines.push(
        formatBulletGroup('add', adapter.noun, diff.added, adapter.formatLabel, combinedMap),
        formatBulletGroup('update', adapter.noun, diff.updated, adapter.formatLabel, combinedMap),
        formatBulletGroup('delete', adapter.noun, diff.removed, adapter.formatLabel, combinedMap),
      )
    } else if (mode === 'overwriteServer') {
      const diff = diffMaps(remoteMap, localMap)
      const combinedMap = new Map([...localMap, ...remoteMap])
      remoteLines.push(
        formatBulletGroup('add', adapter.noun, diff.added, adapter.formatLabel, combinedMap),
        formatBulletGroup('update', adapter.noun, diff.updated, adapter.formatLabel, combinedMap),
        formatBulletGroup('delete', adapter.noun, diff.removed, adapter.formatLabel, combinedMap),
      )
    } else {
      const dirtyEntries = Object.entries(dirty[category] || {})
      const sim = simulateMerge(localMap, remoteMap, dirtyEntries)
      const localPredicted = mergeLocalUnion(localMap, sim.predictedMap)
      // localDiff.removed is always empty by construction — merge never
      // deletes locally, see mergeLocalUnion.
      const localDiff = diffMaps(localMap, localPredicted)
      const combinedMap = new Map([...localMap, ...remoteMap, ...sim.predictedMap, ...localPredicted])
      localLines.push(
        formatBulletGroup('add', adapter.noun, localDiff.added, adapter.formatLabel, combinedMap),
        formatBulletGroup('update', adapter.noun, localDiff.updated, adapter.formatLabel, combinedMap),
      )
      remoteLines.push(
        formatBulletGroup('add', adapter.noun, sim.remoteAdd, adapter.formatLabel, combinedMap),
        formatBulletGroup('update', adapter.noun, sim.remoteUpdate, adapter.formatLabel, combinedMap),
        formatBulletGroup('delete', adapter.noun, sim.remoteDelete, adapter.formatLabel, combinedMap),
        formatBulletGroup(
          'kept server version over your older edit for',
          adapter.noun,
          sim.conflictLost,
          adapter.formatLabel,
          combinedMap,
        ),
      )
    }
  }

  return {
    localChanges: localLines.filter(Boolean),
    remoteChanges: remoteLines.filter(Boolean),
  }
}

// Executes the sync for the given categories/mode. Local writes use each
// category's raw replace so incoming synced data is never mistaken for a
// local edit (see db.js putObservation's doc comment).
export async function runSync({ categories, mode }) {
  const adapters = await makeAdapters()

  for (const category of categories) {
    const adapter = adapters[category]

    if (mode === 'overwriteLocal') {
      const remoteRaw = await adapter.getRemoteRaw()
      await adapter.replaceLocalRaw(remoteRaw)
      continue
    }

    if (mode === 'overwriteServer') {
      const localRaw = await adapter.getLocalRaw()
      await adapter.saveServerRaw(localRaw)
      continue
    }

    // merge
    const dirty = await getSyncDirty()
    const dirtyEntries = Object.entries(dirty[category] || {})
    const localRaw = await adapter.getLocalRaw()
    const localMap = adapter.toMap(localRaw)

    const deletes = []
    const upserts = []
    for (const [key, entry] of dirtyEntries) {
      if (entry.op === 'delete') {
        deletes.push(key)
        continue
      }
      const item = localMap.get(key)
      if (!item) continue
      if (category === 'findingPaths') {
        upserts.push({ objectId: item.objectId, startHip: item.startHip, steps: item.steps, updatedAt: item.updatedAt })
      } else {
        upserts.push(item)
      }
    }

    const mergedServerRaw = await adapter.mergePush(upserts, deletes)
    const mergedServerMap = adapter.toMap(mergedServerRaw)
    const nextLocalMap = mergeLocalUnion(localMap, mergedServerMap)
    await adapter.replaceLocalRaw(adapter.fromMap(nextLocalMap))
    await clearSyncDirtyKeys(
      category,
      dirtyEntries.map(([key]) => key),
    )
  }
}
