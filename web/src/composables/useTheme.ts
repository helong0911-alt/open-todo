/**
 * useTheme — singleton composable for light/dark theme management.
 * Persists preference to localStorage, falls back to system preference.
 * Toggles the 'dark' class on <html> and exposes reactive isDark for
 * Naive UI theme switching.
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'otd_theme'

function getInitialDark(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark') return true
  if (stored === 'light') return false
  // Fallback: system preference
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const isDark = ref(getInitialDark())

function applyTheme(dark: boolean) {
  const html = document.documentElement
  if (dark) {
    html.classList.add('dark')
  } else {
    html.classList.remove('dark')
  }
}

// Apply on load
applyTheme(isDark.value)

// Watch for changes
watch(isDark, (dark) => {
  applyTheme(dark)
  localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
})

function toggleTheme() {
  isDark.value = !isDark.value
}

export function useTheme() {
  return { isDark, toggleTheme }
}
