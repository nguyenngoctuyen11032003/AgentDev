<template>
  <div class="workflow-workbench" :class="{ 'no-selection': !selectedWorkflow, 'sidebar-open': sidebarVisible }">
    <div
      id="workflow-sidebar"
      class="workflow-sidebar"
      :class="{ open: sidebarVisible }"
      :inert="!sidebarVisible"
      :aria-hidden="!sidebarVisible"
    >
      <div class="sidebar-header">
        <h2 class="sidebar-title">{{ $t('nav.workflows') }}</h2>
        <button
          ref="closeBtnRef"
          type="button"
          class="btn ghost icon-only sidebar-close"
          :aria-expanded="sidebarVisible"
          aria-controls="workflow-sidebar"
          :aria-label="$t('workbench.hide_sidebar')"
          :title="$t('workbench.hide_sidebar')"
          @click="handleToggleSidebar"
        >
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6" /></svg>
        </button>
      </div>
      <WorkflowList
        ref="workflowListRef"
        :use-routing="false"
        :selected="selectedWorkflow"
        @select="handleSelect"
        @loaded="existingFiles = $event"
        @open-assistant="openAssistant('create')"
      />
    </div>

    <!-- Collapsed rail: the way back to the list -->
    <div class="sidebar-rail">
      <button
        ref="openBtnRef"
        type="button"
        class="btn secondary icon-only sidebar-open-btn"
        :aria-expanded="sidebarVisible"
        aria-controls="workflow-sidebar"
        :aria-label="$t('workbench.show_sidebar')"
        :title="$t('workbench.show_sidebar')"
        @click="handleToggleSidebar"
      >
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
      </button>
    </div>

    <div class="workflow-viewer">
      <WorkflowView
        v-if="selectedWorkflow"
        ref="workflowViewRef"
        :workflow-name="selectedWorkflow"
        :key="`${selectedWorkflow}#${reloadKey}`"
        @refresh-workflows="handleRefreshWorkflows"
      />
      <div v-else class="placeholder">
        <div class="start-panel">
          <h2 class="start-title">{{ $t('workbench.start_title') }}</h2>
          <p class="start-subtitle">{{ $t('workbench.choose_workflow') }}</p>

          <WorkflowTemplateCards :existing-files="existingFiles" @open="handleSelect" />

          <div class="start-actions">
            <button type="button" class="btn primary" @click="workflowListRef?.openCreate?.()">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              {{ $t('workbench.create_new') }}
            </button>
            <button
              v-if="defaultTemplate"
              type="button"
              class="btn secondary"
              @click="handleSelect(defaultTemplate)"
            >
              {{ $t('workbench.open_template') }}
            </button>
          </div>

          <div class="start-hint">
            <strong>{{ $t('workbench.start_hint_title') }}</strong>
            <span>{{ $t('workbench.start_hint') }}</span>
          </div>
        </div>
      </div>
      <!-- Workflow assistant: explain / edit the open workflow, or build a new one -->
      <button
        v-if="!isAssistantOpen"
        ref="toggleRef"
        type="button"
        class="assistant-toggle"
        :title="$t('workflow_assistant.open')"
        :aria-label="$t('workflow_assistant.open')"
        @click="openAssistant(selectedWorkflow ? 'workflow' : 'create')"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" /><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" /></svg>
        <span class="assistant-toggle-label">{{ $t('workflow_assistant.short_title') }}</span>
      </button>
    </div>
    <WorkflowAssistantPanel
      v-if="isAssistantOpen"
      @close="closeAssistant"
      @apply="handleApply"
      @undo="undoApply"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WorkflowList from './WorkflowList.vue'
