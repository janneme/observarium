<script>
  import { onMount } from 'svelte'
  import { get } from 'svelte/store'
  import { getMeta, setMeta, getAllObservations, markDirty, getSyncDirtyTotalCount } from '../lib/db.js'
  import CustomInput from '../components/CustomInput.svelte'
  import CustomCheckbox from '../components/CustomCheckbox.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import { keyboardActive } from '../stores/keyboard.js'
  import { pendingChanges, fovCircleInstrument, finderInstrument } from '../stores/ui.js'
  import EditIcon from '../icons/EditIcon.svelte'
  import DeleteIcon from '../icons/DeleteIcon.svelte'
  import BackIcon from '../icons/BackIcon.svelte'

  export let onClose = () => {}

  let telescopes = []
  let eyepieces = []

  let telescopesExpanded = true
  let eyepiecesExpanded = true

  let warningMsg = ''
  let saveMsg = ''

  let newTelescope = { name: '', focalLengthMm: '', diameterInches: '', needsEyepiece: true }
  let newEyepiece = { name: '', focalLengthMm: '', fovDeg: '' }

  let editingTelescopeId = null
  let editingEyepieceId = null
  let telescopeDraft = null
  let eyepieceDraft = null
  let confirmOpen = false
  let confirmTitle = 'Confirm'
  let confirmMessage = ''
  let pendingDelete = null

  // Telescopes by aperture ascending, eyepieces by focal length descending
  // (i.e. widest field / lowest magnification first) - applied everywhere
  // these lists are shown or picked from.
  function sortTelescopes(items) {
    return [...items].sort((a, b) => (a.diameterInches ?? 0) - (b.diameterInches ?? 0))
  }

  function sortEyepieces(items) {
    return [...items].sort((a, b) => (b.focalLengthMm ?? 0) - (a.focalLengthMm ?? 0))
  }

  function newUuid() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
    return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
  }

  function parseNumber(raw) {
    const v = Number(String(raw ?? '').trim())
    return Number.isFinite(v) ? v : null
  }

  function clearMessages() {
    warningMsg = ''
    saveMsg = ''
  }

  async function loadData() {
    const [savedTelescopes, savedEyepieces] = await Promise.all([getMeta('telescopes'), getMeta('eyepieces')])
    telescopes = sortTelescopes(Array.isArray(savedTelescopes) ? savedTelescopes : [])
    eyepieces = sortEyepieces(Array.isArray(savedEyepieces) ? savedEyepieces : [])
  }

  async function persistTelescopes() {
    await setMeta('telescopes', telescopes)
  }

  async function persistEyepieces() {
    await setMeta('eyepieces', eyepieces)
  }

  async function markTelescopeDirty(id, op) {
    await markDirty('telescopes', id, op)
    pendingChanges.set(await getSyncDirtyTotalCount())
  }

  async function markEyepieceDirty(id, op) {
    await markDirty('eyepieces', id, op)
    pendingChanges.set(await getSyncDirtyTotalCount())
  }

  async function inUseIds() {
    const observations = await getAllObservations()
    const telescopeIds = new Set()
    const eyepieceIds = new Set()

    for (const obs of observations) {
      if (!Array.isArray(obs?.objects)) continue
      for (const entry of obs.objects) {
        if (entry?.telescopeId) telescopeIds.add(entry.telescopeId)
        if (entry?.eyepieceId) eyepieceIds.add(entry.eyepieceId)
        if (!Array.isArray(entry?.telescopeResults)) continue
        for (const result of entry.telescopeResults) {
          if (result?.telescopeId) telescopeIds.add(result.telescopeId)
          if (result?.eyepieceId) eyepieceIds.add(result.eyepieceId)
          if (Array.isArray(result?.eyepieceIds)) {
            for (const id of result.eyepieceIds) {
              if (id) eyepieceIds.add(id)
            }
          }
        }
      }
    }

    return { telescopeIds, eyepieceIds }
  }

  async function addTelescope() {
    clearMessages()
    const name = newTelescope.name.trim()
    const focalLengthMm = parseNumber(newTelescope.focalLengthMm)
    const diameterInches = parseNumber(newTelescope.diameterInches)
    if (!name || focalLengthMm == null || diameterInches == null) {
      warningMsg = 'Fill telescope name, focal length (mm), and diameter (inches).'
      return
    }
    const item = {
      id: newUuid(),
      name,
      focalLengthMm,
      diameterInches,
      needsEyepiece: !!newTelescope.needsEyepiece,
      updatedAt: new Date().toISOString(),
    }
    telescopes = sortTelescopes([...telescopes, item])
    await persistTelescopes()
    await markTelescopeDirty(item.id, 'upsert')
    saveMsg = 'Telescope added.'
    newTelescope = { name: '', focalLengthMm: '', diameterInches: '', needsEyepiece: true }
  }

  async function addEyepiece() {
    clearMessages()
    const name = newEyepiece.name.trim()
    const focalLengthMm = parseNumber(newEyepiece.focalLengthMm)
    const fovDeg = parseNumber(newEyepiece.fovDeg)
    if (!name || focalLengthMm == null || fovDeg == null) {
      warningMsg = 'Fill eyepiece name, focal length (mm), and FOV (degrees).'
      return
    }
    const item = { id: newUuid(), name, focalLengthMm, fovDeg, updatedAt: new Date().toISOString() }
    eyepieces = sortEyepieces([...eyepieces, item])
    await persistEyepieces()
    await markEyepieceDirty(item.id, 'upsert')
    saveMsg = 'Eyepiece added.'
    newEyepiece = { name: '', focalLengthMm: '', fovDeg: '' }
  }

  function editTelescope(item) {
    clearMessages()
    editingTelescopeId = item.id
    telescopeDraft = {
      name: item.name,
      focalLengthMm: String(item.focalLengthMm ?? ''),
      diameterInches: String(item.diameterInches ?? ''),
      needsEyepiece: !!item.needsEyepiece,
    }
  }

  function cancelEditTelescope() {
    editingTelescopeId = null
    telescopeDraft = null
  }

  async function saveEditTelescope(itemId) {
    clearMessages()
    const name = telescopeDraft.name.trim()
    const focalLengthMm = parseNumber(telescopeDraft.focalLengthMm)
    const diameterInches = parseNumber(telescopeDraft.diameterInches)
    if (!name || focalLengthMm == null || diameterInches == null) {
      warningMsg = 'Fill telescope name, focal length (mm), and diameter (inches).'
      return
    }
    telescopes = sortTelescopes(
      telescopes.map((t) =>
        t.id === itemId
          ? {
              ...t,
              name,
              focalLengthMm,
              diameterInches,
              needsEyepiece: !!telescopeDraft.needsEyepiece,
              updatedAt: new Date().toISOString(),
            }
          : t,
      ),
    )
    await persistTelescopes()
    await markTelescopeDirty(itemId, 'upsert')
    saveMsg = 'Telescope updated.'
    cancelEditTelescope()
  }

  function editEyepiece(item) {
    clearMessages()
    editingEyepieceId = item.id
    eyepieceDraft = {
      name: item.name,
      focalLengthMm: String(item.focalLengthMm ?? ''),
      fovDeg: String(item.fovDeg ?? ''),
    }
  }

  function cancelEditEyepiece() {
    editingEyepieceId = null
    eyepieceDraft = null
  }

  async function saveEditEyepiece(itemId) {
    clearMessages()
    const name = eyepieceDraft.name.trim()
    const focalLengthMm = parseNumber(eyepieceDraft.focalLengthMm)
    const fovDeg = parseNumber(eyepieceDraft.fovDeg)
    if (!name || focalLengthMm == null || fovDeg == null) {
      warningMsg = 'Fill eyepiece name, focal length (mm), and FOV (degrees).'
      return
    }
    eyepieces = sortEyepieces(
      eyepieces.map((e) =>
        e.id === itemId ? { ...e, name, focalLengthMm, fovDeg, updatedAt: new Date().toISOString() } : e,
      ),
    )
    await persistEyepieces()
    await markEyepieceDirty(itemId, 'upsert')
    saveMsg = 'Eyepiece updated.'
    cancelEditEyepiece()
  }

  async function requestDeleteTelescope(item) {
    clearMessages()
    const { telescopeIds } = await inUseIds()
    if (telescopeIds.has(item.id)) {
      warningMsg = 'This telescope is used in observations and cannot be deleted.'
      return
    }
    pendingDelete = { kind: 'telescope', item }
    confirmTitle = 'Delete telescope'
    confirmMessage = `Delete telescope "${item.name}"?`
    confirmOpen = true
  }

  // Clears a persisted telescope/eyepiece selection (FOV circle, Finder
  // telescope view) if it refers to an id that no longer exists, since a
  // half-valid pair (only one of the two ids still real) can't render a
  // real view either way.
  function clearStaleInstrumentSelections(deletedId) {
    const fovSel = get(fovCircleInstrument)
    if (fovSel.telescopeId === deletedId || fovSel.eyepieceId === deletedId) {
      fovCircleInstrument.set({ mode: 'finder', telescopeId: null, eyepieceId: null })
    }
    const finderSel = get(finderInstrument)
    if (finderSel.telescopeId === deletedId || finderSel.eyepieceId === deletedId) {
      finderInstrument.set({ telescopeId: null, eyepieceId: null })
    }
  }

  async function deleteTelescope(item) {
    telescopes = sortTelescopes(telescopes.filter((t) => t.id !== item.id))
    await persistTelescopes()
    await markTelescopeDirty(item.id, 'delete')
    clearStaleInstrumentSelections(item.id)
    saveMsg = 'Telescope deleted.'
    if (editingTelescopeId === item.id) cancelEditTelescope()
  }

  async function requestDeleteEyepiece(item) {
    clearMessages()
    const { eyepieceIds } = await inUseIds()
    if (eyepieceIds.has(item.id)) {
      warningMsg = 'This eyepiece is used in observations and cannot be deleted.'
      return
    }
    pendingDelete = { kind: 'eyepiece', item }
    confirmTitle = 'Delete eyepiece'
    confirmMessage = `Delete eyepiece "${item.name}"?`
    confirmOpen = true
  }

  async function deleteEyepiece(item) {
    eyepieces = sortEyepieces(eyepieces.filter((e) => e.id !== item.id))
    await persistEyepieces()
    await markEyepieceDirty(item.id, 'delete')
    clearStaleInstrumentSelections(item.id)
    saveMsg = 'Eyepiece deleted.'
    if (editingEyepieceId === item.id) cancelEditEyepiece()
  }

  function cancelConfirm() {
    confirmOpen = false
    pendingDelete = null
  }

  async function confirmDelete() {
    if (!pendingDelete) {
      cancelConfirm()
      return
    }
    const { kind, item } = pendingDelete
    cancelConfirm()
    if (kind === 'telescope') await deleteTelescope(item)
    else await deleteEyepiece(item)
  }

  onMount(async () => {
    await loadData()
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" on:click={onClose} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Telescopes</span>
  </div>

  <div class="content">
    {#if warningMsg}
      <div class="msg warning">{warningMsg}</div>
    {/if}
    {#if saveMsg}
      <div class="msg success">{saveMsg}</div>
    {/if}

    <section class="section">
      <button class="section-title" on:click={() => (telescopesExpanded = !telescopesExpanded)}>
        <span>Telescopes ({telescopes.length})</span>
        <span>{telescopesExpanded ? '▾' : '▸'}</span>
      </button>

      {#if telescopesExpanded}
        <div class="list">
          {#each telescopes as t}
            <div class="item">
              {#if editingTelescopeId === t.id}
                <div class="form-grid edit-box">
                  <div class="field">
                    <div class="field-label">Name</div>
                    <CustomInput bind:value={telescopeDraft.name} placeholder="Name" />
                  </div>
                  <div class="field">
                    <div class="field-label">Focal length (mm)</div>
                    <CustomInput bind:value={telescopeDraft.focalLengthMm} placeholder="Focal length (mm)" />
                  </div>
                  <div class="field">
                    <div class="field-label">Diameter (inches)</div>
                    <CustomInput bind:value={telescopeDraft.diameterInches} placeholder="Diameter (inches)" />
                  </div>
                  <CustomCheckbox bind:checked={telescopeDraft.needsEyepiece} label="Needs eyepiece" />
                  <div class="actions">
                    <button class="btn" on:click={() => saveEditTelescope(t.id)}>Save</button>
                    <button class="btn ghost" on:click={cancelEditTelescope}>Cancel</button>
                  </div>
                </div>
              {:else}
                <div class="item-head">
                  <div class="item-main">
                    <div class="item-title">{t.name}</div>
                    <div class="item-meta">
                      {t.focalLengthMm} mm · {t.diameterInches}" · {t.needsEyepiece ? 'needs eyepiece' : 'no eyepiece'}
                    </div>
                  </div>
                  <div class="icon-actions">
                    <button class="icon-btn" on:click={() => editTelescope(t)} aria-label="Edit telescope" title="Edit">
                      <EditIcon size="0.9rem" aria-hidden="true" />
                    </button>
                    <button
                      class="icon-btn danger"
                      on:click={() => requestDeleteTelescope(t)}
                      aria-label="Delete telescope"
                      title="Delete"
                    >
                      <DeleteIcon size="0.9rem" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              {/if}
            </div>
          {/each}
        </div>

        <div class="form-grid add-box">
          <div class="add-title">Add telescope</div>
          <div class="field">
            <div class="field-label">Name</div>
            <CustomInput bind:value={newTelescope.name} placeholder="Name" />
          </div>
          <div class="field">
            <div class="field-label">Focal length (mm)</div>
            <CustomInput bind:value={newTelescope.focalLengthMm} placeholder="Focal length (mm)" />
          </div>
          <div class="field">
            <div class="field-label">Diameter (inches)</div>
            <CustomInput bind:value={newTelescope.diameterInches} placeholder="Diameter (inches)" />
          </div>
          <CustomCheckbox bind:checked={newTelescope.needsEyepiece} label="Needs eyepiece" />
          <div class="actions"><button class="btn" on:click={addTelescope}>Add</button></div>
        </div>
      {/if}
    </section>

    <section class="section">
      <button class="section-title" on:click={() => (eyepiecesExpanded = !eyepiecesExpanded)}>
        <span>Eyepieces ({eyepieces.length})</span>
        <span>{eyepiecesExpanded ? '▾' : '▸'}</span>
      </button>

      {#if eyepiecesExpanded}
        <div class="list">
          {#each eyepieces as e}
            <div class="item">
              {#if editingEyepieceId === e.id}
                <div class="form-grid edit-box">
                  <div class="field">
                    <div class="field-label">Name</div>
                    <CustomInput bind:value={eyepieceDraft.name} placeholder="Name" />
                  </div>
                  <div class="field">
                    <div class="field-label">Focal length (mm)</div>
                    <CustomInput bind:value={eyepieceDraft.focalLengthMm} placeholder="Focal length (mm)" />
                  </div>
                  <div class="field">
                    <div class="field-label">FOV (degrees)</div>
                    <CustomInput bind:value={eyepieceDraft.fovDeg} placeholder="FOV (degrees)" />
                  </div>
                  <div class="actions">
                    <button class="btn" on:click={() => saveEditEyepiece(e.id)}>Save</button>
                    <button class="btn ghost" on:click={cancelEditEyepiece}>Cancel</button>
                  </div>
                </div>
              {:else}
                <div class="item-head">
                  <div class="item-main">
                    <div class="item-title">{e.name}</div>
                    <div class="item-meta">{e.focalLengthMm} mm · {e.fovDeg}°</div>
                  </div>
                  <div class="icon-actions">
                    <button class="icon-btn" on:click={() => editEyepiece(e)} aria-label="Edit eyepiece" title="Edit">
                      <EditIcon size="0.9rem" aria-hidden="true" />
                    </button>
                    <button
                      class="icon-btn danger"
                      on:click={() => requestDeleteEyepiece(e)}
                      aria-label="Delete eyepiece"
                      title="Delete"
                    >
                      <DeleteIcon size="0.9rem" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              {/if}
            </div>
          {/each}
        </div>

        <div class="form-grid add-box">
          <div class="add-title">Add eyepiece</div>
          <div class="field">
            <div class="field-label">Name</div>
            <CustomInput bind:value={newEyepiece.name} placeholder="Name" />
          </div>
          <div class="field">
            <div class="field-label">Focal length (mm)</div>
            <CustomInput bind:value={newEyepiece.focalLengthMm} placeholder="Focal length (mm)" />
          </div>
          <div class="field">
            <div class="field-label">FOV (degrees)</div>
            <CustomInput bind:value={newEyepiece.fovDeg} placeholder="FOV (degrees)" />
          </div>
          <div class="actions"><button class="btn" on:click={addEyepiece}>Add</button></div>
        </div>
      {/if}
    </section>
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
    on:cancel={cancelConfirm}
  />
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 12;
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
    padding: 0.75rem 1rem 6.5rem;
  }

  .msg {
    font-size: 0.85rem;
    margin-bottom: 0.75rem;
    padding: 0.45rem 0.55rem;
    border-radius: 6px;
  }

  .msg.warning {
    color: #ff9a9a;
    border: 1px solid rgba(255, 154, 154, 0.5);
    background: rgba(255, 80, 80, 0.08);
  }

  .msg.success {
    color: #9ad1ff;
    border: 1px solid rgba(154, 209, 255, 0.4);
    background: rgba(90, 160, 255, 0.09);
  }

  .section {
    margin-bottom: 1.25rem;
    border: 1px solid rgba(232, 232, 232, 0.1);
    border-radius: 8px;
    overflow: hidden;
  }

  .section-title {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border: none;
    background: rgba(232, 232, 232, 0.04);
    color: var(--fg);
    font-size: 0.9rem;
    padding: 0.65rem 0.75rem;
    cursor: pointer;
  }

  .list {
    display: flex;
    flex-direction: column;
  }

  .item {
    border-top: 1px solid rgba(232, 232, 232, 0.08);
    padding: 0.65rem 0.75rem;
  }

  .item-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .item-main {
    min-width: 0;
  }

  .item-title {
    font-size: 0.95rem;
    font-weight: 600;
  }

  .item-meta {
    font-size: 0.78rem;
    opacity: 0.72;
    margin-top: 0.15rem;
  }

  .form-grid {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .field-label {
    font-size: 0.78rem;
    opacity: 0.72;
  }

  .add-box {
    border: 1px solid rgba(232, 232, 232, 0.2);
    border-radius: 8px;
    padding: 0.75rem;
    margin: 0.75rem;
    background: rgba(232, 232, 232, 0.02);
  }

  .edit-box {
    border: 1px solid rgba(232, 232, 232, 0.2);
    border-radius: 8px;
    padding: 0.75rem;
    background: rgba(232, 232, 232, 0.02);
  }

  .add-title {
    font-size: 0.8rem;
    opacity: 0.7;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.15rem;
  }

  .actions {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
  }

  .icon-actions {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
  }

  .icon-btn {
    width: 1.75rem;
    height: 1.75rem;
    border: 1px solid rgba(232, 232, 232, 0.35);
    border-radius: 6px;
    background: none;
    color: var(--fg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
  }

  .icon-btn.danger {
    border-color: rgba(255, 120, 120, 0.5);
    color: #ff9a9a;
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
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .section {
    border-color: rgba(200, 0, 0, 0.22);
  }

  :global([data-theme='nightly']) .section-title {
    background: rgba(200, 0, 0, 0.1);
  }

  :global([data-theme='nightly']) .item {
    border-top-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .add-box {
    border-color: rgba(200, 0, 0, 0.35);
    border-top-color: rgba(200, 0, 0, 0.2);
    background: rgba(200, 0, 0, 0.06);
  }

  :global([data-theme='nightly']) .edit-box {
    border-color: rgba(200, 0, 0, 0.35);
    background: rgba(200, 0, 0, 0.06);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .icon-btn {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .icon-btn.danger {
    border-color: rgba(255, 120, 120, 0.55);
    color: #ff9a9a;
  }
</style>
