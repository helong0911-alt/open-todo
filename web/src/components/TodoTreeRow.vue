<script setup lang="ts">
/**
 * TodoTreeRow — a single row in the WBS tree-table.
 * Shows expand/collapse toggle, indentation, dynamic field values, action buttons.
 * Used within ProjectDetailView's flattened tree list.
 */
import { ref } from 'vue'
import { NButton, NIcon, NPopconfirm, NCheckbox } from 'naive-ui'
import DynamicFieldRenderer from './DynamicFieldRenderer.vue'
import type { TodoTreeNode, FieldDefinition } from '@/types'

const props = defineProps<{
  node: TodoTreeNode & { depth: number }
  fields: FieldDefinition[]
}>()

const emit = defineEmits<{
  (e: 'toggle', todoId: string): void
  (e: 'addChild', parentId: string): void
  (e: 'edit', node: TodoTreeNode): void
  (e: 'delete', todoId: string): void
  (e: 'toggleComplete', node: TodoTreeNode): void
}>()

const indent = ref(props.node.depth * 24)
</script>

<template>
  <tr class="border-b border-gray-800 hover:bg-gray-900/50 transition-colors">
    <!-- Tree column: indent + expand toggle + first field or ID -->
    <td class="px-3 py-2 whitespace-nowrap">
      <div class="flex items-center" :style="{ paddingLeft: indent + 'px' }">
        <!-- Expand/collapse button -->
        <button
          v-if="node.children && node.children.length > 0"
          class="w-5 h-5 mr-1 flex items-center justify-center text-gray-400 hover:text-gray-200"
          @click="emit('toggle', node.todoId)"
        >
          <svg
            class="w-3.5 h-3.5 transition-transform"
            :class="{ 'rotate-90': node.expanded }"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M6 6l8 4-8 4V6z" />
          </svg>
        </button>
        <span v-else class="w-5 mr-1" />

        <!-- Completion checkbox -->
        <n-checkbox
          :checked="node.isCompleted"
          class="mr-2"
          @update:checked="emit('toggleComplete', node)"
        />

        <!-- First field value or todoId snippet -->
        <span
          class="text-gray-200 truncate max-w-[200px]"
          :class="{ 'line-through text-gray-500': node.isCompleted }"
        >
          <template v-if="fields.length > 0 && node.content[fields[0].fieldName]">
            {{ node.content[fields[0].fieldName] }}
          </template>
          <template v-else>
            <span class="text-gray-500 font-mono text-xs">{{ node.todoId.slice(0, 8) }}</span>
          </template>
        </span>
      </div>
    </td>

    <!-- Dynamic field columns (skip first, already shown in tree col) -->
    <td
      v-for="field in fields.slice(1)"
      :key="field.fieldName"
      class="px-3 py-2"
    >
      <DynamicFieldRenderer
        :field="field"
        :value="node.content[field.fieldName]"
      />
    </td>

    <!-- Actions column -->
    <td class="px-3 py-2 whitespace-nowrap text-right">
      <div class="flex items-center justify-end gap-1">
        <n-button
          size="tiny"
          quaternary
          class="text-green-500"
          title="Add child task"
          @click="emit('addChild', node.todoId)"
        >
          + Child
        </n-button>
        <n-button
          size="tiny"
          quaternary
          class="text-blue-400"
          title="Edit"
          @click="emit('edit', node)"
        >
          Edit
        </n-button>
        <n-popconfirm @positive-click="emit('delete', node.todoId)">
          <template #trigger>
            <n-button size="tiny" quaternary class="text-red-400" title="Delete">
              Del
            </n-button>
          </template>
          Delete this task and all children?
        </n-popconfirm>
      </div>
    </td>
  </tr>
</template>
