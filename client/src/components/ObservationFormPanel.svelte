<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import CustomInput from './CustomInput.svelte'
  import CustomTextarea from './CustomTextarea.svelte'
  import TelescopeUsageEditor from './TelescopeUsageEditor.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { keyboardActive } from '../stores/keyboard.js'
  import {
    getMeta,
    getObservationByDate,
    putObservation,
    getSyncDirtyTotalCount,
    resolveObservationDateKey,
  } from '../lib/db.js'
  import { pendingChanges } from '../stores/ui.js'

  export let objectId = ''
  export let time = new Date()

  const dispatch = createEventDispatcher()

  let dateTimeText = ''
  let locationNameText = ''
  let latText = ''
  let lonText = ''
  let sessionNotes = ''
  let objectNotes = ''

  let telescopes = []
  let eyepieces = []
  let telescopeStates = []

  let errorMsg = ''
  let saving = false

  function fmt2(n) {
    return String(n).padStart(2, '0')
  }

  function localDateTimeString(d) {
    return `${d.getFullYear()}-${fmt2(d.getMonth() + 1)}-${fmt2(d.getDate())} ${fmt2(d.getHours())}:${fmt2(d.getMinutes())}`
  }

  function parseDateTimeText(s) {
    const m = String(s)
      .trim()
      .match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?$/)
    if (!m) return null
    const y = Number(m[1])
    const mo = Number(m[2])
    const d = Number(m[3])
    const hh = Number(m[4] ?? '0')
    const mm = Number(m[5] ?? '0')
    const out = new Date(y, mo - 1, d, hh, mm, 0, 0)
    if (Number.isNaN(out.getTime())) return null
    return out
  }

  function parseMaybeNumber(s) {
    if (String(s).trim() === '') return null
    const n = Number(String(s).trim())
    return Number.isFinite(n) ? n : null
  }

  function eyepiecesForSelection() {
    return [...eyepieces].sort((a, b) =>
      String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
    )
  }

  function telescopeNeedsEyepiece(t) {
    const v = t?.needsEyepiece
    if (typeof v === 'boolean') return v
    if (typeof v === 'number') return v !== 0
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase()
      if (s === 'true' || s === '1' || s === 'yes') return true
      if (s === 'false' || s === '0' || s === 'no') return false
    }
    return !!v
  }

  function setSeen(telescopeId, seen) {
    telescopeStates = telescopeStates.map((s) => {
      if (s.telescopeId !== telescopeId) return s
      return {
        ...s,
        seen,
        eyepieceIds: seen === true ? s.eyepieceIds || [] : [],
      }
    })
  }

  function toggleTelescope(telescopeId) {
    const state = telescopeStates.find((s) => s.telescopeId === telescopeId)
    const nextSeen = state?.seen === true ? null : true
    setSeen(telescopeId, nextSeen)
  }

  function toggleEyepiece(telescopeId, eyepieceId) {
    telescopeStates = telescopeStates.map((s) => {
      if (s.telescopeId !== telescopeId) return s
      const current = Array.isArray(s.eyepieceIds) ? s.eyepieceIds : []
      const exists = current.includes(eyepieceId)
      return {
        ...s,
        eyepieceIds: exists ? current.filter((id) => id !== eyepieceId) : [...current, eyepieceId],
      }
    })
  }

  function clearLocation() {
    latText = ''
    lonText = ''
  }

  async function loadInitialState() {
    dateTimeText = localDateTimeString(time)

    const [savedTelescopes, savedEyepieces] = await Promise.all([getMeta('telescopes'), getMeta('eyepieces')])
    telescopes = Array.isArray(savedTelescopes)
      ? [...savedTelescopes].sort((a, b) =>
          String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
        )
      : []
    eyepieces = Array.isArray(savedEyepieces) ? savedEyepieces : []

    telescopeStates = telescopes.map((t) => ({
      telescopeId: t.id,
      seen: null,
      eyepieceIds: [],
    }))

    const selectedKey = await resolveObservationDateKey(time)
    const selectedObservation = await getObservationByDate(selectedKey)
    if (selectedObservation?.location?.name) locationNameText = String(selectedObservation.location.name)
    const existingObject = selectedObservation?.objects?.find((o) => o.id === objectId)
    if (existingObject) {
      objectNotes = existingObject.notes || ''
      if (Array.isArray(existingObject.telescopeResults)) {
        const byId = new Map(existingObject.telescopeResults.map((r) => [r.telescopeId, r]))
        telescopeStates = telescopeStates.map((s) => {
          const r = byId.get(s.telescopeId)
          if (!r) return s
          return {
            ...s,
            seen: typeof r.seen === 'boolean' ? r.seen : null,
            eyepieceIds: Array.isArray(r.eyepieceIds) ? r.eyepieceIds : r.eyepieceId ? [r.eyepieceId] : [],
          }
        })
      }
    }

    if (selectedObservation?.notes) sessionNotes = selectedObservation.notes

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          latText = String(Number(pos.coords.latitude).toFixed(5))
          lonText = String(Number(pos.coords.longitude).toFixed(5))
        },
        () => {
          // ignored; location can be entered manually or cleared
        },
        { timeout: 5000 },
      )
    }
  }

  async function save() {
    if (saving) return
    errorMsg = ''

    const dt = parseDateTimeText(dateTimeText)
    if (!dt) {
      errorMsg = 'Date/time must be in YYYY-MM-DD HH:MM format.'
      return
    }

    const dateKey = await resolveObservationDateKey(dt)
    const lat = parseMaybeNumber(latText)
    const lon = parseMaybeNumber(lonText)
    const locationName = String(locationNameText || '').trim()
    let location = lat != null && lon != null ? { lat, lon } : null
    if (locationName) location = { ...(location || {}), name: locationName }

    for (const s of telescopeStates) {
      const t = telescopes.find((x) => x.id === s.telescopeId)
      if (!telescopeNeedsEyepiece(t)) continue
      if (s.seen !== true) continue
      if (!Array.isArray(s.eyepieceIds) || s.eyepieceIds.length === 0) {
        errorMsg = `Select at least one option for ${t.name}.`
        return
      }
    }

    const telescopeResults = telescopeStates
      .filter((s) => s.seen === true || s.seen === false)
      .map((s) => {
        const t = telescopes.find((x) => x.id === s.telescopeId)
        const needsEyepiece = telescopeNeedsEyepiece(t)
        const selectedIds = Array.isArray(s.eyepieceIds) ? s.eyepieceIds : []
        return {
          telescopeId: s.telescopeId,
          seen: s.seen,
          eyepieceIds: s.seen === true && needsEyepiece ? selectedIds : [],
          eyepieceId: s.seen === true && needsEyepiece && selectedIds.length > 0 ? selectedIds[0] : null,
        }
      })

    saving = true
    try {
      const existing = (await getObservationByDate(dateKey)) || {
        date: dateKey,
        location: null,
        objects: [],
        startedAt: dt.toISOString(),
      }

      const priorEntry = (existing.objects || []).find((o) => o.id === objectId)
      const objectEntry = {
        id: objectId,
        telescopeResults,
        notes: objectNotes.trim(),
        loggedAt: priorEntry?.loggedAt ?? dt.toISOString(),
      }

      const others = (existing.objects || []).filter((o) => o.id !== objectId)
      const nextRecord = {
        ...existing,
        date: dateKey,
        location,
        notes: sessionNotes.trim(),
        objects: [...others, objectEntry],
        startedAt: existing.startedAt ?? dt.toISOString(),
      }

      await putObservation(nextRecord)
      pendingChanges.set(await getSyncDirtyTotalCount())
      dispatch('saved')
    } catch (err) {
      errorMsg = err?.message || 'Failed to save observation.'
    } finally {
      saving = false
    }
  }

  onMount(async () => {
    await loadInitialState()
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" on:click={() => dispatch('cancel')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Observation</span>
  </div>

  <div class="content">
    {#if errorMsg}
      <div class="error">{errorMsg}</div>
    {/if}

    <section class="section">
      <div class="date-location-row">
        <div class="field">
          <div class="label">Date & time</div>
          <CustomInput bind:value={dateTimeText} placeholder="YYYY-MM-DD HH:MM" />
        </div>

        <div class="field">
          <div class="label">Location name</div>
          <CustomInput bind:value={locationNameText} placeholder="City / site name" />
        </div>
      </div>

      <div class="field">
        <div class="label">Location (GPS)</div>
        <div class="coords">
          <CustomInput bind:value={latText} placeholder="Latitude" />
          <CustomInput bind:value={lonText} placeholder="Longitude" />
        </div>
        <button class="btn ghost" on:click={clearLocation}>Clear location</button>
      </div>
    </section>

    <section class="section">
      <div class="section-title">Telescopes</div>
      {#key JSON.stringify(telescopeStates)}
        <TelescopeUsageEditor
          {telescopes}
          eyepieces={eyepiecesForSelection()}
          {telescopeStates}
          {telescopeNeedsEyepiece}
          onToggleTelescope={toggleTelescope}
          onToggleEyepiece={toggleEyepiece}
        />
      {/key}
    </section>

    <section class="section">
      <div class="field">
        <div class="label">Observation details</div>
        <CustomTextarea bind:value={sessionNotes} placeholder="Weather, seeing conditions, transparency..." />
      </div>
      <div class="field">
        <div class="label">Object details</div>
        <CustomTextarea
          bind:value={objectNotes}
          placeholder="How the object looked, what helped, notable features..."
        />
      </div>
    </section>

    <div class="footer-actions">
      <button class="btn" on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </div>

  {#if $keyboardActive}
    <OnScreenKeyboard />
  {/if}
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
    gap: 0.35rem;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    padding: 0.25rem 0.15rem 0.25rem 0.5rem;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem 1rem 9.5rem;
  }

  .error {
    margin-bottom: 0.75rem;
    padding: 0.5rem;
    border-radius: 6px;
    border: 1px solid rgba(255, 120, 120, 0.5);
    background: rgba(255, 80, 80, 0.08);
    color: #ff9a9a;
    font-size: 0.85rem;
  }

  .section {
    border: 1px solid rgba(232, 232, 232, 0.15);
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 0.8rem;
  }

  .section-title {
    font-size: 0.82rem;
    opacity: 0.7;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.45rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    margin-bottom: 0.55rem;
  }

  .field:last-child {
    margin-bottom: 0;
  }

  .label {
    font-size: 0.78rem;
    opacity: 0.75;
  }

  .coords {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .date-location-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .footer-actions {
    display: flex;
    justify-content: flex-end;
  }

  .btn {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 6px;
    padding: 0.35rem 0.65rem;
    font-size: 0.8rem;
    cursor: pointer;
  }

  .btn.ghost {
    opacity: 0.8;
    width: fit-content;
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .section {
    border-color: rgba(200, 0, 0, 0.25);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }
</style>
