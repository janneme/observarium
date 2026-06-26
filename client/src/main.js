import App from './App.svelte'
import './styles.css'

// Prevent browser page-zoom on trackpad pinch (Mac Chrome fires wheel+ctrlKey).
const _noZoom = (e) => {
  if (e.ctrlKey) e.preventDefault()
}
window.addEventListener('wheel', _noZoom, { passive: false })
document.addEventListener('wheel', _noZoom, { passive: false })

const app = new App({
  target: document.getElementById('app'),
})

export default app
