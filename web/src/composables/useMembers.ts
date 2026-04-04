import { ref } from 'vue'
import type { ProjectMember } from '@/types'
import { membersList, membersAdd, membersRemove } from '@/api'

/** Shared reactive state for project members (singleton pattern). */
const members = ref<ProjectMember[]>([])
const loading = ref(false)

export function useMembers() {
  async function fetchMembers(projectId: string) {
    loading.value = true
    try {
      members.value = await membersList(projectId)
    } finally {
      loading.value = false
    }
  }

  async function addMember(
    projectId: string,
    agentId: string,
    displayName?: string,
    description?: string
  ) {
    const m = await membersAdd(projectId, agentId, displayName, description)
    members.value.push(m)
    return m
  }

  async function removeMember(memberId: string) {
    const result = await membersRemove(memberId)
    members.value = members.value.filter((m) => m.memberId !== memberId)
    return result
  }

  return {
    members,
    loading,
    fetchMembers,
    addMember,
    removeMember,
  }
}
