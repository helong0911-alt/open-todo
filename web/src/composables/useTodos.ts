import { ref, computed } from 'vue'
import type { Todo, TodoTreeNode } from '@/types'
import { todosList, todosCreate, todosUpdate, todosDelete } from '@/api'
import { buildTree, flattenTree } from '@/utils/treeBuilder'

const rawTodos = ref<Todo[]>([])
const treeRoots = ref<TodoTreeNode[]>([])
const loading = ref(false)

export function useTodos() {
  /** Rebuild tree from raw flat list while preserving expanded state. */
  function rebuildTree() {
    const oldExpanded = new Set<string>()
    function collectExpanded(nodes: TodoTreeNode[]) {
      for (const n of nodes) {
        if (n.expanded) oldExpanded.add(n.todoId)
        collectExpanded(n.children)
      }
    }
    collectExpanded(treeRoots.value)

    treeRoots.value = buildTree(rawTodos.value)

    // Restore expanded state
    function restoreExpanded(nodes: TodoTreeNode[]) {
      for (const n of nodes) {
        if (oldExpanded.has(n.todoId)) n.expanded = true
        restoreExpanded(n.children)
      }
    }
    restoreExpanded(treeRoots.value)
  }

  async function fetchTodos(projectId: string) {
    loading.value = true
    try {
      rawTodos.value = await todosList(projectId)
      rebuildTree()
    } finally {
      loading.value = false
    }
  }

  async function createTodo(projectId: string, content: Record<string, any>, parentId?: string) {
    const todo = await todosCreate(projectId, content, parentId)
    rawTodos.value.push(todo)
    rebuildTree()
    return todo
  }

  async function updateTodo(todoId: string, content: Record<string, any>, opts?: { isCompleted?: boolean; version?: number }) {
    const updated = await todosUpdate(todoId, content, opts)
    const idx = rawTodos.value.findIndex((t) => t.todoId === todoId)
    if (idx >= 0) rawTodos.value[idx] = updated
    rebuildTree()
    return updated
  }

  async function deleteTodo(todoId: string) {
    const result = await todosDelete(todoId)
    // Remove the deleted todo and all its descendants
    const idsToRemove = new Set<string>()
    idsToRemove.add(todoId)
    // BFS to find descendants
    let changed = true
    while (changed) {
      changed = false
      for (const t of rawTodos.value) {
        if (t.parentId && idsToRemove.has(t.parentId) && !idsToRemove.has(t.todoId)) {
          idsToRemove.add(t.todoId)
          changed = true
        }
      }
    }
    rawTodos.value = rawTodos.value.filter((t) => !idsToRemove.has(t.todoId))
    rebuildTree()
    return result
  }

  function toggleExpand(todoId: string) {
    function toggle(nodes: TodoTreeNode[]): boolean {
      for (const n of nodes) {
        if (n.todoId === todoId) {
          n.expanded = !n.expanded
          return true
        }
        if (toggle(n.children)) return true
      }
      return false
    }
    toggle(treeRoots.value)
  }

  const flatList = computed(() => flattenTree(treeRoots.value))

  return {
    rawTodos,
    treeRoots,
    flatList,
    loading,
    fetchTodos,
    createTodo,
    updateTodo,
    deleteTodo,
    toggleExpand,
    rebuildTree,
  }
}
