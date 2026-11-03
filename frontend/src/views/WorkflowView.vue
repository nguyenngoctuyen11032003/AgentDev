<template>
  <div class="workflow-view">
    <div class="workflow-bg"></div>
    <div class="header">
      <!-- Back button disabled -->
      <!-- <button @click="goBack" class="back-button">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button> -->
      <h1 class="workflow-name">{{ currentWorkflowName }}</h1>
    </div>
    
    <div class="content">
      <!-- YAML Editor Tab -->
      <div v-if="activeTab === 'yaml'" class="yaml-editor">
        <div v-if="yamlParseError" class="yaml-error">
          {{ $t('workflow_view.yaml_parse_error') }} {{ yamlParseError }}
        </div>
        <div v-else-if="yamlLoadError" class="yaml-error">
          {{ yamlLoadError }}
        </div>
        <textarea 
          v-model="yamlTextString" 
          class="yaml-textarea"
          :class="{ 'yaml-error-border': yamlParseError }"
          :placeholder="$t('workflow_view.loading_yaml')"
          readonly
        ></textarea>
      </div>

      <!-- VueFlow Graph Tab -->
      <div
        v-if="activeTab === 'graph'"
        class="vueflow-container"
        ref="vueflowContainerRef"
      >
        <VueFlow
         v-model:nodes="nodes"
         v-model:edges="edges"
         :delete-key-code="false"
         :fit-view-on-init="false"
         :min-zoom="MIN_ZOOM"
         :max-zoom="2"
         class="vueflow-graph"
         @node-click="onNodeClick"
         @edge-click="onEdgeClick"
         @connect="onConnect"
         @node-drag-stop="onNodeDragStop"
         @pane-context-menu="onPaneContextMenu"
         @node-context-menu="onNodeContextMenu"
         @edge-context-menu="onEdgeContextMenu">
        <template #node-workflow-node="props">
          <WorkflowNode
            :id="props.id"
            :data="props.data"
            :sprite="nodeSpriteMap.get(props.id) || ''"
            :team="teamChart.get(props.id) || null"
            @hover="onNodeHover"
            @leave="onNodeLeave"
          />
        </template>
        <template #node-start-node="props">
          <StartNode :id="props.id" :data="props.data" />
        </template>
        <template #edge-workflow-edge="props">
          <WorkflowEdge
            :id="props.id"
            :source="props.source"
            :target="props.target"
            :source-x="props.sourceX"
            :source-y="props.sourceY"
            :target-x="props.targetX"
            :target-y="props.targetY"
            :source-position="props.sourcePosition"
            :target-position="props.targetPosition"
            :data="props.data"
            :marker-end="props.markerEnd"
            :animated="props.animated"
            :hovered-node-id="hoveredNodeId === props.source || hoveredNodeId === props.target ? hoveredNodeId : null"
          />
        </template>
        <Background pattern-color="var(--canvas-dot)"/>
        <Controls position="bottom-right"/>
        </VueFlow>

        <!-- Right-click context menu inside VueFlow container -->
        <transition name="fade">
          <div
            v-if="contextMenuVisible"
            class="context-menu"
            :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px' }"
            @click.stop
          >
            <!-- Pane context menu -->
            <template v-if="contextMenuType === 'pane'">
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.createNode" placement="right">
                <div
                  class="context-menu-item"
                  @click.stop="() => { hideContextMenu(); openCreateNodeModal(); }"
                >
                  {{ $t('workflow_view.create_node') }}
                </div>
              </RichTooltip>
              <div
                v-else
                class="context-menu-item"
                @click.stop="() => { hideContextMenu(); openCreateNodeModal(); }"
              >
                {{ $t('workflow_view.create_node') }}
              </div>
            </template>

            <!-- Node context menu -->
            <template v-else-if="contextMenuType === 'node'">
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.copyNode" placement="right">
                <div
                  class="context-menu-item"
                  @click.stop="() => { hideContextMenu(); onCopyNodeFromContext(); }"
                >
                  {{ $t('workflow_view.copy_node') }}
                </div>
              </RichTooltip>
              <div
                v-else
                class="context-menu-item"
                @click.stop="() => { hideContextMenu(); onCopyNodeFromContext(); }"
              >
                {{ $t('workflow_view.copy_node') }}
              </div>
              <!-- One click: "Backend Developer" -> "Backend Developer 2", added to the same teams -->
              <div
                class="context-menu-item"
                :title="$t('workflow_view.duplicate_node_hint')"
                @click.stop="() => { hideContextMenu(); onDuplicateNodeFromContext(); }"
              >
                {{ $t('workflow_view.duplicate_node') }}
              </div>
              <!-- Build a roster fast: N numbered copies at once, all joining the original's teams -->
              <div
                v-if="contextNodeIsAgent"
                class="context-menu-item"
                :title="$t('workflow_view.duplicate_many_hint')"
                @click.stop="() => { const id = contextNodeId; hideContextMenu(); openDuplicateManyModal(id); }"
              >
                {{ $t('workflow_view.duplicate_many') }}
              </div>
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.deleteNode" placement="right">
                <div
                  class="context-menu-item"
                  @click.stop="() => { hideContextMenu(); onDeleteNodeFromContext(); }"
                >
                  {{ $t('workflow_view.delete_node') }}
                </div>
              </RichTooltip>
              <div
                v-else
                class="context-menu-item"
                @click.stop="() => { hideContextMenu(); onDeleteNodeFromContext(); }"
              >
                {{ $t('workflow_view.delete_node') }}
              </div>
            </template>

            <!-- Edge context menu -->
            <template v-else-if="contextMenuType === 'edge'">
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.deleteEdge" placement="right">
                <div
                  class="context-menu-item"
                  @click.stop="() => { hideContextMenu(); onDeleteEdgeFromContext(); }"
                >
                  {{ $t('workflow_view.delete_edge') }}
                </div>
              </RichTooltip>
              <div
                v-else
                class="context-menu-item"
                @click.stop="() => { hideContextMenu(); onDeleteEdgeFromContext(); }"
              >
                {{ $t('workflow_view.delete_edge') }}
              </div>
            </template>
          </div>
        </transition>
      </div>
    </div>

    <div class="tabs">
      <div class="tab-buttons">
        <button
          :class="['tab', { active: activeTab === 'graph' }]"
          @click="activeTab = 'graph'"
        >
          {{ $t('workflow_view.workflow_graph') }}
        </button>
        <button
          :class="['tab', { active: activeTab === 'yaml' }]"
          @click="activeTab = 'yaml'"
        >
          {{ $t('workflow_view.yaml_configuration') }}
        </button>      </div>
      <div v-if="activeTab === 'graph'" class="editor-actions">
        <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.createNodeButton" placement="bottom">
          <button @click="openCreateNodeModal" class="glass-button">
            <span>{{ $t('workflow_view.create_node') }}</span>
          </button>
        </RichTooltip>
        <button v-else @click="openCreateNodeModal" class="glass-button">
          <span>{{ $t('workflow_view.create_node') }}</span>
        </button>
        <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.createEdge" placement="bottom">
          <button @click="openCreateEdgeModal" class="glass-button">
            <span>{{ $t('workflow_view.create_edge') }}</span>
          </button>
        </RichTooltip>
        <button v-else @click="openCreateEdgeModal" class="glass-button">
          <span>{{ $t('workflow_view.create_edge') }}</span>
        </button>
        <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.configureGraph" placement="bottom">
          <button @click="openConfigureGraphModal" class="glass-button">
            <span>{{ $t('workflow_view.configure_graph') }}</span>
          </button>
        </RichTooltip>
        <button v-else @click="openConfigureGraphModal" class="glass-button">
          <span>{{ $t('workflow_view.configure_graph') }}</span>
        </button>
        <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.launch" placement="bottom">
          <button @click="goToLaunch" class="launch-button-primary">
            <span>{{ $t('workflow_view.launch') }}</span>
          </button>
        </RichTooltip>
        <button v-else @click="goToLaunch" class="launch-button-primary">
          <span>{{ $t('workflow_view.launch') }}</span>
        </button>
        <button
          type="button"
          class="glass-button"
          :title="$t('workflow_view.try_in_lab_hint')"
          :disabled="labNavigating"
          @click="goToLab"
        >
          <span>{{ $t('workflow_view.try_in_lab') }}</span>
        </button>

        <div
          class="menu-container"
          @mouseenter="menuHovered = true; showMenu = true"
          @mouseleave="menuHovered = false; showMenu = false"
        >
          <button
            type="button"
            class="menu-trigger"
            :class="{ 'menu-trigger-active': showMenu }"
            :aria-expanded="showMenu"
            :aria-label="$t('workflow_view.more_actions')"
            :title="$t('workflow_view.more_actions')"
            @click.stop="showMenu = menuHovered || !showMenu"
          >
            <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M3 12H21M3 6H21M3 18H21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <transition name="fade">
            <div v-if="showMenu" class="menu-dropdown">
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.renameWorkflow" placement="left">
                <div @click="openRenameWorkflowModal" class="menu-item">{{ $t('workflow_view.rename_workflow') }}</div>
              </RichTooltip>
              <div v-else @click="openRenameWorkflowModal" class="menu-item">{{ $t('workflow_view.rename_workflow') }}</div>
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.copyWorkflow" placement="left">
                <div @click="openCopyWorkflowModal" class="menu-item">{{ $t('workflow_view.copy_workflow') }}</div>
              </RichTooltip>
              <div v-else @click="openCopyWorkflowModal" class="menu-item">{{ $t('workflow_view.copy_workflow') }}</div>
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.manageVariables" placement="left">
                <div @click="openManageVarsModal" class="menu-item">{{ $t('workflow_view.manage_variables') }}</div>
              </RichTooltip>
              <div v-else @click="openManageVarsModal" class="menu-item">{{ $t('workflow_view.manage_variables') }}</div>
              <RichTooltip v-if="shouldShowTooltip" :content="helpContent.contextMenu.manageMemories" placement="left">
                <div @click="openManageMemoriesModal" class="menu-item">{{ $t('workflow_view.manage_memories') }}</div>
              </RichTooltip>
              <div v-else @click="openManageMemoriesModal" class="menu-item">{{ $t('workflow_view.manage_memories') }}</div>
            </div>
          </transition>
        </div>
      </div>
    </div>

  </div>

  <FormGenerator
    v-if="showDynamicFormGenerator"
    :breadcrumbs="formGeneratorBreadcrumbs"
    :recursive="formGeneratorRecursive"
    :workflow-name="currentWorkflowName"
    :initial-yaml="formGeneratorInitialYaml ?? yamlContent"
    :node-order="formGeneratorNodeOrder"
    :initial-form-data="formGeneratorInitialFormData"
    :mode="formGeneratorMode"
    :field-filter="formGeneratorFieldFilter"
    :read-only-fields="formGeneratorReadOnlyFields"
    :title="formGeneratorTitle"
    :submit-label="formGeneratorSubmitLabel"
    @close="closeDynamicFormGenerator"
    @submit="handleFormGeneratorSubmit"
    @copy="handleFormGeneratorCopy"
  />

  <!-- Rename Workflow Modal -->
  <div v-if="showRenameModal" class="modal-overlay" @click.self="closeRenameModal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 class="modal-title">{{ $t('workflow_view.rename_workflow') }}</h3>
        <button @click="closeRenameModal" class="close-button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="rename-workflow-name" class="form-label">{{ $t('workflow_view.workflow_name') }}</label>
          <input
            id="rename-workflow-name"
            v-model="renameWorkflowName"
            type="text"
            class="form-input"
            :placeholder="$t('workflow_view.enter_new_name')"
            @keyup.enter="handleRenameSubmit"
          />
        </div>
      </div>
      <div class="modal-footer">
        <button @click="closeRenameModal" class="cancel-button">{{ $t('common.cancel') }}</button>
        <button @click="handleRenameSubmit" class="submit-button" :disabled="!renameWorkflowName.trim()">{{ $t('common.submit') }}</button>
      </div>
    </div>
  </div>

  <!-- Copy Workflow Modal -->
  <div v-if="showCopyModal" class="modal-overlay" @click.self="closeCopyModal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 class="modal-title">{{ $t('workflow_view.copy_workflow') }}</h3>
        <button @click="closeCopyModal" class="close-button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="copy-workflow-name" class="form-label">{{ $t('workflow_view.workflow_name') }}</label>
          <input
            id="copy-workflow-name"
            v-model="copyWorkflowName"
            type="text"
            class="form-input"
            :placeholder="$t('workflow_view.enter_new_name')"
            @keyup.enter="handleCopySubmit"
          />
        </div>
      </div>
      <div class="modal-footer">
        <button @click="closeCopyModal" class="cancel-button">{{ $t('common.cancel') }}</button>
        <button @click="handleCopySubmit" class="submit-button" :disabled="!copyWorkflowName.trim()">{{ $t('common.submit') }}</button>
      </div>
    </div>
  </div>

  <!-- Duplicate node xN Modal -->
  <div v-if="showDuplicateManyModal" class="modal-overlay" @click.self="closeDuplicateManyModal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 class="modal-title">{{ $t('workflow_view.duplicate_many_title', { name: duplicateManyNodeId }) }}</h3>
        <button @click="closeDuplicateManyModal" class="close-button" :aria-label="$t('common.cancel')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="duplicate-many-count" class="form-label">{{ $t('workflow_view.duplicate_many_count') }}</label>
          <input
            id="duplicate-many-count"
            v-model.number="duplicateManyCount"
            type="number"
            min="1"
            :max="DUPLICATE_MANY_MAX"
            step="1"
            class="form-input"
            @keyup.enter="handleDuplicateManySubmit"
          />
          <p class="duplicate-many-help">{{ duplicateManyPreview }}</p>
          <p v-if="duplicateManyLeads.length" class="duplicate-many-help">
            {{ $t('workflow_view.duplicate_many_team_note', { leads: duplicateManyLeads.join(', ') }) }}
          </p>
        </div>
      </div>
      <div class="modal-footer">
        <button @click="closeDuplicateManyModal" class="cancel-button">{{ $t('common.cancel') }}</button>
        <button
          @click="handleDuplicateManySubmit"
          class="submit-button"
          :disabled="!duplicateManyValid || duplicateManyBusy"
        >
          {{ $t('workflow_view.duplicate_many_submit', { count: duplicateManyValid ? duplicateManyCount : 0 }) }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/controls/dist/style.css'
import '@/assets/styles/vueflow.css'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'
import WorkflowEdge from '@/components/workflow/WorkflowEdge.vue'
import StartNode from '@/components/workflow/StartNode.vue'
import FormGenerator from '@/components/form/FormGenerator.vue'
import RichTooltip from '@/components/common/RichTooltip.vue'
import yaml from 'js-yaml'
import { buildOrgChart, computeTeamLinks, layoutOrgTree } from '@/utils/teamLinks.js'
import { duplicateNodeInGraph } from '@/utils/nodeDuplicate.js'
import { fetchYaml, fetchVueGraph, postVuegraphs, updateYaml, postYamlNameChange, postYamlCopy } from '@/api/client.js'
import { helpContent } from '@/utils/helpContent.js'
import { configStore } from '@/stores/configStore.js'
import { spriteFetcher } from '@/utils/spriteFetcher.js'
import { toast } from '@/utils/toast.js'
import { confirmDialog } from '@/utils/confirm.js'

const shouldShowTooltip = computed(() => configStore.ENABLE_HELP_TOOLTIPS)

const props = defineProps({
  workflowName: {
    type: String,
    required: true
  }
})
const emit = defineEmits(['refresh-workflows'])
const router = useRouter()
const { t } = useI18n()

// Extract a readable backend error detail (FastAPI `detail` may be a string, an object or a list)
const extractErrorDetail = (result) => {
  const raw = result?.detail ?? result?.error?.message ?? result?.error
  if (raw === undefined || raw === null || raw === '') return ''
  if (typeof raw === 'string') return raw
  if (Array.isArray(raw)) {
    return raw
      .map(item => (typeof item === 'string' ? item : (item?.msg || item?.message || JSON.stringify(item))))
      .join('; ')
  }
  if (typeof raw === 'object') return raw.message || raw.msg || JSON.stringify(raw)
  return String(raw)
}

// Localized message, optionally followed by the backend detail
const withErrorDetail = (message, result) => {
  const detail = extractErrorDetail(result)
  return detail ? t('workflow_view.error_with_detail', { message, detail }) : message
}
const { toObject, fromObject, fitView, getViewport, findNode, getNodes, onNodesInitialized } = useVueFlow()
// Default minimum is 0.5, too close for a 12-agent team to fit on screen.
const MIN_ZOOM = 0.15

// Fit the whole graph once the nodes have been measured (right after nextTick they still have no
// size, so big graphs came out cropped). Capped at 100 % so a 2-node workflow is not blown up, and
// with extra room for the characters standing on top of the cards.
// Node sizes arrive asynchronously (ResizeObserver): fit now if every card is measured, otherwise
// as soon as VueFlow reports the nodes initialized (with a short fallback timer).
const FIT_OPTIONS = { padding: 0.18, maxZoom: 1, minZoom: MIN_ZOOM }
let pendingFit = false
let fitFallback = null
const allMeasured = () => {
  const list = getNodes?.value || []
  return list.length > 0 && list.every((node) => node.dimensions?.width > 0 && node.dimensions?.height > 0)
}
// fitView resolves false (and does nothing) while the canvas itself is not ready yet, which is
// the case on a fresh page load: retry briefly until it succeeds.
const runPendingFit = async (attempt = 0) => {
  if (!pendingFit) return
  clearTimeout(fitFallback)
  const done = await fitView?.(FIT_OPTIONS)
  if (done || attempt >= 12) {
    pendingFit = false
    return
  }
  fitFallback = setTimeout(() => runPendingFit(attempt + 1), 120)
}
onNodesInitialized(() => runPendingFit())
const fitGraph = async () => {
  await nextTick()
  pendingFit = true
  if (allMeasured()) {
    runPendingFit()
    return
  }
  clearTimeout(fitFallback)
  fitFallback = setTimeout(() => runPendingFit(), 400)
}

const vueflowContainerRef = ref(null)
// Hovered node id for highlighting related edges
const hoveredNodeId = ref(null)

const onNodeHover = (nodeId) => {
  hoveredNodeId.value = nodeId || null
}
const onNodeLeave = () => {
  hoveredNodeId.value = null
}

const currentWorkflowName = ref('')
const activeTab = ref('graph')
const yamlContent = ref({}) // YAML object
const yamlTextString = ref('') // YAML string
const yamlParseError = ref(null)
const yamlLoadError = ref(null)

const showDynamicFormGenerator = ref(false)
const showMenu = ref(false)
// Hover already opens the menu, so a mouse click on the trigger must not toggle it closed again.
const menuHovered = ref(false)
const formGeneratorBreadcrumbs = ref([])
const formGeneratorRecursive = ref(false)
const formGeneratorInitialYaml = ref(null)
const formGeneratorInitialFormData = ref(null)
const formGeneratorMode = ref('create')
const formGeneratorFieldFilter = ref([])
const formGeneratorReadOnlyFields = ref([])
const formGeneratorNodeOrder = ref(null)

// Modal states for rename and copy
const showRenameModal = ref(false)
const showCopyModal = ref(false)
const renameWorkflowName = ref('')
const copyWorkflowName = ref('')

const FORM_GENERATOR_CONFIG = Object.freeze({
  graph: [
    { node: 'DesignConfig', field: 'graph' }
  ],
  node: [
    { node: 'DesignConfig', field: 'graph' },
    { node: 'GraphDefinition', field: 'nodes' }
  ],
  edge: [
    { node: 'DesignConfig', field: 'graph' },
    { node: 'GraphDefinition', field: 'edges' }
  ],
  memory: [
    { node: 'DesignConfig', field: 'graph' }
  ],
  vars: [
    // Empty breadcrumbs for managing global vars
  ]
})

const cloneDeep = (value) => {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'object') {
    return JSON.parse(JSON.stringify(value))
  }
  return value
}