import WorkflowView from './WorkflowView.vue'
import { pickDefaultTemplate } from '@/components/workflow/workflowTemplates.js'
import WorkflowTemplateCards from '@/components/workflow/WorkflowTemplateCards.vue'
import { lazyPanel } from '@/components/common/lazyPanel.js'
const WorkflowAssistantPanel = lazyPanel(() => import('@/components/workflow/assistant/WorkflowAssistantPanel.vue'), { overlay: true })
import { useWorkflowAssistant } from '@/composables/useWorkflowAssistant.js'
import { dismissToast, toast } from '@/utils/toast.js'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const workflowListRef = ref(null)
const closeBtnRef = ref(null)
const openBtnRef = ref(null)
const existingFiles = ref([])
// "Open a template": the first department template that exists (or any workflow), never a missing file
const defaultTemplate = computed(() => pickDefaultTemplate(existingFiles.value))
const workflowViewRef = ref(null)
const toggleRef = ref(null)
const assistant = useWorkflowAssistant()
const isAssistantOpen = ref(false)
// Bumped to remount WorkflowView once the assistant has saved the workflow (YAML and layout).
const reloadKey = ref(0)

const normalizeName = (name) => name?.replace?.('.yaml', '') ?? ''
const selectedWorkflow = ref(normalizeName(route.params.name))
// The list is an overlay drawer: open it only when there is nothing to show yet. Opening
// /workflows/<name> directly used to leave it open on top of the graph, hiding the
// workflow name, the Graph/YAML tabs and the left part of the canvas.
const isSidebarOpen = ref(!selectedWorkflow.value)

// Narrow screens: the list is the primary view until a workflow is opened
const NARROW_QUERY = '(max-width: 899px)'
const isNarrow = ref(typeof window !== 'undefined' && window.matchMedia(NARROW_QUERY).matches)
let narrowMql = null
const onNarrowChange = (event) => {
  isNarrow.value = event.matches
}
const sidebarVisible = computed(() => isSidebarOpen.value || (isNarrow.value && !selectedWorkflow.value))

watch(
  () => route.params.name,
  (name) => {
    selectedWorkflow.value = normalizeName(name)
  },
  { immediate: true }
)

function setSidebar(open) {
  isSidebarOpen.value = open
  window.dispatchEvent(new CustomEvent('workflow-sidebar-state', { detail: { open } }))
}

function handleToggleSidebar() {
  const open = !isSidebarOpen.value
  setSidebar(open)
  // The toggled-out button is inert/hidden afterwards: hand focus to its counterpart
  nextTick(() => (open ? closeBtnRef.value : openBtnRef.value)?.focus())
}

// Escape closes the drawer (the card menu handles its own Escape first)
const onKeydown = (event) => {
  if (event.key === 'Escape' && isSidebarOpen.value && selectedWorkflow.value && !event.defaultPrevented) {
    handleToggleSidebar()
  }
}

// /workflows/<name>?assist=1 (from Lab): open the assistant on this workflow, then drop the flag.
function openAssistantFromQuery() {
  if (!route.query.assist || !selectedWorkflow.value) return
  openAssistant('workflow')
  const rest = { ...route.query }
  delete rest.assist
  router.replace({ query: rest })
}
// Also when the workbench is already mounted (e.g. a second "fix" from Lab in the same tab).
watch(() => route.query.assist, (assist) => assist && nextTick(openAssistantFromQuery))

