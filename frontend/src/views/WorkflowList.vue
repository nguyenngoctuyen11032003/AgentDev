<template>
  <div class="workflow-list">
    <div class="header-container">
      <!-- Search Bar -->
      <div class="search-container">
        <span class="search-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 21L15 15M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
        <input 
          type="text" 
          v-model="searchQuery" 
          :placeholder="$t('workflow_list.search_placeholder')"
          :aria-label="$t('workflow_list.search_placeholder')"
          class="search-input"
        />
      </div>

      <button class="btn create-btn" @click="openFormGenerator" :title="$t('workflow_list.create')">
        <span>{{ $t('workflow_list.create') }}</span>
        <span class="plus-icon">+</span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
      <p>{{ $t('workflow_list.loading') }}</p>
    </div>
    
    <!-- Error State -->
    <div v-else-if="error" class="error-message">
      <div class="error-icon">⚠️</div>
      <p>{{ error }}</p>
      <button @click="loadWorkflows()" class="retry-button">{{ $t('common.retry') }}</button>
    </div>
    
    <!-- File List -->
    <div v-else class="file-list">
      <!-- Animation for search filter -->
      <transition-group
        name="file-fade"
        tag="div"
        class="file-list-inner"
      >
        <div 
          v-for="file in filteredFiles" 
          :key="file.name"
          :class="['file-item', { active: isSelected(file) }]"
          @click="goToWorkflowView(file.name)"
        >
          <div class="file-info">
            <div class="file-name" :title="file.name">{{ displayName(file.name) }}</div>
            <div class="file-description">{{ localizedWorkflowDescription(file.name, file.description) }}</div>
          </div>
          <button
            type="button"
            class="lab-btn"
            :title="$t('workflow_list.try_in_lab_hint')"
            :aria-label="`${$t('workflow_list.try_in_lab')}: ${displayName(file.name)}`"
            @click.stop="goToLab(file.name)"
          >{{ $t('workflow_list.try_in_lab') }}</button>
          <button
            type="button"
            class="delete-btn"
            :title="$t('workflow_list.delete')"
            :aria-label="$t('workflow_list.delete_aria', { name: displayName(file.name) })"
            :disabled="deleting === file.name"
            @click.stop="confirmDelete(file)"
          >
            <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
            </svg>
          </button>
          <div class="file-arrow">→</div>
        </div>
      </transition-group>
      
      <!-- Empty State -->
      <div v-if="filteredFiles.length === 0" class="empty-state">
        <p>{{ searchQuery.trim() && yamlFiles.length ? $t('workflow_list.no_search_results') : $t('workflow_list.no_files') }}</p>
      </div>
    </div>

    <!-- Create: blank workflow or a ready-made department (lead + roster) -->
    <Teleport to="body">
      <DepartmentTemplatePicker
        v-if="showTemplatePicker"
        :existing-files="yamlFiles.map((f) => f?.name).filter(Boolean)"
        :loading="loading && !yamlFiles.length"
        @close="showTemplatePicker = false"
        @blank="openBlankForm"
        @created="handleTemplateCreated"
      />
    </Teleport>

    <!-- FormGenerator Modal -->
    <!-- Teleport to body in WorkflowWorkbench -->
    <Teleport to="body">
      <FormGenerator
        v-if="showFormGenerator"
        :breadcrumbs="[{node: 'DesignConfig', field: 'graph'}]"
        :recursive="false"
        :title="$t('workflow_list.create_title')"
        :submit-label="$t('workflow_list.create')"
        @close="closeFormGenerator"
        @submit="handleFormGeneratorSubmit"
      />
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchWorkflowsWithDesc, deleteWorkflow } from '@/api/client.js'
import { onWorkflowChanged } from '@/utils/workflowSync.js'
import { confirmDialog } from '@/utils/confirm.js'
import { toast } from '@/utils/toast.js'
import { localizedWorkflowDescription } from '@/utils/workflowDescription.js'
import FormGenerator from '@/components/form/FormGenerator.vue'
import DepartmentTemplatePicker from '@/components/workflow/DepartmentTemplatePicker.vue'

const router = useRouter()
const { locale, t } = useI18n()
const props = defineProps({
  selected: {
    type: String,
    default: ''
  },
  useRouting: {
    type: Boolean,
    default: true
  }
})
const emit = defineEmits(['select'])
const yamlFiles = ref([])
const loading = ref(false)
const error = ref(null)

const showFormGenerator = ref(false)
const deleting = ref('')
const showTemplatePicker = ref(false)
const searchQuery = ref('')

// Debounced copy of the search query so filtering/sorting and the list
// transition don't run on every keystroke
const debouncedQuery = ref('')
let searchDebounceTimer = null
watch(searchQuery, (value) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (!value.trim()) {
    // Clearing the box should feel instant
    searchDebounceTimer = null
    debouncedQuery.value = value
    return
  }
  searchDebounceTimer = setTimeout(() => {
    searchDebounceTimer = null
    debouncedQuery.value = value
  }, 120)
})