// VueFlow nodes and edges
const nodes = ref([])

const edges = ref([])

const isCreatingConnection = ref(false)

// Start node ID
const START_NODE_ID = '__start'

// Map node IDs to mascot sprites shown above each node card.
// Characters come from each node's `mascot` in the YAML (auto-assigned, stable ones
// otherwise), so the editor, launch and office views always show the same mascot.
const nodeSpriteMap = ref(new Map())

const syncNodeSprites = () => {
  spriteFetcher.bindNodes(yamlContent.value?.graph?.nodes || [])
  const nextMap = new Map()
  for (const node of nodes.value || []) {
    if (!node?.id || node.id === START_NODE_ID) continue
    nextMap.set(node.id, spriteFetcher.fetchSprite(node.id, 'D', 1))
  }
  nodeSpriteMap.value = nextMap
}

// Rebuild whenever node ids or chosen mascots change (add / remove / load / edit)
watch(
  () => [
    (nodes.value || []).map(node => node?.id).join('\n'),
    (yamlContent.value?.graph?.nodes || []).map(node => `${node?.id}:${node?.mascot ?? ''}`).join('\n')
  ].join('|'),
  () => syncNodeSprites()
)

// Context menu state
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const pendingNodePosition = ref(null)
const contextMenuType = ref('pane') // 'pane' | 'node' | 'edge'
const contextNodeId = ref(null)
const contextEdgeInfo = ref(null) // { from, to }

const hideContextMenu = () => {
  contextMenuVisible.value = false
}

