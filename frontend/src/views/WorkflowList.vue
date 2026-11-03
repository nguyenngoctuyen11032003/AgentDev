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

      <button type="button" class="btn primary create-btn" @click="openFormGenerator" :title="$t('workflow_list.create')">
        <span>{{ $t('workflow_list.create') }}</span>
        <span class="plus-icon" aria-hidden="true">+</span>
      </button>
    </div>

    <!-- Loading State: skeleton cards keep the list's rhythm while it loads -->
    <div v-if="loading" class="file-list" role="status" aria-live="polite">
      <span class="sr-only">{{ $t('workflow_list.loading') }}</span>
      <div class="file-list-inner" aria-hidden="true">
        <div v-for="n in 4" :key="n" class="file-item skeleton-card">
          <span class="skeleton" style="width: 55%; height: 16px"></span>
          <span class="skeleton" style="width: 100%; height: 12px"></span>
          <span class="skeleton" style="width: 70%; height: 12px"></span>
        </div>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-message">
      <div class="error-icon" aria-hidden="true">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>
      </div>
      <p>{{ error }}</p>
      <button type="button" class="btn secondary retry-button" @click="loadWorkflows()">{{ $t('common.retry') }}</button>
    </div>

    <!-- File List -->
    <div v-else class="file-list">
      <transition-group
        name="file-fade"
        tag="div"
        class="file-list-inner"
      >
        <div
          v-for="file in filteredFiles"
          :key="file.name"
          :class="['file-item', { active: isSelected(file), 'menu-open': menuFor === file.name }]"
          :data-file="file.name"
        >
          <div class="file-head">
            <a
              class="file-link"
              :href="`/workflows/${normalizeName(file.name)}`"
              :aria-current="isSelected(file) ? 'page' : undefined"
              :title="displayName(file.name)"
              @click.prevent="goToWorkflowView(file.name)"
            >
              <span class="file-name">{{ humanName(file.name) }}</span>
            </a>
            <div class="file-menu-wrap">
              <button
                type="button"
                class="btn ghost icon-only file-menu-btn"
                aria-haspopup="menu"
                :aria-expanded="menuFor === file.name"
                :aria-label="$t('workflow_list.more_actions', { name: humanName(file.name) })"
                :title="$t('workflow_list.more_actions', { name: humanName(file.name) })"
                :disabled="deleting === file.name"
                @click.stop="toggleMenu(file.name)"
                @keydown.down.prevent="openMenuFor(file.name, 'first')"
                @keydown.up.prevent="openMenuFor(file.name, 'last')"
              >
                <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
              </button>
              <div
                v-if="menuFor === file.name"
                class="file-menu"
                role="menu"
                :aria-label="humanName(file.name)"
                @keydown="onMenuKeydown"
              >
                <button type="button" role="menuitem" tabindex="-1" class="file-menu-item" :title="$t('workflow_list.try_in_lab_hint')" @click="runMenuAction(() => goToLab(file.name))">
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9V3" /></svg>
                  {{ $t('workflow_list.try_in_lab') }}
                </button>
                <button type="button" role="menuitem" tabindex="-1" class="file-menu-item danger" :aria-label="$t('workflow_list.delete_aria', { name: displayName(file.name) })" @click="runMenuAction(() => confirmDelete(file), false)">
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" /></svg>
                  {{ $t('workflow_list.delete') }}
                </button>
              </div>
            </div>
          </div>
          <p class="file-description" :title="fullDescription(file)">{{ fullDescription(file) }}</p>
          <span v-if="humanName(file.name) !== displayName(file.name)" class="file-id">{{ displayName(file.name) }}</span>
        </div>
      </transition-group>

      <!-- Empty State -->
      <div v-if="filteredFiles.length === 0" class="empty-state">
        <template v-if="searchQuery.trim() && yamlFiles.length">
          <p>{{ $t('workflow_list.no_search_results') }}</p>
          <button type="button" class="btn secondary" @click="clearSearch">{{ $t('workflow_list.clear_search') }}</button>
        </template>
        <template v-else>
          <p>{{ $t('workflow_list.no_files') }}</p>
          <button type="button" class="btn primary create-btn empty-cta" @click="openFormGenerator">
            <span>{{ $t('workflow_list.create') }}</span>
            <span class="plus-icon" aria-hidden="true">+</span>
          </button>
        </template>
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
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
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
const emit = defineEmits(['select', 'loaded'])
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
    emit('loaded', result.workflows.map((f) => f.name))
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

// "demo_loop_counter.yaml" -> "Demo loop counter"; the raw id stays visible as a muted line
const humanName = (fileName) => {
  const text = displayName(fileName).replace(/_+/g, ' ').replace(/\s+/g, ' ').trim()
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : ''
}
const fullDescription = (file) => localizedWorkflowDescription(file.name, file.description)

const clearSearch = () => {
  searchQuery.value = ''
}

