<script>
  import { createEventDispatcher, onMount, tick } from 'svelte'

  export let time = new Date()

  const dispatch = createEventDispatcher()

  const ITEM_H = 44

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

  function buildCalGrid(year, month) {
    const firstDow = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const cells = []
    for (let i = 0; i < firstDow; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(d)
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  }

  function isSel(d) {
    return d && selDate.getFullYear() === calYear && selDate.getMonth() === calMonth && selDate.getDate() === d
  }
  function isTdy(d) {
    return d && today.getFullYear() === calYear && today.getMonth() === calMonth && today.getDate() === d
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
  }

  // ── Time drums ──────────────────────────────────────────
  const hourOptions = Array.from({ length: 24 }, (_, h) => h)
  const minuteOptions = Array.from({ length: 12 }, (_, i) => i * 5)

  let hourIdx = time.getHours()
  let minuteIdx = Math.round(time.getMinutes() / 5) % 12

  let hourEl
  let minuteEl

  function onHourScroll() {
    if (hourEl) hourIdx = Math.max(0, Math.min(23, Math.round(hourEl.scrollTop / ITEM_H)))
  }
  function onMinuteScroll() {
    if (minuteEl) minuteIdx = Math.max(0, Math.min(11, Math.round(minuteEl.scrollTop / ITEM_H)))
  }

  const hourAcc = { v: 0 }
  const minuteAcc = { v: 0 }

  function drumWheel(e, acc, el, count) {
    e.stopPropagation()
    e.preventDefault()
    const px = e.deltaMode === 1 ? e.deltaY * ITEM_H : e.deltaMode === 2 ? e.deltaY * 132 : e.deltaY
    acc.v += px
    const steps = Math.trunc(acc.v / ITEM_H)
    if (steps !== 0) {
      acc.v -= steps * ITEM_H
      const cur = Math.round(el.scrollTop / ITEM_H)
      el.scrollTop = Math.max(0, Math.min(count - 1, cur + steps)) * ITEM_H
    }
  }

  // ── Actions ─────────────────────────────────────────────
  function buildResult() {
    const d = new Date(selDate)
    d.setHours(hourOptions[hourIdx], minuteOptions[minuteIdx], 0, 0)
    return d
  }

  function apply() {
    dispatch('pick', buildResult())
  }
  function cancel() {
    dispatch('cancel')
  }

  async function useNow() {
    const now = new Date()
    selDate = new Date(now)
    selDate.setHours(0, 0, 0, 0)
    calYear = selDate.getFullYear()
    calMonth = selDate.getMonth()
    hourIdx = now.getHours()
    minuteIdx = Math.round(now.getMinutes() / 5) % 12
    await tick()
    if (hourEl) hourEl.scrollTop = hourIdx * ITEM_H
    if (minuteEl) minuteEl.scrollTop = minuteIdx * ITEM_H
  }

  onMount(async () => {
    await tick()
    if (hourEl) hourEl.scrollTop = hourIdx * ITEM_H
    if (minuteEl) minuteEl.scrollTop = minuteIdx * ITEM_H
  })
</script>

<!-- transparent backdrop: blocks canvas pointer events, click = cancel -->
<div
  class="backdrop"
  on:pointerdown|stopPropagation
  on:click={cancel}
  role="button"
  tabindex="-1"
  aria-label="Close"
  on:keydown={(e) => e.key === 'Escape' && cancel()}
></div>

<div class="panel" on:pointerdown|stopPropagation>
  <div class="sheet-header">
    <button class="action-btn" on:click={cancel}>Cancel</button>
    <span class="sheet-title">Date &amp; Time</span>
    <button class="action-btn primary" on:click={apply}>Apply</button>
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
            class:sel={isSel(d)}
            class:today={isTdy(d)}
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

    <!-- Right: time drums -->
    <div class="time-section">
      <span class="time-lbl">Time</span>

      <div class="drum-row">
        <div
          class="drum"
          bind:this={hourEl}
          on:scroll={onHourScroll}
          on:wheel={(e) => drumWheel(e, hourAcc, hourEl, 24)}
        >
          <div class="drum-pad"></div>
          {#each hourOptions as h, i}
            <div class="drum-item" class:sel={i === hourIdx}>{String(h).padStart(2, '0')}</div>
          {/each}
          <div class="drum-pad"></div>
        </div>

        <div class="drum-sep">:</div>

        <div
          class="drum"
          bind:this={minuteEl}
          on:scroll={onMinuteScroll}
          on:wheel={(e) => drumWheel(e, minuteAcc, minuteEl, 12)}
        >
          <div class="drum-pad"></div>
          {#each minuteOptions as m, i}
            <div class="drum-item" class:sel={i === minuteIdx}>{String(m).padStart(2, '0')}</div>
          {/each}
          <div class="drum-pad"></div>
        </div>
      </div>

      <button class="now-btn" on:click={useNow}>Now</button>
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
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(127, 127, 127, 0.12);
  }

  .sheet-title {
    font-size: 0.88rem;
    opacity: 0.75;
  }

  .action-btn {
    background: none;
    border: none;
    color: inherit;
    font-size: 0.88rem;
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    opacity: 0.5;
    transform: none;
  }
  .action-btn:hover {
    background: none;
    transform: none;
  }
  .action-btn.primary {
    opacity: 1;
    font-weight: 600;
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
    font-size: 0.85rem;
    font-weight: 600;
  }

  .nav-btn {
    background: none;
    border: none;
    color: inherit;
    font-size: 1.35rem;
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
    font-size: 0.67rem;
    opacity: 0.38;
    height: 1.25rem;
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
    width: 1.65rem;
    height: 1.65rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 0.82rem;
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

  :global([data-theme='nightly']) .drum-row::before,
  :global([data-theme='nightly']) .drum-row::after {
    background: rgba(224, 0, 0, 0.22);
  }

  :global([data-theme='nightly']) .now-btn {
    border-color: rgba(224, 0, 0, 0.28);
  }

  :global([data-theme='nightly']) .now-btn:hover {
    background: rgba(224, 0, 0, 0.1);
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
    font-size: 0.67rem;
    opacity: 0.38;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  /* ── Drums ── */
  .drum-row {
    display: flex;
    width: 100%;
    height: 132px;
    position: relative;
  }

  .drum-row::before,
  .drum-row::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(255, 255, 255, 0.18);
    z-index: 1;
    pointer-events: none;
  }

  .drum-row::before {
    top: 44px;
  }
  .drum-row::after {
    top: 88px;
  }

  .drum {
    flex: 1;
    overflow-y: auto;
    scroll-snap-type: y mandatory;
    scrollbar-width: none;
    -ms-overflow-style: none;
    touch-action: pan-y;
    -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 33%, black 67%, transparent 100%);
    mask-image: linear-gradient(to bottom, transparent 0%, black 33%, black 67%, transparent 100%);
  }

  .drum::-webkit-scrollbar {
    display: none;
  }

  .drum-pad {
    height: 44px;
    flex-shrink: 0;
  }

  .drum-item {
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    scroll-snap-align: center;
    font-size: 1.05rem;
    opacity: 0.35;
    font-variant-numeric: tabular-nums;
  }

  .drum-item.sel {
    opacity: 1;
    font-weight: 600;
  }

  .drum-sep {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    flex-shrink: 0;
    font-size: 1.1rem;
    font-weight: 600;
    opacity: 0.6;
    padding-bottom: 2px;
  }

  /* ── Now button ── */
  .now-btn {
    background: none;
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: inherit;
    font-size: 0.78rem;
    cursor: pointer;
    padding: 0.3rem 1rem;
    border-radius: 20px;
    opacity: 0.65;
    transform: none;
  }
  .now-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    transform: none;
  }
</style>