onBeforeUnmount(() => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
})

let loadSeq = 0
// `silent` refreshes in the background (no spinner, list stays on screen)
const loadWorkflows = async ({ silent = false } = {}) => {
  const seq = ++loadSeq
  if (!silent) {
    loading.value = true
    error.value = null
  }

  const result = await fetchWorkflowsWithDesc()
  if (seq !== loadSeq) return
  if (result.success) {
    yamlFiles.value = result.workflows
    error.value = null
  } else if (!silent) {
    error.value = result.error
  }

  loading.value = false
}

// Created / renamed / copied / re-described in any tab: refresh the list quietly
let syncTimer = null
const stopWorkflowSync = onWorkflowChanged((detail) => {
  if (detail?.kind === 'graph') return
  clearTimeout(syncTimer)
  syncTimer = setTimeout(() => loadWorkflows({ silent: true }), 250)
})
onBeforeUnmount(() => {
  clearTimeout(syncTimer)
  stopWorkflowSync()
})

// After our own create/copy the change notification has already queued a quiet refresh:
// run it now instead of loading twice.
const refreshNow = () => {
  clearTimeout(syncTimer)
  return loadWorkflows({ silent: true })
}

// Expose loadWorkflows method for parent components
defineExpose({
  loadWorkflows,
  // lets the workbench's empty state open the same "create workflow" form
  openCreate: () => openFormGenerator()
})

// Files are listed by their workflow name; the .yaml extension is implementation detail
const displayName = (fileName) => String(fileName || '').replace(/\.ya?ml$/i, '')

// Sorted once per data/locale change; filtering below only runs on the sorted list
const sortedFiles = computed(() => {
  const rawList = Array.isArray(yamlFiles.value) ? [...yamlFiles.value] : []
  // Sort by name using the current UI locale (vi/en/zh collation)
  const collator = new Intl.Collator(locale.value || 'vi')
  return rawList.sort((a, b) => {
    const nameA = a?.name ?? ''
    const nameB = b?.name ?? ''
    return collator.compare(nameA, nameB)
  })
})

const filteredFiles = computed(() => {
  const query = debouncedQuery.value.toLowerCase().trim()
  if (!query) {
    return sortedFiles.value
  }

  return sortedFiles.value.filter(file => {
    const name = (file?.name ?? '').toString().toLowerCase()
    const desc = localizedWorkflowDescription(file?.name, file?.description ?? '').toString().toLowerCase()

    if (!name && !desc) return false

    return name.includes(query) || desc.includes(query)
  })
})

onMounted(() => {
  loadWorkflows()
})

const normalizeName = (fileName) => fileName?.replace?.('.yaml', '') ?? ''

const goToWorkflowView = (fileName) => {
  const workflowName = normalizeName(fileName)
  if (props.useRouting) {
    router.push(`/workflows/${workflowName}`)
  }
  emit('select', workflowName)
}

const isSelected = (file) => {
  const name = normalizeName(file?.name)
  return props.selected && props.selected === name
}

const extractGraphIdFromPayload = (payload) => {
  if (!payload) return null
  const graphId = payload.fullYaml?.graph?.id
  if (!graphId) return null
  return String(graphId).trim()
}

// "Tạo" first offers a blank workflow or a department template ("Mẫu phòng ban").
const openFormGenerator = () => {
  showTemplatePicker.value = true
}

const openBlankForm = () => {
  showTemplatePicker.value = false
  showFormGenerator.value = true
}

const handleTemplateCreated = async (fileName) => {
  showTemplatePicker.value = false
  await refreshNow()
  goToWorkflowView(fileName)
}

// Workflow edits are saved as they are made, so the Lab always loads the current file.
const goToLab = (fileName) => {
  const name = String(fileName || '')
  if (!name) return
  router.push({ path: '/lab', query: { workflow: /\.ya?ml$/i.test(name) ? name : `${name}.yaml` } })
}

// The editor saves graph edits as they are made, so an open workflow has no unsaved work
// except a node/edge form in progress; the confirmation warns about that case.
const confirmDelete = async (file) => {
  const name = file?.name
  if (!name || deleting.value) return
  const confirmed = await confirmDialog({
    title: t('workflow_list.confirm_delete_title', { name: displayName(name) }),
    message: isSelected(file) ? t('workflow_list.confirm_delete_open') : t('workflow_list.confirm_delete_message'),
    confirmText: t('confirm.delete'),
    tone: 'danger'
  })
  if (!confirmed) return
  deleting.value = name
  try {
    const result = await deleteWorkflow(name)
    if (!result.success) {
      toast.error(result.message || t('workflow_list.delete_failed'))
      return
    }
    toast.success(t('workflow_list.delete_success', { name: displayName(name) }))
    yamlFiles.value = yamlFiles.value.filter((entry) => entry?.name !== name)
    if (isSelected(file)) {
      emit('select', '') // close the deleted workflow in the editor
      if (props.useRouting) router.push('/workflows')
    }
    await refreshNow()
  } finally {
    deleting.value = ''
  }
}