const getFlowPositionFromEvent = (event) => {
  try {
    const viewport = getViewport()
    const container = vueflowContainerRef.value
    if (!viewport || !container || !event) {
      return getCentralPosition()
    }

    const rect = container.getBoundingClientRect()
    const screenX = event.clientX - rect.left
    const screenY = event.clientY - rect.top

    const x = (screenX - viewport.x) / viewport.zoom
    const y = (screenY - viewport.y) / viewport.zoom

    return { x, y }
  } catch (error) {
    console.warn('Failed to convert click position to flow coordinates:', error)
    return getCentralPosition()
  }
}

const onContainerContextMenu = (event) => {
  // Only respond to right-clicks inside the flow container
  if (!vueflowContainerRef.value) {
    return
  }

  // Store menu position relative to container (for UI)
  const rect = vueflowContainerRef.value.getBoundingClientRect()
  contextMenuX.value = event.clientX - rect.left
  contextMenuY.value = event.clientY - rect.top
  contextMenuType.value = 'pane'
  contextNodeId.value = null
  contextEdgeInfo.value = null
  contextMenuVisible.value = true

  // Pre-compute desired node position in flow coordinates
  pendingNodePosition.value = getFlowPositionFromEvent(event)
}

// Disable default pane context behaviour in VueFlow and use custom behaviour
const onPaneContextMenu = (params) => {
  const mouseEvent = params?.event || params
  mouseEvent?.preventDefault?.()
  if (!mouseEvent) return
  onContainerContextMenu(mouseEvent)
}

const onNodeContextMenu = (params) => {
  const mouseEvent = params?.event || params
  const node = params?.node || params?.event?.node || params
  if (!mouseEvent || !node?.id || !vueflowContainerRef.value) {
    return
  }
  mouseEvent.preventDefault?.()
  
  // Ignore context menu for start node, show dim animation
  if (node.id === START_NODE_ID) {
    dimStartNode()
    return
  }

  const rect = vueflowContainerRef.value.getBoundingClientRect()
  contextMenuX.value = mouseEvent.clientX - rect.left
  contextMenuY.value = mouseEvent.clientY - rect.top

  contextMenuType.value = 'node'
  contextNodeId.value = node.id
  contextEdgeInfo.value = null
  pendingNodePosition.value = null
  contextMenuVisible.value = true
}

const onEdgeContextMenu = (params) => {
  const mouseEvent = params?.event || params
  const edge = params?.edge || params?.event?.edge || params
  if (!mouseEvent || !edge || !vueflowContainerRef.value) {
    return
  }
  mouseEvent.preventDefault?.()
  if (edge.data?.virtual) {
    return
  }

  const fromId = edge.data?.from || edge.source
  const toId = edge.data?.to || edge.target
  if (!fromId || !toId) {
    return
  }

  const rect = vueflowContainerRef.value.getBoundingClientRect()
  contextMenuX.value = mouseEvent.clientX - rect.left
  contextMenuY.value = mouseEvent.clientY - rect.top

  contextMenuType.value = 'edge'
  contextNodeId.value = null
  contextEdgeInfo.value = { from: fromId, to: toId }
  pendingNodePosition.value = null
  contextMenuVisible.value = true
}

const onGlobalClick = () => {
  // Clicks outside the menu will bubble to window and handled here
  // Clicks on the menu itself are stopped with @click.stop
  if (contextMenuVisible.value) {
    contextMenuVisible.value = false
  }
  if (showMenu.value) {
    showMenu.value = false
  }
}

let dimStartNodeTimers = []

const dimStartNode = () => {
  // Prefer the graph node from the VueFlow store (reactive), fall back to the model array
  const startNode = findNode?.(START_NODE_ID) || nodes.value.find(node => node.id === START_NODE_ID)
  if (!startNode) return

  const dimSpeed = 120 // milliseconds between opacity changes - slightly slower for smoothness
  const dimSteps = [1, 0.6, 1, 0.6, 1] // Full opacity -> dim -> full -> dim -> full

  // Restart cleanly if the user clicks again mid-blink
  dimStartNodeTimers.forEach(clearTimeout)
  dimStartNodeTimers = dimSteps.map((opacity, index) =>
    setTimeout(() => {
      // Targeted update: only the start node's data changes, so only StartNode
      // re-renders (replacing the whole nodes array re-synced every node)
      startNode.data = { ...startNode.data, opacity }
    }, index * dimSpeed)
  )
}

// Persist an updated YAML snapshot back to the server and refresh local state
const persistYamlSnapshot = async (snapshot) => {
  try {
    if (!currentWorkflowName.value) {
      return false
    }
    const yamlString = yaml.dump(snapshot ?? {})
    const result = await updateYaml(currentWorkflowName.value, yamlString)
    if (!result?.success) {
      console.error('Failed to update workflow YAML:', result?.message || result?.detail)
      toast.error(withErrorDetail(t('workflow_view.alert_save_failed'), result))
      return false
    }
    console.log("YAML snapshot successfully persisted through API")
    return true
  } catch (error) {
    console.error('Error persisting YAML snapshot:', error)
    toast.error(withErrorDetail(t('workflow_view.alert_save_failed'), { detail: error?.message }))
    return false
  }
}

const onCopyNodeFromContext = () => {
  const nodeId = contextNodeId.value
  if (!nodeId) {
    return
  }
  const yamlNodeContent = (yamlContent.value?.graph?.nodes || []).find(node => node.id === nodeId)
  if (!yamlNodeContent) {
    console.warn(`[WorkflowView] Node with id "${nodeId}" not found for copying`)
    return
  }
  handleFormGeneratorCopy({ initialFormData: yamlNodeContent })
}

// Quick team building: copy the node with the next numbered ID and add it to the same teams.
const onDuplicateNodeFromContext = async () => {
  const nodeId = contextNodeId.value
  const source = yamlContent.value
  const result = nodeId && source?.graph ? duplicateNodeInGraph(source.graph, nodeId) : null
  if (!result) {
    return
  }
  const original = vueFlowNodeById(nodeId)
  const ok = await persistYamlSnapshot({ ...source, graph: result.graph })
  if (!ok) {
    return
  }
  await loadYamlFile()
  syncVueNodesAndEdgesData()
  await nextTick()
  // Stand the copy just below the original instead of wherever the auto layout puts new nodes.
  const copy = vueFlowNodeById(result.newId)
  if (copy && original?.position) {
    copy.position = { x: original.position.x, y: original.position.y + 170 }
  }
  await saveVueFlowGraph()
  toast.success(result.leads.length
    ? t('workflow_view.duplicate_node_done_team', { name: result.newId, leads: result.leads.join(', ') })
    : t('workflow_view.duplicate_node_done', { name: result.newId }))
}

// "Nhân bản ×N": N numbered copies of an agent in one save. Each copy goes through the same
// duplicateNodeInGraph() as the single duplicate, so it gets the next free "<name> <n>" ID and is
// inserted into every lead's explicit team.members list that contains the original. Leads with an
// empty member list already pick up every edge-less agent, so the copies join them automatically.
const DUPLICATE_MANY_MAX = 20
const showDuplicateManyModal = ref(false)
const duplicateManyNodeId = ref('')
const duplicateManyCount = ref(1)
const duplicateManyBusy = ref(false)

const contextNodeIsAgent = computed(() => {
  const id = contextNodeId.value
  if (!id) return false
  const node = (yamlContent.value?.graph?.nodes || []).find(item => item?.id === id)
  return node?.type === 'agent'
})

const duplicateManyValid = computed(() => {
  const n = duplicateManyCount.value
  return Number.isInteger(n) && n >= 1 && n <= DUPLICATE_MANY_MAX
})

const duplicateNodeTimes = (graph, nodeId, count) => {
  let current = graph
  const newIds = []
  let leads = []
  for (let i = 0; i < count; i += 1) {
    const result = duplicateNodeInGraph(current, nodeId)
    if (!result) return null
    current = result.graph
    newIds.push(result.newId)
    if (i === 0) leads = result.leads
  }
  return { graph: current, newIds, leads }
}

const duplicateManyPlan = computed(() => {
  const graph = yamlContent.value?.graph
  if (!showDuplicateManyModal.value || !graph || !duplicateManyValid.value) return null
  return duplicateNodeTimes(graph, duplicateManyNodeId.value, duplicateManyCount.value)
})

const duplicateManyLeads = computed(() => duplicateManyPlan.value?.leads || [])

const duplicateManyPreview = computed(() => {
  if (!duplicateManyValid.value) return t('workflow_view.duplicate_many_range', { max: DUPLICATE_MANY_MAX })
  const ids = duplicateManyPlan.value?.newIds || []
  if (!ids.length) return ''
  return ids.length === 1
    ? t('workflow_view.duplicate_many_preview_one', { first: ids[0] })
    : t('workflow_view.duplicate_many_preview', { first: ids[0], last: ids[ids.length - 1] })
})

const openDuplicateManyModal = (nodeId) => {
  if (!nodeId) return
  duplicateManyNodeId.value = nodeId
  duplicateManyCount.value = 1
  showDuplicateManyModal.value = true
}

const closeDuplicateManyModal = () => {
  if (duplicateManyBusy.value) return
  showDuplicateManyModal.value = false
}

// Copies stand in a block next to the original: down a column of 6, then the next column right.
const DUPLICATE_COLUMN = 6
const DUPLICATE_GAP_X = 330
const DUPLICATE_GAP_Y = 170

const handleDuplicateManySubmit = async () => {
  const nodeId = duplicateManyNodeId.value
  const source = yamlContent.value
  if (!duplicateManyValid.value || duplicateManyBusy.value || !source?.graph || !nodeId) return
  const plan = duplicateNodeTimes(source.graph, nodeId, duplicateManyCount.value)
  if (!plan) return
  duplicateManyBusy.value = true
  try {
    const original = vueFlowNodeById(nodeId)
    const origin = original?.position ? { ...original.position } : null
    const ok = await persistYamlSnapshot({ ...source, graph: plan.graph })
    if (!ok) return
    await loadYamlFile()
    syncVueNodesAndEdgesData()
    await nextTick()
    if (origin) {
      plan.newIds.forEach((id, i) => {
        const copy = vueFlowNodeById(id)
        if (!copy) return
        const slot = i + 1 // slot 0 is the original
        copy.position = {
          x: origin.x + Math.floor(slot / DUPLICATE_COLUMN) * DUPLICATE_GAP_X,
          y: origin.y + (slot % DUPLICATE_COLUMN) * DUPLICATE_GAP_Y
        }
      })
    }
    await saveVueFlowGraph()
    const first = plan.newIds[0]
    const last = plan.newIds[plan.newIds.length - 1]
    toast.success(plan.leads.length
      ? t('workflow_view.duplicate_many_done_team', { count: plan.newIds.length, first, last, leads: plan.leads.join(', ') })
      : t('workflow_view.duplicate_many_done', { count: plan.newIds.length, first, last }))
    showDuplicateManyModal.value = false
  } finally {
    duplicateManyBusy.value = false
  }
}

