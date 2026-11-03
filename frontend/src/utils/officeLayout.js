/**
 * Layout of the 2D tech-company office (public/office/office.png) and the rules that
 * staff it from a workflow. Map data (rooms, seats, obstacles) is generated together
 * with the image by scripts/office/draw-office.cjs into officeMap.json.
 * Coordinates are map units: 960x540, one unit = one sprite art pixel.
 */
import MAP from './officeMap.json'
import { computeTeamLinks } from './teamLinks.js'

export const OFFICE_WIDTH = MAP.width
export const OFFICE_HEIGHT = MAP.height
export const OFFICE_IMAGE = '/office/office.png'
export const ENTRANCE = MAP.entrance
export const OBSTACLES = MAP.obstacles

// Department identity colors, one hue per department (color follows the entity), stepped per
// theme. Validated with the dataviz validator (adjacent pairs, display order below):
//   light on #ffffff: band/chroma pass, CVD ΔE 12.2, normal-vision ΔE 22.1, all >= 3:1
//   dark  on #1e1e1e: band/chroma pass, CVD ΔE 12.7, normal-vision ΔE 18.2, all >= 3:1
// Eight hues cannot pass all-pairs, so every surface also names the department in text.
export const DEPARTMENT_HEX = {
  light: { mgmt: '#9f7100', eng: '#106dce', design: '#a61b86', qa: '#f4514f', rnd: '#703dc6', ops: '#109d7b', meeting: '#ab5200', lobby: '#1a93ab' },
  dark: { mgmt: '#b8892d', eng: '#2a80e2', design: '#bb3398', qa: '#f4514f', rnd: '#9e71fd', ops: '#29a987', meeting: '#e06d00', lobby: '#21a3bc' },
}
const DEPT_IDS = ['mgmt', 'eng', 'design', 'qa', 'rnd', 'ops', 'meeting', 'lobby']

// The colors are CSS custom properties so they follow the theme toggle without re-rendering.
// `.dept-scope-dark` pins the dark steps for surfaces that are always dark (the office scene).
const cssVars = (mode) => DEPT_IDS.map((id) => `--dept-${id}:${DEPARTMENT_HEX[mode][id]};`).join('')
if (typeof document !== 'undefined') {
  const css = `:root{${cssVars('dark')}}:root[data-theme="light"]{${cssVars('light')}}:root .dept-scope-dark{${cssVars('dark')}}`
  let el = document.getElementById('dept-palette')
  if (!el) {
    el = document.createElement('style')
    el.id = 'dept-palette'
    document.head.appendChild(el)
  }
  el.textContent = css
}

// Departments in display order; `color` is a CSS color usable in any style binding.
export const DEPARTMENTS = DEPT_IDS.map((id) => ({ id, color: `var(--dept-${id}, ${DEPARTMENT_HEX.dark[id]})` }))
export const DEPARTMENT_COLOR = Object.fromEntries(DEPARTMENTS.map((d) => [d.id, d.color]))

export const ROOMS = MAP.rooms
export const ROOM_BY_ID = Object.fromEntries(ROOMS.map((r) => [r.id, r]))

export const WORK_SEATS = MAP.seats.filter((s) => s.purpose === 'work')
export const HUMAN_SEATS = MAP.seats.filter((s) => s.purpose === 'human')
export const REST_SPOTS = MAP.seats.filter((s) => s.purpose === 'rest')
export const SEATS_BY_DEPT = WORK_SEATS.reduce((acc, s) => {
  (acc[s.dept] ||= []).push(s)
  return acc
}, {})

// Server racks in the ops room (for the blinking status lights overlay).
export const SERVER_RACKS = [[436, 448, 24, 60], [466, 448, 24, 60], [496, 448, 24, 60]]

// When a department is full, staff spill over to the closest related team.
const OVERFLOW = {
  mgmt: ['mgmt', 'meeting', 'eng', 'rnd'],
  eng: ['eng', 'rnd', 'ops', 'meeting', 'qa', 'design'],
  design: ['design', 'eng', 'meeting', 'rnd'],
  qa: ['qa', 'eng', 'rnd', 'meeting'],
  rnd: ['rnd', 'eng', 'meeting', 'qa'],
  ops: ['ops', 'meeting', 'rnd', 'design', 'eng', 'qa'],
  meeting: ['meeting', 'eng', 'rnd', 'ops'],
}
const ALL_DEPTS = ['eng', 'rnd', 'qa', 'ops', 'design', 'meeting', 'mgmt']

// Keyword rules, checked in order against the node id first, then its role prompt.
const RULES = [
  // Infrastructure people run the ops room (before "engineer" sends them to engineering)
  ['ops', /\b(devops|sre|site reliability|infra\w*|deploy\w*|ci ?cd|cloud|platform engineer|kubernetes|docker|release manager|sysadmin|operations)\b|vận hành|hạ tầng/i],
  ['mgmt', /\b(ceo|cto|cpo|coo|cfo|chief|manager|management|director|lead|leader|head|supervisor|coordinator|orchestrat\w*|planner|planning|product owner|product manager|project manager|pm|boss|founder)\b|quản lý|giám đốc|trưởng nhóm|điều phối/i],
  ['qa', /\b(qa|tester|test\w*|review\w*|critic\w*|verif\w*|validat\w*|bug\w*|debug\w*|fix\w*|judge|evaluat\w*|audit\w*|inspect\w*|quality)\b|kiểm thử|đánh giá/i],
  ['design', /\b(design\w*|ui|ux|artist|art|visual\w*|illustrat\w*|graphic\w*|creative|animat\w*|3d|blender|image\w*|draw\w*|paint\w*|writer|writing|editor|content|copy\w*|story\w*|script\w*|poem|poet|article|blog\w*|translat\w*)\b|thiết kế|sáng tạo|biên tập/i],
  ['rnd', /\b(research\w*|analy\w*|data|scien\w*|search\w*|study|insight\w*|math\w*|statistic\w*|ml|knowledge|memory|retriev\w*|summar\w*|report\w*)\b|nghiên cứu|phân tích|dữ liệu/i],
  ['eng', /\b(develop\w*|engineer\w*|code|coder|coding|program\w*|implement\w*|build\w*|executor|launcher|devops|backend|frontend|architect\w*|software|tech\w*)\b|lập trình|kỹ sư/i],
]

