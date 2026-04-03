/**
 * Converts a flat list of Todos (with parentId) into a nested tree.
 */
import type { Todo, TodoTreeNode } from '@/types'

export function buildTree(flat: Todo[]): TodoTreeNode[] {
  const map = new Map<string, TodoTreeNode>()
  const roots: TodoTreeNode[] = []

  // Create augmented nodes
  for (const item of flat) {
    map.set(item.todoId, { ...item, children: [], expanded: false })
  }

  // Link children to parents
  for (const node of map.values()) {
    if (node.parentId && map.has(node.parentId)) {
      map.get(node.parentId)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

/**
 * Flatten a tree back into an ordered list (depth-first).
 */
export function flattenTree(nodes: TodoTreeNode[], depth = 0): Array<TodoTreeNode & { depth: number }> {
  const result: Array<TodoTreeNode & { depth: number }> = []
  for (const node of nodes) {
    result.push({ ...node, depth })
    if (node.expanded && node.children.length > 0) {
      result.push(...flattenTree(node.children, depth + 1))
    }
  }
  return result
}
