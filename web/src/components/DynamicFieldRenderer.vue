<script setup lang="ts">
/**
 * DynamicFieldRenderer - renders a single field value based on its FieldDefinition type.
 * - text     -> plain text
 * - number   -> formatted number
 * - date     -> formatted date string
 * - enum     -> NTag with color
 * - link     -> clickable hyperlink
 * - assignee -> NAvatar + name
 */
import { computed } from 'vue'
import { NTag, NAvatar } from 'naive-ui'
import type { FieldDefinition, ProjectMember } from '@/types'

const props = defineProps<{
  field: FieldDefinition
  value: any
  members?: ProjectMember[]
}>()

const displayValue = computed(() => {
  if (props.value == null || props.value === '') return '—'
  return String(props.value)
})

const formattedDate = computed(() => {
  if (!props.value) return '—'
  try {
    return new Date(props.value).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return String(props.value)
  }
})

const enumColors: Record<number, string> = {
  0: 'info',
  1: 'success',
  2: 'warning',
  3: 'error',
  4: 'default',
}

const enumTagType = computed(() => {
  if (!props.field.enumValues || !props.value) return 'default'
  const idx = props.field.enumValues.indexOf(props.value)
  return (enumColors[idx % 5] || 'default') as any
})

const avatarInitial = computed(() => {
  if (!props.value) return '?'
  return String(props.value).charAt(0).toUpperCase()
})

const resolvedAssignee = computed(() => {
  if (!props.value) return { display: '—', initial: '?' }
  const val = String(props.value)
  const ms = props.members ?? []
  if (ms.length === 0) return { display: val, initial: val.charAt(0).toUpperCase() }
  const member =
    ms.find((m) => m.memberId === val) ||
    ms.find((m) => m.agentId === val) ||
    ms.find((m) => m.displayName === val)
  if (member) {
    const display = member.displayName || member.agentId
    return { display, initial: display.charAt(0).toUpperCase() }
  }
  return { display: val, initial: val.charAt(0).toUpperCase() }
})
</script>

<template>
  <!-- text -->
  <span v-if="field.fieldType === 'text'" class="text-gray-800 dark:text-gray-200">
    {{ displayValue }}
  </span>

  <!-- number -->
  <span v-else-if="field.fieldType === 'number'" class="text-gray-800 dark:text-gray-200 font-mono">
    {{ displayValue }}
  </span>

  <!-- date -->
  <span v-else-if="field.fieldType === 'date'" class="text-gray-700 dark:text-gray-300">
    {{ formattedDate }}
  </span>

  <!-- enum -->
  <n-tag
    v-else-if="field.fieldType === 'enum'"
    :type="enumTagType"
    size="small"
    round
  >
    {{ displayValue }}
  </n-tag>

  <!-- link -->
  <a
    v-else-if="field.fieldType === 'link'"
    :href="value || '#'"
    target="_blank"
    rel="noopener noreferrer"
    class="text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 underline"
  >
    {{ displayValue }}
  </a>

  <!-- assignee -->
  <span v-else-if="field.fieldType === 'assignee'" class="inline-flex items-center gap-1.5">
    <n-avatar :size="22" round class="bg-blue-700 text-xs">
      {{ resolvedAssignee.initial }}
    </n-avatar>
    <span class="text-gray-800 dark:text-gray-200 text-sm">{{ resolvedAssignee.display }}</span>
  </span>

  <!-- fallback -->
  <span v-else class="text-gray-500 dark:text-gray-400">{{ displayValue }}</span>
</template>