const vueFlowNodeById = (id) => (nodes.value || []).find(node => node.id === id)

const deleteNodeById = async (nodeId) => {
  if (!nodeId) {
    return
  }
  const source = yamlContent.value
  if (!source?.graph) {
    return
  }
  const sourceGraph = source.graph
  const nodesArr = Array.isArray(sourceGraph.nodes) ? sourceGraph.nodes : []
  const edgesArr = Array.isArray(sourceGraph.edges) ? sourceGraph.edges : []

  // Remove the node and its related edges
  const nextNodes = nodesArr.filter(node => node?.id !== nodeId)
  const nextEdges = edgesArr.filter(edge => edge?.from !== nodeId && edge?.to !== nodeId)
  
  // Remove node ID from graph.start/end
  const nextStart = Array.isArray(sourceGraph.start)
    ? sourceGraph.start.filter(id => id !== nodeId)
    : sourceGraph.start
  const nextEnd = Array.isArray(sourceGraph.end)
    ? sourceGraph.end.filter(id => id !== nodeId)
    : sourceGraph.end

  const nextSnapshot = {
    ...source,
    graph: {
      ...sourceGraph,
      nodes: nextNodes,
      edges: nextEdges,
      start: nextStart,
      end: nextEnd
    }
  }

  const ok = await persistYamlSnapshot(nextSnapshot)
  if (!ok) {
    return
  }

  await loadYamlFile()
  syncVueNodesAndEdgesData()
  await nextTick()
  await saveVueFlowGraph()
}

const deleteEdgeByEndpoints = async (fromId, toId) => {
  if (!fromId || !toId) {
    return
  }
  const source = yamlContent.value
  if (!source?.graph || !Array.isArray(source.graph.edges)) {
    return
  }
  const sourceGraph = source.graph

  let removed = false
  const nextEdges = sourceGraph.edges.filter(edge => {
    if (!removed && edge?.from === fromId && edge?.to === toId) {
      removed = true
      return false
    }
    return true
  })

  // Delete from .start if edge is from Start Node
  let nextStart = sourceGraph.start
  if (fromId === START_NODE_ID) {
    nextStart = Array.isArray(sourceGraph.start)
      ? sourceGraph.start.filter(id => id !== toId)
      : sourceGraph.start

    // Empty start node array is not allowed
    const startArray = Array.isArray(nextStart) ? nextStart : []
    if (startArray.length === 0) {
      toast.warning(t('workflow_view.alert_start_edge_required'))
      return
    }
  }

  const nextSnapshot = {
    ...source,
    graph: {
      ...sourceGraph,
      edges: nextEdges,
      start: nextStart
    }
  }

  const ok = await persistYamlSnapshot(nextSnapshot)
  if (!ok) {
    return
  }

  await loadYamlFile()
  syncVueNodesAndEdgesData()
  await nextTick()
  await saveVueFlowGraph()
}

const onDeleteNodeFromContext = async () => {
  const nodeId = contextNodeId.value
  contextNodeId.value = null
  const confirmed = await confirmDialog({
    title: t('workflow_view.confirm_delete_node'),
    message: t('workflow_view.confirm_delete_node_detail'),
    confirmText: t('confirm.delete'),
    tone: 'danger'
  })
  if (!confirmed) {
    return
  }
  if (!nodeId) {
    return
  }
  await deleteNodeById(nodeId)
}

const onDeleteEdgeFromContext = async () => {
  const info = contextEdgeInfo.value
  contextEdgeInfo.value = null
  const confirmed = await confirmDialog({
    title: t('workflow_view.confirm_delete_edge'),
    message: t('workflow_view.confirm_delete_edge_detail'),
    confirmText: t('confirm.delete'),
    tone: 'danger'
  })
  if (!confirmed) {
    return
  }
  if (!info?.from || !info?.to) {
    return
  }
  await deleteEdgeByEndpoints(info.from, info.to)
}

const initializeWorkflow = async (name) => {
  if (!name) {
    return
  }
  currentWorkflowName.value = name
  console.log('Workflow initialized: ', currentWorkflowName.value)
  await loadYamlFile()
  loadAndSyncVueFlowGraph()
  await nextTick()
  fitGraph()
}

watch(
  () => props.workflowName,
  async (newName) => {
    await initializeWorkflow(newName)
  },
  { immediate: false }
)

onMounted(async () => {
  window.addEventListener('click', onGlobalClick)
  await initializeWorkflow(props.workflowName)
})

onBeforeUnmount(() => {
  clearTimeout(fitFallback)
  pendingFit = false
  window.removeEventListener('click', onGlobalClick)
  dimStartNodeTimers.forEach(clearTimeout)
  dimStartNodeTimers = []
})

watch(activeTab, async (newTab) => {
  if (newTab === 'graph') {
    await nextTick()
    fitGraph()
  }
})

const saveVueFlowGraph = async () => {
  try {
    const flowObj = toObject()
    const key = currentWorkflowName.value
    const result = await postVuegraphs({
      filename: key,
      content: JSON.stringify(flowObj)
    })

    if (!result?.success) {
      console.error('Failed to save VueFlow graph:', result?.message || result?.detail)
      return false
    }
    return true
  } catch (error) {
    console.error('Failed to save VueFlow graph:', error)
    return false
  }
}

const loadAndSyncVueFlowGraph = async () => {
  try {
    const key = currentWorkflowName.value
    const result = await fetchVueGraph(key)

    if(result?.success === true) {
      console.log("Graph fetched successfully")
    }

    if (result?.status === 404) {
      // Not found in server storage, fallback
      console.log("No graph found, fallback to generation")
      await generateNodesAndEdges()
      return false
    }

    if (!result?.success) {
      console.error('Failed to load VueFlow graph:', result?.message || result?.detail)
      // Fallback if server error
      generateNodesAndEdges()
      return false
    }

    const content = result?.content
    if (content) {
      const flow = JSON.parse(content)
      if (flow) {
        fromObject(flow)
        await nextTick()
        syncVueNodesAndEdgesData()
        return true
      }
    }
  } catch (error) {
    console.error('Failed to load saved VueFlow graph:', error)
  }

  // If no VueFlow graph restored, fall back to manual generation
  await generateNodesAndEdges()
  return false
}

const loadYamlFile = async () => {
  try {
    if (!currentWorkflowName.value) {
      return
    }
    yamlLoadError.value = null
    const result = await fetchYaml(currentWorkflowName.value)

    if (!result?.success) {
      console.error('Failed to load YAML file', result?.message || result?.detail)
      yamlLoadError.value = withErrorDetail(t('workflow_view.yaml_load_failed'), result)
      yamlTextString.value = ''
      return
    }

    const yamlString = result.content ?? ''
    console.log('YAML content loaded successfully')

    // Parse YAML string to YAML object
    try {
      const parsed = yaml.load(yamlString)
      yamlContent.value = parsed || {}
      yamlTextString.value = yamlString
      yamlParseError.value = null
    } catch (parseError) {
      console.error('Error parsing YAML:', parseError)
      yamlParseError.value = parseError.message
      yamlTextString.value = yamlString
    }
  } catch (error) {
    console.error('Error loading YAML file: ', error)
    yamlLoadError.value = withErrorDetail(t('workflow_view.yaml_load_failed'), { detail: error?.message })
    yamlTextString.value = ''
  }
}

const getCentralPosition = () => {
  try {
    const viewport = getViewport()
    if (viewport && vueflowContainerRef.value) {
      // Get container dimensions
      const container = vueflowContainerRef.value
      const containerWidth = container.clientWidth || container.offsetWidth
      const containerHeight = container.clientHeight || container.offsetHeight
      
      const screenCenterX = containerWidth / 2
      const screenCenterY = containerHeight / 2
      
      // Convert screen coordinates to flow coordinates
      // Formula: flowCoord = (screenCoord - viewportOffset) / zoom
      const centerX = (screenCenterX - viewport.x) / viewport.zoom
      const centerY = (screenCenterY - viewport.y) / viewport.zoom
      
      return { x: centerX, y: centerY }
    }
  } catch (error) {
    console.warn('Failed to get viewport center, using default position:', error)
  }
  // Fallback to default center position
  return { x: 400, y: 300 }
}

// Who leads whom (team workflows): drives the org-chart chips on the nodes
const teamChart = computed(() => buildOrgChart(yamlContent.value?.graph))

