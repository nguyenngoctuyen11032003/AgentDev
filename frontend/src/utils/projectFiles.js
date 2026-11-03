// Project folders are opened in place by the local backend (see LocalFolderPicker), so
// the browser never reads them. These helpers only sort out what was dropped on the chat.

// Dependency / build / VCS folders the backend leaves out of a project (mirrors
// IGNORED_PROJECT_DIRS in agentdev/api/services/attachment_service.py).
export const IGNORED_PROJECT_DIRS = new Set([
  '.git', '.hg', '.svn', 'node_modules', 'bower_components', '.venv', 'venv',
  'env', '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox',
  'dist', 'build', 'out', '.next', '.nuxt', '.svelte-kit', '.turbo', '.parcel-cache',
  '.cache', 'coverage', '.gradle', '.idea', 'target', 'Pods', 'DerivedData'
])

const entryToFile = (fileEntry) => new Promise((resolve, reject) => fileEntry.file(resolve, reject))

/**
 * Split a drag-and-drop payload into loose files and the names of dropped folders.
 * A dropped folder does not reveal where it lives on disk, so the caller asks the user
 * to open it with the folder picker instead.
 * Must be called synchronously inside the drop handler (DataTransfer items are only
 * readable during the event); the returned promise can be awaited.
 * @returns {Promise<{files: File[], folders: string[]}>}
 */
export function collectDroppedItems(dataTransfer) {
  const items = Array.from(dataTransfer?.items || [])
  const entries = items
    .filter((item) => item.kind === 'file')
    .map((item) => (typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null))

  // Browsers without the entries API: fall back to plain files.
  if (!entries.length || entries.some((entry) => !entry)) {
    return Promise.resolve({ files: Array.from(dataTransfer?.files || []), folders: [] })
  }

  return (async () => {
    const files = []
    const folders = []
    for (const entry of entries) {
      if (entry.isDirectory) {
        folders.push(entry.name)
      } else if (entry.isFile) {
        try {
          files.push(await entryToFile(entry))
        } catch (error) {
          console.warn(`Skipping unreadable file ${entry.name}:`, error)
        }
      }
    }
    return { files, folders }
  })()
}
