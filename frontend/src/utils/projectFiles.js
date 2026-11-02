// Collect files from a picked/dropped project folder, keeping relative paths
// and skipping dependency/build/VCS folders (mirrors the backend filter in
// agentdev/api/services/attachment_service.py).

export const IGNORED_PROJECT_DIRS = new Set([
  '.git', '.hg', '.svn', 'node_modules', 'bower_components', '.venv', 'venv',
  'env', '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox',
  'dist', 'build', 'out', '.next', '.nuxt', '.svelte-kit', '.turbo', '.parcel-cache',
  '.cache', 'coverage', '.gradle', '.idea', 'target', 'Pods', 'DerivedData'
])
const IGNORED_PROJECT_FILES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini'])

/** True when a path inside a project should not be uploaded. */
export function isIgnoredProjectPath(relativePath) {
  const parts = relativePath.split('/').filter(Boolean)
  if (!parts.length) return true
  const fileName = parts[parts.length - 1]
  return IGNORED_PROJECT_FILES.has(fileName) || parts.slice(0, -1).some((part) => IGNORED_PROJECT_DIRS.has(part))
}

/**
 * Group files from an `<input webkitdirectory>` into projects.
 * Each File carries `webkitRelativePath` = "<root>/<sub>/<file>".
 * @returns {{name: string, entries: {file: File, path: string}[], skipped: number}[]}
 */
export function projectsFromDirectoryInput(fileList) {
  const projects = new Map()
  for (const file of Array.from(fileList || [])) {
    const fullPath = (file.webkitRelativePath || file.name).replace(/\\/g, '/')
    const [root, ...rest] = fullPath.split('/')
    const path = rest.join('/')
    if (!projects.has(root)) projects.set(root, { name: root, entries: [], skipped: 0 })
    const project = projects.get(root)
    if (!path || isIgnoredProjectPath(path)) {
      project.skipped += 1
    } else {
      project.entries.push({ file, path })
    }
  }
  return [...projects.values()]
}

const readAllDirectoryEntries = (directoryEntry) =>
  new Promise((resolve, reject) => {
    const reader = directoryEntry.createReader()
    const all = []
    // readEntries returns results in chunks (~100); call until it returns none.
    const readChunk = () =>
      reader.readEntries((chunk) => {
        if (!chunk.length) {
          resolve(all)
          return
        }
        all.push(...chunk)
        readChunk()
      }, reject)
    readChunk()
  })

const entryToFile = (fileEntry) => new Promise((resolve, reject) => fileEntry.file(resolve, reject))

async function walkDirectory(directoryEntry, prefix, project) {
  for (const entry of await readAllDirectoryEntries(directoryEntry)) {
    const path = prefix ? `${prefix}/${entry.name}` : entry.name
    if (entry.isDirectory) {
      // Skip ignored folders without even listing them (node_modules can be huge).
      if (IGNORED_PROJECT_DIRS.has(entry.name)) {
        project.skipped += 1
        continue
      }
      await walkDirectory(entry, path, project)
    } else if (entry.isFile) {
      if (isIgnoredProjectPath(path)) {
        project.skipped += 1
        continue
      }
      project.entries.push({ file: await entryToFile(entry), path })
    }
  }
}

/**
 * True when the File System Access folder picker is available (Chromium).
 * Unlike `<input webkitdirectory>`, it lets us skip ignored folders without
 * enumerating them, and the browser does not ask to "upload N files" for
 * every file under node_modules/.git.
 */
export const supportsDirectoryPicker = () =>
  typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function'

async function walkDirectoryHandle(directoryHandle, prefix, project) {
  for await (const handle of directoryHandle.values()) {
    const path = prefix ? `${prefix}/${handle.name}` : handle.name
    if (handle.kind === 'directory') {
      if (IGNORED_PROJECT_DIRS.has(handle.name)) {
        project.skipped += 1
        continue
      }
      await walkDirectoryHandle(handle, path, project)
    } else if (isIgnoredProjectPath(path)) {
      project.skipped += 1
    } else {
      project.entries.push({ file: await handle.getFile(), path })
    }
  }
}

/**
 * Open the folder picker and collect one project from it.
 * Rejects with an `AbortError` DOMException when the user cancels.
 * @returns {Promise<{name: string, entries: {file: File, path: string}[], skipped: number}>}
 */
export async function pickProjectDirectory() {
  const directoryHandle = await window.showDirectoryPicker({ id: 'project-upload', mode: 'read' })
  const project = { name: directoryHandle.name, entries: [], skipped: 0 }
  await walkDirectoryHandle(directoryHandle, '', project)
  return project
}

/**
 * Split a drag-and-drop payload into loose files and whole folders.
 * Must be called synchronously inside the drop handler (DataTransfer items
 * are only readable during the event); the returned promise can be awaited.
 * @returns {Promise<{files: File[], projects: {name: string, entries: {file: File, path: string}[], skipped: number}[]}>}
 */
export function collectDroppedItems(dataTransfer) {
  const items = Array.from(dataTransfer?.items || [])
  const entries = items
    .filter((item) => item.kind === 'file')
    .map((item) => (typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null))

  // Browsers without the entries API: fall back to plain files.
  if (!entries.length || entries.some((entry) => !entry)) {
    return Promise.resolve({ files: Array.from(dataTransfer?.files || []), projects: [] })
  }

  return (async () => {
    const files = []
    const projects = []
    for (const entry of entries) {
      if (entry.isDirectory) {
        const project = { name: entry.name, entries: [], skipped: 0 }
        await walkDirectory(entry, '', project)
        projects.push(project)
      } else if (entry.isFile) {
        files.push(await entryToFile(entry))
      }
    }
    return { files, projects }
  })()
}