onMounted(() => {
  openAssistantFromQuery()
  window.addEventListener('toggle-workflow-sidebar', handleToggleSidebar)
  window.addEventListener('keydown', onKeydown)
  narrowMql = window.matchMedia(NARROW_QUERY)
  isNarrow.value = narrowMql.matches
  narrowMql.addEventListener('change', onNarrowChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('toggle-workflow-sidebar', handleToggleSidebar)
  window.removeEventListener('keydown', onKeydown)
  narrowMql?.removeEventListener('change', onNarrowChange)
})

const handleSelect = (name) => {
  const normalized = normalizeName(name)
  selectedWorkflow.value = normalized

  // Minimize sidebar when an entry is selected
  setSidebar(false)

  if (normalized) {
    router.push({ path: `/workflows/${normalized}` })
  } else {
    router.push({ path: '/workflows' })
  }
}

// ---------------------------------------------------------------- workflow assistant
const openAssistant = (mode) => {
  assistant.setContext(mode, mode === 'workflow' ? selectedWorkflow.value : null)
  isAssistantOpen.value = true
  // The list drawer would cover the empty state and its main buttons next to the panel.
  if (mode === 'create' && isSidebarOpen.value) {
    isSidebarOpen.value = false
    window.dispatchEvent(new CustomEvent('workflow-sidebar-state', { detail: { open: false } }))
  }
}

const closeAssistant = () => {
  isAssistantOpen.value = false
  nextTick(() => toggleRef.value?.focus())
}

// The docked panel narrows (or widens) the canvas: refit the graph so it does not sit off-center
// behind the panel. VueFlow learns its new size through its own ResizeObserver, a frame or two
// after the layout change, so wait a little before fitting (an immediate fit uses the old width).
let refitTimer = null
watch(isAssistantOpen, () => {
  clearTimeout(refitTimer)
  refitTimer = setTimeout(() => workflowViewRef.value?.refit?.(), 180)
})
onBeforeUnmount(() => clearTimeout(refitTimer))

// While the panel is open it follows the workflow shown on the canvas.
watch(selectedWorkflow, (name) => {
  if (isAssistantOpen.value) assistant.setContext(name ? 'workflow' : 'create', name || null)
})

// Success toast of an applied edit, with an Undo button for 10 seconds (the applied card in the
// chat offers Undo too).
let undoToastId = null
function showUndoToast(name) {
  undoToastId = toast.success(t('workflow_assistant.applied_edit', { name }), {
    duration: 10000,
    action: { label: t('workflow_assistant.undo'), run: () => undoApply(name) }
  })
}

let undoing = false
async function undoApply(name) {
  if (undoing) return
  // Same guard as Apply: an open node/edge form holds edits the reload would throw away.
  // Clicking the action closed the toast, so offer Undo again.
  if (workflowViewRef.value?.hasOpenForm?.()) {
    toast.warning(t('workflow_assistant.close_form_first'))
    showUndoToast(name)
    return
  }
  undoing = true
  let result
  try {
    // Undo only the change this button belongs to, never a later apply to another workflow.
    result = await assistant.undoLast(name)
  } finally {
    undoing = false
  }
  if (undoToastId !== null) {
    dismissToast(undoToastId)
    undoToastId = null
  }
  if (result.ok) {
    toast.success(t('workflow_assistant.undone'))
    if (normalizeName(result.filename) === selectedWorkflow.value) reloadKey.value += 1
  } else if (result.reason === 'stale') {
    toast.error(t('workflow_assistant.undo_stale'))
  } else if (result.reason === 'none') {
    toast.warning(t('workflow_assistant.undo_unavailable'))
  } else {
    toast.error(result.message || t('workflow_assistant.undo_failed'))
  }
}

const handleApply = async () => {
  const proposal = assistant.currentThread.value.pendingProposal
  if (!proposal) return
  const formOpen = !!workflowViewRef.value?.hasOpenForm?.()
  const result = await assistant.applyProposal({ formOpen })
  // A second click while the first apply runs (or nothing pending any more): nothing to say.
  if (!result.ok && (result.reason === 'busy' || result.reason === 'none')) return
  if (!result.ok) {
    // The chat keeps a conflict notice with a "redo" button, so the toast need not stay forever
    // (it would cover the panel header).
    if (result.reason === 'conflict') toast.error(t('workflow_assistant.conflict'), { duration: 8000 })
    else if (result.reason === 'form_open') toast.warning(t('workflow_assistant.close_form_first'))
    else toast.error(result.message || t('workflow_assistant.apply_failed'))
    return
  }
  const name = normalizeName(result.filename)
  if (proposal.kind === 'create') {
    toast.success(t('workflow_assistant.applied_create', { name }))
    await handleRefreshWorkflows()
    handleSelect(name)
    return
  }
  // YAML and layout are both saved by now: reload the canvas from them.
  if (name === selectedWorkflow.value) reloadKey.value += 1
  showUndoToast(name)
  // Saved, but the canvas layout could not be updated: still a success, with a soft note.
  if (result.warning === 'layout') toast.warning(t('workflow_assistant.applied_layout_warning'))
}

const handleRefreshWorkflows = async () => {
  // Reload workflows in WorkflowList
  if (workflowListRef.value?.loadWorkflows) {
    await workflowListRef.value.loadWorkflows()
  }
}
</script>

<style scoped>
.workflow-workbench {
  --sidebar-w: min(400px, 88vw);
  --rail-w: 56px;
  position: relative;
  display: flex;
  height: calc(calc(100 * var(--vh)) - 55px);
  height: calc(calc(100 * var(--dvh)) - 55px);
  background-color: var(--bg);
  color: var(--fg);
  overflow: hidden;
}

.workflow-sidebar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-w);
  transform: translateX(-100%);
  visibility: hidden;
  transition: transform 0.3s var(--ease-out), visibility 0s linear 0.3s;
  z-index: calc(var(--z-sticky) + 1);
  border-right: 1px solid var(--border-strong);
  background-color: var(--bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 4px 0 16px rgb(0 0 0 / 0.25);
}
.workflow-sidebar.open {
  transform: translateX(0);
  visibility: visible;
  transition: transform 0.3s var(--ease-out), visibility 0s;
}
.workflow-sidebar > :deep(.workflow-list) {
  flex: 1;
  min-height: 0;
  height: auto;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) 0 var(--space-4);
  min-height: calc(var(--control-h) + var(--space-3));
  flex-shrink: 0;
}