const OPS_TYPES = new Set(['python', 'literal', 'passthrough', 'loop_counter', 'loop_timer'])

const matchRules = (text) => {
  if (!text) return null
  for (const [dept, re] of RULES) if (re.test(text)) return dept
  return null
}

// A discipline lead ("Backend Lead", "QA Lead", "Design Lead") sits with the team they lead;
// only a lead of nothing in particular ("Team Lead", "CTO") belongs to management.
const LEAD_WORD = /\b(lead|leader|head|trưởng nhóm)\b/i
const disciplineOf = (id) => {
  if (!LEAD_WORD.test(id)) return null
  const rest = id.replace(new RegExp(LEAD_WORD.source, 'gi'), ' ').replace(/\bteam\b/gi, ' ').trim()
  const dept = matchRules(rest)
  return dept && dept !== 'mgmt' ? dept : null
}

/**
 * Department a workflow node works in.
 * Humans wait in the lobby, sub-workflows meet in the meeting room, plumbing nodes
 * (python, literal, passthrough, loop counters) run the ops room; agents are placed
 * by what their id and role prompt say they do.
 */
export function classifyNode(node) {
  if (!node) return 'eng'
  if (node.type === 'human') return 'lobby'
  if (node.type === 'subgraph') return 'meeting'
  if (OPS_TYPES.has(node.type)) return 'ops'
  if (node.type === 'memory') return 'rnd'
  const id = String(node.id || '').replace(/[_\d-]+/g, ' ')
  const role = String(node.config?.role || node.description || '').slice(0, 400)
  return disciplineOf(id) || matchRules(id) || matchRules(role) || 'eng'
}

/**
 * Assign every person a desk: their department first, then related teams, then any
 * free desk, and finally a standing spot in the corridor so nobody is ever left out.
 * @param {{id:string, dept:string}[]} people - in workflow step order
 * @returns {Map<string, object>} person id -> seat
 */
export function assignSeats(people) {
  const taken = new Set()
  const result = new Map()
  const take = (seat) => { taken.add(seat.id); return seat }
  const freeIn = (dept) => (SEATS_BY_DEPT[dept] || []).find((s) => !taken.has(s.id))

  // Pass 1: everyone who fits sits in their own department.
  for (const person of people) {
    const seat = person.dept === 'lobby' ? HUMAN_SEATS.find((s) => !taken.has(s.id)) : freeIn(person.dept)
    if (seat) result.set(person.id, take(seat))
  }

  // Pass 2: the rest spill over to related teams, then any free desk.
  for (const person of people) {
    if (result.has(person.id)) continue
    const order = [...(OVERFLOW[person.dept] || []), ...ALL_DEPTS]
    let seat = null
    for (const dept of order) {
      seat = freeIn(dept)
      if (seat) break
    }
    if (!seat) {
      // More people than desks: hot-desk standing spots along the corridor.
      const n = result.size
      seat = { id: `hot-${n}`, dept: 'corridor', x: 60 + ((n * 37) % 840), y: 268, facing: 'D', purpose: 'work', kind: 'stand' }
    }
    result.set(person.id, take(seat))
  }
  return result
}

/**
 * Order workflow nodes as steps: breadth-first from `graph.start` along the edges,
 * then any node that is not reachable, in YAML order.
 */
export function orderSteps(graph) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes.filter((n) => n?.id) : []
  const ids = new Set(nodes.map((n) => n.id))
  const next = new Map()
  for (const e of Array.isArray(graph?.edges) ? graph.edges : []) {
    const from = e?.from ?? e?.source
    const to = e?.to ?? e?.target
    if (!ids.has(from) || !ids.has(to)) continue
    if (!next.has(from)) next.set(from, [])
    next.get(from).push(to)
  }
  // Team leads: their members follow them (lead first, then each level of the hierarchy)
  for (const { from, to } of computeTeamLinks(nodes, graph?.edges)) {
    if (!next.has(from)) next.set(from, [])
    next.get(from).push(to)
  }
  const start = Array.isArray(graph?.start) ? graph.start : graph?.start ? [graph.start] : []
  const seen = new Set()
  const queue = start.filter((id) => ids.has(id))
  const order = []
  while (queue.length) {
    const id = queue.shift()
    if (seen.has(id)) continue
    seen.add(id)
    order.push(id)
    for (const to of next.get(id) || []) if (!seen.has(to)) queue.push(to)
  }
  for (const n of nodes) if (!seen.has(n.id)) order.push(n.id)
  const byId = new Map(nodes.map((n) => [n.id, n]))
  return order.map((id) => byId.get(id))
}
