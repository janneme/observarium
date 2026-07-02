# Observarium — Claude Code instructions

## Commits
Never run `git commit`. The user commits all changes themselves.

## UI / Color rules
**NO GREEN.** The app is used for nightly astronomical observation. Green light destroys dark adaptation.
- Never use green or green-tinted colors in any UI element (buttons, badges, indicators, success states, SVG strokes/fills, CSS variables).
- !!! STRICT: The green channel — the middle byte in hex `#RRGGBB` — MUST be `00` in every color, with no exceptions. Examples of ALLOWED colors: `#cc0000` (red), `#0000cc` (blue), `#cc00cc` (magenta), `#000000` (black). Examples of FORBIDDEN: `#9dda9d` (G=218 ✗), `#4a9eff` (G=158 ✗), `rgba(255,255,255,…)` (G=255 ✗), `rgba(232,232,232,…)` (G=232 ✗). The only exemption is the CSS variable `var(--fg)` (the app-wide foreground text color, already established in styles.css).
- For "success" or "found" states use a pure blue with G=00 (e.g. `#0000cc`) or black `#000000`.
- Warnings and errors → red with G=00 (e.g. `#cc0000`, `rgba(200,0,0,…)`). Amber/orange is impossible with G=00 — never use it.
