<template>
  <div ref="rootRef" class="graph-preview" role="img" :aria-label="ariaLabel">
    <VueFlow
      :id="flowId"
      :nodes="flowNodes"
      :edges="flowEdges"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :elements-selectable="false"
      :edges-updatable="false"
      :zoom-on-scroll="false"
      :zoom-on-double-click="false"
      :prevent-scrolling="false"
      :delete-key-code="null"
      :min-zoom="0.2"
      :max-zoom="1.5"
      fit-view-on-init
      class="graph-preview-flow"
    >
      <template #node-workflow-node="nodeProps">
        <WorkflowNode :id="nodeProps.id" :data="nodeProps.data" :team="orgChart.get(nodeProps.id) || null" />
      </template>
      <template #node-removed-node="nodeProps">
        <div class="removed-node" :title="$t('workflow_assistant.preview.removed_node', { id: nodeProps.id })">
          <span class="removed-node-tag">{{ $t('workflow_assistant.preview.removed') }}</span>
          <span class="removed-node-id">{{ nodeProps.id }}</span>
        </div>
      </template>
      <template #edge-workflow-edge="edgeProps">
        <WorkflowEdge
          :id="edgeProps.id"
          :source="edgeProps.source"
          :target="edgeProps.target"
          :source-x="edgeProps.sourceX"
          :source-y="edgeProps.sourceY"
          :target-x="edgeProps.targetX"
          :target-y="edgeProps.targetY"
          :source-position="edgeProps.sourcePosition"
          :target-position="edgeProps.targetPosition"
          :data="edgeProps.data"
          :marker-end="edgeProps.markerEnd"
        />
      </template>
    </VueFlow>
  </div>
</template>

<script setup>
// Read-only picture of a proposed workflow graph. Nodes are laid out in layers: a BFS from
// graph.start along YAML edges and lead -> member team links, one column per depth.
// With a diff, new / changed nodes are tinted and removed nodes are drawn faded and struck out.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueFlow, MarkerType, useVueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@/assets/styles/vueflow.css'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'
import WorkflowEdge from '@/components/workflow/WorkflowEdge.vue'
import { buildOrgChart, computeTeamLinks } from '@/utils/teamLinks.js'

const props = defineProps({
  graph: { type: Object, required: true },
  diff: { type: Object, default: null }
})

const { t } = useI18n()

const GAP_X = 260
// Agent cards with a description and team chips are ~120px tall.
const GAP_Y = 190

