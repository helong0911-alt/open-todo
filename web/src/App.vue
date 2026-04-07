<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NConfigProvider, NMessageProvider, darkTheme } from 'naive-ui'
import { authCaptcha, authLogin, authRegister, authLogout, authMe, onUnauthorized } from '@/api'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleTheme } = useTheme()

const router = useRouter()
const route = useRoute()

const sessionToken = ref(localStorage.getItem('otd_session_token') || '')
const userEmail = ref(localStorage.getItem('otd_user_email') || '')
const showSetup = ref(!sessionToken.value)

// ---------------------------------------------------------------------------
// Tab state: 'login' | 'register'
// ---------------------------------------------------------------------------
const activeTab = ref<'login' | 'register'>('login')

// ---------------------------------------------------------------------------
// Captcha state (shared between tabs)
// ---------------------------------------------------------------------------
const captchaId = ref('')
const captchaImage = ref('')
const captchaCode = ref('')
const captchaLoading = ref(false)

async function loadCaptcha() {
  captchaLoading.value = true
  captchaCode.value = ''
  try {
    const res = await authCaptcha()
    captchaId.value = res.captchaId
    captchaImage.value = res.imageBase64
  } catch {
    window.alert('Failed to load captcha.')
  } finally {
    captchaLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Login state
// ---------------------------------------------------------------------------
const loginEmail = ref('')
const loginPassword = ref('')
const loginLoading = ref(false)

async function handleLogin() {
  if (!loginEmail.value.trim() || !loginPassword.value || !captchaCode.value.trim()) return
  loginLoading.value = true
  try {
    const res = await authLogin(
      loginEmail.value.trim(),
      loginPassword.value,
      captchaId.value,
      captchaCode.value.trim(),
    )
    sessionToken.value = res.sessionToken
    userEmail.value = res.email
    localStorage.setItem('otd_session_token', res.sessionToken)
    localStorage.setItem('otd_user_email', res.email)
    if (res.apiKey) {
      localStorage.setItem('otd_api_key', res.apiKey)
    }
    showSetup.value = false
  } catch (err: any) {
    const msg = err?.response?.data?.detail || 'Login failed.'
    window.alert(msg)
    await loadCaptcha()
  } finally {
    loginLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Register state
// ---------------------------------------------------------------------------
const registerEmail = ref('')
const registerPassword = ref('')
const registerLoading = ref(false)
const registerSuccess = ref(false)

async function handleRegister() {
  if (!registerEmail.value.trim() || !registerPassword.value || !captchaCode.value.trim()) return
  if (registerPassword.value.length < 6) {
    window.alert('Password must be at least 6 characters.')
    return
  }
  registerLoading.value = true
  try {
    await authRegister(
      registerEmail.value.trim(),
      registerPassword.value,
      captchaId.value,
      captchaCode.value.trim(),
    )
    registerSuccess.value = true
  } catch (err: any) {
    const msg = err?.response?.data?.detail || 'Registration failed.'
    window.alert(msg)
    await loadCaptcha()
  } finally {
    registerLoading.value = false
  }
}

function switchToLogin() {
  registerSuccess.value = false
  activeTab.value = 'login'
  loadCaptcha()
}

// ---------------------------------------------------------------------------
// Tab switch handler
// ---------------------------------------------------------------------------
function switchTab(tab: 'login' | 'register') {
  activeTab.value = tab
  captchaCode.value = ''
  registerSuccess.value = false
  loadCaptcha()
}

// ---------------------------------------------------------------------------
// Nav
// ---------------------------------------------------------------------------
const pageTitle = computed(() => {
  if (route.name === 'projects') return 'Projects'
  if (route.name === 'project-detail') return 'WBS Tree'
  if (route.name === 'automation') return 'Automation'
  if (route.name === 'key-management') return 'API Keys'
  if (route.name === 'notifications') return 'Notifications'
  if (route.name === 'user-center') return 'User Center'
  return 'Open-Todo'
})

const isPublicPage = computed(() => route.meta.public === true)

async function logout() {
  try {
    if (sessionToken.value) {
      await authLogout(sessionToken.value)
    }
  } catch {
    // ignore — we're logging out anyway
  }
  forceLogout()
}

/**
 * Clear all auth state and show login overlay.
 * Called by the global 401 interceptor and by explicit logout.
 * Guarded against duplicate invocations.
 */
let _loggingOut = false
function forceLogout() {
  if (_loggingOut) return
  _loggingOut = true
  sessionToken.value = ''
  userEmail.value = ''
  localStorage.removeItem('otd_session_token')
  localStorage.removeItem('otd_user_email')
  localStorage.removeItem('otd_api_key')
  showSetup.value = true
  loginEmail.value = ''
  loginPassword.value = ''
  registerEmail.value = ''
  registerPassword.value = ''
  registerSuccess.value = false
  activeTab.value = 'login'
  router.push('/')
  loadCaptcha()
  // Reset guard after a tick so future logouts still work
  setTimeout(() => { _loggingOut = false }, 0)
}

// Register 401 interceptor callback
onUnauthorized(forceLogout)

onMounted(async () => {
  if (sessionToken.value) {
    // Validate the stored session token against the backend
    try {
      const me = await authMe()
      userEmail.value = me.email
      localStorage.setItem('otd_user_email', me.email)
      showSetup.value = false
    } catch {
      // Token invalid or expired — force re-login
      forceLogout()
    }
  } else {
    showSetup.value = true
    loadCaptcha()
  }
})
</script>

<template>
  <n-config-provider :theme="isDark ? darkTheme : undefined">
    <n-message-provider>
  <!-- Public pages (e.g. email verification) — bypass login overlay -->
  <div v-if="isPublicPage" class="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
    <router-view />
  </div>

  <!-- Setup / Login / Register overlay -->
  <div v-else-if="showSetup" class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
    <div class="w-full max-w-md bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-8">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Open-Todo (OTD)</h1>

      <!-- Tab switcher -->
      <div class="flex mb-6 border-b border-gray-200 dark:border-gray-700">
        <button
          class="flex-1 pb-2 text-sm font-medium text-center transition-colors"
          :class="activeTab === 'login' ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400' : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'"
          @click="switchTab('login')"
        >
          Login
        </button>
        <button
          class="flex-1 pb-2 text-sm font-medium text-center transition-colors"
          :class="activeTab === 'register' ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400' : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'"
          @click="switchTab('register')"
        >
          Register
        </button>
      </div>

      <!-- ============================================================= -->
      <!-- Login tab -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'login'">
        <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Email</label>
        <input
          v-model="loginEmail"
          type="email"
          placeholder="you@example.com"
          class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
          @keyup.enter="handleLogin"
        />

        <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Password</label>
        <input
          v-model="loginPassword"
          type="password"
          placeholder="Enter your password"
          class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
          @keyup.enter="handleLogin"
        />

        <!-- Captcha -->
        <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Captcha</label>
        <div class="flex items-center gap-3 mb-4">
          <div class="h-[38px] flex items-center">
            <img
              v-if="captchaImage"
              :src="'data:image/png;base64,' + captchaImage"
              alt="captcha"
              class="h-[38px] rounded border border-gray-300 dark:border-gray-600"
            />
            <div v-else class="h-[38px] w-[120px] bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded flex items-center justify-center">
              <span class="text-xs text-gray-400 dark:text-gray-500">Loading...</span>
            </div>
          </div>
          <button
            class="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300"
            :disabled="captchaLoading"
            @click="loadCaptcha"
          >
            Refresh
          </button>
        </div>
        <input
          v-model="captchaCode"
          type="text"
          placeholder="Enter captcha code"
          class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
          @keyup.enter="handleLogin"
        />

        <button
          :disabled="loginLoading || !loginEmail.trim() || !loginPassword || !captchaCode.trim()"
          class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50 transition-colors"
          @click="handleLogin"
        >
          {{ loginLoading ? 'Logging in...' : 'Login' }}
        </button>

          <p class="mt-3 text-xs text-gray-400 dark:text-gray-500 text-center">
          Default account: admin / admin123
        </p>
      </div>

      <!-- ============================================================= -->
      <!-- Register tab -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'register'">
        <!-- Success message -->
        <div v-if="registerSuccess" class="text-center py-4">
          <div class="text-green-600 dark:text-green-400 text-lg font-semibold mb-2">Registration Successful</div>
          <p class="text-gray-500 dark:text-gray-400 text-sm mb-4">
            Please check your email to verify your account, then log in with your email and password.
          </p>
          <button
            class="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
            @click="switchToLogin"
          >
            Go to Login
          </button>
        </div>

        <!-- Register form -->
        <div v-else>
          <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Email</label>
          <input
            v-model="registerEmail"
            type="email"
            placeholder="you@example.com"
            class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleRegister"
          />

          <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Password</label>
          <input
            v-model="registerPassword"
            type="password"
            placeholder="Min 6 characters"
            class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleRegister"
          />

          <!-- Captcha -->
          <label class="block text-sm text-gray-500 dark:text-gray-400 mb-2">Captcha</label>
          <div class="flex items-center gap-3 mb-4">
            <div class="h-[38px] flex items-center">
              <img
                v-if="captchaImage"
                :src="'data:image/png;base64,' + captchaImage"
                alt="captcha"
                class="h-[38px] rounded border border-gray-300 dark:border-gray-600"
              />
              <div v-else class="h-[38px] w-[120px] bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded flex items-center justify-center">
                <span class="text-xs text-gray-400 dark:text-gray-500">Loading...</span>
              </div>
            </div>
            <button
              class="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300"
              :disabled="captchaLoading"
              @click="loadCaptcha"
            >
              Refresh
            </button>
          </div>
          <input
            v-model="captchaCode"
            type="text"
            placeholder="Enter captcha code"
            class="w-full px-3 py-2 mb-4 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleRegister"
          />

          <button
            :disabled="registerLoading || !registerEmail.trim() || !registerPassword || !captchaCode.trim()"
            class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50 transition-colors"
            @click="handleRegister"
          >
            {{ registerLoading ? 'Registering...' : 'Register' }}
          </button>

        <p class="mt-3 text-xs text-gray-400 dark:text-gray-500 text-center">
            A verification email will be sent after registration.
          </p>
        </div>
      </div>
    </div>
  </div>

  <!-- Main app -->
  <div v-else class="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
    <!-- Top nav bar -->
    <header class="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div class="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <router-link to="/" class="text-lg font-bold text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300">
            OTD
          </router-link>
          <span class="text-gray-300 dark:text-gray-500">/</span>
          <span class="text-gray-700 dark:text-gray-300">{{ pageTitle }}</span>
        </div>
        <div class="flex items-center gap-4">
          <router-link
            to="/"
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            Projects
          </router-link>
          <router-link
            to="/keys"
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            API Keys
          </router-link>
          <router-link
            to="/notifications"
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            Notifications
          </router-link>
          <span class="text-xs text-gray-400 dark:text-gray-500 font-mono">{{ userEmail }}</span>
          <router-link
            to="/user-center"
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            User Center
          </router-link>
          <button
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400"
            @click="logout"
          >
            Logout
          </button>
          <!-- Theme toggle -->
          <button
            class="text-sm text-gray-500 dark:text-gray-400 hover:text-yellow-500 dark:hover:text-yellow-300 transition-colors"
            :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="toggleTheme"
          >
            <svg v-if="isDark" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 3v1m0 16v1m8.66-13.66l-.71.71M4.05 19.95l-.71.71M21 12h-1M4 12H3m16.66 7.66l-.71-.71M4.05 4.05l-.71-.71M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          </button>
        </div>
      </div>
    </header>

    <!-- Content -->
    <main class="p-6">
      <router-view />
    </main>
  </div>
    </n-message-provider>
  </n-config-provider>
</template>
