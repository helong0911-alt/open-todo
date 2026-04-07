import { ref } from 'vue'
import type { Project, ProjectSchema, FieldDefinition } from '@/types'
import { projectsList, projectsCreate, projectsUpdate, schemaGet, schemaUpdate } from '@/api'

/** Shared reactive state for projects and active project schema. */
const projects = ref<Project[]>([])
const loading = ref(false)
const activeSchema = ref<ProjectSchema | null>(null)
const schemaLoading = ref(false)

export function useProject() {
  async function fetchProjects() {
    loading.value = true
    try {
      projects.value = await projectsList()
    } finally {
      loading.value = false
    }
  }

  async function createProject(
    name: string,
    description?: string,
    projectDirectory?: string,
    gitUrl?: string
  ) {
    const p = await projectsCreate(name, description, projectDirectory, gitUrl)
    projects.value.push(p)
    return p
  }

  async function updateProject(
    projectId: string,
    data: {
      projectName?: string
      projectDescription?: string
      projectDirectory?: string
      gitUrl?: string
    }
  ) {
    const updated = await projectsUpdate(projectId, data)
    const idx = projects.value.findIndex((p) => p.projectId === projectId)
    if (idx !== -1) {
      projects.value[idx] = updated
    }
    return updated
  }

  async function fetchSchema(projectId: string) {
    schemaLoading.value = true
    try {
      activeSchema.value = await schemaGet(projectId)
    } finally {
      schemaLoading.value = false
    }
  }

  async function updateSchema(projectId: string, fields: FieldDefinition[]) {
    activeSchema.value = await schemaUpdate(projectId, fields)
  }

  return {
    projects,
    loading,
    activeSchema,
    schemaLoading,
    fetchProjects,
    createProject,
    updateProject,
    fetchSchema,
    updateSchema,
  }
}
