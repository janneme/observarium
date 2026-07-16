# Observarium — Claude Code instructions

## Commits
Never run `git commit`. The user commits all changes themselves.

## UI / Color rules
**NO GREEN.** The app is used for nightly astronomical observation. Green light destroys dark adaptation.
- Never use green or green-tinted colors in any UI element (buttons, badges, indicators, success states, SVG strokes/fills, CSS variables).
- !!! STRICT: The green channel — the middle byte in hex `#RRGGBB` — MUST be `00` in every color, with no exceptions. Examples of ALLOWED colors: `#cc0000` (red), `#0000cc` (blue), `#cc00cc` (magenta), `#000000` (black). Examples of FORBIDDEN: `#9dda9d` (G=218 ✗), `#4a9eff` (G=158 ✗), `rgba(255,255,255,…)` (G=255 ✗), `rgba(232,232,232,…)` (G=232 ✗). The only exemption is the CSS variable `var(--fg)` (the app-wide foreground text color, already established in styles.css).
- For "success" or "found" states use a pure blue with G=00 (e.g. `#0000cc`) or black `#000000`.
- Warnings and errors → red with G=00 (e.g. `#cc0000`, `rgba(200,0,0,…)`). Amber/orange is impossible with G=00 — never use it.

## Dev logging
`make dev` runs both servers via `run.py` and writes two separate log files, in addition to the console and the combined `/tmp/observarium.log`:
- **Backend**: `/tmp/observarium-be.log` — every level including DEBUG. The console only shows INFO/WARNING/ERROR/CRITICAL; DEBUG-level lines are file-only. Configured via `logging.basicConfig` in `server/local_server.py` (format `"%(levelname)s %(name)s: %(message)s"`); use `logger.debug/info/warning/error` (module-level `logging.getLogger(__name__)`), not `print()`. The console/file split is enforced by `run.py` (`ProcessManager.log_backend`), which parses each line's level prefix — it does not come from separate Python logging handlers.
- **Frontend**: `/tmp/observarium-fe.log` — browser `console.log/info/warn/error/debug` calls are mirrored here (in addition to still printing to the browser devtools console as normal) via a dev-only shim (`client/src/lib/devConsoleLog.js`) that POSTs to a Vite dev-server middleware (`consoleForwardPlugin` in `client/vite.config.mjs`). Dev-server only — inert in production builds.

Both log file paths come from `BACKEND_LOG_FILE`/`FRONTEND_LOG_FILE` env vars set in the root `Makefile`'s `dev` target — never hardcode these paths in Python or JS source.
