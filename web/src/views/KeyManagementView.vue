<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage, NButton, NCard, NInput, NTag, NModal, NSpace } from 'naive-ui'
import { keysCreate, keysList, keysUpdate, keysDelete, keysRefresh } from '@/api'
import type { KeySummary } from '@/types'

const message = useMessage()

const keys = ref<KeySummary[]>([])
const loading = ref(false)

// ---------------------------------------------------------------------------
// Create key modal
// ---------------------------------------------------------------------------
const showCreateModal = ref(false)
const newKeyName = ref('Default')
const createLoading = ref(false)
const createdKeyValue = ref('')
const showCreatedKey = ref(false)

async function fetchKeys() {
  loading.value = true
  try {
    const res = await keysList()
    keys.value = res.keys
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to load API keys.')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!newKeyName.value.trim()) return
  createLoading.value = true
  try {
    const res = await keysCreate(newKeyName.value.trim())
    createdKeyValue.value = res.keyValue
    showCreatedKey.value = true
    showCreateModal.value = false
    newKeyName.value = 'Default'

    // Also store it as the active API key for resource requests
    localStorage.setItem('otd_api_key', res.keyValue)

    await fetchKeys()
    message.success('API key created.')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to create API key.')
  } finally {
    createLoading.value = false
  }
}

function closeCreatedKeyModal() {
  showCreatedKey.value = false
  createdKeyValue.value = ''
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    message.success('Copied to clipboard.')
  }).catch(() => {
    message.error('Failed to copy.')
  })
}

// ---------------------------------------------------------------------------
// Rename
// ---------------------------------------------------------------------------
const renamingKeyId = ref<string | null>(null)
const renameValue = ref('')

function startRename(key: KeySummary) {
  renamingKeyId.value = key.keyId
  renameValue.value = key.keyName
}

async function confirmRename(keyId: string) {
  if (!renameValue.value.trim()) return
  try {
    await keysUpdate(keyId, { keyName: renameValue.value.trim() })
    renamingKeyId.value = null
    await fetchKeys()
    message.success('Key renamed.')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to rename key.')
  }
}

function cancelRename() {
  renamingKeyId.value = null
}

