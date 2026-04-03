<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage, NCard, NSwitch } from 'naive-ui'
import { notificationRulesCreate, notificationRulesList, notificationRulesDelete } from '@/api'
import type { NotificationRule } from '@/types'

const message = useMessage()

const rules = ref<NotificationRule[]>([])
const loading = ref(false)

const EVENT_TYPES = [
  { value: 'TaskCreate', label: 'Task Created', description: 'Email when a new task is created.' },
  { value: 'TaskUpdate', label: 'Task Updated', description: 'Email when a task is updated.' },
  { value: 'TaskDelete', label: 'Task Deleted', description: 'Email when a task is deleted.' },
  { value: 'WebhookFailure', label: 'Webhook Failure', description: 'Email when a webhook delivery permanently fails.' },
]

const ruleMap = computed(() => {
  const map: Record<string, NotificationRule> = {}
  for (const r of rules.value) {
    map[r.eventType] = r
  }
  return map
})

async function fetchRules() {
  loading.value = true
  try {
    rules.value = await notificationRulesList()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to load notification rules.')
  } finally {
    loading.value = false
  }
}

async function toggle(eventType: string) {
  const existing = ruleMap.value[eventType]
  try {
    if (existing) {
      await notificationRulesDelete(existing.ruleId)
    } else {
      await notificationRulesCreate(eventType)
    }
    await fetchRules()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to update notification rule.')
  }
}

onMounted(fetchRules)
</script>

<template>
  <div class="max-w-6xl mx-auto">
    <h2 class="text-xl font-bold text-gray-100 mb-2">Notifications</h2>
    <p class="text-sm text-gray-400 mb-6">
      Toggle email notifications for task and webhook events.
    </p>

    <div v-if="loading" class="text-gray-500 text-center py-8">Loading...</div>
    <div v-else class="space-y-3">
      <n-card
        v-for="evt in EVENT_TYPES"
        :key="evt.value"
        size="small"
        class="bg-gray-900 border-gray-700"
      >
        <div class="flex items-center justify-between">
          <div>
            <span class="text-gray-100 font-medium">{{ evt.label }}</span>
            <div class="text-xs text-gray-500 mt-1">{{ evt.description }}</div>
          </div>
          <n-switch
            :value="!!ruleMap[evt.value]"
            @update:value="toggle(evt.value)"
          />
        </div>
      </n-card>
    </div>
  </div>
</template>