const updateNodesAndEdgesFromYaml = (preserveExistingLayout = false) => {
  try {
    const yamlNodes = Array.isArray(yamlContent.value?.graph?.nodes)
      ? yamlContent.value.graph.nodes
      : []
    const yamlEdges = Array.isArray(yamlContent.value?.graph?.edges)
      ? yamlContent.value.graph.edges
      : []

    // Visual-only "delegation" links lead -> member (never written to YAML, never run by the engine)
    const teamLinks = computeTeamLinks(yamlNodes, yamlEdges)
    const layoutEdges = [...yamlEdges, ...teamLinks]

    const currentNodes = nodes.value || []
    const currentEdges = edges.value || []
    const defaultCenterPosition = getCentralPosition()
    const getDefaultCenterPosition = () => ({
      x: defaultCenterPosition.x,
      y: defaultCenterPosition.y
    })

    const existingNodeById = preserveExistingLayout
      ? new Map(currentNodes.map(node => [node.id, node]))
      : null
    const existingEdgeByKey = preserveExistingLayout
      ? new Map(currentEdges.filter(edge => !edge.data?.virtual).map(edge => [`${edge.source}-${edge.target}`, edge]))
      : null
    
      // Compute node positions using a simple topological layering
      // This arranges nodes by levels (distance from sources)
      // Ignore backward/cycle edges for cyclic graphs
      try {
        const nodeIds = (yamlNodes || []).map(n => n?.id).filter(Boolean)

        // Build adjacency and indegree
        const adj = new Map()
        const indegree = new Map()
        nodeIds.forEach(id => {
          adj.set(id, new Set())
          indegree.set(id, 0)
        })

        ;(layoutEdges || []).forEach(e => {
          if (!e || !e.from || !e.to) return
          if (!adj.has(e.from) || !adj.has(e.to)) return
          adj.get(e.from).add(e.to)
          indegree.set(e.to, (indegree.get(e.to) || 0) + 1)
        })

        // Kahn's algorithm to compute levels
        const levelById = new Map()
        const q = []
        nodeIds.forEach(id => {
          if ((indegree.get(id) || 0) === 0) {
            q.push(id)
            levelById.set(id, 0)
          }
        })

        // Heuristic: if the graph has no indegree-0 nodes (pure cycle),
        // pick the first node declared in YAML `graph.start` as a pseudo-source
        // so Kahn's algorithm can proceed and assign at least one level.
        if (q.length === 0) {
          try {
            const yamlStartList = Array.isArray(yamlContent.value?.graph?.start)
              ? yamlContent.value.graph.start
              : []
            const firstStart = yamlStartList.find(s => nodeIds.includes(s))
            if (firstStart) {
              // Force indegree to zero and seed the queue so at least one node gets level 0
              indegree.set(firstStart, 0)
              q.push(firstStart)
              levelById.set(firstStart, 0)
            }
          } catch {
            // ignore and fall back later
          }
        }

        let queueIndex = 0
        while (queueIndex < q.length) {
          const id = q[queueIndex++]
          const baseLevel = levelById.get(id) || 0
          const neighbors = adj.get(id) || new Set()
          for (const nb of neighbors) {
            const prev = levelById.get(nb) ?? 0
            const newLevel = Math.max(prev, baseLevel + 1)
            levelById.set(nb, newLevel)
            indegree.set(nb, indegree.get(nb) - 1)
            if (indegree.get(nb) === 0) q.push(nb)
          }
        }

        
        const predecessors = new Map()
        nodeIds.forEach(id => predecessors.set(id, new Set()))
        ;(layoutEdges || []).forEach(e => {
          if (!e || !e.from || !e.to) return
          if (!predecessors.has(e.to)) return
          predecessors.get(e.to).add(e.from)
        })

        let changed = true
        let iterations = 0
        const maxIterations = nodeIds.length + 5
        while (changed && iterations < maxIterations) {
          changed = false
          iterations++
          nodeIds.forEach(id => {
            if (levelById.has(id)) return
            const preds = predecessors.get(id) || new Set()
            const predLevels = Array.from(preds).map(p => levelById.get(p)).filter(l => typeof l === 'number')
            if (predLevels.length) {
              const lvl = Math.max(...predLevels) + 1
              levelById.set(id, lvl)
              changed = true
            }
          })
        }

        // Any remaining unassigned nodes -> fallback to level 0
        nodeIds.forEach(id => {
          if (!levelById.has(id)) levelById.set(id, 0)
        })

        // Group nodes by level and compute positions (simple grid per level)
        const buckets = new Map()
        for (const [id, lvl] of levelById.entries()) {
          if (!buckets.has(lvl)) buckets.set(lvl, [])
          buckets.get(lvl).push(id)
        }

        const positions = new Map()
        const levelKeys = Array.from(buckets.keys()).sort((a, b) => a - b)
        const spacingX = 280
        const spacingY = 120
        const startX = 50
        const startY = 50

        levelKeys.forEach(lvl => {
          const ids = buckets.get(lvl) || []
          const x = startX + lvl * spacingX
          let currentY = startY
          // Apply a slight Y offset (+/-10) to the first node in each layer to avoid exact horizontal alignments
          const layerOffset = (lvl % 2 === 0) ? -30 : 30
          ids.forEach((id, idx) => {
            const yPos = currentY + (idx === 0 ? layerOffset : 0)
            positions.set(id, { x, y: yPos })
            currentY += spacingY
          })
        })

        // Team workflows read as an org chart: lead on the left, each level one column to the right
        if (teamLinks.length) {
          for (const [id, pos] of layoutOrgTree(teamLinks, { originX: startX, originY: startY, gapY: 200 })) {
            if (positions.has(id) || nodeIds.includes(id)) positions.set(id, pos)
          }
        }

        // Build nextNodes respecting preserveExistingLayout where possible
        const nextNodes = yamlNodes.map((yamlNode) => {
          const id = yamlNode?.id
          if (!id) return null
          if (preserveExistingLayout && existingNodeById?.has(id)) {
            const existingNode = existingNodeById.get(id)
            return {
              ...existingNode,
              id,
              label: id,
              data: yamlNode
            }
          }

          const pos = positions.get(id) || getDefaultCenterPosition()
          return {
            id,
            type: 'workflow-node',
            label: id,
            position: pos,
            data: yamlNode
          }
        }).filter(Boolean)

        nodes.value = nextNodes
      } catch (err) {
        console.error('Failed to compute topological layout, falling back to center positions:', err)
        // Fallback to previous behavior
        const nextNodes = yamlNodes.map((yamlNode) => ({
          id: yamlNode.id,
          type: 'workflow-node',
          label: yamlNode.id,
          position: getDefaultCenterPosition(),
          data: yamlNode
        }))
        nodes.value = nextNodes
      }

    // Build edges from YAML (preserve layout where possible)
    const nextYamlEdges = yamlEdges.map(yamlEdge => {
      const key = `${yamlEdge.from}-${yamlEdge.to}`
      const baseEdge = preserveExistingLayout && existingEdgeByKey?.has(key)
        ? existingEdgeByKey.get(key)
        : {
            id: key,
            source: yamlEdge.from,
            target: yamlEdge.to,
            type: 'workflow-edge'
          }

      return {
        ...baseEdge,
        id: key,
        source: yamlEdge.from,
        target: yamlEdge.to,
        data: yamlEdge,
        markerEnd: {
          type: MarkerType.Arrow,
          width: 16,
          height: 16,
          // Set color to match with edge
          color: (yamlEdge && yamlEdge.trigger === false) ? 'var(--text-muted-2)' : 'var(--text-1)',
          strokeWidth: 1.5,
        },
      }
    })
    // Nodes in .start
    const declaredStartSet = new Set(Array.isArray(yamlContent.value?.graph?.start) ? yamlContent.value.graph.start : [])

    // Create visual-only start node (reuse existing if present)
    let startNode = null
    if (preserveExistingLayout && existingNodeById?.has(START_NODE_ID)) {
      startNode = { ...existingNodeById.get(START_NODE_ID), id: START_NODE_ID, type: 'start-node', data: { id: START_NODE_ID, label: 'Start' } }
    } else {
      try {
        // Place start node to the left of the leftmost column
        const yamlNodesInGraph = (nodes.value || []).filter(n => n && n.id !== START_NODE_ID)
        if (yamlNodesInGraph.length) {
          const xs = yamlNodesInGraph.map(n => (n?.position && typeof n.position.x === 'number') ? n.position.x : defaultCenterPosition.x)
          const minX = Math.min(...xs)
          // Find nodes in that left column
          const tol = 1
          const leftColumn = yamlNodesInGraph.filter(n => Math.abs((n?.position?.x || 0) - minX) <= tol)
          const ys = leftColumn.map(n => (n?.position && typeof n.position.y === 'number') ? n.position.y : defaultCenterPosition.y)
          const avgY = ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : defaultCenterPosition.y
          const startXOffset = -100
          const startYOffset = 80
          startNode = {
            id: START_NODE_ID,
            type: 'start-node',
            label: 'Start',
            position: { x: minX + startXOffset, y: avgY + startYOffset },
            data: { id: START_NODE_ID, label: 'Start' }
          }
        } else {
          startNode = {
            id: START_NODE_ID,
            type: 'start-node',
            label: 'Start',
            position: getDefaultCenterPosition(),
            data: { id: START_NODE_ID, label: 'Start' }
          }
        }
      } catch (err) {
        console.warn('Failed to compute start node position, falling back to center:', err)
        startNode = {
          id: START_NODE_ID,
          type: 'start-node',
          label: 'Start',
          position: getDefaultCenterPosition(),
          data: { id: START_NODE_ID, label: 'Start' }
        }
      }
    }

    // Build start edges to YAML nodes that are declared in graph.start
    const startEdges = (yamlNodes || []).map(yamlNode => {
      if (!yamlNode?.id) return null
      if (!declaredStartSet.has(yamlNode.id)) return null

      const key = `${START_NODE_ID}-${yamlNode.id}`
      const baseEdge = preserveExistingLayout && existingEdgeByKey?.has(key)
        ? existingEdgeByKey.get(key)
        : {
            id: key,
            source: START_NODE_ID,
            target: yamlNode.id,
            type: 'workflow-edge'
          }

        return {
        ...baseEdge,
        id: key,
        source: START_NODE_ID,
        target: yamlNode.id,
        data: { from: START_NODE_ID, to: yamlNode.id },
        markerEnd: {
          type: MarkerType.Arrow,
          width: 16,
          height: 16,
          color: 'var(--text-1)',
          strokeWidth: 1.5,
        },
        animated: false
      }
    }).filter(Boolean)

    // Visual-only team edges. `virtual: true` and no from/to keep them out of every YAML code path.
    const teamEdges = teamLinks.map(link => ({
      id: `team:${link.from}->${link.to}`,
      source: link.from,
      target: link.to,
      type: 'workflow-edge',
      selectable: false,
      focusable: false,
      deletable: false,
      updatable: false,
      data: { virtual: true, kind: 'team', lead: link.from, member: link.to },
      markerEnd: {
        type: MarkerType.Arrow,
        width: 14,
        height: 14,
        color: 'var(--text-muted-2)',
        strokeWidth: 1.2,
      },
    }))

    // Combine YAML edges with visual start edges (preserve any existing non-yaml edges)
    const nextYamlEdgeIdSet = new Set(nextYamlEdges.map(edge => edge.id))
    edges.value = [
      // keep any existing edges that are not YAML edges (e.g., visual-only) when preserving layout
      // but always exclude previous Start edges so they are replaced by the newly computed ones
      ...(preserveExistingLayout ? currentEdges.filter(e => {
        const k = `${e.source}-${e.target}`
        // drop if it's a YAML-defined edge or a previous Start edge
        const isYamlEdge = nextYamlEdgeIdSet.has(k)
        const isStartEdge = e.source === START_NODE_ID
        // Also drop if it looks like a YAML edge (has data.from/to) but isn't in nextYamlEdges (stale)
        const isStaleYamlEdge = e.data?.from && e.data?.to
        const isVirtualEdge = !!e.data?.virtual
        return !isYamlEdge && !isStartEdge && !isStaleYamlEdge && !isVirtualEdge
      }) : []),
      ...nextYamlEdges,
      ...startEdges,
      ...teamEdges
    ]

    // Ensure start node is present in nodes list (preserving layout if asked)
    if (!nodes.value.some(n => n.id === START_NODE_ID)) {
      nodes.value = [startNode, ...nodes.value]
    } else {
      // if present, ensure the start node data/type is correct
      nodes.value = nodes.value.map(n => n.id === START_NODE_ID ? startNode : n)
    }
  } catch (error) {
    console.error('Error syncing nodes and edges from YAML:', error)
  }
}

const generateNodesAndEdges = async (options = {}) => {
  updateNodesAndEdgesFromYaml(false)

  // Save generated graph at nextTick
  try {
    await nextTick()
    if (options.fit) {
      fitGraph()
    }
    await saveVueFlowGraph()
  } catch (err) {
    console.warn('Failed to persist generated VueFlow graph:', err)
  }
}

const syncVueNodesAndEdgesData = () => {
  updateNodesAndEdgesFromYaml(true)
}

