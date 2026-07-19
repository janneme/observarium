# Observarium — Claude Code instructions

## Commits
Never run `git commit`. The user commits all changes themselves.

## UI / Color rules
**NO GREEN — nightly theme only.** The app is used for nightly astronomical observation, and while the nightly theme (`data-theme="nightly"`) is active, green light destroys dark adaptation. This rule does NOT apply to the daily theme — daily-mode colors are unrestricted (yellow, green, white, whatever suits the design); only nightly-mode colors are constrained.
- Never use green or green-tinted colors in any **nightly-theme** UI element (buttons, badges, indicators, success states, SVG strokes/fills, CSS variables scoped under `:global([data-theme='nightly'])` or a `nightly`/`$theme === 'nightly'` branch).
- !!! STRICT, nightly theme only: The green channel — the middle byte in hex `#RRGGBB` — MUST be `00` in every color used while nightly theme is active, with no exceptions. Examples of ALLOWED nightly colors: `#cc0000` (red), `#0000cc` (blue), `#cc00cc` (magenta), `#000000` (black). Examples of FORBIDDEN in nightly: `#9dda9d` (G=218 ✗), `#4a9eff` (G=158 ✗), `rgba(255,255,255,…)` (G=255 ✗), `rgba(232,232,232,…)` (G=232 ✗). The only exemption is the CSS variable `var(--fg)` (the app-wide foreground text color, already established in styles.css).
- In nightly theme, for "success" or "found" states use a pure blue with G=00 (e.g. `#0000cc`) or black `#000000`.
- In nightly theme, warnings and errors → red with G=00 (e.g. `#cc0000`, `rgba(200,0,0,…)`). Amber/orange is impossible with G=00 — never use it in nightly theme.
- Code that branches on theme (e.g. `const x = nightly ? colorA : colorB`) only needs the nightly-side (`colorA`) value to obey the G=00 constraint — the daily-side value is free.

## Dev logging
`make dev` runs both servers via `run.py` and writes two separate log files, in addition to the console and the combined `/tmp/observarium.log`:
- **Backend**: `/tmp/observarium-be.log` — every level including DEBUG. The console only shows INFO/WARNING/ERROR/CRITICAL; DEBUG-level lines are file-only. Configured via `logging.basicConfig` in `server/local_server.py` (format `"%(levelname)s %(name)s: %(message)s"`); use `logger.debug/info/warning/error` (module-level `logging.getLogger(__name__)`), not `print()`. The console/file split is enforced by `run.py` (`ProcessManager.log_backend`), which parses each line's level prefix — it does not come from separate Python logging handlers.
- **Frontend**: `/tmp/observarium-fe.log` — browser `console.log/info/warn/error/debug` calls are mirrored here (in addition to still printing to the browser devtools console as normal) via a dev-only shim (`client/src/lib/devConsoleLog.js`) that POSTs to a Vite dev-server middleware (`consoleForwardPlugin` in `client/vite.config.mjs`). Dev-server only — inert in production builds.

Both log file paths come from `BACKEND_LOG_FILE`/`FRONTEND_LOG_FILE` env vars set in the root `Makefile`'s `dev` target — never hardcode these paths in Python or JS source.

**Claude must NEVER start or kill the app itself** — no `make dev`, no launching `run.py`/`local_server.py`/`vite` directly, no `kill`/`pkill`/`SIGINT` against those processes, under any circumstance. This holds even if the app appears not to be running, looks stale, or you suspect it needs a restart: always ask the user to start/stop/restart it themselves instead of doing it yourself. The app runs in a dedicated terminal the user watches directly for live log output; Claude touching that process undermines it.
