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
          :placeholder="$t('common.search')"
          :aria-label="$t('common.search')"
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
            <div class="file-name">{{ file.name }}</div>
            <div class="file-description">{{ localizedWorkflowDescription(file.name, file.description) }}</div>
          </div>
          <div class="file-arrow">→</div>
        </div>
      </transition-group>
      
      <!-- Empty State -->
      <div v-if="filteredFiles.length === 0" class="empty-state">
        <p>{{ searchQuery.trim() && yamlFiles.length ? $t('workflow_list.no_search_results') : $t('workflow_list.no_files') }}</p>
      </div>
    </div>

    <!-- FormGenerator Modal -->
    <!-- Teleport to body in WorkflowWorkbench -->
    <Teleport to="body">
      <FormGenerator
        v-if="showFormGenerator"
        :breadcrumbs="[{node: 'DesignConfig', field: 'graph'}]"
        :recursive="false"  
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
import { fetchWorkflowsWithDesc } from '@/api/client.js'
import { localizedWorkflowDescription } from '@/utils/workflowDescription.js'
import FormGenerator from '@/components/form/FormGenerator.vue'

const router = useRouter()
const { locale } = useI18n()
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

const loadWorkflows = async () => {
  loading.value = true
  error.value = null

  const result = await fetchWorkflowsWithDesc()
  if (result.success) {
    yamlFiles.value = result.workflows
  } else {
    error.value = result.error
  }

  loading.value = false
}

// Expose loadWorkflows method for parent components
defineExpose({
  loadWorkflows
})

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

const openFormGenerator = () => {
  showFormGenerator.value = true
}

const closeFormGenerator = () => {
  showFormGenerator.value = false
}

const handleFormGeneratorSubmit = async (payload) => {
  await loadWorkflows()
  showFormGenerator.value = false

  const graphId = extractGraphIdFromPayload(payload)
  console.log('Extracted graphId:', graphId)
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
  background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  filter: blur(120px);
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
  /* Wide enough for longer placeholders such as Vietnamese "Tìm kiếm" */
  width: 100px;
  min-height: 20px;
  transition: width 0.3s ease, background-color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
  backdrop-filter: blur(5px);
}

.search-container:hover,
.search-container:focus-within {
  background-color: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
  width: 160px;
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.1);
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

/* Run the blurred gradient animation only on the hovered card, not on every
   card in the list (an invisible animation still repaints each frame) */
.file-item:hover::before {
  opacity: 1;
  animation: gradientShift 3s ease-in-out infinite;
}

/* Removed the left border glow ::before pseudo-element */

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
