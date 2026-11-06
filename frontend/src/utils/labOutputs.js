// Helpers for browsing what a Lab run produced (file tree, default file, sizes, icons).

/**
 * Stable key of a run: its `run_id` (kept across a resume) when the job has one; jobs stored before
 * run ids existed fall back to the run's position, which the server still accepts.
 */
export const runKey = (run, index) => run?.run_id || index

/**
 * Readable text of a Lab API error: translated by its stable `code` (lab.errors.<code>, with the
 * server's params) when the UI knows it, else the message the server sent.
 */
export function labErrorText(error, { t, te }) {
  const code = error?.code || error?.error_code
  if (code && te(`lab.errors.${code}`)) return t(`lab.errors.${code}`, error.params || error.error_params || {})
  if (typeof error === 'string') return error
  return error?.message || error?.serverMessage || error?.error || String(error || '')
}

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

/** 3355443 -> "3,2 MB" (vi) / "3.2 MB" (en): one decimal from KB up, locale-aware separator. */
export function formatBytes(bytes, locale = 'vi') {
  let value = Number(bytes) || 0
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value)} ${UNITS[unit]}`
}

/**
 * Flat file list -> nested folders. Folders first, then files, both by name.
 * Node: {name, path, type: 'dir'|'file', children?, file?, size}
 */
export function buildTree(files) {
  const root = { name: '', path: '', type: 'dir', children: [], size: 0 }
  const dirs = new Map([['', root]])
  for (const file of files) {
    const parts = String(file.path).split('/').filter(Boolean)
    let parent = root
    for (let i = 0; i < parts.length - 1; i += 1) {
      const path = parts.slice(0, i + 1).join('/')
      let dir = dirs.get(path)
      if (!dir) {
        dir = { name: parts[i], path, type: 'dir', children: [], size: 0 }
        dirs.set(path, dir)
        parent.children.push(dir)
      }
      parent = dir
    }
    parent.children.push({ name: parts[parts.length - 1], path: file.path, type: 'file', file, size: file.size || 0 })
  }
  const sortAndSum = (node) => {
    node.children.sort((a, b) =>
      a.type !== b.type ? (a.type === 'dir' ? -1 : 1) : a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' })
    )
    for (const child of node.children) if (child.type === 'dir') sortAndSum(child)
    node.size = node.children.reduce((sum, child) => sum + child.size, 0)
  }
  sortAndSum(root)
  return root
}

/** Visible rows of the tree for the given expanded folder paths (depth drives the indent). */
export function flattenTree(root, expanded) {
  const rows = []
  const walk = (node, depth) => {
    for (const child of node.children) {
      rows.push({ node: child, depth })
      if (child.type === 'dir' && expanded.has(child.path)) walk(child, depth + 1)
    }
  }
  walk(root, 0)
  return rows
}

/** All ancestor folder paths of a file path ("a/b/c.md" -> ["a", "a/b"]). */
export function ancestorsOf(path) {
  const parts = String(path).split('/')
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join('/'))
}

const depthOf = (path) => String(path).split('/').length
const baseName = (path) => String(path).split('/').pop().toLowerCase()

/** What to show first: a README, then an index page, then the shallowest document, then anything. */
export function pickDefaultFile(files) {
  if (!files?.length) return null
  const byDepth = [...files].sort((a, b) => depthOf(a.path) - depthOf(b.path) || a.path.localeCompare(b.path))
  return (
    byDepth.find((f) => /^readme([-_.][\w-]*)?(\.(md|markdown|txt))?$/.test(baseName(f.path))) ||
    byDepth.find((f) => baseName(f.path) === 'index.html') ||
    byDepth.find((f) => /^(index|overview|tong[-_]?quan|tom[-_]?tat)\.(md|markdown)$/.test(baseName(f.path))) ||
    byDepth.find((f) => f.kind === 'markdown') ||
    byDepth.find((f) => f.kind === 'html') ||
    byDepth.find((f) => ['text', 'pdf', 'image', 'video'].includes(f.kind)) ||
    byDepth[0]
  )
}

/** Count files per kind, most common first: [{kind, n}]. */
export function countKinds(files) {
  const counts = new Map()
  for (const f of files || []) counts.set(f.kind, (counts.get(f.kind) || 0) + 1)
  return [...counts.entries()].map(([kind, n]) => ({ kind, n })).sort((a, b) => b.n - a.n)
}

// 24px stroke icons, one or more paths each (drawn with stroke="currentColor").
export const KIND_ICONS = {
  folder: ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z'],
  folderOpen: ['M3 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v1', 'M3 7v10a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L21.5 12a1.5 1.5 0 0 0-1.4-2H7.4a2 2 0 0 0-1.9 1.4L3 19'],
  markdown: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'M9 13h6M9 17h4'],
  text: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'M9 13h6M9 17h6'],
  code: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'm10 13-2 2 2 2M14 13l2 2-2 2'],
  image: ['M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z', 'M9 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z', 'm20 15-4.5-4.5L5 20'],
  video: ['M4 6h11a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z', 'm16 10 5-3v10l-5-3'],
  audio: ['M9 18V5l11-2v13', 'M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'],
  html: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z'],
  pdf: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'M8.5 17v-4h1.3a1.2 1.2 0 0 1 0 2.4H8.5M13 13v4h.8a1.6 1.6 0 0 0 1.6-1.6v-.8A1.6 1.6 0 0 0 13.8 13H13'],
  binary: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5']
}

/** Text-like kinds are fetched and shown inline; the rest stream from their URL. */
export const TEXT_KINDS = new Set(['markdown', 'text', 'code'])
/** Same limit as the server (larger text answers 413): don't even try. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024

// Explorer-style badges for common source files ("JS", "{}", "#"), coloured by language like a code editor.
const FILE_BADGES = [
  [/\.(m|c)?js$/, 'JS', 'js'],
  [/\.(jsx|tsx)$/, '⚛', 'react'],
  [/\.(m|c)?ts$/, 'TS', 'ts'],
  [/\.vue$/, 'V', 'vue'],
  [/\.svelte$/, 'S', 'html'],
  [/\.jsonc?$/, '{}', 'json'],
  [/\.(css|scss|sass|less)$/, '#', 'css'],
  [/\.html?$/, '<>', 'html'],
  [/\.(md|markdown|mdx)$/, 'M↓', 'md'],
  [/\.py$/, 'PY', 'py'],
  [/\.(ya?ml|toml)$/, '≡', 'yaml'],
  [/\.sql$/, 'DB', 'db'],
  [/\.(sh|bash|ps1|bat|cmd)$/, '$', 'shell'],
  [/\.(java|kt|go|rs|c|h|cpp|hpp|cs|rb|php|swift|dart)$/, '</>', 'ts'],
  [/^(\.env.*|\.gitignore|\.dockerignore|\.editorconfig|\.npmrc|\.nvmrc|\.prettierrc.*|\.eslintrc.*|\.babelrc)$/, '⚙', 'config'],
  [/\.lock$/, '⚙', 'config'],
  [/^dockerfile$|\.dockerfile$/, 'D', 'ts']
]

/** `{label, tone}` badge of a source/config file by its name, or null (the kind icon is drawn instead). */
export function fileBadge(name) {
  const lower = String(name || '').toLowerCase()
  if (lower === 'package-lock.json') return { label: '{}', tone: 'config' }
  for (const [re, label, tone] of FILE_BADGES) if (re.test(lower)) return { label, tone }
  return null
}
