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
        :workflow-name="selectedWorkflow"
        :key="selectedWorkflow"
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
            <button type="button" class="btn secondary" @click="handleSelect('software_company')">
              {{ $t('workbench.open_template') }}
            </button>
          </div>

          <div class="start-hint">
            <strong>{{ $t('workbench.start_hint_title') }}</strong>
            <span>{{ $t('workbench.start_hint') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkflowList from './WorkflowList.vue'
import WorkflowView from './WorkflowView.vue'
import WorkflowTemplateCards from '@/components/workflow/WorkflowTemplateCards.vue'

const route = useRoute()
const router = useRouter()
const workflowListRef = ref(null)
const closeBtnRef = ref(null)
const openBtnRef = ref(null)
const existingFiles = ref([])

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

onMounted(() => {
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
  height: calc(100vh - 55px);
  height: calc(100dvh - 55px);
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
