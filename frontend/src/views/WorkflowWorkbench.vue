<template>
  <div class="workflow-workbench">
    <div class="workflow-sidebar" :class="{ open: isSidebarOpen }">
      <WorkflowList
        ref="workflowListRef"
        :use-routing="false"
        :selected="selectedWorkflow"
        @select="handleSelect"
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
        :workflow-name="selectedWorkflow"
        :key="selectedWorkflow"
        @refresh-workflows="handleRefreshWorkflows"
      />
      <div v-else class="placeholder">
        <div class="placeholder-title"> {{ $t('workbench.select_workflow') }}</div>
        <div class="placeholder-subtitle">{{ $t('workbench.choose_workflow') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkflowList from './WorkflowList.vue'
import WorkflowView from './WorkflowView.vue'

const route = useRoute()
const router = useRouter()
const workflowListRef = ref(null)

const normalizeName = (name) => name?.replace?.('.yaml', '') ?? ''
const selectedWorkflow = ref(normalizeName(route.params.name))
const isSidebarOpen = ref(true)

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
  font-size: 14px;
  color: rgb(var(--ink-softer) / 0.6);
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
