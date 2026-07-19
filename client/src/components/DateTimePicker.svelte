<script>
  import { createEventDispatcher } from 'svelte'
  import CloseIcon from '../icons/CloseIcon.svelte'

  export let time = new Date()

  const dispatch = createEventDispatcher()

  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // ── Calendar state ──────────────────────────────────────
  let calYear = time.getFullYear()
  let calMonth = time.getMonth()

  let selDate = new Date(time)
  selDate.setHours(0, 0, 0, 0)

  const MONTH_NAMES = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ]
  const DOW = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

  $: calCells = buildCalGrid(calYear, calMonth)
  // Explicit reactive values (rather than isSel(d)/isTdy(d) function calls in the
  // template) — Svelte's dependency tracking only sees identifiers referenced
  // directly in a template expression. A function call site doesn't expose the
  // variables the function's body closes over, so selDate/today changes would
  // never re-trigger the {#each} row's class:sel/class:today bindings.
  $: selDay = selDate.getFullYear() === calYear && selDate.getMonth() === calMonth ? selDate.getDate() : null
  $: todayDay = today.getFullYear() === calYear && today.getMonth() === calMonth ? today.getDate() : null

  function buildCalGrid(year, month) {
    const firstDow = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const cells = []
    for (let i = 0; i < firstDow; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(d)
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  }

  function prevMonth() {
    if (calMonth === 0) {
      calYear--
      calMonth = 11
    } else calMonth--
  }
  function nextMonth() {
    if (calMonth === 11) {
      calYear++
      calMonth = 0
    } else calMonth++
  }
  function selectDay(d) {
    if (d) selDate = new Date(calYear, calMonth, d)
    applyLive()
  }

  // ── Time ────────────────────────────────────────────────
  const hourOptions = Array.from({ length: 24 }, (_, h) => h)
  const minuteOptions = Array.from({ length: 12 }, (_, i) => i * 5)

  let hourIdx = time.getHours()
  let minuteIdx = Math.round(time.getMinutes() / 5) % 12

  // Arrow-button stepping — the only way to adjust the time; no drum/scroll
  // gesture, so this works the same with or without a touch screen. Wraps
  // around at both ends (23 -> 0, 0 -> 23; last minute step -> 0, 0 -> last).
  function stepHour(delta) {
    hourIdx = (hourIdx + delta + hourOptions.length) % hourOptions.length
    applyLive()
  }
  function stepMinute(delta) {
    minuteIdx = (minuteIdx + delta + minuteOptions.length) % minuteOptions.length
    applyLive()
  }

  // ── Actions ─────────────────────────────────────────────
  function buildResult() {
    const d = new Date(selDate)
    d.setHours(hourOptions[hourIdx], minuteOptions[minuteIdx], 0, 0)
    return d
  }

  // Applies the current selection immediately (top bar/sky reflect it live)
  // without closing the picker, so the user can keep adjusting date/time.
  function applyLive() {
    const result = buildResult()
    dispatch('pick', result)
  }

  function close() {
    dispatch('done')
  }

  // "Now" jumps to the current moment and explicitly tells the parent to
  // resume live sky updates — a dedicated event rather than relying on the
  // parent inferring intent by comparing dates, so this stays correct even
  // if the picked moment doesn't happen to land on today for some reason.
  function useNow() {
    const now = new Date()
    selDate = new Date(now)
    selDate.setHours(0, 0, 0, 0)
    calYear = selDate.getFullYear()
    calMonth = selDate.getMonth()
    hourIdx = now.getHours()
    minuteIdx = Math.round(now.getMinutes() / 5) % 12
    dispatch('resumeLive')
    applyLive()
  }
</script>

<!-- transparent backdrop: blocks canvas pointer events, click = close -->
<div
  class="backdrop"
  on:pointerdown|stopPropagation
  on:click={close}
  role="button"
  tabindex="-1"
  aria-label="Close"
  on:keydown={(e) => e.key === 'Escape' && close()}
></div>

<div class="panel" on:pointerdown|stopPropagation>
  <div class="sheet-header">
    <span class="sheet-title">Date &amp; Time</span>
    <button class="now-btn" on:click={useNow}>Now</button>
    <button class="close-btn" on:click={close} aria-label="Close">
      <CloseIcon size="1.1rem" aria-hidden="true" />
    </button>
  </div>

  <div class="picker-body">
    <!-- Left: calendar -->
    <div class="cal-section">
      <div class="month-nav">
        <button class="nav-btn" on:click={prevMonth}>‹</button>
        <span class="month-label">{MONTH_NAMES[calMonth]} {calYear}</span>
        <button class="nav-btn" on:click={nextMonth}>›</button>
      </div>

      <div class="dow-row">
        {#each DOW as d}<div class="dow-cell">{d}</div>{/each}
      </div>

      <div class="day-grid">
        {#each calCells as d}
          <div
            class="day-cell"
            class:sel={!!d && d === selDay}
            class:today={!!d && d === todayDay}
            class:empty={!d}
            role="button"
            tabindex={d ? 0 : -1}
            on:click={() => selectDay(d)}
            on:keydown={(e) => e.key === 'Enter' && selectDay(d)}
          >
            <span class="day-num">{d ?? ''}</span>
          </div>
        {/each}
      </div>
    </div>

    <!-- Right: time -->
    <div class="time-section">
      <span class="time-lbl">Time</span>

      <div class="time-cols">
        <div class="time-col">
          <button class="drum-arrow" on:click={() => stepHour(-1)} aria-label="Previous hour">▲</button>
          <span class="time-value">{String(hourOptions[hourIdx]).padStart(2, '0')}</span>
          <button class="drum-arrow" on:click={() => stepHour(1)} aria-label="Next hour">▼</button>
        </div>
        <span class="drum-sep">:</span>
        <div class="time-col">
          <button class="drum-arrow" on:click={() => stepMinute(-1)} aria-label="Previous 5 minutes">▲</button>
          <span class="time-value">{String(minuteOptions[minuteIdx]).padStart(2, '0')}</span>
          <button class="drum-arrow" on:click={() => stepMinute(1)} aria-label="Next 5 minutes">▼</button>
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  /* ── Positioning ── */
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
  }

  .panel {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    z-index: 51;
    background: var(--surface-bg);
    color: var(--surface-fg);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border-bottom: 1px solid rgba(127, 127, 127, 0.15);
    border-radius: 0 0 10px 10px;
  }

  /* ── Header ── */
  .sheet-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(127, 127, 127, 0.12);
  }

  .sheet-title {
    flex: 1;
    font-size: 1.056rem;
    opacity: 0.75;
  }

  .close-btn {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0.2rem 0.3rem;
    opacity: 0.6;
    transform: none;
    display: flex;
    align-items: center;
  }
  .close-btn:hover {
    background: none;
    opacity: 1;
    transform: none;
  }

  /* ── Side-by-side body ── */
  .picker-body {
    display: flex;
    align-items: flex-start;
  }

  /* ── Calendar (left column) ── */
  .cal-section {
    flex: 1 1 0;
    min-width: 0;
    padding: 0.35rem 0.6rem 0.5rem;
    border-right: 1px solid rgba(127, 127, 127, 0.12);
  }

  .month-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 1.9rem;
  }

  .month-label {
    font-size: 1.02rem;
    font-weight: 600;
  }

  .nav-btn {
    background: none;
    border: none;
    color: inherit;
    font-size: 2.1rem;
    line-height: 1;
    cursor: pointer;
    padding: 0 0.45rem;
    opacity: 0.55;
    transform: none;
  }
  .nav-btn:hover {
    background: none;
    opacity: 1;
    transform: none;
  }

  .dow-row {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    margin-bottom: 1px;
  }

  .dow-cell {
    text-align: center;
    font-size: 0.98rem;
    font-weight: 700;
    opacity: 0.38;
    height: 1.4rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .day-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
  }

  .day-cell {
    height: 1.85rem;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .day-cell.empty {
    pointer-events: none;
  }

  .day-num {
    width: 1.8rem;
    height: 1.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 0.98rem;
    transition: background 100ms;
  }

  .day-cell:not(.empty):not(.sel):hover .day-num {
    background: rgba(255, 255, 255, 0.12);
  }

  .day-cell.sel .day-num {
    background: var(--accent);
    color: #fff;
    font-weight: 600;
  }

  :global([data-theme='nightly']) .day-cell.sel .day-num {
    background: #e00000;
    color: #000;
  }

  .day-cell.today:not(.sel) .day-num {
    font-weight: 700;
    color: #ffffff;
  }

  :global([data-theme='nightly']) .day-cell.today:not(.sel) .day-num {
    color: #ff0000;
  }

  :global([data-theme='nightly']) .day-cell:not(.empty):not(.sel):hover .day-num {
    background: rgba(224, 0, 0, 0.15);
  }

  :global([data-theme='nightly']) .panel {
    border-bottom-color: rgba(136, 0, 0, 0.25);
  }

  :global([data-theme='nightly']) .sheet-header {
    border-bottom-color: rgba(136, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .cal-section {
    border-right-color: rgba(136, 0, 0, 0.2);
  }

  /* Nightly: opacity-based dimming reads as too faint to use comfortably in
     the dark. Force full opacity and use a solid (non-transparent) dimmer
     red for de-emphasized text instead, keeping pure #ff0000 for the
     selected/emphasized state so hierarchy is still readable. */
  :global([data-theme='nightly']) .sheet-title,
  :global([data-theme='nightly']) .close-btn,
  :global([data-theme='nightly']) .nav-btn,
  :global([data-theme='nightly']) .dow-cell,
  :global([data-theme='nightly']) .time-lbl,
  :global([data-theme='nightly']) .time-value,
  :global([data-theme='nightly']) .drum-sep,
  :global([data-theme='nightly']) .drum-arrow {
    opacity: 1;
    color: rgba(180, 0, 0, 1);
  }

  :global([data-theme='nightly']) .nav-btn:hover,
  :global([data-theme='nightly']) .drum-arrow:hover,
  :global([data-theme='nightly']) .close-btn:hover {
    color: #ff0000;
  }

  /* ── Time section (right column) ── */
  .time-section {
    flex: 0 0 9rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.35rem 0.4rem 0.55rem;
    gap: 0.35rem;
  }

  .time-lbl {
    font-size: 0.8rem;
    opacity: 0.38;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  /* ── Time value display: each hour/minute column stacks its own arrows
     directly above/below its own digits, so they're always centered on the
     value they control regardless of column width. ── */
  .time-cols {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .time-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.1rem;
  }

  .time-value {
    min-width: 2.2rem;
    text-align: center;
    font-size: 1.9rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .drum-sep {
    width: 1.1rem;
    flex-shrink: 0;
    text-align: center;
    font-size: 1.9rem;
    font-weight: 600;
    opacity: 0.6;
  }

  /* ── Time arrow buttons (mouse-clickable alternative to swipe/wheel) ── */
  .drum-arrow {
    background: none;
    border: none;
    color: inherit;
    font-size: 1.3rem;
    line-height: 1;
    cursor: pointer;
    padding: 0.15rem 0.6rem;
    opacity: 0.55;
    transform: none;
  }
  .drum-arrow:hover {
    background: none;
    opacity: 1;
    transform: none;
  }

  /* ── Now button ── */
  .now-btn {
    background: var(--accent);
    border: none;
    color: #fff;
    font-size: 0.95rem;
    font-weight: 700;
    cursor: pointer;
    padding: 0.35rem 1.1rem;
    border-radius: 20px;
    opacity: 1;
    transform: none;
  }
  .now-btn:hover {
    filter: brightness(1.12);
    transform: none;
  }

  :global([data-theme='nightly']) .now-btn {
    background: none;
    border: 2px solid #cc0000;
    color: #cc0000;
  }
  :global([data-theme='nightly']) .now-btn:hover {
    background: rgba(204, 0, 0, 0.15);
    filter: none;
  }
</style>