const updateVueFlowNodeId = (oldId, newId) => {
  if (!oldId || !newId || oldId === newId) {
    return
  }

  nodes.value = (nodes.value || []).map(node => {
    if (node.id !== oldId) {
      return node
    }
    return {
      ...node,
      id: newId,
      label: newId,
      data: node.data
        ? { ...node.data, id: newId }
        : { id: newId }
    }
  })

  edges.value = (edges.value || []).map(edge => {
    let source = edge.source
    let target = edge.target
    let edgeChanged = false

    if (source === oldId) {
      source = newId
      edgeChanged = true
    }

    if (target === oldId) {
      target = newId
      edgeChanged = true
    }

    let nextData = edge.data
    if (edge.data) {
      const nextFrom = edge.data.from === oldId ? newId : edge.data.from
      const nextTo = edge.data.to === oldId ? newId : edge.data.to

      if (nextFrom !== edge.data.from || nextTo !== edge.data.to) {
        nextData = {
          ...edge.data,
          from: nextFrom,
          to: nextTo
        }
      }
    }

    const nextEdge = {
      ...edge,
      source,
      target,
      data: nextData
    }

    if (edgeChanged) {
      nextEdge.id = `${source}-${target}`
    }

    return nextEdge
  })

  // Update node ID in graph.start
  if (yamlContent.value?.graph?.start && Array.isArray(yamlContent.value.graph.start)) {
    yamlContent.value.graph.start = yamlContent.value.graph.start.map(startNodeId =>
      startNodeId === oldId ? newId : startNodeId
    )
  }

  // Same for graph.end
  if (yamlContent.value?.graph?.end && Array.isArray(yamlContent.value.graph.end)) {
    yamlContent.value.graph.end = yamlContent.value.graph.end.map(endNodeId =>
      endNodeId === oldId ? newId : endNodeId
    )
  }
}

// FormGenerator integration
// Build YAML without specific node (shallow clone path to avoid full deep-clone on editor open)
const buildYamlWithoutNode = (nodeId) => {
  const source = yamlContent.value
  if (!source?.graph?.nodes || !Array.isArray(source.graph.nodes)) {
    return source
  }
  return {
    ...source,
    graph: {
      ...source.graph,
      nodes: source.graph.nodes.filter(node => node?.id !== nodeId)
    }
  }
}

const buildYamlWithoutEdge = (fromId, toId) => {
  const source = yamlContent.value
  if (!source?.graph?.edges || !Array.isArray(source.graph.edges)) {
    return source
  }
  let removed = false
  const filteredEdges = source.graph.edges.filter(edge => {
    if (!removed && edge?.from === fromId && edge?.to === toId) {
      removed = true
      return false
    }
    return true
  })
  return {
    ...source,
    graph: {
      ...source.graph,
      edges: filteredEdges
    }
  }
}

const buildYamlWithoutVars = () => {
  const source = yamlContent.value
  if (!source || typeof source !== 'object') {
    return source
  }
  if (!Object.prototype.hasOwnProperty.call(source, 'vars')) {
    return source
  }
  const sanitized = { ...source }
  delete sanitized.vars
  return sanitized
}

const buildYamlWithoutMemory = () => {
  const source = yamlContent.value
  if (!source?.graph) {
    return source
  }
  if (Object.prototype.hasOwnProperty.call(source.graph, 'memory')) {
    const newGraph = { ...source.graph }
    delete newGraph.memory
    return {
      ...source,
      graph: newGraph
    }
  }
  return source
}

const buildYamlWithoutGraph = () => {
  const source = yamlContent.value
  if (!source || typeof source !== 'object') {
    return source
  }
  if (!Object.prototype.hasOwnProperty.call(source, 'graph')) {
    return source
  }
  const sanitized = { ...source }
  delete sanitized.graph
  return sanitized
}

const autoAddStartEdge = async (nextNodeId) => {
  const workflowNodes = (yamlContent.value?.graph?.nodes || []).filter(node => node?.id !== START_NODE_ID)
  if (workflowNodes.length === 1 && workflowNodes[0]?.id === nextNodeId) {
    const source = yamlContent.value
    const sourceGraph = source?.graph && typeof source.graph === 'object' ? source.graph : {}
    const currentStart = Array.isArray(sourceGraph.start) ? sourceGraph.start : []
    if (!currentStart.includes(nextNodeId)) {
      const nextSnapshot = {
        ...source,
        graph: {
          ...sourceGraph,
          start: [...currentStart, nextNodeId]
        }
      }
      const ok = await persistYamlSnapshot(nextSnapshot)
      if (ok) {
        await loadYamlFile()
        syncVueNodesAndEdgesData()
        await nextTick()
      }
    }
  }
}

// Heading and confirm button of the form, so it is always clear what is being created or edited
const formGeneratorKind = ref('')
const formGeneratorTitle = computed(() => {
  const kind = formGeneratorKind.value
  const isEdit = formGeneratorMode.value === 'edit'
  const data = formGeneratorInitialFormData.value || {}
  if (kind === 'node') return isEdit ? t('form_generator.title_edit_node', { id: data.id || '' }) : t('form_generator.title_create_node')
  if (kind === 'edge') {
    return isEdit && data.from && data.to
      ? t('form_generator.title_edit_edge', { from: data.from, to: data.to })
      : t('form_generator.title_create_edge')
  }
  if (kind === 'graph') return t('workflow_view.configure_graph')
  if (kind === 'vars') return t('workflow_view.manage_variables')
  if (kind === 'memory') return t('workflow_view.manage_memories')
  return ''
})
const formGeneratorSubmitLabel = computed(() => {
  const kind = formGeneratorKind.value
  if (formGeneratorMode.value === 'edit' || ['graph', 'vars', 'memory'].includes(kind)) return t('form_generator.save_changes')
  if (kind === 'node') return t('form_generator.submit_create_node')
  if (kind === 'edge') return t('form_generator.submit_create_edge')
  return ''
})

const openDynamicFormGenerator = (type, options = {}) => {
  const config = FORM_GENERATOR_CONFIG[type]
  if (!config) {
    console.error(`[FormGenerator] Unknown type: ${type}`)
    return
  }
  formGeneratorBreadcrumbs.value = config.map(crumb => ({ ...crumb }))
  formGeneratorKind.value = type
  formGeneratorRecursive.value = options.recursive ?? true

  const resolvedMode = typeof options.mode === 'string' && ['create', 'edit'].includes(options.mode)
    ? options.mode
    : (options.initialFormData ? 'edit' : 'create')
  formGeneratorMode.value = resolvedMode

  const hasCustomYaml = Object.prototype.hasOwnProperty.call(options, 'initialYaml')
  const yamlSource = hasCustomYaml ? options.initialYaml : yamlContent.value
  formGeneratorInitialYaml.value = yamlSource || null

  if (Object.prototype.hasOwnProperty.call(options, 'initialFormData')) {
    formGeneratorInitialFormData.value = options.initialFormData || null
  } else {
    formGeneratorInitialFormData.value = null
  }

  formGeneratorFieldFilter.value = options.fieldFilter ?? []
  formGeneratorReadOnlyFields.value = options.readOnlyFields ?? []
  formGeneratorNodeOrder.value = (yamlContent.value?.graph?.nodes || []).map((node) => node?.id)

  showDynamicFormGenerator.value = true
}

const closeDynamicFormGenerator = () => {
  showDynamicFormGenerator.value = false
  formGeneratorBreadcrumbs.value = []
  formGeneratorInitialYaml.value = null
  formGeneratorInitialFormData.value = null
  formGeneratorMode.value = 'create'
  formGeneratorFieldFilter.value = null
  formGeneratorReadOnlyFields.value = []
}

const handleFormGeneratorSubmit = async (payload) => {
  try {
    const previousNodeId = formGeneratorInitialFormData.value?.id
    const nextNodeId = payload?.rawFormData?.id

    //Update VueFlow node ID based on updated YAML if change present
    if (previousNodeId && nextNodeId && previousNodeId !== nextNodeId) {
      updateVueFlowNodeId(previousNodeId, nextNodeId)
    }

    await loadYamlFile()
    syncVueNodesAndEdgesData()
    // Ensure VueFlow internal state is updated from v-model bindings
    // before taking a snapshot to be saved into vuegraphs.db
    await nextTick()

    // If we opened the FormGenerator from a right-click context menu while creating
    // a new node, place that node at the stored position.
    if (formGeneratorMode.value === 'create' && pendingNodePosition.value && nextNodeId) {
      const newNode = (nodes.value || []).find(node => node.id === nextNodeId)
      if (newNode) {
        newNode.position = {
          x: pendingNodePosition.value.x,
          y: pendingNodePosition.value.y
        }
      }
      pendingNodePosition.value = null
    }

    // Auto-connect start node to new node
    if (formGeneratorMode.value === 'create' && nextNodeId) {
      await autoAddStartEdge(nextNodeId)
    }

    await saveVueFlowGraph()
  } catch (error) {
    console.error('Error refreshing workflow after dynamic form submission:', error)
  } finally {
    closeDynamicFormGenerator()
  }
}

const handleFormGeneratorCopy = (payload) => {
  try {
    const copied = payload?.initialFormData ? cloneDeep(payload.initialFormData) : null
    if (copied && typeof copied === 'object') {
      copied.id = ''
    }

    // @close of original modal calls closeDynamicFormGenerator()
    // Defer new "create node" modal to the next tick to avoid being closed
    setTimeout(() => {
      openDynamicFormGenerator('node', {
        mode: 'create',
        initialFormData: copied
      })
    }, 0)
  } catch (error) {
    console.error('Error copying node:', error)
  }
}

const openNodeEditor = (nodeId) => {
  if (!nodeId) {
    return
  }
  const yamlNodeContent = (yamlContent.value?.graph?.nodes || []).find(node => node.id === nodeId)
  if (!yamlNodeContent) {
    console.warn(`[WorkflowView] Node with id "${nodeId}" not found for editing`)
    return
  }
  // Pass YAML without specific node to the FormGenerator to "recreate" the node
  const sanitizedYaml = buildYamlWithoutNode(nodeId)
  openDynamicFormGenerator('node', {
    initialYaml: sanitizedYaml,
    initialFormData: yamlNodeContent,
    mode: 'edit'
  })
}

const openEdgeEditor = (fromId, toId, fallbackData = null) => {
  if (!fromId || !toId) {
    return
  }
  const yamlEdge = (yamlContent.value?.graph?.edges || []).find(edge => edge.from === fromId && edge.to === toId)
  const edgeData = yamlEdge || (fallbackData ? cloneDeep(fallbackData) : null)
  if (!edgeData) {
    console.warn(`[WorkflowView] Edge "${fromId}-${toId}" not found for editing`)
    return
  }
  const sanitizedYaml = buildYamlWithoutEdge(fromId, toId)
  openDynamicFormGenerator('edge', {
    initialYaml: sanitizedYaml,
    initialFormData: edgeData,
    mode: 'edit'
  })
}

// Create Node functions
const openCreateNodeModal = () => {
  // Set position to center of graph when creating from 'Create Node'
  pendingNodePosition.value = getCentralPosition()
  openDynamicFormGenerator('node', { mode: 'create' })
}

