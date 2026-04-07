<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authVerify } from '@/api'

const route = useRoute()
const router = useRouter()

const status = ref<'loading' | 'success' | 'error'>('loading')
const email = ref('')
const errorMsg = ref('')

onMounted(async () => {
  const token = route.query.token as string | undefined
  if (!token) {
    status.value = 'error'
    errorMsg.value = 'Verification token is missing.'
    return
  }
  try {
    const res = await authVerify(token)
    email.value = res.email
    status.value = 'success'
  } catch (err: any) {
    status.value = 'error'
    errorMsg.value = err?.response?.data?.detail || 'Verification failed. The token may be invalid or expired.'
  }
})

function goToLogin() {
  router.push('/')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
    <div class="w-full max-w-md bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-8 text-center">
      <h1 class="text-2xl font-bold text-blue-600 dark:text-blue-400 mb-6">Open-Todo</h1>

      <!-- Loading -->
      <div v-if="status === 'loading'">
        <div class="flex justify-center mb-4">
          <div class="w-10 h-10 border-4 border-gray-300 dark:border-gray-600 border-t-blue-600 dark:border-t-blue-400 rounded-full animate-spin"></div>
        </div>
        <p class="text-gray-500 dark:text-gray-400">Verifying your email...</p>
      </div>

      <!-- Success -->
      <div v-else-if="status === 'success'">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-green-900/40 border-2 border-green-500 flex items-center justify-center">
          <svg class="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 class="text-xl font-semibold text-green-600 dark:text-green-400 mb-2">Email Verified</h2>
        <p class="text-gray-500 dark:text-gray-400 text-sm mb-1">
          Your account has been activated successfully.
        </p>
        <p v-if="email" class="text-gray-400 dark:text-gray-500 text-xs mb-6">{{ email }}</p>
        <button
          class="px-8 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
          @click="goToLogin"
        >
          Go to Login
        </button>
      </div>

      <!-- Error -->
      <div v-else>
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-red-900/40 border-2 border-red-500 flex items-center justify-center">
          <svg class="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <h2 class="text-xl font-semibold text-red-500 dark:text-red-400 mb-2">Verification Failed</h2>
        <p class="text-gray-500 dark:text-gray-400 text-sm mb-6">{{ errorMsg }}</p>
        <button
          class="px-8 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
          @click="goToLogin"
        >
          Go to Login
        </button>
      </div>
    </div>
  </div>
</template>
