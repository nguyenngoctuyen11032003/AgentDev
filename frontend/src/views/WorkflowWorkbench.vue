<template>
  <div class="workflow-workbench">
    <div class="workflow-sidebar" :class="{ open: isSidebarOpen }">
      <WorkflowList
        ref="workflowListRef"
        :use-routing="false"
        :selected="selectedWorkflow"
        @select="handleSelect"
        @open-assistant="openAssistant('create')"
      />
    </div>
    <!-- Sidebar toggle button, positioned next to the sidebar -->
    <button 
      class="sidebar-toggle-btn" 
      :class="{ 'sidebar-open': isSidebarOpen }"
      @click="handleToggleSidebar" 
      :aria-label="isSidebarOpen ? $t('workbench.hide_sidebar') : $t('workbench.show_sidebar')"
      :title="isSidebarOpen ? $t('workbench.hide_sidebar') : $t('workbench.show_sidebar')"
    >
      <span v-if="isSidebarOpen">‹</span>
      <span v-else>›</span>
    </button>
    <div class="workflow-viewer" :class="{ 'sidebar-open': isSidebarOpen }">
      <WorkflowView
        v-if="selectedWorkflow"
        ref="workflowViewRef"
        :workflow-name="selectedWorkflow"
        :key="`${selectedWorkflow}#${reloadKey}`"
        @refresh-workflows="handleRefreshWorkflows"
      />
      <div v-else class="placeholder">
        <div class="placeholder-title">{{ $t('workbench.select_workflow') }}</div>
        <div class="placeholder-subtitle">{{ $t('workbench.choose_workflow') }}</div>
        <div class="placeholder-actions">
          <button type="button" class="ph-btn primary" @click="workflowListRef?.openCreate?.()">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            {{ $t('workbench.create_new') }}
          </button>
          <button type="button" class="ph-btn" @click="handleSelect('software_company')">
            {{ $t('workbench.open_template') }}
          </button>
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
    />
  </div>
</template>

<script setup>
import { nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WorkflowList from './WorkflowList.vue'
import WorkflowView from './WorkflowView.vue'
import WorkflowAssistantPanel from '@/components/workflow/assistant/WorkflowAssistantPanel.vue'
import { useWorkflowAssistant } from '@/composables/useWorkflowAssistant.js'
import { toast } from '@/utils/toast.js'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const workflowListRef = ref(null)
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

watch(
  () => route.params.name,
  (name) => {
    selectedWorkflow.value = normalizeName(name)
  },
  { immediate: true }
)

function handleToggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
  window.dispatchEvent(new CustomEvent('workflow-sidebar-state', { detail: { open: isSidebarOpen.value } }))
}

onMounted(() => {
  window.addEventListener('toggle-workflow-sidebar', handleToggleSidebar)
})

onBeforeUnmount(() => {
  window.removeEventListener('toggle-workflow-sidebar', handleToggleSidebar)
})

const handleSelect = (name) => {
  const normalized = normalizeName(name)
  selectedWorkflow.value = normalized

  // Minimize sidebar when an entry is selected
  isSidebarOpen.value = false
  window.dispatchEvent(new CustomEvent('workflow-sidebar-state', { detail: { open: isSidebarOpen.value } }))

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
}

const closeAssistant = () => {
  isAssistantOpen.value = false
  nextTick(() => toggleRef.value?.focus())
}

// While the panel is open it follows the workflow shown on the canvas.
watch(selectedWorkflow, (name) => {
  if (isAssistantOpen.value) assistant.setContext(name ? 'workflow' : 'create', name || null)
})

const undoApply = async () => {
  const result = await assistant.undoLast()
  if (result.ok) {
    toast.success(t('workflow_assistant.undone'))
    if (normalizeName(result.filename) === selectedWorkflow.value) reloadKey.value += 1
  } else if (result.reason === 'stale') {
    toast.error(t('workflow_assistant.undo_stale'))
  } else {
    toast.error(result.message || t('workflow_assistant.undo_failed'))
  }
}

const handleApply = async () => {
  const proposal = assistant.currentThread.value.pendingProposal
  if (!proposal) return
  const formOpen = !!workflowViewRef.value?.hasOpenForm?.()
  const result = await assistant.applyProposal({ formOpen })
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
  toast.success(t('workflow_assistant.applied_edit', { name }), {
    duration: 10000,
    action: { label: t('workflow_assistant.undo'), run: undoApply }
  })
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
  position: relative;
  display: flex;
  height: calc(100vh - 55px);
  background-color: var(--bg-base);
  color: var(--text-1);
  overflow: hidden;
}

.workflow-sidebar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  transform: translateX(calc(-100% + 10px));
  transition: transform 0.35s cubic-bezier(.77,.2,.05,1.0);
  z-index: 3;
  border-right: 1px solid rgb(var(--ink) / 0.08);
  background-color: var(--bg-deep);
  overflow-y: auto;
  overflow-x: hidden;
  box-shadow: 4px 0 16px rgb(var(--shade) / 0.35);
  will-change: transform;
}
.workflow-sidebar.open {
  transform: translateX(0);
}