const closeFormGenerator = () => {
  showFormGenerator.value = false
}

const handleFormGeneratorSubmit = async (payload) => {
  showFormGenerator.value = false
  await refreshNow()

  const graphId = extractGraphIdFromPayload(payload)
  if (!graphId) {
    return
  }

  const fileName = graphId.endsWith('.yaml') ? graphId : `${graphId}.yaml`
  goToWorkflowView(fileName)
}
</script>

<style scoped>
.workflow-list {
  width: 100%;
  height: 100%;
  background-color: var(--bg-base); /* Match HomeView background */
  padding: 10px;
  box-sizing: border-box;
  font-family: 'Inter', sans-serif;
  color: var(--text-1);
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
}

.workflow-list::-webkit-scrollbar {
  display: none;
}

.workflow-list::before {
  content: '';
  position: fixed;
  top: -150px;
  left: 0;
  right: 0;
  height: 500px;
  /* Pre-softened radial glows instead of filter: blur(120px) on a full-width
     fixed layer, which is very expensive to rasterise and composite. */
  background:
    radial-gradient(ellipse 40% 70% at 18% 45%, var(--accent-mint), transparent 72%),
    radial-gradient(ellipse 40% 70% at 50% 45%, var(--accent-sky), transparent 72%),
    radial-gradient(ellipse 40% 70% at 82% 45%, var(--accent-indigo), transparent 72%);
  opacity: 0.15;
  z-index: 0;
  pointer-events: none;
}

.header-container,
.file-list,
.loading,
.error-message,
.empty-state {
  position: relative;
  z-index: 1;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  width: 100%;
}

/* Search Bar Styles */
.search-container {
  display: flex;
  align-items: center;
  background-color: rgb(var(--ink) / 0.05);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 15px;
  padding: 10px 12px;
  /* Takes the room left by the create button: the placeholder is always readable */
  flex: 1;
  min-width: 0;
  min-height: 20px;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.search-container:hover,
.search-container:focus-within {
  background-color: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
}

.search-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  color: rgb(var(--ink) / 0.4);
  transition: color 0.3s ease;
}

.search-container:focus-within .search-icon {
  color: var(--accent-indigo);
}

.search-input {
  background: transparent;
  border: none;
  color: var(--text-1);
  font-size: 14px;
  font-weight: 500;
  width: 100%;
  outline: none;
  font-family: 'Inter', sans-serif;
}

.search-input::placeholder {
  color: rgb(var(--ink-softer) / 0.3);
}

/* Styled Add Button - Matching HomeView aesthetic */
.create-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  padding: 10px 16px;
  min-height: 40px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 15px;
  cursor: pointer;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  text-decoration: none;
  color: var(--bg-base);
  
  /* Pastel Rainbow Gradient from HomeView */
  background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  background-size: 200% 100%;
  animation: gradientShift 4s ease-in-out infinite;
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.2);
  position: relative;
  overflow: hidden;
}

.create-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgb(var(--shade) / 0.3);
}

@keyframes gradientShift {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 100% 0%; }
}

.create-btn:active {
  transform: translateY(0);
}

