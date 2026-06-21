import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  root: '.',
  test: {
    environment: 'node',
    include: ['test/**/*.test.js'],
  },
})
