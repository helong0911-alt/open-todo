<script setup lang="ts">
/**
 * ProjectDetailView — WBS tree-table with schema and member management.
 * URL-first: project ID comes from route param.
 */
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NModal, NCard, NInput, NSelect, NSpin, NEmpty,
  NForm, NFormItem, NDynamicInput, NTag, NPopconfirm, useMessage
} from 'naive-ui'
import { useProject } from '@/composables/useProject'
import { useTodos } from '@/composables/useTodos'
import { useMembers } from '@/composables/useMembers'
import TodoTreeRow from '@/components/TodoTreeRow.vue'
import type { FieldDefinition, TodoTreeNode } from '@/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const projectId = computed(() => route.params.id as string)

const { activeSchema, schemaLoading, fetchSchema, updateSchema } = useProject()
const { flatList, loading: todosLoading, fetchTodos, createTodo, updateTodo, deleteTodo, toggleExpand } = useTodos()
const { members, loading: membersLoading, fetchMembers, addMember, removeMember } = useMembers()

// Schema editor
const showSchemaEditor = ref(false)
const editingFields = ref<FieldDefinition[]>([])
const savingSchema = ref(false)

function openSchemaEditor() {
  editingFields.value = activeSchema.value
    ? JSON.parse(JSON.stringify(activeSchema.value.fieldsDefinition))
    : []
  showSchemaEditor.value = true
}

async function saveSchema() {
  savingSchema.value = true
  try {
    await updateSchema(projectId.value, editingFields.value)
    showSchemaEditor.value = false
    message.success('Schema updated')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to update schema')
  } finally {
    savingSchema.value = false
  }
}

// Members management
const showMembersModal = ref(false)
const newAgentId = ref('')
const newDisplayName = ref('')
const newDescription = ref('')
const addingMember = ref(false)

function openMembersModal() {
  showMembersModal.value = true
}

async function handleAddMember() {
  if (!newAgentId.value.trim()) {
    message.warning('Agent ID is required')
    return
  }
  addingMember.value = true
  try {
    await addMember(
      projectId.value,
      newAgentId.value.trim(),
      newDisplayName.value.trim() || undefined,
      newDescription.value.trim() || undefined
    )
    newAgentId.value = ''
    newDisplayName.value = ''
    newDescription.value = ''
    message.success('Member added')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to add member')
  } finally {
    addingMember.value = false
  }
}

async function handleRemoveMember(memberId: string) {
  try {
    await removeMember(memberId)
    message.success('Member removed')
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Failed to remove member')
  }
}

// Todo create / edit modal
const showTodoModal = ref(false)
const editingTodo = ref<TodoTreeNode | null>(null)
const todoParentId = ref<string | undefined>(undefined)
const todoContent = ref<Record<string, any>>({})
const savingTodo = ref(false)

const fields = computed<FieldDefinition[]>(() =>
  activeSchema.value?.fieldsDefinition ?? []
)

const fieldTypeOptions = [
  { label: 'text', value: 'text' },
  { label: 'number', value: 'number' },
  { label: 'date', value: 'date' },
  { label: 'enum', value: 'enum' },
  { label: 'link', value: 'link' },
  { label: 'assignee', value: 'assignee' },
]

// Assignee select options derived from members
const assigneeOptions = computed(() =>
  members.value.map((m) => ({
    label: m.displayName || m.agentId,
    value: m.agentId,
    description: m.description,
  }))
)

function openCreateTodo(parentId?: string) {
  editingTodo.value = null
  todoParentId.value = parentId
  todoContent.value = {}
  showTodoModal.value = true
}

function openEditTodo(node: TodoTreeNode) {
  editingTodo.value = node
  todoParentId.value = undefined
  todoContent.value = { ...node.content }
  showTodoModal.value = true
}

async function saveTodo() {
  savingTodo.value = true
  try {
    if (editingTodo.value) {
      await updateTodo(editingTodo.value.todoId, todoContent.value, {
        version: editingTodo.value.version,
      })
      message.success('Updated')
    } else {
      await createTodo(projectId.value, todoContent.value, todoParentId.value)
      message.success('Created')
    }
    showTodoModal.value = false
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Save failed')
  } finally {
    savingTodo.value = false
  }
}

async function handleDelete(todoId: string) {
  try {
    const result = await deleteTodo(todoId)
    message.success(`Deleted ${result.deletedCount} task(s)`)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Delete failed')
  }
}

async function handleToggleComplete(node: TodoTreeNode) {
  try {
    await updateTodo(node.todoId, node.content, {
      isCompleted: !node.isCompleted,
      version: node.version,
    })
  } catch (err: any) {
    message.error(err?.response?.data?.detail || 'Update failed')
  }
}

// Polling for real-time sync (optional, every 10s)
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    fetchTodos(projectId.value)
  }, 10000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Load data
onMounted(async () => {
  await fetchSchema(projectId.value)
  await Promise.all([
    fetchTodos(projectId.value),
    fetchMembers(projectId.value),
  ])
  startPolling()
})

