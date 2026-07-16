import { appendFile } from 'node:fs/promises'
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Dev-only: forwards browser console.* calls (see src/lib/devConsoleLog.js) to
// a file on disk, mirroring the backend's BACKEND_LOG_FILE setup, so you don't
// have to copy/paste from the browser devtools console. Path comes from the
// FRONTEND_LOG_FILE env var (set by the root Makefile's `dev` target), not
// hardcoded here. configureServer is never invoked during `vite build`, but
// Vitest does reuse Vite's server internals, so it fires there too — the
// VITEST check below keeps that from printing a spurious warning on every
// test run.
function consoleForwardPlugin() {
  const logFile = process.env.FRONTEND_LOG_FILE
  let warned = false

  return {
    name: 'console-forward',
    configureServer(server) {
      if (!logFile && !process.env.VITEST) {
        console.warn('[console-forward] FRONTEND_LOG_FILE not set — browser console forwarding to a file is disabled.')
      }
      server.middlewares.use('/__console_log', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end()
          return
        }
        let raw = ''
        req.on('data', (chunk) => {
          raw += chunk
        })
        req.on('end', async () => {
          res.statusCode = 204
          res.end()
          if (!logFile) return
          try {
            const { level, message, time } = JSON.parse(raw)
            const line = `[${time}] ${String(level || 'log').toUpperCase()} ${message}\n`
            await appendFile(logFile, line, 'utf-8')
          } catch (err) {
            if (!warned) {
              warned = true
              console.warn('[console-forward] failed to write frontend log:', err)
            }
          }
        })
      })
    },
  }
}

export default defineConfig({
  plugins: [svelte(), consoleForwardPlugin()],
  root: '.',
  test: {
    environment: 'node',
    include: ['test/**/*.test.js'],
    hookTimeout: 600000,
    testTimeout: 600000,
  },
})
