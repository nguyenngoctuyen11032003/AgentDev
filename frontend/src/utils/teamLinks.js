// Who delegates to whom in a "team lead" workflow. Mirrors the backend resolve_members():
// a lead is an agent node with config.team.enabled; its members are config.team.members, or,
// when that list is empty, every agent node that has no edges at all.
// The links are derived, never written to the YAML and never executed as graph edges.

export function computeTeamLinks(nodes, edges) {
  const connected = new Set()
  for (const e of Array.isArray(edges) ? edges : []) {
    const from = e?.from ?? e?.source
    const to = e?.to ?? e?.target
    if (from) connected.add(from)
    if (to) connected.add(to)
  }
  const list = (Array.isArray(nodes) ? nodes : []).filter((n) => n?.id)
  const byId = new Map(list.map((n) => [n.id, n]))
  const links = []
  for (const lead of list) {
    if (lead.type !== 'agent' || lead.config?.team?.enabled !== true) continue
    const listed = Array.isArray(lead.config.team.members) ? lead.config.team.members : []
    const memberIds = listed.length
      ? listed
      : list.filter((n) => n.type === 'agent' && !connected.has(n.id)).map((n) => n.id)
    for (const memberId of memberIds) {
      if (memberId === lead.id || byId.get(memberId)?.type !== 'agent') continue
      links.push({ from: lead.id, to: memberId })
    }
  }
  return links
}

/**
 * Left-to-right tidy tree for a set of team links: one column per level, leaves stacked
 * evenly, every lead vertically centred on its members. Returns Map id -> {x, y}.
 * Only people that appear in a link are placed; everyone else is left to the caller.
 */
export function layoutOrgTree(links, { originX = 50, originY = 50, gapX = 330, gapY = 150 } = {}) {
  const children = new Map()
  const parentOf = new Map()
  const order = []
  const touch = (id) => {
    if (!children.has(id)) {
      children.set(id, [])
      order.push(id)
    }
  }
  for (const { from, to } of links) {
    touch(from)
    touch(to)
    if (parentOf.has(to) || from === to) continue // first lead wins: the chart stays a tree
    parentOf.set(to, from)
    children.get(from).push(to)
  }
  const positions = new Map()
  let nextRow = 0
  const place = (id, depth, seen) => {
    seen.add(id)
    const kids = (children.get(id) || []).filter((kid) => !seen.has(kid))
    let y
    if (!kids.length) {
      y = originY + nextRow * gapY
      nextRow += 1
    } else {
      const ys = kids.map((kid) => place(kid, depth + 1, seen))
      y = (ys[0] + ys[ys.length - 1]) / 2
    }
    positions.set(id, { x: originX + depth * gapX, y })
    return y
  }
  const seen = new Set()
  for (const id of order) if (!parentOf.has(id) && !seen.has(id)) place(id, 0, seen)
  return positions
}

/**
 * Org chart of a graph: id -> { parent, depth, members }. The first lead that lists a person
 * is their "reports to"; people nobody delegates to are roots (depth 0).
 */
export function buildOrgChart(graph) {
  const links = computeTeamLinks(graph?.nodes, graph?.edges)
  const chart = new Map()
  const entry = (id) => {
    if (!chart.has(id)) chart.set(id, { parent: '', depth: 0, members: [] })
    return chart.get(id)
  }
  for (const link of links) {
    const member = entry(link.to)
    entry(link.from).members.push(link.to)
    if (!member.parent) member.parent = link.from
  }
  const depthOf = (id, seen = new Set()) => {
    const item = chart.get(id)
    if (!item?.parent || seen.has(id)) return 0
    seen.add(id)
    return depthOf(item.parent, seen) + 1
  }
  for (const id of chart.keys()) chart.get(id).depth = depthOf(id)
  return chart
}
