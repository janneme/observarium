<script>
  import { onMount } from 'svelte'
  import { getObjectsByIds } from '../lib/db.js'
  import {
    getAllLists,
    saveList,
    deleteList,
    renameList,
    setListActive,
    addObjectToList,
    removeObjectFromList,
    updateListObjectNote,
    reorderListObject,
    newListId,
  } from '../lib/lists.js'
  import { computeListDifficultyOrder } from '../lib/listDifficulty.js'
  import { keyboardActive } from '../stores/keyboard.js'
  import CustomInput from '../components/CustomInput.svelte'
  import CustomTextarea from '../components/CustomTextarea.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import PlusIcon from '../icons/PlusIcon.svelte'
  import EditIcon from '../icons/EditIcon.svelte'
  import DeleteIcon from '../icons/DeleteIcon.svelte'
  import AcceptIcon from '../icons/AcceptIcon.svelte'
  import CloseIcon from '../icons/CloseIcon.svelte'
  import MoveUpIcon from '../icons/MoveUpIcon.svelte'
  import MoveDownIcon from '../icons/MoveDownIcon.svelte'
  import ObservedIcon from '../icons/ObservedIcon.svelte'
  import StrikeOverlayIcon from '../icons/StrikeOverlayIcon.svelte'

  export let onClose = () => {}

  const SORT_TYPES = [
    { key: 'name', label: 'Name' },
    { key: 'difficulty', label: 'Difficulty' },
    { key: 'manual', label: 'Manual' },
  ]

  let lists = []
  let objectById = new Map()
  let expandedListIds = new Set()
  let loading = true
  let errorMsg = ''

  let showAddForm = false
  let newListDraft = { name: '', sortType: 'name' }

  let editingListId = null
  let listNameDraft = ''

  let addObjectListId = null

  let objectEdit = null // { listId, objectId, draftNote }

  let confirmOpen = false
  let confirmTitle = 'Confirm'
  let confirmMessage = ''
  let pendingAction = null

  function sortListsByName(items) {
    return [...items].sort((a, b) =>
      String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' }),
    )
  }

  function fallbackLabelFromId(id) {
    const raw = String(id || '')
    if (raw.startsWith('dso_M')) return `M ${Number(raw.slice(5))}`
    if (raw.startsWith('dso_NGC')) return `NGC ${Number(raw.slice(7))}`
    if (raw.startsWith('dso_IC')) return `IC ${Number(raw.slice(6))}`
    return raw || 'Unknown object'
  }

  function dsoCatalogueLabel(obj) {
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    return fallbackLabelFromId(obj.id)
  }

  function starLabel(obj) {
    if (obj.name) return obj.name
    if (obj.bay && obj.constellation) return `${obj.bay} ${obj.constellation}`
    if (obj.flam && obj.constellation) return `${obj.flam} ${obj.constellation}`
    if (obj.hip) return `HIP ${obj.hip}`
    if (obj.hd) return `HD ${obj.hd}`
    if (obj.wds) return `WDS ${obj.wds}`
    return fallbackLabelFromId(obj.id)
  }

  // Star (incl. double star): bold name-or-catalogue. DSO: bold catalogue
  // number, plus the name in parens when it has one. See lists.md §2.
  function listObjectLabel(obj) {
    if (!obj) return { bold: 'Unknown object', rest: '' }
    if (obj.type === 'dso') {
      const cat = dsoCatalogueLabel(obj)
      return { bold: cat, rest: obj.name ? ` (${obj.name})` : '' }
    }
    return { bold: starLabel(obj), rest: '' }
  }

  function labelSortKey(obj) {
    const { bold, rest } = listObjectLabel(obj)
    return `${bold}${rest}`
  }

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs) for (const c of String(p.comp || '')) if (c >= 'A' && c <= 'Z') letters.add(c)
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

  function clearMessages() {
    errorMsg = ''
  }

  async function loadObjectsFor(lists_) {
    const allIds = new Set()
    for (const list of lists_) for (const entry of list.objects || []) allIds.add(entry.id)
    const found = await getObjectsByIds([...allIds])
    objectById = found
  }

  async function loadData() {
    const raw = await getAllLists()
    lists = sortListsByName(raw)
    await loadObjectsFor(lists)
    loading = false
  }

  onMount(async () => {
    await loadData()
  })

  function toggleExpand(listId) {
    const next = new Set(expandedListIds)
    if (next.has(listId)) next.delete(listId)
    else next.add(listId)
    expandedListIds = next
  }

  function openAddForm() {
    clearMessages()
    newListDraft = { name: '', sortType: 'name' }
    showAddForm = true
  }

  function cancelAddForm() {
    showAddForm = false
  }

  async function submitAddForm() {
    const name = newListDraft.name.trim()
    if (!name) {
      errorMsg = 'Enter a list name.'
      return
    }
    await saveList({ id: newListId(), name, sortType: newListDraft.sortType, active: false, objects: [] })
    lists = sortListsByName(await getAllLists())
    showAddForm = false
  }

  function startEditListName(list) {
    clearMessages()
    editingListId = list.id
    listNameDraft = list.name
  }

  function cancelEditListName() {
    editingListId = null
    listNameDraft = ''
  }

  async function saveEditListName() {
    const name = listNameDraft.trim()
    if (!name) {
      cancelEditListName()
      return
    }
    await renameList(editingListId, name)
    lists = sortListsByName(await getAllLists())
    cancelEditListName()
  }

  async function toggleActive(list) {
    await setListActive(list.id, !list.active)
    lists = sortListsByName(await getAllLists())
  }

  function requestDeleteList(list) {
    pendingAction = { kind: 'list', list }
    confirmTitle = 'Delete list'
    confirmMessage = `Delete list "${list.name}"?`
    confirmOpen = true
  }

  function requestDeleteObject(list, entry) {
    pendingAction = { kind: 'object', list, entry }
    confirmTitle = 'Remove object'
    confirmMessage = `Remove ${labelSortKey(objectById.get(entry.id))} from "${list.name}"?`
    confirmOpen = true
  }

  function cancelConfirm() {
    confirmOpen = false
    pendingAction = null
  }

  async function confirmAction() {
    if (!pendingAction) {
      cancelConfirm()
      return
    }
    const action = pendingAction
    cancelConfirm()
    if (action.kind === 'list') {
      await deleteList(action.list.id)
      lists = sortListsByName(await getAllLists())
    } else {
      await removeObjectFromList(action.list.id, action.entry.id)
      lists = sortListsByName(await getAllLists())
    }
  }

  function openAddObject(listId) {
    clearMessages()
    addObjectListId = listId
  }

  function closeAddObject() {
    addObjectListId = null
  }

  async function onAcceptSearchObject(obj) {
    if (!addObjectListId) return
    await addObjectToList(addObjectListId, obj.id)
    if (!objectById.has(obj.id)) objectById = new Map(objectById).set(obj.id, obj)
    lists = sortListsByName(await getAllLists())
    closeAddObject()
  }

  function existingIdsForList(listId) {
    const list = lists.find((l) => l.id === listId)
    return new Set((list?.objects || []).map((o) => o.id))
  }

  function startEditNote(listId, entry) {
    clearMessages()
    objectEdit = { listId, objectId: entry.id, draftNote: entry.note || '' }
  }

  function cancelEditNote() {
    objectEdit = null
  }

  async function saveEditNote() {
    const { listId, objectId, draftNote } = objectEdit
    await updateListObjectNote(listId, objectId, draftNote.trim())
    lists = sortListsByName(await getAllLists())
    cancelEditNote()
  }

  async function moveObject(listId, objectId, direction) {
    await reorderListObject(listId, objectId, direction)
    lists = sortListsByName(await getAllLists())
  }

  function sortedObjectEntries(list) {
    const entries = Array.isArray(list.objects) ? list.objects : []
    if (list.sortType === 'manual') return entries
    if (list.sortType === 'difficulty') {
      const withObj = entries.map((e) => ({ entry: e, obj: objectById.get(e.id) })).filter((x) => x.obj)
      const withoutObj = entries.filter((e) => !objectById.get(e.id))
      const ordered = computeListDifficultyOrder(withObj.map((x) => x.obj))
      const entryByObjId = new Map(withObj.map((x) => [x.obj.id, x.entry]))
      return [...ordered.map((obj) => entryByObjId.get(obj.id)), ...withoutObj]
    }
    // name
    return [...entries].sort((a, b) =>
      labelSortKey(objectById.get(a.id)).localeCompare(labelSortKey(objectById.get(b.id)), undefined, {
        sensitivity: 'base',
      }),
    )
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={onClose} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Lists</span>
    <button class="icon-btn add-list" type="button" on:click={openAddForm} title="Add list">
      <PlusIcon size="1rem" aria-hidden="true" />
    </button>
  </div>

  <div class="content">
    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    {#if showAddForm}
      <div class="add-list-box">
        <div class="field-row">
          <div class="field-label">List name</div>
          <CustomInput bind:value={newListDraft.name} placeholder="List name" />
        </div>
        <div class="field-row">
          <div class="field-label">Sort type</div>
          <div class="pills">
            {#each SORT_TYPES as opt}
              <button
                class="pill"
                class:selected={newListDraft.sortType === opt.key}
                type="button"
                on:click={() => (newListDraft = { ...newListDraft, sortType: opt.key })}
              >
                {opt.label}
              </button>
            {/each}
          </div>
        </div>
        <div class="edit-actions">
          <button class="btn" type="button" on:click={submitAddForm}>Add</button>
          <button class="btn ghost" type="button" on:click={cancelAddForm}>Cancel</button>
        </div>
      </div>
    {/if}

    {#if loading}
      <div class="hint">Loading...</div>
    {:else if lists.length === 0}
      <div class="hint">No lists yet.</div>
    {:else}
      {#each lists as list (list.id)}
        <section class="list-card">
          <div class="list-header">
            {#if editingListId === list.id}
              <span class="list-toggle">
                <span class="caret">{expandedListIds.has(list.id) ? '▾' : '▸'}</span>
                <span class="list-name-edit">
                  <CustomInput bind:value={listNameDraft} placeholder="List name" />
                </span>
              </span>
            {:else}
              <button class="list-toggle" type="button" on:click={() => toggleExpand(list.id)}>
                <span class="caret">{expandedListIds.has(list.id) ? '▾' : '▸'}</span>
                <span class="list-title" class:active={list.active}
                  >{list.name} ({(list.objects || []).length})</span
                >
              </button>
            {/if}
            <span class="header-actions">
              {#if editingListId === list.id}
                <button class="icon-btn" type="button" on:click={saveEditListName} title="Accept" aria-label="Accept">
                  <AcceptIcon size="1rem" aria-hidden="true" />
                </button>
                <button
                  class="icon-btn"
                  type="button"
                  on:click={cancelEditListName}
                  title="Cancel"
                  aria-label="Cancel"
                >
                  <CloseIcon size="1rem" aria-hidden="true" />
                </button>
              {:else}
                <button
                  class="icon-btn"
                  type="button"
                  on:click={(e) => {
                    e.stopPropagation()
                    startEditListName(list)
                  }}
                  title="Edit"
                >
                  <EditIcon size="1rem" aria-hidden="true" />
                </button>
                <button
                  class="icon-btn danger"
                  type="button"
                  on:click={(e) => {
                    e.stopPropagation()
                    requestDeleteList(list)
                  }}
                  title="Delete"
                >
                  <DeleteIcon size="1rem" aria-hidden="true" />
                </button>
                <button
                  class="icon-btn icon-stack"
                  type="button"
                  on:click={(e) => {
                    e.stopPropagation()
                    toggleActive(list)
                  }}
                  title={list.active ? 'Active (marked in sky view)' : 'Inactive'}
                >
                  <ObservedIcon size="1rem" aria-hidden="true" />
                  {#if !list.active}
                    <span class="strike-overlay"><StrikeOverlayIcon /></span>
                  {/if}
                </button>
              {/if}
            </span>
          </div>

          {#if expandedListIds.has(list.id)}
            <div class="list-details">
              <div class="objects-title-row">
                <span class="objects-title">Objects</span>
                <button class="icon-btn" type="button" on:click={() => openAddObject(list.id)} title="Add object">
                  <PlusIcon size="0.9rem" aria-hidden="true" />
                </button>
              </div>

              {#if (list.objects || []).length === 0}
                <div class="hint small">No objects in this list.</div>
              {:else}
                <div class="objects-list">
                  {#each sortedObjectEntries(list) as entry (entry.id)}
                    {@const obj = objectById.get(entry.id)}
                    <div
                      class="object-row"
                      class:editing={objectEdit &&
                        objectEdit.listId === list.id &&
                        objectEdit.objectId === entry.id}
                    >
                      <div class="object-main">
                        <span class="obj-symbol"><ObservationObjectSymbol kind={objectSymbolKind(obj)} /></span>
                        <span class="object-name"
                          ><strong>{listObjectLabel(obj).bold}</strong>{listObjectLabel(obj).rest}</span
                        >
                        <span class="object-actions">
                          {#if list.sortType === 'manual'}
                            <button
                              class="icon-btn"
                              type="button"
                              on:click={() => moveObject(list.id, entry.id, 'up')}
                              title="Move up"
                            >
                              <MoveUpIcon size="0.9rem" aria-hidden="true" />
                            </button>
                            <button
                              class="icon-btn"
                              type="button"
                              on:click={() => moveObject(list.id, entry.id, 'down')}
                              title="Move down"
                            >
                              <MoveDownIcon size="0.9rem" aria-hidden="true" />
                            </button>
                          {/if}
                          <button
                            class="icon-btn"
                            type="button"
                            on:click={() => startEditNote(list.id, entry)}
                            title="Edit note"
                          >
                            <EditIcon size="1rem" aria-hidden="true" />
                          </button>
                          <button
                            class="icon-btn danger"
                            type="button"
                            on:click={() => requestDeleteObject(list, entry)}
                            title="Remove"
                          >
                            <DeleteIcon size="1rem" aria-hidden="true" />
                          </button>
                        </span>
                      </div>
                      {#if entry.note}
                        <div class="object-notes">{entry.note}</div>
                      {/if}
                    </div>

                    {#if objectEdit && objectEdit.listId === list.id && objectEdit.objectId === entry.id}
                      <div class="object-edit">
                        <CustomTextarea bind:value={objectEdit.draftNote} placeholder="Note..." />
                        <div class="edit-actions">
                          <button class="btn" type="button" on:click={saveEditNote}>Accept</button>
                          <button class="btn ghost" type="button" on:click={cancelEditNote}>Cancel</button>
                        </div>
                      </div>
                    {/if}
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    {/if}
  </div>
</div>

<ConfirmDialog
  open={confirmOpen}
  title={confirmTitle}
  message={confirmMessage}
  confirmLabel="Delete"
  cancelLabel="Cancel"
  on:confirm={confirmAction}
  on:cancel={cancelConfirm}
/>

{#if addObjectListId}
  <SearchPanel
    title="Add object to list"
    placeholder="Search objects…"
    useSearchStore={false}
    manageSelection={false}
    includeSolar={false}
    showDetailsAction={false}
    showFindingPathsAction={false}
    autoCloseOnAccept={false}
    topOffset="2.75rem"
    zIndex={50}
    resultFilter={(obj) => !existingIdsForList(addObjectListId).has(obj.id)}
    onAcceptObject={onAcceptSearchObject}
    on:close={closeAddObject}
  />
{/if}

{#if $keyboardActive}
  <OnScreenKeyboard />
{/if}

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

  .add-list {
    margin-left: auto;
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
    font-size: 1.2rem;
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
    font-size: 0.984rem;
  }

  .add-list-box {
    border: 1px solid rgba(232, 232, 232, 0.2);
    border-radius: 8px;
    padding: 0.55rem;
    margin-bottom: 0.75rem;
  }

  .list-card {
    border: 1px solid rgba(232, 232, 232, 0.15);
    border-radius: 8px;
    margin-bottom: 0.65rem;
  }

  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.45rem;
    padding: 0.45rem 0.55rem;
  }

  .list-toggle {
    flex: 1;
    min-width: 0;
    border: none;
    background: none;
    color: var(--fg);
    display: flex;
    justify-content: flex-start;
    gap: 0.5rem;
    align-items: center;
    text-align: left;
    cursor: pointer;
    padding: 0;
  }

  .list-title {
    font-size: 1.032rem;
    line-height: 1.25;
  }

  .list-title.active {
    font-weight: 700;
  }

  .list-name-edit {
    flex: 1;
    min-width: 0;
  }

  .header-actions {
    display: inline-flex;
    gap: 0.25rem;
    position: relative;
    z-index: 1;
  }

  .caret {
    font-size: 1.56rem;
    line-height: 1;
    opacity: 0.7;
    flex-shrink: 0;
  }

  .list-details {
    border-top: 1px solid rgba(232, 232, 232, 0.08);
    padding: 0.45rem 0.55rem 0.6rem;
  }

  .field-row {
    margin-bottom: 0.35rem;
  }

  .field-label {
    font-size: 0.888rem;
    opacity: 0.75;
    margin-bottom: 0.2rem;
  }

  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .pill {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 999px;
    padding: 0.3rem 0.75rem;
    font-size: 0.86rem;
    cursor: pointer;
  }

  .pill.selected {
    border-color: rgba(46, 119, 255, 0.85);
    background: rgba(46, 119, 255, 0.18);
    font-weight: 600;
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
    font-size: 0.912rem;
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
    font-size: 0.984rem;
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
    font-size: 0.936rem;
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

  .icon-stack {
    position: relative;
  }

  .strike-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .strike-overlay :global(svg) {
    width: 1rem;
    height: 1rem;
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
    font-size: 0.912rem;
    cursor: pointer;
  }

  .btn.ghost {
    opacity: 0.85;
  }

  .hint {
    font-size: 1.008rem;
    opacity: 0.72;
  }

  .hint.small {
    font-size: 0.936rem;
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .list-card {
    border-color: rgba(200, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .list-details {
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

  :global([data-theme='nightly']) .add-list-box {
    border-color: rgba(200, 0, 0, 0.35);
  }

  :global([data-theme='nightly']) .pill {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .pill.selected {
    border-color: #ff0000;
    background: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .icon-btn,
  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .icon-btn.danger {
    border-color: rgba(200, 0, 0, 0.75);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .error-msg {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff9a9a;
  }

  :global([data-theme='nightly']) .caret,
  :global([data-theme='nightly']) .field-label,
  :global([data-theme='nightly']) .objects-title,
  :global([data-theme='nightly']) .obj-symbol,
  :global([data-theme='nightly']) .object-notes,
  :global([data-theme='nightly']) .btn.ghost,
  :global([data-theme='nightly']) .hint {
    opacity: 1;
    color: rgba(180, 0, 0, 1);
  }
</style>