// ---------------------------------------------------------------------------
// Toggle enable/disable
// ---------------------------------------------------------------------------
async function toggleEnabled(key: KeySummary) {
  try {
    await keysUpdate(key.keyId, { isEnabled: !key.isEnabled })
    await fetchKeys()
    message.success(key.isEnabled ? 'Key disabled.' : 'Key enabled.')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to update key.')
  }
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
async function handleDelete(key: KeySummary) {
  if (!confirm(`Delete key "${key.keyName}"? This cannot be undone.`)) return
  try {
    await keysDelete(key.keyId)
    await fetchKeys()
    message.success('Key deleted.')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to delete key.')
  }
}

// ---------------------------------------------------------------------------
// Refresh key (regenerate value)
// ---------------------------------------------------------------------------
async function handleRefresh(key: KeySummary) {
  const label = key.isSystem
    ? `Regenerate System key "${key.keyName}"? You will be logged out and need to re-login.`
    : `Regenerate key "${key.keyName}"? The old value will be immediately invalidated.`
  if (!confirm(label)) return
  try {
    const res = await keysRefresh(key.keyId)

    if (key.isSystem) {
      // System key was regenerated — the stored API key is now invalid.
      // Clear auth state and force re-login so the new key is issued at login.
      localStorage.removeItem('otd_session_token')
      localStorage.removeItem('otd_user_email')
      localStorage.removeItem('otd_api_key')
      window.location.href = '/'
      return
    }

    createdKeyValue.value = res.keyValue
    showCreatedKey.value = true
    await fetchKeys()
    message.success('Key regenerated.')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to regenerate key.')
  }
}

// ---------------------------------------------------------------------------
// Use key (set as active for resource requests)
// ---------------------------------------------------------------------------
function useKey(key: KeySummary) {
  // We can't use the masked key — user would need the full key.
  // But we can indicate this is the "selected" key.
  message.info('To use a key, copy it when first created and set it in your client.')
}

onMounted(fetchKeys)
</script>

<template>
  <div class="max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-100">API Keys</h2>
      <n-button type="primary" @click="showCreateModal = true">
        Create Key
      </n-button>
    </div>

    <p class="text-sm text-gray-400 mb-6">
      API keys are used for programmatic access to the Open-Todo API.
      Send your key as the <code class="text-blue-400">X-API-KEY</code> header.
    </p>

    <!-- Key list -->
    <div v-if="loading" class="text-gray-500 text-center py-8">Loading...</div>
    <div v-else-if="keys.length === 0" class="text-gray-500 text-center py-8">
      No API keys yet. Create one to get started.
    </div>
    <div v-else class="space-y-3">
      <n-card
        v-for="key in keys"
        :key="key.keyId"
        size="small"
        class="bg-gray-900 border-gray-700"
      >
        <div class="flex items-center justify-between">
          <div class="flex-1 min-w-0">
            <!-- Name (inline rename) -->
            <div class="flex items-center gap-2 mb-1">
              <template v-if="renamingKeyId === key.keyId">
                <n-input
                  v-model:value="renameValue"
                  size="small"
                  placeholder="Key name"
                  class="max-w-[200px]"
                  @keyup.enter="confirmRename(key.keyId)"
                />
                <n-button size="tiny" type="primary" @click="confirmRename(key.keyId)">
                  Save
                </n-button>
                <n-button size="tiny" @click="cancelRename">
                  Cancel
                </n-button>
              </template>
              <template v-else>
                <span class="text-gray-100 font-medium">{{ key.keyName }}</span>
                <n-tag v-if="key.isSystem" size="small" type="info">System</n-tag>
                <n-tag
                  :type="key.isEnabled ? 'success' : 'warning'"
                  size="small"
                >
                  {{ key.isEnabled ? 'Enabled' : 'Disabled' }}
                </n-tag>
              </template>
            </div>

            <!-- Masked key -->
            <div class="text-xs text-gray-500 font-mono">
              {{ key.keyValueMasked }}
            </div>

            <!-- Created at -->
            <div class="text-xs text-gray-600 mt-1">
              Created {{ new Date(key.createdAt).toLocaleDateString() }}
            </div>
          </div>

          <!-- Actions -->
          <n-space size="small">
            <n-button v-if="!key.isSystem" size="tiny" quaternary @click="startRename(key)">
              Rename
            </n-button>
            <n-button size="tiny" quaternary type="info" @click="handleRefresh(key)">
              Refresh
            </n-button>
            <n-button
              v-if="!key.isSystem"
              size="tiny"
              quaternary
              :type="key.isEnabled ? 'warning' : 'success'"
              @click="toggleEnabled(key)"
            >
              {{ key.isEnabled ? 'Disable' : 'Enable' }}
            </n-button>
            <n-button v-if="!key.isSystem" size="tiny" quaternary type="error" @click="handleDelete(key)">
              Delete
            </n-button>
          </n-space>
        </div>
      </n-card>
    </div>

    <!-- Create key modal -->
    <n-modal v-model:show="showCreateModal" preset="dialog" title="Create API Key">
      <div class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">Key Name</label>
          <n-input
            v-model:value="newKeyName"
            placeholder="e.g. My Script, CI/CD Pipeline"
          />
        </div>
      </div>
      <template #action>
        <n-space>
          <n-button @click="showCreateModal = false">Cancel</n-button>
          <n-button
            type="primary"
            :loading="createLoading"
            :disabled="!newKeyName.trim()"
            @click="handleCreate"
          >
            Create
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Created key display modal -->
    <n-modal v-model:show="showCreatedKey" preset="dialog" title="API Key Created">
      <div class="space-y-4">
        <p class="text-sm text-gray-400">
          Copy your API key now. You won't be able to see it again.
        </p>
        <div class="flex items-center gap-2">
          <code class="flex-1 px-3 py-2 bg-gray-800 border border-gray-600 rounded text-green-400 text-sm font-mono break-all">
            {{ createdKeyValue }}
          </code>
          <n-button size="small" type="primary" @click="copyToClipboard(createdKeyValue)">
            Copy
          </n-button>
        </div>
      </div>
      <template #action>
        <n-button type="primary" @click="closeCreatedKeyModal">Done</n-button>
      </template>
    </n-modal>
  </div>
</template>
