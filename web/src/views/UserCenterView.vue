<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { authChangePassword, authLogout } from '@/api'

const router = useRouter()
const message = useMessage()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const changePasswordLoading = ref(false)

async function handleChangePassword() {
  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    message.warning('Please fill in all fields.')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    message.error('New password and confirm password do not match.')
    return
  }
  if (newPassword.value.length < 6) {
    message.error('New password must be at least 6 characters.')
    return
  }
  
  changePasswordLoading.value = true
  try {
    await authChangePassword(oldPassword.value, newPassword.value)
    message.success('Password changed successfully. Please log in again.')
    
    // Clear session and reload
    const sessionToken = localStorage.getItem('otd_session_token')
    if (sessionToken) {
      try {
        await authLogout(sessionToken)
      } catch {
        // ignore
      }
    }
    
    localStorage.removeItem('otd_session_token')
    localStorage.removeItem('otd_user_email')
    localStorage.removeItem('otd_api_key')
    
    window.location.href = '/'
  } catch (err: any) {
    const msg = err?.response?.data?.detail || 'Failed to change password.'
    message.error(msg)
  } finally {
    changePasswordLoading.value = false
  }
}
</script>

<template>
  <div class="max-w-3xl mx-auto py-8 px-4">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-gray-100">User Center</h1>
      <p class="text-sm text-gray-400 mt-1">Manage your account profile and security.</p>
    </div>

    <div class="bg-gray-900 border border-gray-800 rounded-lg p-6">
      <h2 class="text-xl font-semibold mb-6 text-gray-100 border-b border-gray-800 pb-2">Change Password</h2>
      
      <div class="space-y-4 max-w-md">
        <div>
          <label class="block text-sm text-gray-400 mb-2">Current Password</label>
          <input
            v-model="oldPassword"
            type="password"
            placeholder="Current password"
            class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleChangePassword"
          />
        </div>
        
        <div>
          <label class="block text-sm text-gray-400 mb-2">New Password</label>
          <input
            v-model="newPassword"
            type="password"
            placeholder="New password"
            class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleChangePassword"
          />
        </div>
        
        <div>
          <label class="block text-sm text-gray-400 mb-2">Confirm New Password</label>
          <input
            v-model="confirmPassword"
            type="password"
            placeholder="Confirm new password"
            class="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            @keyup.enter="handleChangePassword"
          />
        </div>
        
        <div class="pt-4">
          <button
            class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors disabled:opacity-50"
            @click="handleChangePassword"
            :disabled="changePasswordLoading || !oldPassword || !newPassword || !confirmPassword"
          >
            {{ changePasswordLoading ? 'Saving...' : 'Update Password' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
