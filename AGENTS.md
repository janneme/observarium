- No authoring comments (like "Created with Claude")
- Prefer OOP
- Max function/method size: 50 lines, max file size: 1000 lines; refactor proactively to avoid exceeding these limits
- Backend and data preparation layer must be well unit-tested
- In Python use `uv` package manager (Python ≥ 3.12), `ruff` and `pylint` (both are intentional—pylint catches OOP and semantic issues that ruff does not). Ensure that any code
  change passes `ruff` and `pylint`
- In JavaScript use `eslint` (with `eslint-plugin-svelte` for `.svelte` files) and `prettier`.
  Run `svelte-check` for Svelte template validation. Ensure that any code change passes
  `eslint`, `prettier` and `svelte-check`
- Client code uses JavaScript only — no TypeScript
- Client sky-rendering logic (coordinate projection, magnitude scaling) must have unit tests using Vitest
