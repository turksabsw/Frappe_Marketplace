import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

// ---------------------------------------------------------------------------
// Service Worker Registration
// ---------------------------------------------------------------------------
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then(function (registration) {
        registration.addEventListener('updatefound', function () {
          var newWorker = registration.installing
          if (!newWorker) return

          newWorker.addEventListener('statechange', function () {
            if (
              newWorker.state === 'installed' &&
              navigator.serviceWorker.controller
            ) {
              showUpdateNotification(registration)
            }
          })
        })
      })
      .catch(function (error) {
        if (process.env.NODE_ENV !== 'production') {
          console.warn('SW registration failed:', error)
        }
      })
  })
}

/**
 * Show a Turkish-language update notification banner.
 * When the user clicks "Güncelle", the waiting SW is activated and the page reloads.
 *
 * @param {ServiceWorkerRegistration} registration
 */
function showUpdateNotification(registration) {
  var banner = document.createElement('div')
  banner.setAttribute('role', 'alert')
  banner.setAttribute('aria-live', 'polite')
  Object.assign(banner.style, {
    position: 'fixed',
    bottom: '16px',
    left: '50%',
    transform: 'translateX(-50%)',
    background: '#1a56db',
    color: '#ffffff',
    padding: '12px 24px',
    borderRadius: '8px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    zIndex: '10000',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    fontFamily: 'DM Sans, system-ui, sans-serif',
    fontSize: '14px',
    maxWidth: '90vw'
  })

  var message = document.createElement('span')
  message.textContent = 'Yeni bir sürüm mevcut.'

  var btn = document.createElement('button')
  btn.textContent = 'Güncelle'
  Object.assign(btn.style, {
    background: '#ffffff',
    color: '#1a56db',
    border: 'none',
    padding: '6px 16px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: '14px',
    whiteSpace: 'nowrap'
  })

  btn.addEventListener('click', function () {
    if (registration.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    }
    window.location.reload()
  })

  var dismiss = document.createElement('button')
  dismiss.textContent = '\u00D7'
  dismiss.setAttribute('aria-label', 'Kapat')
  Object.assign(dismiss.style, {
    background: 'transparent',
    color: '#ffffff',
    border: 'none',
    fontSize: '18px',
    cursor: 'pointer',
    padding: '0 4px',
    lineHeight: '1'
  })
  dismiss.addEventListener('click', function () {
    banner.remove()
  })

  banner.appendChild(message)
  banner.appendChild(btn)
  banner.appendChild(dismiss)
  document.body.appendChild(banner)
}
