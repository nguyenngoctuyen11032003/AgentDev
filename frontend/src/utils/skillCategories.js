// Skill categories, in display order. Ids match backend `skill_categories.CATEGORIES`;
// labels live in i18n under `skills.categories.<id>`.
// `icon` is the inner SVG markup of a 24x24 stroke icon; `hue` tints the category tile.
export const SKILL_CATEGORIES = [
  { id: 'video', hue: 350, icon: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/>' },
  { id: 'image', hue: 285, icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>' },
  { id: 'audio', hue: 160, icon: '<path d="M9 18V6l11-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>' },
  { id: 'motion', hue: 28, icon: '<path d="M12 3 3 8l9 5 9-5z"/><path d="m3 13 9 5 9-5"/><path d="m3 18 9 5 9-5" opacity=".5"/>' },
  { id: 'marketing', hue: 45, icon: '<path d="M3 11v2a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M17 8a5 5 0 0 1 0 8"/>' },
  { id: 'design', hue: 320, icon: '<path d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-.4-.2-.8-.4-1.1-.3-.3-.4-.6-.4-1 0-.8.7-1.5 1.5-1.5H16a5 5 0 0 0 5-5c0-4.4-4-7.9-9-7.9z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7" r="1"/><circle cx="15.5" cy="8" r="1"/>' },
  { id: 'dev', hue: 210, icon: '<path d="m8 8-5 4 5 4"/><path d="m16 8 5 4-5 4"/><path d="m14 4-4 16"/>' },
  { id: 'workflow', hue: 255, icon: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.5 6H15a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h6.5"/>' },
  { id: 'docs', hue: 190, icon: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h5"/>' },
  { id: 'other', hue: null, icon: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>' }
]

export const CATEGORY_IDS = SKILL_CATEGORIES.map((c) => c.id)
const BY_ID = Object.fromEntries(SKILL_CATEGORIES.map((c) => [c.id, c]))

// A skill's category id; anything unknown (old backend, typo) counts as "other".
export const categoryOf = (skill) => (BY_ID[skill?.category] ? skill.category : 'other')

export const categoryMeta = (id) => BY_ID[id] || BY_ID.other

// { id: count } for every category (zero included) plus `all`.
export function countByCategory(skills) {
  const counts = Object.fromEntries(CATEGORY_IDS.map((id) => [id, 0]))
  for (const skill of skills) counts[categoryOf(skill)] += 1
  counts.all = skills.length
  return counts
}

// Non-empty groups in display order: [{ id, skills }]
export function groupByCategory(skills) {
  const groups = new Map(CATEGORY_IDS.map((id) => [id, []]))
  for (const skill of skills) groups.get(categoryOf(skill)).push(skill)
  return [...groups].filter(([, list]) => list.length).map(([id, list]) => ({ id, skills: list }))
}

const searchText = (s) => {
  const g = s.guide || {}
  return `${s.name} ${s.description || ''} ${g.purpose || ''} ${g.when || ''} ${g.benefit || ''}`.toLowerCase()
}

// Case-insensitive match on name, description and the plain-language guide (so Vietnamese words find skills),
// optionally inside one category ('all' = every one).
export function filterSkills(skills, { query = '', category = 'all' } = {}) {
  const q = query.trim().toLowerCase()
  return skills.filter((s) => (category === 'all' || categoryOf(s) === category) && (!q || searchText(s).includes(q)))
}
