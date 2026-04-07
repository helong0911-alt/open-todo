<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NCard, NSpin, NEmpty } from 'naive-ui'
import { useProject } from '@/composables/useProject'

const router = useRouter()
const { projects, loading, fetchProjects, createProject } = useProject()

const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')
const newDirectory = ref('')
const newGitUrl = ref('')
const creating = ref(false)

async function handleCreate() {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    await createProject(
      newName.value.trim(),
      newDesc.value.trim() || undefined,
      newDirectory.value.trim() || undefined,
      newGitUrl.value.trim() || undefined
    )
    newName.value = ''
    newDesc.value = ''
    newDirectory.value = ''
    newGitUrl.value = ''
    showCreate.value = false
  } catch (err: any) {
    window.alert(err?.response?.data?.detail || 'Failed to create project')
  } finally {
    creating.value = false
  }
}

function goToProject(id: string) {
  router.push(`/project/${id}`)
}

onMounted(() => {
  fetchProjects()
})
</script>

<template>
  <div class="max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Projects</h2>
      <n-button type="primary" @click="showCreate = !showCreate">
        {{ showCreate ? 'Cancel' : '+ New Project' }}
      </n-button>
    </div>

    <!-- Create form -->
    <n-card v-if="showCreate" class="mb-6" size="small">
      <div class="space-y-3">
        <n-input
          v-model:value="newName"
          placeholder="Project name"
          @keyup.enter="handleCreate"
        />
        <n-input
          v-model:value="newDesc"
          type="textarea"
          placeholder="Description (optional)"
          :rows="2"
        />
        <n-input
          v-model:value="newDirectory"
          placeholder="Project directory (optional)"
        />
        <n-input
          v-model:value="newGitUrl"
          placeholder="Git URL (optional)"
        />
        <n-button
          type="primary"
          :loading="creating"
          :disabled="!newName.trim()"
          @click="handleCreate"
        >
          Create
        </n-button>
      </div>
    </n-card>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12">
      <n-spin size="large" />
    </div>

    <!-- Empty state -->
    <n-empty v-else-if="projects.length === 0" description="No projects yet" class="py-12" />

    <!-- Project list -->
    <div v-else class="space-y-3">
      <div
        v-for="p in projects"
        :key="p.projectId"
        class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 cursor-pointer hover:border-gray-400 dark:hover:border-gray-600 transition-colors"
        @click="goToProject(p.projectId)"
      >
        <div class="flex items-center justify-between">
          <div class="min-w-0 flex-1">
            <h3 class="text-gray-900 dark:text-gray-100 font-medium">{{ p.projectName }}</h3>
            <p v-if="p.projectDescription" class="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {{ p.projectDescription }}
            </p>
            <div v-if="p.projectDirectory || p.gitUrl" class="flex flex-wrap gap-x-4 gap-y-1 mt-2">
              <span v-if="p.projectDirectory" class="text-xs text-gray-400 dark:text-gray-500 font-mono truncate max-w-xs" :title="p.projectDirectory">
                Dir: {{ p.projectDirectory }}
              </span>
              <span v-if="p.gitUrl" class="text-xs text-gray-400 dark:text-gray-500 font-mono truncate max-w-xs" :title="p.gitUrl">
                Git: {{ p.gitUrl }}
              </span>
            </div>
          </div>
          <div class="flex gap-2 ml-4 shrink-0">
            <router-link
              :to="`/project/${p.projectId}/automation`"
              class="text-xs text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
              @click.stop
            >
              Automation
            </router-link>
            <span class="text-gray-400 dark:text-gray-600 text-xs font-mono">{{ p.projectId.slice(0, 8) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
