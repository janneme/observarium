<script>
  import { onMount, tick } from 'svelte'
  import {
    getAllObservations,
    getSearchIndex,
    getMeta,
    putObservation,
    incrementPendingChanges,
    deleteObservationByDate,
  } from '../lib/db.js'
  import { pendingChanges } from '../stores/ui.js'
  import { keyboardActive } from '../stores/keyboard.js'
  import CustomInput from '../components/CustomInput.svelte'
  import CustomTextarea from '../components/CustomTextarea.svelte'
  import TelescopeUsageEditor from '../components/TelescopeUsageEditor.svelte'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import PlusIcon from '../icons/PlusIcon.svelte'
  import EditIcon from '../icons/EditIcon.svelte'
  import DeleteIcon from '../icons/DeleteIcon.svelte'
  import AcceptIcon from '../icons/AcceptIcon.svelte'
  import CloseIcon from '../icons/CloseIcon.svelte'

  export let onClose = () => {}
  export let onOpenObject = () => {}

  let observations = []
  let expandedDates = new Set()
  let labelByObjectId = new Map()
  let objectById = new Map()
  let telescopeById = new Map()
  let eyepieceById = new Map()
  let searchItems = []
  let addObjectInput = null
  let addObjectQuery = ''
  let activeCandidates = []
  let objectEdit = null
  let observationEdit = null
  let addObjectState = null
  let confirmOpen = false
  let confirmTitle = 'Confirm delete'
  let confirmMessage = ''
  let pendingDelete = null
  let errorMsg = ''
  let objectEditError = ''
  let loading = true

  function normalizeDate(dateText) {
    const d = new Date(`${dateText}T00:00:00`)
    if (Number.isNaN(d.getTime())) return dateText
    return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`
  }

  function trimList(items, maxLen = 46) {
    if (!items.length) return 'no objects'
    let out = ''
    for (let i = 0; i < items.length; i += 1) {
      const part = i === 0 ? items[i] : `, ${items[i]}`
      if ((out + part).length > maxLen) return `${out}, ...`
      out += part
    }
    return out
  }

  function fallbackLabelFromId(id) {
    const raw = String(id || '')
    if (raw.startsWith('dso_M')) return `M ${Number(raw.slice(5))}`
    if (raw.startsWith('dso_NGC')) return `NGC ${Number(raw.slice(7))}`
    if (raw.startsWith('dso_IC')) return `IC ${Number(raw.slice(6))}`
    if (raw.startsWith('solar_')) {
      const n = raw.slice(6).replace(/_/g, ' ').trim()
      return n ? n[0].toUpperCase() + n.slice(1) : raw
    }
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
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    return fallbackLabelFromId(obj.id)
  }

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs)
      for (const c of String(p.comp || ''))
        if (c >= 'A' && c <= 'Z') letters.add(c)
    return letters.size
  }

  function objectSymbolKind(obj) {
    if (!obj) return 'generic'
    if (obj.type === 'double_star') return dsLetterCount(obj.pairs) > 2 ? 'double_star_multi' : 'double_star'
    if (obj.type === 'star') {
      if (obj.dbl === 'm') return 'double_star_multi'
      if (obj.dbl) return 'double_star'
      return 'star'
    }
    if (obj.type === 'solar_system_body') return String(obj.name || '').toLowerCase() || 'generic'

    const type = String(obj.dsoType || '').toLowerCase()
    if (type === 'open cluster') return 'open_cluster'
    if (type === 'globular cluster') return 'globular_cluster'
    if (type === 'planetary nebula') return 'planetary_nebula'
    if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') return 'galaxy'
    if (type === 'dark nebula') return 'dark_nebula'
    if (type === 'galaxy cluster' || type === 'cluster of galaxies') return 'galaxy_cluster'
    if (type === 'quasar' || type === 'qso' || type === 'bl lac') return 'quasar'
    if (type.includes('nebula')) return 'nebula'
    return 'generic'
  }

  function normalizeSearchText(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '')
  }

  function safeStringify(value) {
    try {
      return JSON.stringify(value)
    } catch {
      return '{"error":"stringify_failed"}'
    }
  }

  function observationHeaderLabel(obs) {
    const names = (obs.objects || []).map((entry) => labelByObjectId.get(entry.id) || fallbackLabelFromId(entry.id))
    const locationName = String(obs?.location?.name || '').trim()
    const datePart = normalizeDate(obs.date)
    if (locationName) return `${datePart}, ${locationName} (${trimList(names)})`
    return `${datePart} (${trimList(names)})`
  }

  function observationLocationLabel(obs) {
    const locationName = String(obs?.location?.name || '').trim()
    const hasLatLon = obs?.location?.lat != null && obs?.location?.lon != null
    if (locationName && hasLatLon) return `${locationName} (${obs.location.lat}, ${obs.location.lon})`
    if (locationName) return locationName
    if (hasLatLon) return `${obs.location.lat}, ${obs.location.lon}`
    return ''
  }

  function sortedObservations(items) {
    return [...items].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')))
  }

  function isObjectEditing(date, objectId) {
    return objectEdit?.date === date && String(objectEdit?.objectId) === String(objectId)
  }

  function editedEntryForObservation(obs) {
    if (!objectEdit || objectEdit.date !== obs?.date) return null
    return (obs.objects || []).find((entry) => String(entry.id) === String(objectEdit.objectId)) || null
  }

  function isObservationEditing(date) {
    return observationEdit?.date === date
  }

  function toggleDate(date) {
    const next = new Set(expandedDates)
    if (next.has(date)) next.delete(date)
    else next.add(date)
    expandedDates = next
  }

  function parseDateKey(value) {
    const s = String(value || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
    const d = new Date(`${s}T00:00:00`)
    if (Number.isNaN(d.getTime())) return null
    return s
  }

  function parseOptionalNumber(value) {
    if (String(value ?? '').trim() === '') return null
    const n = Number(String(value).trim())
    return Number.isFinite(n) ? n : null
  }

  function telescopeNeedsEyepiece(telescope) {
    const v = telescope?.needsEyepiece
    if (typeof v === 'boolean') return v
    if (typeof v === 'number') return v !== 0
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase()
      if (s === 'true' || s === '1' || s === 'yes') return true
      if (s === 'false' || s === '0' || s === 'no') return false
    }
    return !!v
  }

  function normalizeTelescopeResults(results) {
    if (!Array.isArray(results)) return []
    return results
      .filter((r) => r && typeof r === 'object' && r.telescopeId != null)
      .map((r) => ({
        telescopeId: r.telescopeId,
        seen: typeof r.seen === 'boolean' ? r.seen : null,
        eyepieceIds: Array.isArray(r.eyepieceIds) ? r.eyepieceIds.filter((id) => id != null) : [],
        eyepieceId: r.eyepieceId ?? null,
      }))
  }

  function telescopesForSelection() {
    return [...telescopeById.values()].sort((a, b) =>
      String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
    )
  }

  function eyepiecesForSelection() {
    return [...eyepieceById.values()].sort((a, b) =>
      String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
    )
  }

  function telescopeResultLabel(result) {
    const tName = telescopeById.get(result.telescopeId)?.name || result.telescopeId || 'Telescope'
    const ids = Array.isArray(result.eyepieceIds) ? result.eyepieceIds : result.eyepieceId ? [result.eyepieceId] : []
    if (!ids.length) return tName
    const options = ids.map((id) => eyepieceById.get(id)?.name || id).join(', ')
    return `${tName} (${options})`
  }

  function objectDetailsLabel(entry) {
    if (!Array.isArray(entry?.telescopeResults)) return ''
    const used = entry.telescopeResults.filter((r) => r?.seen === true)
    if (!used.length) return ''
    return used.map((r) => telescopeResultLabel(r)).join(' | ')
  }

  async function bumpPending(dates = []) {
    const nextPending = await incrementPendingChanges(1, dates)
    pendingChanges.set(nextPending)
  }

  function startObjectEdit(date, entry) {
    const telescopes = telescopesForSelection()
    const normalizedResults = normalizeTelescopeResults(entry?.telescopeResults)
    const byTelescopeId = new Map(normalizedResults.map((r) => [r.telescopeId, r]))
    const telescopeStates = telescopes.map((t) => {
      const r = byTelescopeId.get(t.id)
      const ids =
        Array.isArray(r?.eyepieceIds) && r.eyepieceIds.length > 0 ? r.eyepieceIds : r?.eyepieceId ? [r.eyepieceId] : []
      return {
        telescopeId: t.id,
        seen: typeof r?.seen === 'boolean' ? r.seen : null,
        eyepieceIds: ids,
      }
    })
    const next = new Set(expandedDates)
    next.add(date)
    expandedDates = next
    objectEdit = {
      date,
      objectId: String(entry?.id ?? ''),
      draftNotes: String(entry?.notes || ''),
      telescopeStates,
    }
    objectEditError = ''
  }

  function onObservationEditClick(obs, e) {
    e.preventDefault()
    e.stopPropagation()
    startObservationEdit(obs)
  }

  function onObservationDeleteClick(date, e) {
    e.preventDefault()
    e.stopPropagation()
    openDeleteObservation(date)
  }

  function onObjectEditClick(date, entry, e) {
    e.preventDefault()
    e.stopPropagation()
    startObjectEdit(date, entry)
  }

  function onObjectDeleteClick(date, entry, e) {
    e.preventDefault()
    e.stopPropagation()
    openDeleteObject(date, entry)
  }

  function onAddObjectClick(date, e) {
    e.preventDefault()
    e.stopPropagation()
    openAddObject(date)
  }

  function openObjectFromObservation(objectId, e) {
    e?.preventDefault?.()
    e?.stopPropagation?.()
    const object = objectById.get(objectId)
    if (!object) return
    onOpenObject(object)
  }

  function cancelObjectEdit() {
    objectEdit = null
    objectEditError = ''
  }

  function toggleObjectTelescope(telescopeId) {
    if (!objectEdit) return
    objectEdit = {
      ...objectEdit,
      telescopeStates: objectEdit.telescopeStates.map((s) => {
        if (s.telescopeId !== telescopeId) return s
        const nextSeen = s.seen === true ? null : true
        return {
          ...s,
          seen: nextSeen,
          eyepieceIds: nextSeen === true ? s.eyepieceIds || [] : [],
        }
      }),
    }
    objectEditError = ''
  }

  function toggleObjectEyepiece(telescopeId, eyepieceId) {
    if (!objectEdit) return
    objectEdit = {
      ...objectEdit,
      telescopeStates: objectEdit.telescopeStates.map((s) => {
        if (s.telescopeId !== telescopeId) return s
        const current = Array.isArray(s.eyepieceIds) ? s.eyepieceIds : []
        return {
          ...s,
          eyepieceIds: current.includes(eyepieceId)
            ? current.filter((id) => id !== eyepieceId)
            : [...current, eyepieceId],
        }
      }),
    }
    objectEditError = ''
  }

  async function saveObjectEdit() {
    if (!objectEdit) return
    const { date, objectId, draftNotes, telescopeStates } = objectEdit
    const telescopes = telescopesForSelection()

    for (const state of telescopeStates) {
      if (state.seen !== true) continue
      const telescope = telescopes.find((t) => t.id === state.telescopeId)
      if (!telescopeNeedsEyepiece(telescope)) continue
      if (!Array.isArray(state.eyepieceIds) || state.eyepieceIds.length === 0) {
        objectEditError = `Select at least one option for ${telescope?.name || 'selected telescope'}.`
        return
      }
    }

    const telescopeResults = telescopeStates
      .filter((s) => s.seen === true || s.seen === false)
      .map((s) => {
        const telescope = telescopes.find((t) => t.id === s.telescopeId)
        const needsEyepiece = telescopeNeedsEyepiece(telescope)
        const selectedIds = Array.isArray(s.eyepieceIds) ? s.eyepieceIds : []
        return {
          telescopeId: s.telescopeId,
          seen: s.seen,
          eyepieceIds: s.seen === true && needsEyepiece ? selectedIds : [],
          eyepieceId: s.seen === true && needsEyepiece && selectedIds.length > 0 ? selectedIds[0] : null,
        }
      })

    const next = observations.map((obs) => {
      if (obs.date !== date) return obs
      return {
        ...obs,
        objects: (obs.objects || []).map((entry) =>
          String(entry.id) === String(objectId)
            ? {
                ...entry,
                notes: String(draftNotes || '').trim(),
                telescopeResults,
              }
            : entry,
        ),
      }
    })
    const updated = next.find((obs) => obs.date === date)
    if (!updated) return
    await putObservation(updated)
    observations = sortedObservations(next)
    objectEdit = null
    objectEditError = ''
    await bumpPending([date])
  }

  function startObservationEdit(obs) {
    const next = new Set(expandedDates)
    next.add(obs.date)
    expandedDates = next
    observationEdit = {
      date: obs.date,
      draftDate: obs.date,
      draftLocationName: obs.location?.name ? String(obs.location.name) : '',
      draftLat: obs.location?.lat != null ? String(obs.location.lat) : '',
      draftLon: obs.location?.lon != null ? String(obs.location.lon) : '',
      draftNotes: obs.notes || '',
    }
    errorMsg = ''
  }

  function cancelObservationEdit() {
    if (observationEdit?.date) {
      const nextExpanded = new Set(expandedDates)
      nextExpanded.delete(observationEdit.date)
      expandedDates = nextExpanded
    }
    observationEdit = null
    errorMsg = ''
  }

  async function saveObservationEdit() {
    if (!observationEdit) return
    const originalDate = observationEdit.date
    const nextDate = parseDateKey(observationEdit.draftDate)
    if (!nextDate) {
      errorMsg = 'Date must be in YYYY-MM-DD format.'
      return
    }
    if (nextDate !== originalDate && observations.some((obs) => obs.date === nextDate)) {
      errorMsg = `Observation for ${normalizeDate(nextDate)} already exists.`
      return
    }

    const lat = parseOptionalNumber(observationEdit.draftLat)
    const lon = parseOptionalNumber(observationEdit.draftLon)
    if ((lat == null) !== (lon == null)) {
      errorMsg = 'Fill both latitude and longitude, or leave both empty.'
      return
    }
    const locationName = String(observationEdit.draftLocationName || '').trim()
    let location = lat != null && lon != null ? { lat, lon } : null
    if (locationName) location = { ...(location || {}), name: locationName }

    const current = observations.find((obs) => obs.date === originalDate)
    if (!current) return
    const updated = {
      ...current,
      date: nextDate,
      location,
      notes: observationEdit.draftNotes.trim(),
    }

    if (nextDate !== originalDate) await deleteObservationByDate(originalDate)
    await putObservation(updated)

    observations = sortedObservations([...observations.filter((obs) => obs.date !== originalDate), updated])

    const nextExpanded = new Set(expandedDates)
    nextExpanded.delete(originalDate)
    nextExpanded.delete(nextDate)
    expandedDates = nextExpanded

    objectEdit = null
    observationEdit = null
    errorMsg = ''
    await bumpPending([nextDate])
  }

  function openDeleteObject(date, entry) {
    confirmTitle = 'Delete object from observation'
    confirmMessage = `Delete ${labelByObjectId.get(entry.id) || fallbackLabelFromId(entry.id)} from ${normalizeDate(date)}?`
    pendingDelete = { type: 'object', date, objectId: entry.id }
    confirmOpen = true
  }

  function openDeleteObservation(date) {
    confirmTitle = 'Delete observation'
    confirmMessage = `Delete observation for ${normalizeDate(date)}?`
    pendingDelete = { type: 'observation', date }
    confirmOpen = true
  }

  function cancelDelete() {
    confirmOpen = false
    pendingDelete = null
  }

  async function confirmDelete() {
    const task = pendingDelete
    cancelDelete()
    if (!task) return

    if (task.type === 'observation') {
      await deleteObservationByDate(task.date)
      observations = observations.filter((obs) => obs.date !== task.date)
      if (observationEdit?.date === task.date) observationEdit = null
      if (objectEdit?.date === task.date) objectEdit = null
    } else {
      const next = observations
        .map((obs) => {
          if (obs.date !== task.date) return obs
          return { ...obs, objects: (obs.objects || []).filter((entry) => entry.id !== task.objectId) }
        })
        .filter((obs) => (obs.objects || []).length > 0)

      const updated = next.find((obs) => obs.date === task.date)
      if (updated) await putObservation(updated)
      else await deleteObservationByDate(task.date)

      observations = sortedObservations(next)
      if (objectEdit?.date === task.date && objectEdit?.objectId === task.objectId) objectEdit = null
    }

    await bumpPending([task.date])
  }

  async function openAddObject(date) {
    const next = new Set(expandedDates)
    next.add(date)
    expandedDates = next
    addObjectState = { date }
    addObjectQuery = ''
    await tick()
    addObjectInput?.focus?.()
  }

  function closeAddObject() {
    addObjectState = null
    addObjectQuery = ''
  }

  function filteredCandidates(date, queryText, allObservations, allSearchItems) {
    if (!addObjectState || addObjectState.date !== date) return []
    const existingIds = new Set(
      (allObservations.find((obs) => obs.date === date)?.objects || []).map((entry) => entry.id),
    )
    const q = normalizeSearchText(queryText)
    if (!q) return []
    return allSearchItems
      .filter((item) => !existingIds.has(item.id))
      .filter((item) => item.searchTextNormalized.includes(q))
      .slice(0, 10)
  }

  $: if (addObjectState) {
    activeCandidates = filteredCandidates(addObjectState.date, addObjectQuery, observations, searchItems)
  } else {
    activeCandidates = []
  }

  function nextAvailableDateKey(baseDate = new Date()) {
    const taken = new Set(observations.map((obs) => obs.date))
    const d = new Date(baseDate)
    d.setHours(0, 0, 0, 0)
    for (let i = 0; i < 3650; i += 1) {
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      if (!taken.has(key)) return key
      d.setDate(d.getDate() + 1)
    }
    return null
  }

  async function addObservation() {
    const date = nextAvailableDateKey()
    if (!date) {
      errorMsg = 'Cannot find free date for a new observation.'
      return
    }
    const record = { date, location: null, notes: '', objects: [] }
    await putObservation(record)
    observations = sortedObservations([...observations, record])
    startObservationEdit(record)
    await bumpPending([date])
  }

  async function addObjectToObservation(date, objectId) {
    let createdEntry = null
    const next = observations.map((obs) => {
      if (obs.date !== date) return obs
      if ((obs.objects || []).some((entry) => entry.id === objectId)) return obs
      createdEntry = { id: objectId, telescopeResults: [], notes: '' }
      return {
        ...obs,
        objects: [...(obs.objects || []), createdEntry],
      }
    })
    const updated = next.find((obs) => obs.date === date)
    if (!updated) return
    await putObservation(updated)
    observations = sortedObservations(next)
    closeAddObject()
    if (createdEntry) startObjectEdit(date, createdEntry)
    await bumpPending([date])
  }

  async function loadData() {
    loading = true
    const [allObservations, searchIndex, telescopes, eyepieces] = await Promise.all([
      getAllObservations(),
      getSearchIndex(),
      getMeta('telescopes'),
      getMeta('eyepieces'),
    ])

    labelByObjectId = new Map(searchIndex.map((obj) => [obj.id, objectLabel(obj)]))
    objectById = new Map(searchIndex.map((obj) => [obj.id, obj]))
    telescopeById = new Map((Array.isArray(telescopes) ? telescopes : []).map((t) => [t.id, t]))
    eyepieceById = new Map((Array.isArray(eyepieces) ? eyepieces : []).map((e) => [e.id, e]))
    searchItems = searchIndex.map((obj) => {
      const label = objectLabel(obj)
      const variants = [label, fallbackLabelFromId(obj.id), obj.id || '', obj.name || '']
      if (obj.m != null) variants.push(`M${obj.m}`, `M ${obj.m}`)
      if (obj.ngc != null) variants.push(`NGC${obj.ngc}`, `NGC ${obj.ngc}`)
      if (obj.ic != null) variants.push(`IC${obj.ic}`, `IC ${obj.ic}`)
      if (obj.caldwell != null) variants.push(`C${obj.caldwell}`, `C ${obj.caldwell}`)
      const rawId = String(obj.id || '')
      if (rawId.startsWith('dso_M')) {
        const n = Number(rawId.slice(5))
        if (Number.isFinite(n)) variants.push(`M${n}`, `M ${n}`)
      }
      if (rawId.startsWith('dso_NGC')) {
        const n = Number(rawId.slice(7))
        if (Number.isFinite(n)) variants.push(`NGC${n}`, `NGC ${n}`)
      }
      if (rawId.startsWith('dso_IC')) {
        const n = Number(rawId.slice(6))
        if (Number.isFinite(n)) variants.push(`IC${n}`, `IC ${n}`)
      }
      return {
        id: obj.id,
        label,
        symbolKind: objectSymbolKind(obj),
        searchTextNormalized: normalizeSearchText(variants.join(' ')),
      }
    })
    observations = sortedObservations(Array.isArray(allObservations) ? allObservations : [])
    loading = false
  }

  onMount(async () => {
    await loadData()
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={onClose}>←</button>
    <span class="header-title">Observations</span>
    <button class="icon-btn add-observation" type="button" on:click={addObservation} title="Add observation">
      <PlusIcon size="1rem" aria-hidden="true" />
    </button>
  </div>

  <div class="content">
    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    {#if loading}
      <div class="hint">Loading...</div>
    {:else if observations.length === 0}
      <div class="hint">No observations yet.</div>
    {:else}
      {#each observations as obs}
        <section class="obs-card">
          <div class="obs-header">
            <button class="obs-toggle" on:click={() => toggleDate(obs.date)}>
              <span class="obs-title">{observationHeaderLabel(obs)}</span>
              <span class="caret">{expandedDates.has(obs.date) ? '▾' : '▸'}</span>
            </button>
            <span class="header-actions">
              <button
                class="icon-btn"
                type="button"
                on:click={(e) => onObservationEditClick(obs, e)}
                title="Edit observation"
              >
                <EditIcon size="1rem" aria-hidden="true" />
              </button>
              <button
                class="icon-btn danger"
                type="button"
                on:click={(e) => onObservationDeleteClick(obs.date, e)}
                title="Delete observation"
              >
                <DeleteIcon size="1rem" aria-hidden="true" />
              </button>
            </span>
          </div>

          {#if expandedDates.has(obs.date)}
            <div class="obs-details">
              {#if isObservationEditing(obs.date)}
                <div class="edit-observation">
                  <div class="date-location-row">
                    <div class="field-row">
                      <div class="field-label">Date</div>
                      <CustomInput bind:value={observationEdit.draftDate} placeholder="YYYY-MM-DD" />
                    </div>
                    <div class="field-row">
                      <div class="field-label">Location name</div>
                      <CustomInput bind:value={observationEdit.draftLocationName} placeholder="City / site name" />
                    </div>
                  </div>
                  <div class="coords">
                    <div class="field-row">
                      <div class="field-label">Latitude</div>
                      <CustomInput bind:value={observationEdit.draftLat} placeholder="Latitude" />
                    </div>
                    <div class="field-row">
                      <div class="field-label">Longitude</div>
                      <CustomInput bind:value={observationEdit.draftLon} placeholder="Longitude" />
                    </div>
                  </div>
                  <div class="field-row">
                    <div class="field-label">Description</div>
                    <CustomTextarea bind:value={observationEdit.draftNotes} placeholder="Observation details..." />
                  </div>
                  <div class="edit-actions">
                    <button
                      class="icon-btn"
                      type="button"
                      on:click={saveObservationEdit}
                      title="Accept"
                      aria-label="Accept"
                    >
                      <AcceptIcon size="1rem" aria-hidden="true" />
                    </button>
                    <button
                      class="icon-btn"
                      type="button"
                      on:click={cancelObservationEdit}
                      title="Cancel"
                      aria-label="Cancel"
                    >
                      <CloseIcon size="1rem" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              {:else}
                {#if obs.notes}
                  <div class="detail-row"><span class="label">Session:</span>{obs.notes}</div>
                {/if}
                {#if obs.location}
                  <div class="detail-row">
                    <span class="label">Location:</span>{observationLocationLabel(obs)}
                  </div>
                {/if}
              {/if}

              <div class="objects-title-row">
                <div class="objects-title">OBJECTS</div>
                <button
                  class="icon-btn"
                  type="button"
                  on:click={(e) => onAddObjectClick(obs.date, e)}
                  title="Add object"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z" />
                  </svg>
                </button>
              </div>

              {#if addObjectState?.date === obs.date}
                <div class="add-object-box" on:pointerdown|stopPropagation>
                  <CustomInput
                    bind:this={addObjectInput}
                    bind:value={addObjectQuery}
                    placeholder="Search object to add..."
                  />
                  <div class="candidate-list">
                    {#if !addObjectQuery.trim()}
                      <div class="hint small">Type to search objects.</div>
                    {/if}
                    {#each activeCandidates as cand}
                      <button
                        class="candidate"
                        type="button"
                        on:click={() => addObjectToObservation(obs.date, cand.id)}
                      >
                        <span class="obj-symbol"><ObservationObjectSymbol kind={cand.symbolKind} /></span>
                        <span>{cand.label}</span>
                      </button>
                    {/each}
                    {#if addObjectQuery.trim() && activeCandidates.length === 0}
                      <div class="hint small">No matching objects.</div>
                    {/if}
                  </div>
                  <div class="edit-actions">
                    <button class="btn ghost small" type="button" on:click={closeAddObject}>Cancel</button>
                  </div>
                </div>
              {/if}

              {#if Array.isArray(obs.objects) && obs.objects.length > 0}
                <div class="objects-list">
                  {#each obs.objects as entry}
                    <div class="object-row" class:editing={isObjectEditing(obs.date, entry.id)}>
                      <div class="object-main">
                        <span class="obj-symbol"
                          ><ObservationObjectSymbol kind={objectSymbolKind(objectById.get(entry.id))} /></span
                        >
                        <button
                          class="object-name object-link"
                          type="button"
                          on:click={(e) => openObjectFromObservation(entry.id, e)}
                          title="Open About object"
                        >
                          {labelByObjectId.get(entry.id) || fallbackLabelFromId(entry.id)}
                        </button>
                        {#if objectDetailsLabel(entry)}
                          <span class="object-meta">{objectDetailsLabel(entry)}</span>
                        {/if}
                        <span class="object-actions">
                          <button
                            class="icon-btn"
                            type="button"
                            on:pointerup={(e) => onObjectEditClick(obs.date, entry, e)}
                            on:click={(e) => onObjectEditClick(obs.date, entry, e)}
                            title="Edit"
                          >
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                              <path
                                d="M4 20h4l10-10-4-4L4 16v4Zm12.7-12.7 1.3-1.3a1 1 0 0 1 1.4 0l.9.9a1 1 0 0 1 0 1.4L19 9.6l-2.3-2.3Z"
                              />
                            </svg>
                          </button>
                          <button
                            class="icon-btn danger"
                            type="button"
                            on:click={(e) => onObjectDeleteClick(obs.date, entry, e)}
                            title="Delete"
                          >
                            <svg viewBox="0 0 32 32" aria-hidden="true">
                              <rect x="12" y="12" width="2" height="12" />
                              <rect x="18" y="12" width="2" height="12" />
                              <path d="M4,6V8H6V28a2,2,0,0,0,2,2H24a2,2,0,0,0,2-2V8h2V6ZM8,28V8H24V28Z" />
                              <rect x="12" y="2" width="8" height="2" />
                            </svg>
                          </button>
                        </span>
                      </div>
                      {#if entry.notes}
                        <div class="object-notes">{entry.notes}</div>
                      {/if}
                    </div>
                  {/each}
                </div>

                {@const editedEntry = editedEntryForObservation(obs)}
                {#if editedEntry}
                  <div class="object-edit">
                    <div class="field-label object-edit-title">
                      Editing: {labelByObjectId.get(editedEntry.id) || fallbackLabelFromId(editedEntry.id)}
                    </div>
                    {#if objectEditError}
                      <div class="object-edit-error">{objectEditError}</div>
                    {/if}
                    {#if telescopesForSelection().length === 0}
                      <div class="hint small">No telescopes defined yet.</div>
                    {:else}
                      {#key safeStringify(objectEdit.telescopeStates)}
                        <TelescopeUsageEditor
                          telescopes={telescopesForSelection()}
                          eyepieces={eyepiecesForSelection()}
                          telescopeStates={objectEdit.telescopeStates}
                          {telescopeNeedsEyepiece}
                          onToggleTelescope={toggleObjectTelescope}
                          onToggleEyepiece={toggleObjectEyepiece}
                        />
                      {/key}
                    {/if}
                    <CustomTextarea bind:value={objectEdit.draftNotes} placeholder="Object notes..." />
                    <div class="edit-actions">
                      <button class="btn" type="button" on:click={saveObjectEdit}>Accept</button>
                      <button class="btn ghost" type="button" on:click={cancelObjectEdit}>Cancel</button>
                    </div>
                  </div>
                {/if}
              {:else}
                <div class="hint small">No objects in this observation.</div>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    {/if}
  </div>

  {#if $keyboardActive}
    <OnScreenKeyboard />
  {/if}

  <ConfirmDialog
    open={confirmOpen}
    title={confirmTitle}
    message={confirmMessage}
    confirmLabel="Delete"
    cancelLabel="Cancel"
    on:confirm={confirmDelete}
    on:cancel={cancelDelete}
  />
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 40;
    background: #000;
    color: var(--fg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.15);
    gap: 0.5rem;
  }

  .add-observation {
    margin-left: auto;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem 1rem 1rem;
  }

  .error-msg {
    margin-bottom: 0.6rem;
    border: 1px solid rgba(255, 120, 120, 0.5);
    border-radius: 6px;
    padding: 0.45rem 0.55rem;
    color: #ff9a9a;
    font-size: 0.82rem;
  }

  .obs-card {
    border: 1px solid rgba(232, 232, 232, 0.15);
    border-radius: 8px;
    margin-bottom: 0.65rem;
  }

  .obs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.45rem;
    padding: 0.45rem 0.55rem;
  }

  .obs-toggle {
    flex: 1;
    min-width: 0;
    border: none;
    background: none;
    color: var(--fg);
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: center;
    text-align: left;
    cursor: pointer;
    padding: 0;
  }

  .obs-title {
    font-size: 0.86rem;
    line-height: 1.25;
  }

  .header-actions {
    display: inline-flex;
    gap: 0.25rem;
    position: relative;
    z-index: 1;
  }

  .caret {
    opacity: 0.7;
    flex-shrink: 0;
  }

  .obs-details {
    border-top: 1px solid rgba(232, 232, 232, 0.08);
    padding: 0.45rem 0.55rem 0.6rem;
  }

  .detail-row {
    margin-bottom: 0.3rem;
    font-size: 0.8rem;
    line-height: 1.3;
  }

  .label {
    opacity: 0.75;
    margin-right: 0.35rem;
  }

  .coords {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.45rem;
  }

  .date-location-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.45rem;
  }

  .field-row {
    margin-bottom: 0.35rem;
  }

  .field-label {
    font-size: 0.74rem;
    opacity: 0.75;
    margin-bottom: 0.2rem;
  }

  .objects-title-row {
    display: flex;
    justify-content: flex-start;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.25rem;
    margin-bottom: 0.2rem;
  }

  .objects-title {
    font-size: 0.76rem;
    opacity: 0.75;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .objects-list {
    display: flex;
    flex-direction: column;
    gap: 0.14rem;
  }

  .object-row {
    border-bottom: 1px solid rgba(232, 232, 232, 0.08);
    padding: 0.18rem 0;
  }

  .object-row:last-child {
    border-bottom: none;
  }

  .object-row.editing {
    background: rgba(232, 232, 232, 0.04);
    border-radius: 4px;
  }

  .object-main {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    min-height: 1.5rem;
  }

  .obj-symbol {
    width: 1rem;
    text-align: center;
    opacity: 0.9;
    flex-shrink: 0;
  }

  .object-name {
    font-size: 0.82rem;
    font-weight: 600;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 40%;
  }

  .object-link {
    border: none;
    background: none;
    color: inherit;
    padding: 0;
    cursor: pointer;
    text-align: left;
    text-decoration: none;
  }

  .object-meta {
    font-size: 0.74rem;
    opacity: 0.72;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }

  .object-actions {
    display: inline-flex;
    gap: 0.25rem;
    margin-left: auto;
    flex-shrink: 0;
    position: relative;
    z-index: 1;
  }

  .object-notes {
    font-size: 0.78rem;
    line-height: 1.28;
    margin-top: 0.12rem;
    margin-left: 1.35rem;
    white-space: pre-wrap;
    opacity: 0.9;
  }

  .object-edit {
    margin-top: 0.22rem;
    border: 1px solid rgba(232, 232, 232, 0.16);
    border-radius: 6px;
    padding: 0.35rem;
  }

  .object-edit-title {
    margin-bottom: 0.3rem;
  }

  .object-edit-error {
    margin-bottom: 0.3rem;
    border: 1px solid rgba(255, 120, 120, 0.5);
    border-radius: 6px;
    padding: 0.35rem 0.45rem;
    color: #ff9a9a;
    font-size: 0.78rem;
  }

  .add-object-box {
    border: 1px solid rgba(232, 232, 232, 0.2);
    border-radius: 6px;
    padding: 0.35rem;
    margin-bottom: 0.3rem;
  }

  .candidate-list {
    margin-top: 0.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    max-height: 11rem;
    overflow: auto;
  }

  .candidate {
    border: 1px solid rgba(232, 232, 232, 0.25);
    background: none;
    color: var(--fg);
    border-radius: 6px;
    font-size: 0.78rem;
    padding: 0.22rem 0.4rem;
    display: flex;
    gap: 0.35rem;
    align-items: center;
    text-align: left;
    cursor: pointer;
  }

  .icon-btn {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 4px;
    width: 1.65rem;
    height: 1.65rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    line-height: 1;
  }

  .icon-btn.danger {
    border-color: rgba(220, 60, 60, 0.7);
    color: #e84a4a;
  }

  .edit-actions {
    margin-top: 0.25rem;
    display: flex;
    gap: 0.35rem;
    justify-content: flex-end;
  }

  .btn {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 6px;
    padding: 0.22rem 0.52rem;
    font-size: 0.76rem;
    cursor: pointer;
  }

  .btn.ghost {
    opacity: 0.85;
  }

  .btn.small {
    font-size: 0.74rem;
  }

  .hint {
    font-size: 0.84rem;
    opacity: 0.72;
  }

  .hint.small {
    font-size: 0.78rem;
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .obs-card {
    border-color: rgba(200, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .obs-details {
    border-top-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .object-row {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .object-row.editing {
    background: rgba(200, 0, 0, 0.08);
  }

  :global([data-theme='nightly']) .object-edit {
    border-color: rgba(200, 0, 0, 0.35);
  }

  :global([data-theme='nightly']) .icon-btn,
  :global([data-theme='nightly']) .btn,
  :global([data-theme='nightly']) .candidate,
  :global([data-theme='nightly']) .add-object-box {
    border-color: rgba(200, 0, 0, 0.55);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .icon-btn.danger {
    border-color: rgba(200, 0, 0, 0.75);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .error-msg {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff9a9a;
  }
</style>
