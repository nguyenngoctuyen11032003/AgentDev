/**
 * Carry a saved Vue Flow layout over to an edited workflow graph.
 *
 * Nodes that are still in the graph keep their position, removed nodes leave the layout, and each
 * new node is placed next to a node it is connected to (or below the lowest node when it has no
 * placed neighbour). Edges are not added here: the editor rebuilds YAML edges from the file.
 */

// Visual-only entry node drawn by WorkflowView (never in the YAML graph)
const START_NODE_ID = '__start'

const NEIGHBOUR_OFFSET = { x: 260, y: 0 }
const BELOW_OFFSET = { x: 0, y: 160 }
const EMPTY_ORIGIN = { x: 50, y: 50 }
const OVERLAP_DISTANCE = 40

const isPosition = (pos) => Number.isFinite(pos?.x) && Number.isFinite(pos?.y)

const overlaps = (pos, placed) =>
  [...placed.values()].some(
    (other) => Math.abs(other.x - pos.x) < OVERLAP_DISTANCE && Math.abs(other.y - pos.y) < OVERLAP_DISTANCE
  )

// Step down until the spot is free, so siblings added next to the same node do not stack.
const freeSpot = (pos, placed) => {
  const spot = { ...pos }
  while (overlaps(spot, placed)) spot.y += BELOW_OFFSET.y
  return spot
}

const neighbourPosition = (id, edges, placed) => {
  for (const edge of edges) {
    const other = edge?.to === id ? edge?.from : edge?.from === id ? edge?.to : null
    if (other && other !== id && placed.has(other)) {
      const base = placed.get(other)
      return { x: base.x + NEIGHBOUR_OFFSET.x, y: base.y + NEIGHBOUR_OFFSET.y }
    }
  }
  return null
}

const belowLowest = (placed) => {
  let lowest = null
  for (const pos of placed.values()) {
    if (!lowest || pos.y > lowest.y) lowest = pos
  }
  return lowest ? { x: lowest.x + BELOW_OFFSET.x, y: lowest.y + BELOW_OFFSET.y } : { ...EMPTY_ORIGIN }
}

/**
 * @param {object|null} flowJson - Saved Vue Flow object ({nodes, edges, ...}); null when none was saved.
 * @param {object} newGraph - The new workflow `graph` ({nodes: [{id}], edges: [{from, to}]}).
 * @param {object} diff - Backend diff_summary (uses `nodes_removed`).
 * @returns {object|null} The reconciled Vue Flow object, or null (the editor lays the graph out itself).
 */
export function reconcileLayout(flowJson, newGraph, diff) {
  if (!flowJson || typeof flowJson !== 'object') return null

  const graphNodes = (Array.isArray(newGraph?.nodes) ? newGraph.nodes : []).filter((n) => n?.id)
  const graphEdges = Array.isArray(newGraph?.edges) ? newGraph.edges : []
  const graphIds = new Set(graphNodes.map((n) => n.id))
  const removed = new Set(Array.isArray(diff?.nodes_removed) ? diff.nodes_removed : [])

  const keptNodes = (Array.isArray(flowJson.nodes) ? flowJson.nodes : []).filter(
    (node) => node?.id && !removed.has(node.id) && (graphIds.has(node.id) || node.id === START_NODE_ID)
  )

  // Positions of the nodes already on the canvas; the start node is not a graph neighbour.
  const placed = new Map()
  for (const node of keptNodes) {
    if (node.id !== START_NODE_ID && isPosition(node.position)) placed.set(node.id, { ...node.position })
  }

  const keptIds = new Set(keptNodes.map((n) => n.id))
  const pending = graphNodes.filter((n) => !keptIds.has(n.id))
  const addedNodes = []
  while (pending.length) {
    // Prefer a node that touches something already placed; otherwise drop the first one below the rest.
    let index = pending.findIndex((n) => neighbourPosition(n.id, graphEdges, placed))
    let target
    if (index === -1) {
      index = 0
      target = belowLowest(placed)
    } else {
      target = neighbourPosition(pending[index].id, graphEdges, placed)
    }
    const [yamlNode] = pending.splice(index, 1)
    const position = freeSpot(target, placed)
    placed.set(yamlNode.id, position)
    addedNodes.push({ id: yamlNode.id, type: 'workflow-node', label: yamlNode.id, position, data: yamlNode })
  }

  const nodeIds = new Set([...keptIds, ...addedNodes.map((n) => n.id)])
  const graphEdgeKeys = new Set(graphEdges.map((e) => `${e?.from}-${e?.to}`))
  const edges = (Array.isArray(flowJson.edges) ? flowJson.edges : []).filter((edge) => {
    if (!nodeIds.has(edge?.source) || !nodeIds.has(edge?.target)) return false
    // Start and team links are drawn by the editor, not stored in the YAML graph.
    if (edge.source === START_NODE_ID || edge.data?.virtual) return true
    return graphEdgeKeys.has(`${edge.source}-${edge.target}`)
  })

  return { ...flowJson, nodes: [...keptNodes, ...addedNodes], edges }
}