// ---- Per-card overflow menu (Try in Lab / Delete) ----
const menuFor = ref('')
const triggerOf = (name) => {
  const card = [...document.querySelectorAll('.workflow-list .file-item')].find((el) => el.dataset.file === name)
  return card?.querySelector('.file-menu-btn') || null
}
const menuItems = () => [...document.querySelectorAll('.workflow-list .file-menu [role="menuitem"]')]
const closeMenu = (returnFocus = true) => {
  const name = menuFor.value
  if (!name) return
  menuFor.value = ''
  if (returnFocus) nextTick(() => triggerOf(name)?.focus())
}
const openMenuFor = async (name, focus = 'first') => {
  menuFor.value = name
  await nextTick()
  const items = menuItems()
  const target = focus === 'last' ? items[items.length - 1] : items[0]
  target?.focus()
}
const toggleMenu = (name) => {
  if (menuFor.value === name) closeMenu()
  else openMenuFor(name, 'first')
}
const runMenuAction = (fn, returnFocus = true) => {
  closeMenu(returnFocus)
  fn()
}
const onMenuKeydown = (event) => {
  const items = menuItems()
  const index = items.indexOf(document.activeElement)
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeMenu()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    items[(index + 1) % items.length]?.focus()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    items[(index - 1 + items.length) % items.length]?.focus()
  } else if (event.key === 'Home') {
    event.preventDefault()
    items[0]?.focus()
  } else if (event.key === 'End') {
    event.preventDefault()
    items[items.length - 1]?.focus()
  } else if (event.key === 'Tab') {
    closeMenu(false)
  }
}
const onDocPointerDown = (event) => {
  if (!menuFor.value) return
  if (event.target.closest?.('.file-menu-wrap')) return
  closeMenu(false)
}
onMounted(() => document.addEventListener('pointerdown', onDocPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocPointerDown))

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
  background-color: var(--bg);
  padding: var(--space-3);
  box-sizing: border-box;
  color: var(--fg);
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
}

.workflow-list::-webkit-scrollbar {
  display: none;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.header-container,
.file-list,
.error-message {
  position: relative;
  z-index: 1;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  width: 100%;
}

/* Search Bar Styles */
.search-container {
  display: flex;
  align-items: center;
  background-color: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  padding: 0 var(--space-3);
  /* Takes the room left by the create button: the placeholder is always readable */
  flex: 1;
  min-width: 0;
  min-height: var(--control-h);
  box-sizing: border-box;
  transition: border-color 0.2s var(--ease-out);
}

.search-container:hover {
  border-color: var(--fg-subtle);
}

.search-container:focus-within {
  border-color: var(--accent);
}

.search-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: var(--space-3);
  color: var(--fg-muted);
  transition: color 0.2s var(--ease-out);
}

.search-container:focus-within .search-icon {
  color: var(--accent);
}

.search-input {
  background: transparent;
  border: none;
  color: var(--fg);
  font-size: 14px;
  font-weight: 500;
  width: 100%;
  outline: none;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--fg-subtle);
}

.create-btn {
  gap: var(--space-2);
  flex-shrink: 0;
}

.empty-cta {
  margin-top: var(--space-2);
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
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Filter animation */
.file-fade-enter-active,
.file-fade-leave-active {
  transition: opacity 0.2s var(--ease-out), transform 0.2s var(--ease-out);
}

.file-fade-move {
  transition: transform 0.2s var(--ease-out);
}

.file-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.file-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.file-fade-leave-active {
  position: absolute;
  width: 100%;
}

/* Card: a vertical stack. Name + overflow menu, then a clamped description, then the id. */
.file-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: transform 0.2s var(--ease-out), background-color 0.2s var(--ease-out), border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
  position: relative;
  z-index: 1;
}

.file-item.menu-open {
  z-index: 5; /* the open menu must overlay the cards below it */
}

.file-item:hover,
.file-item:has(.file-link:focus-visible) {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  background-color: var(--surface-raised);
}

.file-item.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.skeleton-card {
  gap: var(--space-2);
  cursor: default;
  padding: var(--space-4);
}

.skeleton-card:hover {
  transform: none;
  background-color: var(--surface);
  border-color: var(--border);
}

.file-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

/* The title link stretches over the whole card; the menu button sits above it */
.file-link {
  display: block;
  flex: 1;
  min-width: 0;
  color: inherit;
  text-decoration: none;
  outline: none;
}

.file-link::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: var(--radius-lg);
}

.file-link:focus-visible::after {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.file-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
  color: var(--fg);
}

.file-description {
  margin: 0;
  color: var(--fg-muted);
  font-size: 13px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.file-id {
  margin-top: var(--space-1);
  color: var(--fg-subtle);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--fs-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Overflow menu */
.file-menu-wrap {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  margin: calc(var(--space-2) * -1) 0;
}

.file-menu-btn {
  opacity: 0.7;
  transition: opacity 0.2s var(--ease-out), background-color 0.2s var(--ease-out), color 0.2s var(--ease-out);
}

.file-item:hover .file-menu-btn,
.file-item:focus-within .file-menu-btn,
.file-item.menu-open .file-menu-btn {
  opacity: 1;
}

.file-menu-btn[aria-expanded='true'] {
  background: var(--surface-raised);
  color: var(--fg);
}

@media (hover: none) {
  .file-menu-btn {
    opacity: 1;
  }
}

.file-menu {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  min-width: 190px;
  display: flex;
  flex-direction: column;
  padding: var(--space-1);
  background: var(--surface-raised);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.28);
}

.file-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-h);
  padding: 0 var(--space-3);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
}

.file-menu-item:hover,
.file-menu-item:focus-visible {
  background: var(--border);
  outline: none;
}

.file-menu-item:focus-visible {
  box-shadow: inset 0 0 0 2px var(--focus-ring);
}

.file-menu-item.danger {
  color: var(--danger);
}

.file-menu-item.danger:hover,
.file-menu-item.danger:focus-visible {
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}

/* Error state */
.error-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-5);
  color: var(--fg-muted);
  text-align: center;
}

.error-icon {
  display: grid;
  place-items: center;
  margin-bottom: var(--space-4);
  color: var(--warn);
}

.retry-button {
  margin-top: var(--space-4);
}

@media (prefers-reduced-motion: reduce) {
  .file-item:hover,
  .file-item:has(.file-link:focus-visible) {
    transform: none;
  }
  .file-fade-enter-active,
  .file-fade-leave-active,
  .file-fade-move,
  .file-item,
  .file-menu-btn {
    transition-duration: 0.01s;
  }
}
</style>
