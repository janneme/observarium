import js from '@eslint/js'
import svelte from 'eslint-plugin-svelte'
import globals from 'globals'

export default [
  { ignores: ['dist/**'] },
  js.configs.recommended,
  ...svelte.configs['flat/recommended'],
  ...svelte.configs['flat/prettier'],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
  },
  {
    files: ['vite.config.mjs', 'scripts/**'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
]