.plus-icon {
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

/* File List Styles */
.file-list {
  display: flex;
  flex-direction: column;
  max-width: 1000px; /* Limit width for better readability on large screens */
  margin: 0 auto;
}

.file-list-inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Filter animation */
.file-fade-enter-active,
.file-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.file-fade-move {
  transition: transform 0.2s ease;
}

/* Enter: fade in from bottom */
.file-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

/* Leave: fade out to top */
.file-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.file-fade-leave-active {
  position: absolute;
  width: 100%;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background-color: rgb(var(--ink) / 0.03); /* Transparent card */
  border: 1px solid rgb(var(--ink) / 0.1); /* Thin border */
  border-radius: 16px;
  cursor: pointer;
  transition: transform 0.3s ease, background-color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
  position: relative;
  /* overflow: hidden; */
  z-index: 1;
  /* No per-card backdrop-filter: the card sits on a flat surface, and a blur
     layer per card makes scrolling long lists expensive for no visible gain */
}

.file-item:hover {
  background-color: rgb(var(--ink) / 0.05);
  transform: translateY(-2px);
  border-color: rgb(var(--ink) / 0.2);
}

.file-item.active {
  border-color: rgb(var(--accent-indigo-rgb) / 0.5);
  box-shadow: 0 0 0 1px rgb(var(--accent-indigo-rgb) / 0.35);
}

.file-item.active .file-arrow {
  color: var(--accent-indigo);
}

.file-item::before {
  content: '';
  position: absolute;
  inset: -2px;
  z-index: -1;
  border-radius: 18px;
  padding: 2px;
  background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  -webkit-mask: 
     linear-gradient(var(--text-strong) 0 0) content-box, 
     linear-gradient(var(--text-strong) 0 0);
  mask: 
     linear-gradient(var(--text-strong) 0 0) content-box, 
     linear-gradient(var(--text-strong) 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  opacity: 0;
  transition: opacity 0.3s ease;
  background-size: 400% 100%;
  filter: blur(4px);
}

/* Hover only fades the (static) glow border in. Animating background-position
   under a blur and mask repainted the card every frame while hovered. */
.file-item:hover::before {
  opacity: 1;
}

/* Removed the left border glow ::before pseudo-element */

.lab-btn {
  flex-shrink: 0;
  margin: 0 8px 0 10px;
  padding: 5px 10px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.15);
  background: rgb(var(--ink) / 0.04);
  color: var(--text-1);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}

.file-item:hover .lab-btn,
.lab-btn:focus-visible {
  opacity: 1;
}

.lab-btn:hover {
  border-color: var(--accent-indigo);
  background: rgb(var(--ink) / 0.08);
}

.delete-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  margin-right: 2px;
  padding: 0;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: rgb(var(--ink-softer) / 0.6);
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s ease, color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}

.file-item:hover .delete-btn,
.delete-btn:focus-visible {
  opacity: 1;
}

.delete-btn:hover {
  color: var(--danger);
  border-color: var(--danger);
  background: rgb(var(--ink) / 0.06);
}

.delete-btn:disabled {
  cursor: wait;
  opacity: 0.4;
}

.file-info {
  flex: 1;
}

.file-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: 4px;
}

.file-description {
  color: rgb(var(--ink-softer) / 0.6);
  font-size: 12px;
  line-height: 1.4;
}

.file-arrow {
  color: rgb(var(--ink-softer) / 0.3);
  font-size: 20px;
  font-weight: 300;
  transition: transform 0.3s ease, color 0.3s ease;
  margin-left: 16px;
}

.file-item:hover .file-arrow {
  color: var(--accent-indigo);
  transform: translateX(4px);
}

/* Loading & Error States */
.loading, .error-message, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: rgb(var(--ink-softer) / 0.6);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgb(var(--ink) / 0.1);
  border-top-color: var(--accent-indigo);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.retry-button {
  margin-top: 16px;
  padding: 10px 24px;
  background-color: var(--line-2);
  color: var(--text-1);
  border: none;
  border-radius: 50px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-weight: 500;
}

.retry-button:hover {
  background-color: var(--line-4);
}

/* ---------- Light theme: lift low-alpha text/borders and deepen the pastel CTA ---------- */
:root[data-theme="light"] .search-container {
  background-color: var(--surface-1);
  border-color: var(--line-4);
}
:root[data-theme="light"] .search-container:hover,
:root[data-theme="light"] .search-container:focus-within {
  background-color: var(--surface-1);
  border-color: var(--neutral-1);
}
:root[data-theme="light"] .search-icon {
  color: var(--text-muted-3);
}
:root[data-theme="light"] .search-input::placeholder {
  color: var(--text-muted-3);
}
:root[data-theme="light"] .create-btn {
  color: #fff;
  background: linear-gradient(90deg, #047857, #0369a1, #4338ca);
  background-size: 200% 100%;
}
:root[data-theme="light"] .file-item {
  background-color: var(--surface-1);
  border-color: var(--line-4);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.1);
}
:root[data-theme="light"] .file-item:hover {
  background-color: var(--surface-1);
  border-color: var(--neutral-1);
}
:root[data-theme="light"] .file-item.active {
  border-color: rgb(var(--accent-indigo-rgb) / 0.6);
}
:root[data-theme="light"] .file-description,
:root[data-theme="light"] .loading,
:root[data-theme="light"] .error-message,
:root[data-theme="light"] .empty-state {
  color: var(--text-muted-3);
}
:root[data-theme="light"] .file-arrow {
  color: var(--neutral-1);
}
:root[data-theme="light"] .file-item:hover .file-arrow,
:root[data-theme="light"] .file-item.active .file-arrow {
  color: var(--accent-indigo);
}
:root[data-theme="light"] .workflow-list::before {
  opacity: 0.08;
}

@media (prefers-reduced-motion: reduce) {
  .create-btn,
  .file-item:hover::before {
    animation: none;
  }
  .file-fade-enter-active,
  .file-fade-leave-active,
  .file-fade-move,
  .file-item,
  .create-btn {
    transition-duration: 0.01s;
  }
}
</style>