// Every preview needs its own Vue Flow store, apart from the canvas and from other cards.
const flowId = `assistant-preview-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

const rootRef = ref(null)
const { fitView } = useVueFlow(flowId)

// Refit when the box changes size (panel dragged wider, window resized, narrow layout).
let resizeObserver = null
let frame = 0
onMounted(() => {
  if (typeof ResizeObserver !== 'function' || !rootRef.value) return
  resizeObserver = new ResizeObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => fitView())
  })
  resizeObserver.observe(rootRef.value)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  resizeObserver?.disconnect()
})

const yamlNodes = computed(() => (Array.isArray(props.graph?.nodes) ? props.graph.nodes : []).filter((n) => n?.id))
const yamlEdges = computed(() =>
  (Array.isArray(props.graph?.edges) ? props.graph.edges : []).filter((e) => e?.from && e?.to)
)
const teamLinks = computed(() => computeTeamLinks(yamlNodes.value, yamlEdges.value))
const orgChart = computed(() => buildOrgChart({ nodes: yamlNodes.value, edges: yamlEdges.value }))

const added = computed(() => new Set(props.diff?.nodes_added || []))
const changed = computed(() => new Set((props.diff?.nodes_changed || []).map((item) => item?.id)))
const ids = computed(() => new Set(yamlNodes.value.map((n) => n.id)))
const removed = computed(() => (props.diff?.nodes_removed || []).filter((id) => !ids.value.has(id)))

// id -> depth. Nodes no start reaches become extra roots, in file order.
const depths = computed(() => {
  const next = new Map()
  const link = (from, to) => {
    if (!next.has(from)) next.set(from, [])
    next.get(from).push(to)
  }
  for (const e of yamlEdges.value) link(e.from, e.to)
  for (const l of teamLinks.value) link(l.from, l.to)

  const depth = new Map()
  const walk = (roots) => {
    const queue = roots.filter((id) => ids.value.has(id) && !depth.has(id))
    for (const id of queue) depth.set(id, 0)
    while (queue.length) {
      const id = queue.shift()
      for (const to of next.get(id) || []) {
        if (!ids.value.has(to) || depth.has(to)) continue
        depth.set(to, depth.get(id) + 1)
        queue.push(to)
      }
    }
  }
  const start = Array.isArray(props.graph?.start) ? props.graph.start : props.graph?.start ? [props.graph.start] : []
  walk(start)
  for (const n of yamlNodes.value) walk([n.id])
  return depth
})

const statusClass = (id) => {
  if (added.value.has(id)) return 'added'
  if (changed.value.has(id)) return 'changed'
  return ''
}

const flowNodes = computed(() => {
  const rows = new Map()
  const placed = yamlNodes.value.map((node) => {
    const col = depths.value.get(node.id) ?? 0
    const row = rows.get(col) ?? 0
    rows.set(col, row + 1)
    return {
      id: node.id,
      type: 'workflow-node',
      label: node.id,
      position: { x: col * GAP_X, y: row * GAP_Y },
      data: node,
      class: statusClass(node.id)
    }
  })
  // Removed nodes have no place in the new graph: stack them in a column of their own.
  const lastCol = placed.length ? Math.max(...placed.map((n) => n.position.x / GAP_X)) + 1 : 0
  removed.value.forEach((id, row) => {
    placed.push({
      id,
      type: 'removed-node',
      label: id,
      position: { x: lastCol * GAP_X, y: row * GAP_Y },
      data: { id },
      class: 'removed'
    })
  })
  return placed
})

const marker = (color, size = 16) => ({ type: MarkerType.Arrow, width: size, height: size, color, strokeWidth: 1.5 })

const flowEdges = computed(() => {
  const seen = new Map()
  const edges = yamlEdges.value.map((edge) => {
    const pair = `${edge.from}-${edge.to}`
    const n = seen.get(pair) || 0
    seen.set(pair, n + 1)
    return {
      id: n ? `${pair}#${n}` : pair,
      source: edge.from,
      target: edge.to,
      type: 'workflow-edge',
      data: edge,
      markerEnd: marker(edge.trigger === false ? 'var(--text-muted-2)' : 'var(--text-1)')
    }
  })
  for (const l of teamLinks.value) {
    edges.push({
      id: `team:${l.from}->${l.to}`,
      source: l.from,
      target: l.to,
      type: 'workflow-edge',
      data: { virtual: true, kind: 'team', lead: l.from, member: l.to },
      markerEnd: marker('var(--text-muted-2)', 14)
    })
  }
  return edges
})

const ariaLabel = computed(() =>
  t('workflow_assistant.preview.aria', { nodes: yamlNodes.value.length, edges: yamlEdges.value.length })
)
</script>

<style scoped>
.graph-preview {
  height: 240px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.1);
  background: rgb(var(--ink) / 0.02);
  overflow: hidden;
}

.graph-preview-flow {
  width: 100%;
  height: 100%;
}

.graph-preview :deep(.vue-flow__node.added .workflow-node) {
  box-shadow: 0 0 0 2px var(--accent-green-1);
}

.graph-preview :deep(.vue-flow__node.changed .workflow-node) {
  box-shadow: 0 0 0 2px var(--warn-soft-1);
}

.removed-node {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 120px;
  max-width: 200px;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px dashed var(--danger);
  background: rgb(var(--ink) / 0.03);
  opacity: 0.6;
  color: var(--text-1);
  font-size: 12px;
}

.removed-node-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--danger);
}

.removed-node-id {
  text-decoration: line-through;
  word-break: break-word;
}
</style>