const openManageVarsModal = () => {
  const currentVars = yamlContent.value?.vars || null
  const sanitizedYaml = buildYamlWithoutVars()
  openDynamicFormGenerator('vars', {
    recursive: false,
    initialYaml: sanitizedYaml,
    initialFormData: currentVars ? { vars: currentVars } : null,
    mode: currentVars ? 'edit' : 'create',
    fieldFilter: ['vars']
  })
}

const openManageMemoriesModal = () => {
  const currentMemories = yamlContent.value?.graph?.memory || null
  const sanitizedYaml = buildYamlWithoutMemory()
  openDynamicFormGenerator('memory', {
    initialYaml: sanitizedYaml,
    initialFormData: currentMemories ? { memory: currentMemories } : null,
    mode: currentMemories ? 'edit' : 'create',
    fieldFilter: ['memory']
  })
}

const openConfigureGraphModal = () => {
  const currentGraph = yamlContent.value?.graph || null
  const sanitizedYaml = buildYamlWithoutGraph()
  openDynamicFormGenerator('graph', {
    recursive: false,
    initialYaml: sanitizedYaml,
    initialFormData: currentGraph,
    mode: currentGraph ? 'edit' : 'create',
    fieldFilter: null,
    readOnlyFields: ['id']
  })
}

const onNodeClick = (event) => {
  if (isCreatingConnection.value) {
    return
  }
  const clickedNode = event?.node || event
  if (!clickedNode?.id) {
    return
  }

  // Ignore left click for start node but show dim animation
  if (clickedNode.id === START_NODE_ID) {
    dimStartNode()
    return
  }

  openNodeEditor(clickedNode.id)
}

const onEdgeClick = (event) => {
  const clickedEdge = event?.edge || event
  if (!clickedEdge?.id || clickedEdge.data?.virtual) {
    return
  }

  const fromId = clickedEdge.data?.from || clickedEdge.source || ''
  const toId = clickedEdge.data?.to || clickedEdge.target || ''

  // Ignore start node edge
  if (fromId === START_NODE_ID || toId === START_NODE_ID) {
    return
  }
  if (!fromId || !toId) {
    return
  }

  const fallbackData = {
    from: fromId,
    to: toId
  }

  if (clickedEdge.data?.condition !== undefined) {
    fallbackData.condition = clickedEdge.data.condition
  }

  if (clickedEdge.data?.trigger !== undefined) {
    fallbackData.trigger = clickedEdge.data.trigger
  }

  openEdgeEditor(fromId, toId, fallbackData)
}

// Autosave when moving nodes
const onNodeDragStop = () => {
  saveVueFlowGraph()
}

const onConnect = async (connection) => {
  if (!connection?.source || !connection?.target) {
    return
  }

  // Set flag to avoid opening node edit modal
  isCreatingConnection.value = true

  // Special handling for StartNode connections
  if (connection.source === START_NODE_ID) {
    // Add target node to graph.start array instead of opening FormGenerator
    const source = yamlContent.value
    if (!source?.graph) {
      setTimeout(() => {
        isCreatingConnection.value = false
      }, 10)
      return
    }
    const sourceGraph = source.graph

    // Ensure graph.start exists as an array
    const currentStart = Array.isArray(sourceGraph.start) ? sourceGraph.start : []

    // Add target node to start array if not already present
    if (!currentStart.includes(connection.target)) {
      const nextSnapshot = {
        ...source,
        graph: {
          ...sourceGraph,
          start: [...currentStart, connection.target]
        }
      }

      // Persist the updated YAML
      const ok = await persistYamlSnapshot(nextSnapshot)
      if (ok) {
        await loadYamlFile()
        syncVueNodesAndEdgesData()
        await nextTick()
        await saveVueFlowGraph()
      }
    }

    setTimeout(() => {
      isCreatingConnection.value = false
    }, 10)
    return
  }

  // Do not open modal if edge already exists
  const yamlEdges = yamlContent.value?.graph?.edges || []
  const edgeAlreadyExistsInYaml = yamlEdges.some(
    e => e.from === connection.source && e.to === connection.target
  )
  const edgeAlreadyExistsInGraph = edges.value.some(
    e => e.source === connection.source && e.target === connection.target
  )
  if (edgeAlreadyExistsInYaml || edgeAlreadyExistsInGraph) {
    setTimeout(() => {
      isCreatingConnection.value = false
    }, 10)
    return
  }

  // Remove the automatically created edge (VueFlow may optimistically add one)
  const autoCreatedEdgeIndex = edges.value.findIndex(
    edge => edge.source === connection.source && edge.target === connection.target
  )
  if (autoCreatedEdgeIndex !== -1) {
    edges.value.splice(autoCreatedEdgeIndex, 1)
  }

  openDynamicFormGenerator('edge', {
    initialFormData: {
      from: connection.source,
      to: connection.target,
      condition: {
        type: 'function',
        config: {
          name: 'true'
        }
      },
      trigger: true
    },
    mode: 'create'
  })

  // Reset flag after a short delay so click handlers stay disabled
  setTimeout(() => {
    isCreatingConnection.value = false
  }, 100)
}

// Create Edge functions
const openCreateEdgeModal = () => {
  openDynamicFormGenerator('edge', { mode: 'create' })
}

const goToLaunch = () => {
  if (!currentWorkflowName.value) {
    return
  }
  const fileName = currentWorkflowName.value.endsWith('.yaml')
    ? currentWorkflowName.value
    : `${currentWorkflowName.value}.yaml`

  const resolved = router.resolve({
    path: '/launch',
    query: { workflow: fileName }
  })

  window.open(resolved.href, '_blank', 'noopener')
}

// "Thử trong Lab": every graph edit is written to the YAML immediately (persistYamlSnapshot), so the
// file the Lab loads is current; flush the canvas layout too, then open the Lab on this workflow.
const labNavigating = ref(false)
const goToLab = async () => {
  if (!currentWorkflowName.value || labNavigating.value) return
  const fileName = currentWorkflowName.value.endsWith('.yaml')
    ? currentWorkflowName.value
    : `${currentWorkflowName.value}.yaml`
  labNavigating.value = true
  try {
    try {
      await saveVueFlowGraph()
    } catch (error) {
      console.warn('Could not save the canvas layout before opening the Lab:', error)
    }
    router.push({ path: '/lab', query: { workflow: fileName } })
  } finally {
    labNavigating.value = false
  }
}

// Modal functions for rename and copy workflow
const openRenameWorkflowModal = () => {
  showMenu.value = false
  renameWorkflowName.value = currentWorkflowName.value.replace('.yaml', '')
  showRenameModal.value = true
}

const closeRenameModal = () => {
  showRenameModal.value = false
  renameWorkflowName.value = ''
}

const handleRenameSubmit = async () => {
  if (!renameWorkflowName.value.trim()) {
    return
  }

  const newName = renameWorkflowName.value.trim()
  const result = await postYamlNameChange(currentWorkflowName.value, newName)

  if (result.success) {
    // Handle VueGraph rename
    const oldWorkflowKey = currentWorkflowName.value.replace('.yaml', '')
    const newWorkflowKey = newName

    // Save VueGraph into new workflow
    try {
      const oldVueGraphResult = await fetchVueGraph(oldWorkflowKey)
      if (oldVueGraphResult.success && oldVueGraphResult.content) {
        const saveResult = await postVuegraphs({
          filename: newWorkflowKey,
          content: oldVueGraphResult.content
        })
        if (!saveResult.success) {
          console.warn('Failed to rename VueGraph:', saveResult.message)
        }
      }
    } catch (error) {
      console.warn('Error handling VueGraph rename:', error)
    }

    toast.success(t('workflow_view.rename_success', { name: newName }))
    closeRenameModal()

    // Refresh workflow list first
    emit('refresh-workflows')

    // Small delay to allow workflow list to refresh before navigating
    await new Promise(resolve => setTimeout(resolve, 500))

    // Navigate to the renamed workflow
    const newWorkflowName = result.filename || `${newName}.yaml`
    const workflowNameWithoutExtension = newWorkflowName.replace('.yaml', '')
    router.push({ path: `/workflows/${workflowNameWithoutExtension}` })
  } else {
    toast.error(withErrorDetail(t('workflow_view.rename_failed'), result))
  }
}

const openCopyWorkflowModal = () => {
  showMenu.value = false
  copyWorkflowName.value = currentWorkflowName.value.replace('.yaml', '') + '_copy'
  showCopyModal.value = true
}

const closeCopyModal = () => {
  showCopyModal.value = false
  copyWorkflowName.value = ''
}

const handleCopySubmit = async () => {
  if (!copyWorkflowName.value.trim()) {
    return
  }

  const newName = copyWorkflowName.value.trim()
  const result = await postYamlCopy(currentWorkflowName.value, newName)

  if (result.success) {
    // Handle VueGraph copy
    const sourceWorkflowKey = currentWorkflowName.value.replace('.yaml', '')
    const targetWorkflowKey = newName

    try {
      // Load the VueGraph for the source workflow
      const sourceVueGraphResult = await fetchVueGraph(sourceWorkflowKey)
      if (sourceVueGraphResult.success && sourceVueGraphResult.content) {
        // Save the VueGraph with the new workflow name
        const saveResult = await postVuegraphs({
          filename: targetWorkflowKey,
          content: sourceVueGraphResult.content
        })
        if (!saveResult.success) {
          console.warn('Failed to copy VueGraph:', saveResult.message)
        }
      }
    } catch (error) {
      console.warn('Error handling VueGraph copy:', error)
    }

    toast.success(t('workflow_view.copy_success', { name: newName }))
    closeCopyModal()

    // Refresh workflow list first
    emit('refresh-workflows')

    // Small delay to allow workflow list to refresh before navigating
    await new Promise(resolve => setTimeout(resolve, 500))

    // Navigate to the copied workflow
    const newWorkflowName = result.filename || `${newName}.yaml`
      const workflowNameWithoutExtension = newWorkflowName.replace('.yaml', '')
    router.push({ path: `/workflows/${workflowNameWithoutExtension}` })
  } else {
    toast.error(withErrorDetail(t('workflow_view.copy_failed'), result))
  }
}
</script>

<style scoped>
.workflow-view {
  width: 100%;
  height: calc(100vh - 55px);
  display: flex;
  flex-direction: column;
  background-color: var(--bg-base);
  color: var(--text-1);
  font-family: 'Inter', sans-serif;
  position: relative;
  overflow: hidden;
}

.workflow-bg {
  position: fixed;
  top: -150px;
  left: 0;
  right: 0;
  height: 500px;
  /* Pre-softened radial glows instead of filter: blur(120px) on a large layer,
     which is very expensive to rasterise and composite. */
  background:
    radial-gradient(ellipse 40% 70% at 18% 45%, var(--accent-mint), transparent 72%),
    radial-gradient(ellipse 40% 70% at 50% 45%, var(--accent-sky), transparent 72%),
    radial-gradient(ellipse 40% 70% at 82% 45%, var(--accent-indigo), transparent 72%);
  opacity: 0.15;
  z-index: 0;
  pointer-events: none;
}

