// What a Lab run produced, reduced to one product type for the overview cards and the run-row chips.
// Input: one entry of GET /api/lab/jobs/{id}/products -> runs[].

const DOC_KINDS = ['markdown', 'text', 'pdf']
const MEDIA_KINDS = ['image', 'video', 'audio']

const sum = (kinds, names) => names.reduce((n, k) => n + (kinds?.[k] || 0), 0)

/**
 * -> null when the run made nothing, else {type, count}
 * type: webapp (runnable app) | site (static HTML) | media | docs | code | files
 * count: the number of files of that type (used by the chips: "6 tài liệu").
 */
export function productType(entry) {
  if (!entry?.available || !entry.file_count) return null
  const kinds = entry.kinds || {}
  const project = entry.project || {}
  if (project.type === 'static') return { type: 'site', count: kinds.html || 1 }
  if (project.can_preview && (project.type === 'node' || project.type === 'python')) return { type: 'webapp', count: entry.file_count }
  const media = sum(kinds, MEDIA_KINDS)
  if (media) return { type: 'media', count: media }
  const docs = sum(kinds, DOC_KINDS)
  const code = sum(kinds, ['code', 'html'])
  if (docs && docs >= code) return { type: 'docs', count: docs }
  if (code) return { type: 'code', count: code }
  return { type: 'files', count: entry.file_count }
}

// Overview order: what can be opened right away first.
export const TYPE_ORDER = { webapp: 0, site: 1, media: 2, docs: 3, code: 4, files: 5 }

/** The stack in "Ứng dụng Node (Vite + React + Express)" -> "Vite + React + Express"; '' when none is named. */
export function stackOf(project) {
  const match = /\(([^)]+)\)/.exec(project?.summary || '')
  if (match) return match[1]
  return project?.type === 'python' ? 'Python' : ''
}

/** Address to show for a running preview: "localhost:47100" (relative /api/... URLs get the page's host). */
export function displayUrl(url) {
  if (!url) return ''
  if (url.startsWith('/')) return `${window.location.host}${url.split('?')[0]}`
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
}
