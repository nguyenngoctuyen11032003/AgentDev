// "Duplicate node" for team building: "Backend Developer" -> "Backend Developer 2", "... 3", ...
// The copy keeps the whole configuration (role, model, account, skills, tools), gets the next free
// numbered ID, and joins every team whose explicit member list contains the original, right after
// the original and its earlier copies, so the lead's roster stays grouped.

const NUMBERED = /^(.*\S)\s+(\d+)$/

/** Next free "<base> <n>" ID for a copy of `id` (n starts at 2, or after the number `id` already has). */
export function nextDuplicateId(id, existingIds) {
  const taken = new Set(existingIds)
  const match = NUMBERED.exec(String(id))
  const base = match ? match[1] : String(id)
  let n = match ? Number(match[2]) + 1 : 2
  while (taken.has(`${base} ${n}`)) n += 1
  return `${base} ${n}`
}

const baseOf = (id) => {
  const match = NUMBERED.exec(String(id))
  return match ? match[1] : String(id)
}

const clone = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)))

/**
 * Returns { graph, newId, leads } where `graph` is a new graph object with the copy added after the
 * original, and `leads` lists the team leads the copy was added to. Returns null if `nodeId` is unknown.
 */
export function duplicateNodeInGraph(graph, nodeId) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const index = nodes.findIndex((node) => node?.id === nodeId)
  if (index < 0) return null

  const newId = nextDuplicateId(nodeId, nodes.map((node) => node?.id).filter(Boolean))
  const copy = clone(nodes[index])
  copy.id = newId
  // Let the copy get its own character instead of a twin of the original.
  delete copy.mascot

  const group = baseOf(nodeId)
  const leads = []
  const nextNodes = nodes.map((node) => {
    const members = node?.config?.team?.members
    if (node?.type !== 'agent' || !Array.isArray(members) || !members.includes(nodeId)) return node
    let insertAt = members.length
    for (let i = members.length - 1; i >= 0; i -= 1) {
      if (baseOf(members[i]) === group) {
        insertAt = i + 1
        break
      }
    }
    const nextMembers = [...members.slice(0, insertAt), newId, ...members.slice(insertAt)]
    leads.push(node.id)
    return { ...node, config: { ...node.config, team: { ...node.config.team, members: nextMembers } } }
  })

  // Place the copy after the original and its earlier copies.
  let insertNode = index + 1
  while (insertNode < nextNodes.length && baseOf(nextNodes[insertNode]?.id) === group) insertNode += 1
  nextNodes.splice(insertNode, 0, copy)

  return { graph: { ...graph, nodes: nextNodes }, newId, leads }
}