.content {
  position: relative;
  z-index: 1;
}

.header,
.tabs {
  position: relative;
  z-index: 2;
}

.header {
  display: flex;
  align-items: center;
  padding: 0 20px;
  height: 40px;
  background-color: rgb(var(--ink) / 0.05);
  border-bottom: 1px solid rgb(var(--ink) / 0.1);
  flex-shrink: 0;
}

.back-button {
  padding: 8px;
  margin-right: 16px;
  background: transparent;
  color: rgb(var(--ink) / 0.6);
  cursor: pointer;
  transition: color 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  outline: none;
}

.back-button:hover {
  background: transparent;
  color: var(--text-1);
  border-color: transparent;
}

.back-button:focus,
.back-button:focus-visible {
  outline: none;
  border-color: transparent;
}

.workflow-name {
  color: var(--text-1);
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.tabs {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  height: 50px;
  background-color: rgb(var(--ink) / 0.02);
  border-top: 1px solid rgb(var(--ink) / 0.1);
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  z-index: 2;
}

.tab-buttons {
  display: flex;
  gap: 4px;
  height: 100%;
}

.tab {
  padding: 0 20px;
  height: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  font-family: 'Inter', sans-serif;
  color: var(--text-muted-4);
  font-weight: 500;
  transition: color 0.2s ease;
  position: relative;
}

.tab:hover {
  color: var(--text-1);
}

.tab.active {
  background: linear-gradient(
    135deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-weight: 500;
}

.editor-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  height: 100%;
}

/* Glass Button - Matching WorkflowList entries */
  .glass-button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: rgb(var(--ink) / 0.03);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  cursor: pointer;
  transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease;
  color: var(--text-1);
  font-size: 14px;
  position: relative;
  z-index: 1;
}

.launch-button-primary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.3s ease, box-shadow 0.3s ease, opacity 0.3s ease;
  color: var(--bg-base);
  font-size: 14px;
  font-weight: 600;
  /* Opaque gradient: no backdrop-filter needed (it only cost a blur per frame) */
  background: linear-gradient(
    135deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  position: relative;
  isolation: isolate;
  z-index: 1;
}

/* Gradient shimmer as an opacity cross-fade (compositor) instead of an
   animated background-position (repaint every frame) */
.launch-button-primary::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  z-index: -1;
  pointer-events: none;
  background: linear-gradient(135deg, var(--accent-sky), var(--accent-indigo));
  opacity: 0;
  animation: gradientFade 6s ease-in-out infinite;
  will-change: opacity;
}

.launch-button-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.2);
  opacity: 0.9;
}

@keyframes gradientFade {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}

.glass-button:hover {
  background-color: rgb(var(--ink) / 0.05);
  border-color: rgb(var(--ink) / 0.05);
}

@keyframes gradientShift {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 100% 0%; }
}

.glass-button::before {
  content: '';
  position: absolute;
  inset: -2px;
  z-index: -1;
  border-radius: 14px;
  padding: 2px;
  background: linear-gradient(
    135deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  -webkit-mask: 
     linear-gradient(var(--text-1) 0 0) content-box, 
     linear-gradient(var(--text-1) 0 0);
  mask: 
     linear-gradient(var(--text-1) 0 0) content-box, 
     linear-gradient(var(--text-1) 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  opacity: 0;
  transition: opacity 0.3s ease;
  background-size: 200% 100%;
  animation: gradientShift 6s ease-in-out infinite;
  /* The blurred ring is invisible until hover; do not tick its animation until then */
  animation-play-state: paused;
  filter: blur(4px);
}

.glass-button:hover::before {
  opacity: 1;
  animation-play-state: running;
}

@media (prefers-reduced-motion: reduce) {
  .launch-button-primary::before,
  .glass-button::before {
    animation: none;
    will-change: auto;
  }

  .launch-button-primary,
  .glass-button,
  .submit-button {
    transition: none;
  }

  .launch-button-primary:hover,
  .submit-button:hover:not(:disabled) {
    transform: none;
  }
}

.btn-icon {
  font-size: 16px;
}

/* Menu Dropdown */
.menu-container {
  position: relative;
  z-index: 3;
  height: 100%;
}

.menu-trigger {
  padding: 0;
  border: 0;
  background: transparent;
  font: inherit;
  width: 40px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
  color: rgb(var(--ink) / 0.7);
}

.menu-dropdown {
  position: absolute;
  bottom: 100%;
  right: 0;
  background: rgb(var(--panel-60) / 0.99);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  padding: 8px;
  min-width: 180px;
  box-shadow: 0 10px 30px rgb(var(--shade) / 0.5);
  z-index: 3;
}

.menu-item {
  padding: 10px 16px;
  color: rgb(var(--ink) / 0.8);
  font-size: 14px;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.menu-item:hover {
  background-color: rgb(var(--ink) / 0.1);
  color: var(--text-1);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.content {
  flex: 1;
  overflow: hidden;
  position: relative;
  min-height: 0;
}

.yaml-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.yaml-error {
  padding: 12px 20px;
  background-color: rgba(255, 68, 68, 0.1);
  border-bottom: 1px solid rgba(255, 68, 68, 0.3);
  color: var(--danger-3);
  font-size: 14px;
  margin: 0;
}

.yaml-textarea {
  flex: 1;
  padding: 20px;
  border: none;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  outline: none;
  background: transparent;
  color: var(--text-soft-4);
}

.yaml-textarea::-webkit-scrollbar {
  display: none;
}

.yaml-error-border {
  border: 2px solid var(--danger-4) !important;
}

.vueflow-container {
  height: 100%;
  width: 100%;
  background-color: rgb(var(--ink) / 0.03);
  /* No backdrop-filter here: it re-blurred the full-screen canvas on every pan/zoom
     frame, and the only thing behind it is the already blur(120px) backdrop */
  z-index: 1;
  position: relative;
}

.vueflow-graph {
  width: 100%;
  height: 100%;
}

.context-menu {
  position: absolute;
  min-width: 160px;
  background: rgb(var(--panel-40) / 0.98);
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 10px 30px rgb(var(--shade) / 0.6);
  border: 1px solid rgb(var(--ink) / 0.1);
  z-index: 5;
}

.context-menu-item {
  padding: 8px 12px;
  color: rgb(var(--ink) / 0.85);
  font-size: 13px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.context-menu-item:hover {
  background-color: rgb(var(--ink) / 0.1);
  color: var(--text-1);
}

/* Modal Styles - Matching FormGenerator modal-content */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgb(var(--shade) / 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  display: flex;
  flex-direction: column;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  background-color: rgb(var(--panel-33) / 0.98);
  border-radius: 16px;
  border: 1px solid rgb(var(--ink) / 0.08);
  box-shadow: 0 20px 40px rgb(var(--shade) / 0.6);
  overflow: hidden;
}

.modal-header {
  flex-shrink: 0;
  height: 28px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background-color: transparent;
  border-bottom: 1px solid rgb(var(--ink) / 0.04);
}

.modal-title {
  color: var(--text-1);
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  flex: 1;
}

.close-button {
  margin-left: auto;
  background: transparent;
  border: none;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: rgb(var(--ink) / 0.6);
  transition: color 0.2s ease;
}

.close-button:hover {
  color: var(--text-1);
}

.modal-body {
  flex: 1;
  padding: 20px;
  max-height: none;
  overflow-y: auto;
  border-top: 1px solid rgb(var(--ink) / 0.04);
  border-bottom: 1px solid rgb(var(--ink) / 0.04);
  scrollbar-width: none;
}

.modal-body::-webkit-scrollbar {
  display: none;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  color: var(--text-1);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
}

.duplicate-many-help {
  margin: 8px 0 0;
  color: var(--text-2, rgb(var(--ink) / 0.65));
  font-size: 12px;
  line-height: 1.45;
}

.form-input {
  width: 90%;
  padding: 12px 16px;
  background-color: rgb(var(--ink) / 0.05);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 8px;
  color: var(--text-1);
  font-size: 14px;
  font-family: 'Inter', sans-serif;
  outline: none;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.form-input:focus {
  border-color: rgb(var(--accent-mint-rgb) / 0.5);
  background-color: rgb(var(--ink) / 0.08);
}

.form-input::placeholder {
  color: rgb(var(--ink) / 0.4);
}

.modal-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  background-color: transparent;
  border-top: 1px solid rgb(var(--ink) / 0.04);
}

.cancel-button,
.submit-button {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  font-family: 'Inter', sans-serif;
}

.cancel-button {
  background-color: transparent;
  border: 1px solid rgb(var(--ink) / 0.1);
  color: rgb(var(--ink) / 0.7);
}

.cancel-button:hover {
  background-color: rgb(var(--ink) / 0.05);
  border-color: rgb(var(--ink) / 0.2);
  color: var(--text-1);
}

.submit-button {
  background: linear-gradient(135deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo));
  border: none;
  color: var(--bg-base);
  font-weight: 600;
}

.submit-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgb(var(--shade) / 0.2);
}

.submit-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* ---------- Light theme: legible text and visible edges on white ---------- */
/* Inactive tabs: #64748b sat at ~4.4:1 on the tinted bar */
:root[data-theme="light"] .tab {
  color: var(--text-soft-1);
}

:root[data-theme="light"] .tab:hover {
  color: var(--text-1);
}

/* Active tab gradient text: the mint stop (#0f9d7a) is only ~3.4:1 on white */
:root[data-theme="light"] .tab.active {
  background: linear-gradient(135deg, #047857, #0369a1, #4338ca);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* Primary buttons: near-white text on the mint stop was ~3.3:1; use darker stops */
:root[data-theme="light"] .launch-button-primary,
:root[data-theme="light"] .submit-button {
  background: linear-gradient(135deg, #047857, #0369a1, #4338ca);
  color: #fff;
}

:root[data-theme="light"] .launch-button-primary::before {
  background: linear-gradient(135deg, #0369a1, #4338ca);
}

:root[data-theme="light"] .glass-button,
:root[data-theme="light"] .glass-button:hover,
:root[data-theme="light"] .cancel-button {
  border-color: rgb(var(--ink) / 0.18);
}

:root[data-theme="light"] .cancel-button:hover {
  border-color: rgb(var(--ink) / 0.28);
}

:root[data-theme="light"] .form-input {
  border-color: rgb(var(--ink) / 0.2);
}

:root[data-theme="light"] .form-input:focus {
  border-color: rgb(var(--accent-mint-rgb) / 0.7);
}

:root[data-theme="light"] .form-input::placeholder {
  color: rgb(var(--ink) / 0.55);
}

:root[data-theme="light"] .yaml-error {
  color: var(--danger-soft);
}
</style>
