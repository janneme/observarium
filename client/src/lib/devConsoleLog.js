// Dev-only: mirrors console.log/info/warn/error/debug to a file on disk
// (see FRONTEND_LOG_FILE handling in vite.config.mjs), so browser-side logs
// don't have to be manually copy/pasted out of devtools. No-ops in production
// builds and never throws — a failed forward must never break the app.

const LEVELS = ['log', 'info', 'warn', 'error', 'debug']

function safeStringify(value) {
  if (typeof value === 'string') return value
  if (value instanceof Error) return value.stack || value.message
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function initDevConsoleLog() {
  if (!import.meta.env.DEV) return

  for (const level of LEVELS) {
    const original = console[level].bind(console)
    console[level] = (...args) => {
      original(...args)
      try {
        const body = JSON.stringify({
          level,
          message: args.map(safeStringify).join(' '),
          time: new Date().toISOString(),
        })
        fetch('/__console_log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
          keepalive: true,
        }).catch(() => {})
      } catch {
        // Forwarding must never break the app or recurse into console.*.
      }
    }
  }
}