.sidebar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--fg);
}

/* Collapsed rail with the single, always-visible list toggle */
.sidebar-rail {
  flex-shrink: 0;
  width: var(--rail-w);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: var(--space-3);
  border-right: 1px solid var(--border);
  background: var(--surface);
}

.workflow-viewer {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* Assistant button: fixed in the top-right corner, inside the workflow header row */
.assistant-toggle {
  position: absolute;
  top: 5px;
  right: 12px;
  z-index: var(--z-raised);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px 0 10px;
  border: 1px solid rgb(var(--accent-sky-rgb) / 0.45);
  border-radius: 999px;
  background: rgb(var(--accent-sky-rgb) / 0.1);
  color: var(--accent-sky);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.assistant-toggle:hover {
  background: rgb(var(--accent-sky-rgb) / 0.18);
  border-color: var(--accent-sky);
}

.assistant-toggle:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

@media (max-width: 599px) {
  .assistant-toggle {
    padding: 0 8px;
  }

  .assistant-toggle-label {
    display: none;
  }
}

.placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-y: auto;
  padding: var(--space-6) var(--space-5);
}

.start-panel {
  width: 100%;
  max-width: 780px;
  margin: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.start-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--fg);
}

.start-subtitle {
  margin: calc(var(--space-3) * -1) 0 0;
  max-width: 56ch;
  font-size: 14px;
  line-height: 1.6;
  color: var(--fg-muted);
  text-wrap: pretty;
}

.start-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.start-hint {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  font-size: 13px;
  line-height: 1.6;
  color: var(--fg-muted);
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
}

.start-hint strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
}

/* Nothing open yet (wide screens): the list is docked beside the start panel, not over it */
@media (min-width: 900px) {
  .workflow-workbench.no-selection.sidebar-open .workflow-sidebar {
    position: relative;
    flex-shrink: 0;
    box-shadow: none;
  }
  .workflow-workbench.no-selection.sidebar-open .sidebar-rail {
    display: none;
  }
}

/* Narrow screens: the list is the whole screen until a workflow is opened */
@media (max-width: 899px) {
  .workflow-workbench.no-selection .workflow-viewer,
  .workflow-workbench.no-selection .sidebar-rail,
  .workflow-workbench.no-selection .sidebar-close {
    display: none;
  }
  .workflow-workbench.no-selection {
    --sidebar-w: 100%;
  }
  .workflow-workbench {
    --rail-w: 48px;
  }
  .placeholder {
    padding: var(--space-5) var(--space-4);
  }
}

@media (prefers-reduced-motion: reduce) {
  .workflow-sidebar,
  .workflow-sidebar.open {
    transition-duration: 0.01s;
  }
}
</style>
