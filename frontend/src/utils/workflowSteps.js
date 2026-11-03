// The steps of a workflow in run order, with what the Kanban board and the dashboard
// show about each one. Department and colour come from the office layout, so an agent
// looks the same in every view.
import { classifyNode, DEPARTMENT_COLOR, orderSteps } from '@/utils/officeLayout.js'

const roleSnippet = (text, limit = 140) => {
  const clean = String(text || '').replace(/\$\{[^}]*\}/g, '').replace(/\s+/g, ' ').trim()
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean
}

const modelOf = (node) => {
  const name = node?.config?.name
  return typeof name === 'string' && name && !name.startsWith('${') ? name : ''
}

/**
 * @param {object} graph   workflow graph from the YAML (nodes, edges, start)
 * @param {Map<string,string>} spriteMap  node id -> character sprite image
 */
export function buildSteps(graph, spriteMap = new Map()) {
  return orderSteps(graph)
    .filter(Boolean)
    .map((node, i) => {
      const dept = classifyNode(node)
      return {
        id: node.id,
        index: i + 1,
        type: node.type || 'agent',
        isHuman: node.type === 'human',
        dept,
        color: DEPARTMENT_COLOR[dept] || DEPARTMENT_COLOR.eng || '#64b5f6',
        model: modelOf(node),
        // The node's short description is written for people (and in the UI language);
        // the role is a long English system prompt, only a fallback
        role: roleSnippet(node.description || node.config?.role),
        sprite: spriteMap.get(node.id) || ''
      }
    })
}

/** Initials for a step without a character sprite ("Programmer Code Review" -> "PC"). */
export function initialsOf(id) {
  const words = String(id || '?').replace(/[_-]+/g, ' ').split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || '?').slice(0, 2)).toUpperCase()
}
