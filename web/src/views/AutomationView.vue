<script setup lang="ts">
/**
 * AutomationView — Webhook rule configuration, audit log timeline, one-click retry.
 * URL-first: project ID from route param.
 */
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NCard, NSelect, NInput, NSpin, NEmpty, NTag, NTimeline,
  NTimelineItem, useMessage, NPopconfirm
} from 'naive-ui'
import type { WebhookRule, WebhookLogEntry } from '@/types'
import { webhooksList, webhooksCreate, webhookLogs, webhookRetry } from '@/api'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const projectId = computed(() => route.params.id as string)

// Webhook rules
const rules = ref<WebhookRule[]>([])
const rulesLoading = ref(false)

// Create rule form
const showCreateRule = ref(false)
const newEventType = ref<string>('Create')
const newTargetField = ref<string>('*')
const newWebhookUrl = ref('')
const creatingRule = ref(false)

const eventTypeOptions = [
  { label: 'Create', value: 'Create' },
  { label: 'Update', value: 'Update' },
  { label: 'Delete', value: 'Delete' },
]

const targetFieldOptions = computed(() => {
  const opts = [{ label: '* (all fields)', value: '*' }]
  // Could be extended to pull from schema, but keeping it simple with manual input
  return opts
})

async function fetchRules() {
  rulesLoading.value = true
  try {
    rules.value = await webhooksList(projectId.value)
  } finally {
    rulesLoading.value = false
  }
}

async function handleCreateRule() {
  if (!newWebhookUrl.value.trim()) return
  creatingRule.value = true
  try {
    await webhooksCreate(
      projectId.value,
      newEventType.value,
      newWebhookUrl.value.trim(),
      newTargetField.value || '*'
    )
    await fetchRules()
    showCreateRule.value = false
    newWebhookUrl.value = ''
    message.success('Webhook rule created')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to create rule')
  } finally {
    creatingRule.value = false
  }
}

// Audit logs
const logs = ref<WebhookLogEntry[]>([])
const logsTotal = ref(0)
const logsLoading = ref(false)

async function fetchLogs() {
  logsLoading.value = true
  try {
    const res = await webhookLogs(projectId.value)
    logs.value = res.logs
    logsTotal.value = res.total
  } finally {
    logsLoading.value = false
  }
}

async function handleRetry(taskId: string) {
  try {
    const res = await webhookRetry(taskId)
    message.success(`Retried (count: ${res.retryCount})`)
    await fetchLogs()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Retry failed')
  }
}

function statusColor(status: string): 'success' | 'error' | 'warning' | 'info' | 'default' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'pending') return 'warning'
  return 'default'
}

function statusTimelineType(status: string): 'success' | 'error' | 'warning' | 'info' | 'default' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'error'
  return 'warning'
}

onMounted(() => {
  fetchRules()
  fetchLogs()
})
</script>

<template>
  <div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <n-button quaternary size="small" @click="router.push('/')">
          &larr; Projects
        </n-button>
        <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Automation</h2>
        <span class="text-xs text-gray-400 dark:text-gray-500 font-mono">{{ projectId.slice(0, 8) }}</span>
      </div>
    </div>

    <!-- Webhook Rules Section -->
    <section class="mb-8">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-medium text-gray-800 dark:text-gray-200">Webhook Rules</h3>
        <n-button size="small" @click="showCreateRule = !showCreateRule">
          {{ showCreateRule ? 'Cancel' : '+ New Rule' }}
        </n-button>
      </div>

      <!-- Create rule form -->
      <n-card v-if="showCreateRule" class="mb-4" size="small">
        <div class="space-y-3">
          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">Event Type</label>
              <n-select
                v-model:value="newEventType"
                :options="eventTypeOptions"
                size="small"
              />
            </div>
            <div>
              <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">Target Field</label>
              <n-input
                v-model:value="newTargetField"
                placeholder="* for all"
                size="small"
              />
            </div>
            <div>
              <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">Webhook URL</label>
              <n-input
                v-model:value="newWebhookUrl"
                placeholder="https://..."
                size="small"
                @keyup.enter="handleCreateRule"
              />
            </div>
          </div>
          <n-button
            type="primary"
            size="small"
            :loading="creatingRule"
            :disabled="!newWebhookUrl.trim()"
            @click="handleCreateRule"
          >
            Create Rule
          </n-button>
        </div>
      </n-card>

      <!-- Rules list -->
      <div v-if="rulesLoading" class="py-4 flex justify-center"><n-spin /></div>
      <n-empty v-else-if="rules.length === 0" description="No webhook rules" class="py-4" />
      <div v-else class="space-y-2">
        <div
          v-for="rule in rules"
          :key="rule.ruleId"
          class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded p-3 flex items-center justify-between"
        >
          <div class="flex items-center gap-3">
            <n-tag :type="rule.eventType === 'Create' ? 'success' : rule.eventType === 'Update' ? 'info' : 'error'" size="small">
              {{ rule.eventType }}
            </n-tag>
            <span class="text-gray-700 dark:text-gray-300 text-sm">
              field: <code class="text-blue-600 dark:text-blue-400">{{ rule.targetField }}</code>
            </span>
            <span class="text-gray-400 dark:text-gray-500 text-xs">&rarr;</span>
            <span class="text-gray-500 dark:text-gray-400 text-sm font-mono truncate max-w-[300px]">
              {{ rule.webhookUrl }}
            </span>
          </div>
          <span class="text-xs text-gray-400 dark:text-gray-600 font-mono">{{ rule.ruleId.slice(0, 8) }}</span>
        </div>
      </div>
    </section>

    <!-- Audit Log Section -->
    <section>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-medium text-gray-800 dark:text-gray-200">
          Audit Log
          <span v-if="logsTotal > 0" class="text-sm text-gray-400 dark:text-gray-500 font-normal ml-2">({{ logsTotal }})</span>
        </h3>
        <n-button size="small" @click="fetchLogs">Refresh</n-button>
      </div>

      <div v-if="logsLoading" class="py-4 flex justify-center"><n-spin /></div>
      <n-empty v-else-if="logs.length === 0" description="No webhook deliveries yet" class="py-4" />

      <n-timeline v-else>
        <n-timeline-item
          v-for="log in logs"
          :key="log.taskId"
          :type="statusTimelineType(log.status)"
          :title="`${log.eventType} — ${log.todoId.slice(0, 8)}`"
          :time="new Date(log.createdAt).toLocaleString()"
        >
          <div class="text-sm space-y-1">
            <div class="flex items-center gap-2">
              <n-tag :type="statusColor(log.status)" size="small">{{ log.status }}</n-tag>
              <span class="text-gray-400 dark:text-gray-500 font-mono text-xs">{{ log.webhookUrl }}</span>
            </div>
            <div v-if="log.retryCount > 0" class="text-xs text-gray-400 dark:text-gray-500">
              Retries: {{ log.retryCount }}
              <span v-if="log.nextRetryAt"> | Next: {{ new Date(log.nextRetryAt).toLocaleString() }}</span>
            </div>
            <div v-if="log.lastError" class="text-xs text-red-500 dark:text-red-400 font-mono bg-gray-100 dark:bg-gray-900 p-1 rounded">
              {{ log.lastError }}
            </div>
            <n-button
              v-if="log.status === 'failed'"
              size="tiny"
              type="warning"
              class="mt-1"
              @click="handleRetry(log.taskId)"
            >
              Retry Now
            </n-button>
          </div>
        </n-timeline-item>
      </n-timeline>
    </section>
  </div>
</template>