/* Sidebar toggle button - positioned next to the sidebar */
.sidebar-toggle-btn {
  position: absolute;
  left: 10px; /* Keep 10px visible when collapsed */
  top: 50%;
  transform: translateY(-50%);
  width: 12px;
  height: 72px;
  padding: 12px;
  background: linear-gradient(180deg, var(--surface-3), var(--surface-1));
  border: 1px solid rgb(var(--accent-indigo-rgb) / 0.3);
  border-left: none;
  border-radius: 0 12px 12px 0;
  color: var(--accent-indigo);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
  /* Slide with transform (compositor only) instead of animating `left`,
     which would relayout the workbench on every frame */
  transition: transform 0.35s cubic-bezier(.77,.2,.05,1.0),
              color 0.2s,
              border-color 0.2s,
              box-shadow 0.2s;
  box-shadow: 4px 0 12px rgb(var(--shade) / 0.4);
  will-change: transform;
}

.sidebar-toggle-btn.sidebar-open {
  transform: translate(390px, -50%); /* Follow the sidebar when expanded (10px + 390px = 400px) */
}

.sidebar-toggle-btn:hover {
  background: linear-gradient(180deg, var(--line-1), var(--surface-4));
  color: var(--accent-indigo-3);
  border-color: rgb(var(--accent-indigo-rgb) / 0.6);
  box-shadow: 4px 0 16px rgb(var(--accent-indigo-rgb) / 0.15);
}

.sidebar-toggle-btn span {
  font-weight: 700;
  line-height: 1;
  text-shadow: 0 0 8px rgb(var(--accent-indigo-rgb) / 0.5);
}

.workflow-viewer {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-left: 10px; /* Match the visible width when the sidebar is collapsed */
  position: relative;
}

/* Assistant button: fixed in the top-right corner, inside the workflow header row */
.assistant-toggle {
  position: absolute;
  top: 5px;
  right: 12px;
  z-index: 5;
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
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: transparent;
  color: rgb(var(--ink-softer) / 0.7);
  text-align: center;
  padding: 24px;
}

.placeholder::before {
  content: '';
  position: absolute;
  top: -150px;
  left: 0;
  right: 0;
  height: 500px;
  /* Pre-softened radial glows instead of filter: blur(120px) on a 500px-tall
     layer, which is very expensive to rasterise and composite. */
  background:
    radial-gradient(ellipse 40% 70% at 18% 45%, var(--accent-mint), transparent 72%),
    radial-gradient(ellipse 40% 70% at 50% 45%, var(--accent-sky), transparent 72%),
    radial-gradient(ellipse 40% 70% at 82% 45%, var(--accent-indigo), transparent 72%);
  opacity: 0.15;
  z-index: 0;
  pointer-events: none;
}

.placeholder-title {
  position: relative;
  z-index: 1;
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.placeholder-subtitle {
  position: relative;
  z-index: 1;
  max-width: 46ch;
  font-size: 14px;
  line-height: 1.6;
  color: rgb(var(--ink-softer) / 0.6);
}

.placeholder-actions {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 22px;
}

.ph-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 18px;
  border: 0;
  border-radius: 11px;
  background: rgb(var(--ink) / 0.06);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.12);
  color: var(--text-1);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ph-btn:hover {
  background: rgb(var(--ink) / 0.1);
}

.ph-btn.primary {
  background: var(--accent-sky);
  box-shadow: none;
  color: #05141f;
}

.ph-btn.primary:hover {
  filter: brightness(1.06);
}

:root[data-theme="light"] .ph-btn.primary {
  color: #fff;
}

.ph-btn:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

/* ---------- Light theme: solid text colors, visible edges, no glow ---------- */
:root[data-theme="light"] .workflow-sidebar {
  border-right-color: var(--line-4);
  box-shadow: 4px 0 16px rgb(var(--shade) / 0.18);
}
:root[data-theme="light"] .sidebar-toggle-btn {
  border-color: rgb(var(--accent-indigo-rgb) / 0.45);
  box-shadow: 2px 0 8px rgb(var(--shade) / 0.18);
}
:root[data-theme="light"] .sidebar-toggle-btn span {
  text-shadow: none;
}
:root[data-theme="light"] .placeholder {
  color: var(--text-soft-1);
}
:root[data-theme="light"] .placeholder-title {
  color: var(--text-1);
}
:root[data-theme="light"] .placeholder-subtitle {
  color: var(--text-muted-3);
}
:root[data-theme="light"] .placeholder::before {
  opacity: 0.08;
}

@media (prefers-reduced-motion: reduce) {
  .workflow-sidebar,
  .sidebar-toggle-btn {
    transition-duration: 0.01s;
  }
}
</style>