// Cleanup on unmount-ish (watch for route change)
watch(
  () => route.params.id,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      stopPolling()
      await fetchSchema(newId)
      await Promise.all([
        fetchTodos(newId),
        fetchMembers(newId),
      ])
      startPolling()
    }
  }
)
</script>

<template>
  <div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-3">
        <n-button quaternary size="small" @click="router.push('/')">
          &larr; Projects
        </n-button>
        <h2 class="text-xl font-semibold text-gray-100">WBS Tree</h2>
        <span class="text-xs text-gray-500 font-mono">{{ projectId.slice(0, 8) }}</span>
      </div>
      <div class="flex gap-2">
        <n-button size="small" @click="openSchemaEditor">
          Schema
        </n-button>
        <n-button size="small" @click="openMembersModal">
          Members
          <span v-if="members.length" class="ml-1 text-xs text-gray-400">({{ members.length }})</span>
        </n-button>
        <n-button size="small" @click="() => fetchTodos(projectId)">
          Refresh
        </n-button>
        <n-button type="primary" size="small" @click="openCreateTodo()">
          + Root Task
        </n-button>
      </div>
    </div>

    <!-- Schema info -->
    <div v-if="schemaLoading" class="py-4 flex justify-center"><n-spin /></div>
    <div v-else-if="fields.length === 0" class="mb-4 p-3 bg-gray-900 border border-gray-800 rounded text-sm text-gray-400">
      No schema fields defined.
      <button class="text-blue-400 hover:underline ml-1" @click="openSchemaEditor">Configure schema</button>
      to add dynamic fields.
    </div>

    <!-- WBS Tree Table -->
    <div v-if="todosLoading && flatList.length === 0" class="py-12 flex justify-center">
      <n-spin size="large" />
    </div>
    <n-empty v-else-if="flatList.length === 0" description="No tasks yet" class="py-12" />
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-700 text-left text-gray-400">
            <th class="px-3 py-2 font-medium min-w-[280px]">
              {{ fields.length > 0 ? fields[0].fieldName : 'Task' }}
            </th>
            <th
              v-for="field in fields.slice(1)"
              :key="field.fieldName"
              class="px-3 py-2 font-medium"
            >
              {{ field.fieldName }}
            </th>
            <th class="px-3 py-2 font-medium text-right w-[160px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          <TodoTreeRow
            v-for="node in flatList"
            :key="node.todoId"
            :node="node"
            :fields="fields"
            :members="members"
            @toggle="toggleExpand"
            @add-child="openCreateTodo"
            @edit="openEditTodo"
            @delete="handleDelete"
            @toggle-complete="handleToggleComplete"
          />
        </tbody>
      </table>
    </div>

    <!-- Schema editor modal -->
    <n-modal v-model:show="showSchemaEditor">
      <n-card title="Edit Schema" :bordered="false" style="width: 600px; max-width: 90vw;">
        <div class="space-y-4">
          <div
            v-for="(field, idx) in editingFields"
            :key="idx"
            class="flex items-start gap-2 bg-gray-900 border border-gray-800 rounded p-3"
          >
            <div class="flex-1 space-y-2">
              <n-input v-model:value="field.fieldName" placeholder="Field name" size="small" />
              <n-select
                v-model:value="field.fieldType"
                :options="fieldTypeOptions"
                placeholder="Type"
                size="small"
              />
              <n-input
                v-model:value="field.fieldDescription"
                placeholder="Description (optional)"
                size="small"
              />
              <n-dynamic-input
                v-if="field.fieldType === 'enum'"
                v-model:value="field.enumValues"
                placeholder="Enum value"
                size="small"
              />
            </div>
            <n-button
              size="tiny"
              quaternary
              class="text-red-400 mt-1"
              @click="editingFields.splice(idx, 1)"
            >
              X
            </n-button>
          </div>

          <n-button
            dashed
            block
            @click="editingFields.push({ fieldName: '', fieldType: 'text' } as any)"
          >
            + Add Field
          </n-button>
        </div>

        <template #action>
          <div class="flex justify-end gap-2">
            <n-button @click="showSchemaEditor = false">Cancel</n-button>
            <n-button type="primary" :loading="savingSchema" @click="saveSchema">
              Save Schema
            </n-button>
          </div>
        </template>
      </n-card>
    </n-modal>

    <!-- Members management modal -->
    <n-modal v-model:show="showMembersModal">
      <n-card title="Project Members" :bordered="false" style="width: 560px; max-width: 90vw;">
        <!-- Existing members -->
        <div class="space-y-2 mb-4">
          <div v-if="membersLoading" class="py-4 flex justify-center"><n-spin /></div>
          <div v-else-if="members.length === 0" class="text-sm text-gray-500 py-2">
            No members registered yet.
          </div>
          <div
            v-for="m in members"
            :key="m.memberId"
            class="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded p-3"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-gray-200 truncate">{{ m.displayName || m.agentId }}</span>
                <n-tag size="tiny" type="info" round>Agent</n-tag>
              </div>
              <div class="text-xs text-gray-500 font-mono mt-0.5">{{ m.agentId }}</div>
              <div v-if="m.description" class="text-xs text-gray-400 mt-1">{{ m.description }}</div>
            </div>
            <n-popconfirm @positive-click="handleRemoveMember(m.memberId)">
              <template #trigger>
                <n-button size="tiny" quaternary class="text-red-400">Remove</n-button>
              </template>
              Remove this member?
            </n-popconfirm>
          </div>
        </div>

        <!-- Add member form -->
        <div class="border-t border-gray-800 pt-4">
          <h4 class="text-sm font-medium text-gray-300 mb-2">Add Member</h4>
          <div class="space-y-2">
            <n-input
              v-model:value="newAgentId"
              placeholder="Agent ID (required)"
              size="small"
            />
            <n-input
              v-model:value="newDisplayName"
              placeholder="Display name (optional)"
              size="small"
            />
            <n-input
              v-model:value="newDescription"
              placeholder="Description (optional)"
              size="small"
            />
            <n-button
              type="primary"
              size="small"
              :loading="addingMember"
              :disabled="!newAgentId.trim()"
              @click="handleAddMember"
            >
              + Add
            </n-button>
          </div>
        </div>

        <template #action>
          <div class="flex justify-end">
            <n-button @click="showMembersModal = false">Close</n-button>
          </div>
        </template>
      </n-card>
    </n-modal>

    <!-- Todo create/edit modal -->
    <n-modal v-model:show="showTodoModal">
      <n-card
        :title="editingTodo ? 'Edit Task' : 'New Task'"
        :bordered="false"
        style="width: 500px; max-width: 90vw;"
      >
        <div class="space-y-3">
          <div v-if="fields.length === 0" class="text-sm text-gray-400 mb-2">
            No schema fields. Data will be saved as raw JSON.
          </div>
          <div v-for="field in fields" :key="field.fieldName">
            <label class="block text-xs text-gray-400 mb-1">
              {{ field.fieldName }}
              <span v-if="field.fieldDescription" class="text-gray-600"> — {{ field.fieldDescription }}</span>
            </label>

            <!-- enum -> select -->
            <n-select
              v-if="field.fieldType === 'enum'"
              :value="todoContent[field.fieldName] || null"
              :options="(field.enumValues || []).map(v => ({ label: v, value: v }))"
              clearable
              placeholder="Select..."
              size="small"
              @update:value="(v: string | null) => todoContent[field.fieldName] = v"
            />

            <!-- assignee -> select from members (or fallback to text input) -->
            <n-select
              v-else-if="field.fieldType === 'assignee' && assigneeOptions.length > 0"
              :value="todoContent[field.fieldName] || null"
              :options="assigneeOptions"
              clearable
              filterable
              placeholder="Select assignee..."
              size="small"
              @update:value="(v: string | null) => todoContent[field.fieldName] = v"
            />

            <!-- assignee fallback when no members -->
            <n-input
              v-else-if="field.fieldType === 'assignee'"
              :value="todoContent[field.fieldName] || ''"
              placeholder="Assignee"
              size="small"
              @update:value="(v: string) => todoContent[field.fieldName] = v || undefined"
            />

            <!-- number -->
            <n-input
              v-else-if="field.fieldType === 'number'"
              :value="todoContent[field.fieldName]?.toString() || ''"
              placeholder="0"
              size="small"
              @update:value="(v: string) => todoContent[field.fieldName] = v ? Number(v) : undefined"
            />

            <!-- date -->
            <n-input
              v-else-if="field.fieldType === 'date'"
              :value="todoContent[field.fieldName] || ''"
              placeholder="YYYY-MM-DD"
              size="small"
              @update:value="(v: string) => todoContent[field.fieldName] = v || undefined"
            />

            <!-- text / link -->
            <n-input
              v-else
              :value="todoContent[field.fieldName] || ''"
              :placeholder="field.fieldType === 'link' ? 'https://...' : field.fieldName"
              size="small"
              @update:value="(v: string) => todoContent[field.fieldName] = v || undefined"
            />
          </div>

          <!-- Fallback raw JSON when no schema -->
          <div v-if="fields.length === 0">
            <n-input
              :value="JSON.stringify(todoContent, null, 2)"
              type="textarea"
              :rows="4"
              placeholder='{ "title": "My task" }'
              @update:value="(v: string) => { try { todoContent = JSON.parse(v) } catch {} }"
            />
          </div>
        </div>

        <template #action>
          <div class="flex justify-end gap-2">
            <n-button @click="showTodoModal = false">Cancel</n-button>
            <n-button type="primary" :loading="savingTodo" @click="saveTodo">
              {{ editingTodo ? 'Update' : 'Create' }}
            </n-button>
          </div>
        </template>
      </n-card>
    </n-modal>
  </div>
</template>
