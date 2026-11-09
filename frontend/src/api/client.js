import i18n from '@/i18n'
import { notifyWorkflowChanged } from '@/utils/workflowSync.js'
import { localizeBackendError } from '@/utils/errorTranslate.js'

const apiUrl = (path) => path

// Workflow reads must always reflect the latest save (another tab may have just edited it)
const FRESH = { cache: 'no-store' }

const t = (key, params = {}) => i18n.global.t(key, params)

// Turn any backend error payload into a readable string.
// Handles FastAPI `detail` (string, {message}, or a list of validation errors
// [{loc, msg, type}]) and the custom {error: {code, message, details}} envelope.
export function extractErrorDetail(payload, depth = 0) {
  if (payload === null || payload === undefined || depth > 4) {
    return ''
  }
  if (typeof payload === 'string') {
    return payload.trim()
  }
  if (typeof payload === 'number' || typeof payload === 'boolean') {
    return String(payload)
  }
  if (payload instanceof Error) {
    return payload.message || ''
  }
  if (Array.isArray(payload)) {
    return payload
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          const loc = Array.isArray(item.loc)
            ? item.loc.filter((part) => part !== 'body').join('.')
            : ''
          return loc ? `${loc}: ${item.msg}` : String(item.msg)
        }
        return extractErrorDetail(item, depth + 1)
      })
      .filter(Boolean)
      .join('; ')
  }
  if (typeof payload === 'object') {
    for (const key of ['detail', 'error', 'message', 'msg']) {
      if (key in payload) {
        const text = extractErrorDetail(payload[key], depth + 1)
        if (text) {
          return text
        }
      }
    }
    try {
      return JSON.stringify(payload)
    } catch {
      return ''
    }
  }
  return String(payload)
}

// Localized summary, optionally followed by the backend detail. A recognised backend error text
// (see utils/errorTranslate.js) is shown in the UI language; callers keep the raw text as `detail`.
const errorMessage = (key, detail) => {
  const summary = t(key)
  if (!detail) return summary
  return t('errors.with_detail', { summary, detail: localizeBackendError(detail) || detail })
}

const httpStatusDetail = (response) => {
  return [response?.status, response?.statusText].filter(Boolean).join(' ')
}

// Build an Error with a localized message from a failed fetch Response.
const responseError = async (key, response) => {
  const body = await response.json().catch(() => null)
  const detail = extractErrorDetail(body) || httpStatusDetail(response)
  const error = new Error(errorMessage(key, detail))
  error.status = response.status
  error.detail = detail // original technical text
  error.code = body?.code || body?.error?.code || undefined
  return error
}

// Failure result for the {success, detail, message, status} API helpers.
// `detail` is always a plain string (never an object), `message` is localized.
const failureResult = (key, response, data) => {
  const detail = extractErrorDetail(data) || httpStatusDetail(response)
  return {
    success: false,
    detail: detail || undefined,
    message: errorMessage(key, detail),
    status: response?.status
  }
}

const networkFailure = (error) => ({
  success: false,
  message: errorMessage('errors.api.network', extractErrorDetail(error))
})

const addYamlSuffix = (filename) => {
  const trimmed = (filename || '').trim()
  if (!trimmed) {
    return ''
  }
  if (trimmed.endsWith('.yaml') || trimmed.endsWith('.yml')) {
    return trimmed
  }
  return `${trimmed}.yaml`
}

// Upload a YAML file
export async function postYaml(filename, content) {
  try {
    const fullFilename = addYamlSuffix(filename)
    const response = await fetch(apiUrl('/api/workflows/upload/content'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename: fullFilename,
        content: content
      })
    })

    // Return 400 when content is invalid
    if (response.ok || response.status === 400) {
      const data = await response.json()

      // If status is missing, content validation failed and detail contains the error
      if (data.status) {
        notifyWorkflowChanged(fullFilename)
        return {
          success: true,
          message: t('common.api_success.yaml_saved')
        }
      } else if (data.detail || data.error) {
        return failureResult('errors.api.save_yaml_failed', response, data)
      } else {
        return {
          success: false,
          message: t('errors.api.save_yaml_unknown')
        }
      }
    } else {
      const errorData = await response.json().catch(() => ({}))
      console.error('Error saving YAML file:', errorData)
      return failureResult('errors.api.save_yaml_failed', response, errorData)
    }
  } catch (error) {
    console.error('Error saving YAML file:', error)
    return networkFailure(error)
  }
}

export async function updateYaml(filename, content) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/update`), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        content
      })
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(data?.filename || yamlFilename)
      return {
        success: true,
        filename: data?.filename || yamlFilename,
        message: t('common.api_success.workflow_updated')
      }
    }

    return failureResult('errors.api.update_workflow_failed', response, data)
  } catch (error) {
    console.error('Error updating workflow YAML:', error)
    return networkFailure(error)
  }
}

// Save an edited workflow document from the visual editor. The server changes only the lines whose
// data differs, so comments, anchors/aliases and block text in hand-written YAML survive the save.
export async function mergeWorkflowDocument(filename, document) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/merge`), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ document })
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(data?.filename || yamlFilename)
      return {
        success: true,
        filename: data?.filename || yamlFilename,
        content: typeof data?.content === 'string' ? data.content : null,
        message: t('common.api_success.workflow_updated')
      }
    }

    return failureResult('errors.api.update_workflow_failed', response, data)
  } catch (error) {
    console.error('Error saving workflow document:', error)
    return networkFailure(error)
  }
}

export async function deleteWorkflow(filename) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/delete`), {
      method: 'DELETE'
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(yamlFilename, { kind: 'delete' })
      return { success: true, filename: data?.filename || yamlFilename }
    }

    return failureResult('errors.api.delete_workflow_failed', response, data)
  } catch (error) {
    console.error('Error deleting workflow:', error)
    return networkFailure(error)
  }
}

// Rename YAML file
export async function postYamlNameChange(filename, newFilename) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const yamlNewFilename = addYamlSuffix(newFilename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/rename`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        new_filename: yamlNewFilename
      })
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(data?.filename || yamlNewFilename, { kind: 'rename', previous: yamlFilename })
      return {
        success: true,
        filename: data?.filename || yamlNewFilename,
        message: t('common.api_success.workflow_renamed')
      }
    }

    return failureResult('errors.api.rename_workflow_failed', response, data)
  } catch (error) {
    console.error('Error renaming workflow YAML:', error)
    return networkFailure(error)
  }
}

// Copy YAML file
export async function postYamlCopy(filename, newFilename) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const yamlNewFilename = addYamlSuffix(newFilename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/copy`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        new_filename: yamlNewFilename
      })
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(data?.filename || yamlNewFilename, { kind: 'copy' })
      return {
        success: true,
        filename: data?.filename || yamlNewFilename,
        message: t('common.api_success.workflow_copied')
      }
    }

    return failureResult('errors.api.copy_workflow_failed', response, data)
  } catch (error) {
    console.error('Error copying workflow YAML:', error)
    return networkFailure(error)
  }
}

// Load the YAML file list from the API with names and descriptions
// Names only, one request: for pickers that do not show descriptions (fetchWorkflowsWithDesc
// costs one extra request per workflow).
export async function fetchWorkflowNames() {
  const response = await fetch(apiUrl('/api/workflows'), FRESH)
  if (!response.ok) {
    throw await responseError('errors.api.load_workflows_failed', response)
  }
  const data = await response.json()
  return Array.isArray(data.workflows) ? data.workflows : []
}

export async function fetchWorkflowsWithDesc() {
  try {
    // One request: the server reads every description (no /desc call per workflow)
    const response = await fetch(apiUrl('/api/workflows?include_descriptions=true'), FRESH)
    if (!response.ok) {
      throw await responseError('errors.api.load_workflows_failed', response)
    }
    const data = await response.json()
    const descriptions = data.descriptions && typeof data.descriptions === 'object' ? data.descriptions : {}

    return {
      success: true,
      workflows: (Array.isArray(data.workflows) ? data.workflows : []).map((filename) => ({
        name: filename,
        description: descriptions[filename] || t('workflow_list.no_description')
      }))
    }
  } catch (err) {
    console.error('Failed to load YAML files:', err)
    return {
      success: false,
      error: err?.status
        ? err.message
        : errorMessage('errors.api.load_workflows_unavailable', extractErrorDetail(err))
    }
  }
}

// Fetch YAML file content
export async function fetchWorkflowYAML(filename) {
  try {
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(filename)}/get`), FRESH)
    if (!response.ok) {
      throw await responseError('errors.api.load_workflow_failed', response)
    }
    const data = await response.json()
    return data.content
  } catch (err) {
    console.error('Failed to load YAML file:', err)
    throw err
  }
}

// Fetch YAML for the specified workflow
export async function fetchYaml(filename) {
  try {
    const yamlFilename = addYamlSuffix(filename)
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/get`), FRESH)

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      return {
        success: true,
        content: data?.content
      }
    }

    return failureResult('errors.api.load_workflow_failed', response, data)
  } catch (error) {
    console.error('Error fetching YAML file:', error)
    return networkFailure(error)
  }
}

// Fetch the VueFlow graph
export async function fetchVueGraph(key) {
  try {
    const response = await fetch(apiUrl(`/api/vuegraphs/${encodeURIComponent(key)}`), FRESH)
    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      return {
        success: true,
        content: data?.content,
        status: response.status
      }
    }

    return failureResult('errors.api.load_graph_failed', response, data)
  } catch (error) {
    console.error('Error fetching VueFlow graph:', error)
    return networkFailure(error)
  }
}

// Save the VueFlow graph
export async function postVuegraphs({ filename, content }) {
  try {
    const response = await fetch(apiUrl('/api/vuegraphs/upload/content'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename,
        content
      })
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      notifyWorkflowChanged(filename, { kind: 'graph' })
      return {
        success: true,
        message: t('common.api_success.graph_saved')
      }
    }

    return failureResult('errors.api.save_graph_failed', response, data)
  } catch (error) {
    console.error('Error saving VueFlow graph:', error)
    return networkFailure(error)
  }
}

// Fetch the config schema
export async function fetchConfigSchema(breadcrumbs) {
  try {
    const response = await fetch(apiUrl('/api/config/schema'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        breadcrumbs: breadcrumbs
      })
    })

    if (!response.ok) {
      throw await responseError('errors.api.load_schema_failed', response)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error('Failed to fetch config schema:', error)
    throw error
  }
}

// Download execution logs
export async function fetchLogsZip(sessionId) {
  try {
    const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/download`))

    if (!response.ok) {
      throw await responseError('errors.api.download_logs_failed', response)
    }

    // Get zip file data
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)

    // Create a download link and trigger download
    const link = document.createElement('a')
    link.href = url
    link.download = `execution_logs_${sessionId}.zip`
    document.body.appendChild(link)
    link.click()

    // Cleanup
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    return { success: true }
  } catch (error) {
    console.error('Failed to download execution logs:', error)
    throw error
  }
}

// Fetch session attachments
export async function getAttachment(sessionId, attachmentId) {
  try {
    if (!sessionId) {
      throw new Error(t('errors.api.missing_session_id'))
    }
    if (!attachmentId) {
      throw new Error(t('errors.api.missing_attachment_id'))
    }

    const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(attachmentId)}`))

    if (!response.ok) {
      throw await responseError('errors.api.load_attachment_failed', response)
    }

    const data = await response.json()
    return data?.data_uri
  } catch (error) {
    console.error('Failed to fetch attachment:', error)
    throw error
  }
}

// Batch workflow execution
export async function postBatchWorkflow({ file, sessionId, yamlFile, maxParallel, logLevel }) {
  try {
    const formData = new FormData()

    // Append required parameters
    if (file) {
      formData.append('file', file)
    }
    if (sessionId) {
      formData.append('session_id', sessionId)
    }
    if (yamlFile) {
      formData.append('yaml_file', yamlFile)
    }
    if (maxParallel !== undefined) {
      formData.append('max_parallel', maxParallel.toString())
    }
    if (logLevel) {
      formData.append('log_level', logLevel)
    }

    const response = await fetch(apiUrl('/api/workflows/batch'), {
      method: 'POST',
      body: formData
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      return {
        success: true,
        ...data,
        message: t('common.api_success.batch_started')
      }
    }

    return failureResult('errors.api.batch_failed', response, data)
  } catch (error) {
    console.error('Error executing batch workflow:', error)
    return networkFailure(error)
  }
}

// Start a run (or a follow-up turn) in a connected session. Resolves to {ok, status, data}:
// the caller tells a busy session (409, code run_in_progress) from a real failure.
// A network failure rejects, like fetch.
export async function postWorkflowExecute({ yamlFile, taskPrompt, sessionId, attachments = [], mode }) {
  const response = await fetch(apiUrl('/api/workflow/execute'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      yaml_file: yamlFile,
      task_prompt: taskPrompt,
      session_id: sessionId,
      attachments,
      mode
    })
  })
  const data = await response.json().catch(() => ({}))
  return { ok: response.ok, status: response.status, data }
}

// Upload a binary file
export async function postFile(sessionId, file) {
  try {
    if (!sessionId) {
      throw new Error(t('errors.api.missing_session_id'))
    }

    if (!file) {
      throw new Error(t('errors.api.missing_file'))
    }

    const formData = new FormData()
    let payload = file
    let filename = 'upload.bin'

    if (typeof file === 'string') {
      payload = new Blob([file], { type: 'application/octet-stream' })
    } else if (file?.name) {
      filename = file.name
    }

    formData.append('file', payload, filename)

    const response = await fetch(apiUrl(`/api/uploads/${encodeURIComponent(sessionId)}`), {
      method: 'POST',
      body: formData
    })

    const data = await response.json().catch(() => ({}))

    if (response.ok) {
      return {
        success: true,
        message: t('common.api_success.file_uploaded'),
        name: data?.name,
        attachmentId: data?.attachment_id,
        mimeType: data?.mime_type,
        size: data?.size
      }
    }

    return failureResult('errors.api.upload_failed', response, data)
  } catch (error) {
    console.error('Error uploading file:', error)
    return {
      success: false,
      message: error?.message || t('errors.api.network')
    }
  }
}

// ---------------------------------------------------------------------------
// Saved workflow sessions (sidebar history; survives reloads and server restarts)
// ---------------------------------------------------------------------------

async function sessionsRequest(path, options = {}) {
  const response = await fetch(apiUrl(`/api/sessions${path}`), {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) {
    throw await responseError('errors.api.sessions_failed', response)
  }
  return response.json()
}

export const fetchSessions = async () => (await sessionsRequest('')).sessions || []

export const renameSession = (sessionId, title) =>
  sessionsRequest(`/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify({ title }) })

/** What a finished run delivered (task, each agent's hand-over, changed files, summary) and its review. */
export const fetchSessionDigest = (sessionId) =>
  sessionsRequest(`/${encodeURIComponent(sessionId)}/digest`)

/** Save the user's verdict: { verdict: 'approved' | 'rework' | 'pending', rating, tags, feedback, rework_session_id } */
export const saveSessionReview = (sessionId, review) =>
  sessionsRequest(`/${encodeURIComponent(sessionId)}/review`, { method: 'PUT', body: JSON.stringify(review) })

// Only a draft (not launched yet) can switch workflow; a launched session keeps its own
export const updateSessionWorkflow = (sessionId, yamlFile) =>
  sessionsRequest(`/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify({ yaml_file: yamlFile }) })

/**
 * Bring a project into a new session from its latest state in an earlier session,
 * so "new session in this project" needs no folder pick or re-upload.
 */
export async function cloneProjectIntoSession(sessionId, { sourceSessionId, projectId, yamlFile = null }) {
  try {
    const response = await fetch(apiUrl(`/api/uploads/${encodeURIComponent(sessionId)}/projects/clone`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_session_id: sourceSessionId, project_id: projectId, yaml_file: yamlFile })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      return failureResult('errors.api.project_upload_failed', response, data)
    }
    return {
      success: true,
      kind: 'project',
      name: data?.name,
      attachmentId: data?.attachment_id,
      mimeType: data?.mime_type,
      size: data?.total_size,
      fileCount: data?.file_count,
      workspacePath: data?.workspace_path
    }
  } catch (error) {
    console.error('Error cloning project:', error)
    return { success: false, message: error?.message || t('errors.api.network') }
  }
}

/** Folders on this machine for the in-app "Open folder" picker (no path: home folders and drives). */
export async function browseLocalFolders(path = '') {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  const response = await fetch(apiUrl(`/api/local-folders${query}`))
  if (!response.ok) {
    throw await responseError('errors.api.local_folders_failed', response)
  }
  return response.json()
}

/** Create a new empty folder inside `parent`; resolves to the new folder's listing. */
export async function createLocalFolder(parent, name) {
  const response = await fetch(apiUrl('/api/local-folders'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name })
  })
  if (!response.ok) {
    throw await responseError('errors.api.local_folders_failed', response)
  }
  return response.json()
}

/** Where this session saves code, videos and other results: its opened project, else its own workspace folder. */
export async function fetchOutputLocation(sessionId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/output-location`))
  if (!response.ok) {
    throw await responseError('errors.api.local_folders_failed', response)
  }
  return response.json()
}

/** Show that output folder in the file manager. */
export async function openOutputLocation(sessionId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/output-location/open`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}'
  })
  if (!response.ok) {
    throw await responseError('errors.api.local_folders_failed', response)
  }
  return response.json()
}

// --- What a chat session produced (its output folder), browsed and run like a Lab run's product ---
const sessionOutputsPath = (sessionId) => `/api/sessions/${encodeURIComponent(sessionId)}/outputs`
const encodeOutputPath = (path) => String(path || '').split('/').map(encodeURIComponent).join('/')

async function sessionOutputsRequest(sessionId, suffix, options = {}) {
  const response = await fetch(apiUrl(`${sessionOutputsPath(sessionId)}${suffix}`), {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...options
  })
  if (!response.ok) throw await responseError('errors.api.local_folders_failed', response)
  return response.json()
}

/** -> {available, file_count, total_bytes, kinds, project, location: 'project'|'session', root, preview} */
export const sessionOutputsSummary = (sessionId) => sessionOutputsRequest(sessionId, '/summary')
/** -> {available, root, total_bytes, file_count, truncated, files: [{path, size, kind}], project, location} */
export const sessionOutputsFiles = (sessionId) => sessionOutputsRequest(sessionId, '/files')
// The product as a .zip (no node_modules, .venv, .git, caches, .env or attachments)
// Test accounts the user keeps for the session's app ("Tài khoản dùng thử")
export const sessionAccounts = (sessionId) => sessionOutputsRequest(sessionId, '/accounts')
export const sessionAccountsSave = (sessionId, accounts) =>
  sessionOutputsRequest(sessionId, '/accounts', { method: 'PUT', body: JSON.stringify({ accounts }) })
export const sessionOutputsArchiveUrl = (sessionId) => apiUrl(`${sessionOutputsPath(sessionId)}/archive`)
export const sessionOutputsFileUrl = (sessionId, path) =>
  apiUrl(`${sessionOutputsPath(sessionId)}/file?path=${encodeURIComponent(path)}`)
export const sessionOutputsSiteUrl = (sessionId, path = '') =>
  apiUrl(`${sessionOutputsPath(sessionId)}/site/${encodeOutputPath(path)}`)
export async function sessionOutputsFileText(sessionId, path, { signal } = {}) {
  const response = await fetch(sessionOutputsFileUrl(sessionId, path), { cache: 'no-store', signal })
  if (!response.ok) throw await responseError('errors.api.local_folders_failed', response)
  return response.text()
}
export const sessionOutputsOpen = (sessionId, { path = '', reveal = false } = {}) =>
  sessionOutputsRequest(sessionId, '/open', { method: 'POST', body: JSON.stringify({ path, reveal }) })
// "Chạy thử": start / poll / stop the session's web app or site (ports 47100-47199, stops itself when idle)
export const sessionPreviewStart = (sessionId) => sessionOutputsRequest(sessionId, '/preview', { method: 'POST', body: '{}' })
export const sessionPreviewStatus = (sessionId) => sessionOutputsRequest(sessionId, '/preview')
export const sessionPreviewStop = (sessionId) => sessionOutputsRequest(sessionId, '/preview', { method: 'DELETE' })

// Git checkpoints: what the latest run turn changed in a git workspace, with undo (never overwrites the user's edits)
async function sessionChangesRequest(sessionId, suffix, options = {}) {
  const response = await fetch(apiUrl(`${sessionOutputsPath(sessionId)}/changes${suffix}`), {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...options
  })
  if (!response.ok) throw await responseError('errors.api.git_changes_failed', response)
  return response.json()
}
/** -> {status: ok|running|not_git|disabled|no_checkpoint|error, turn, files: [{path, change, state, diff, binary, truncated}], counts} */
export const sessionChanges = (sessionId) => sessionChangesRequest(sessionId, '')
/** paths = null undoes every pending file. -> {restored, removed, conflicts: [{path, reason}], errors} */
export const sessionChangesUndo = (sessionId, paths = null) =>
  sessionChangesRequest(sessionId, '/undo', { method: 'POST', body: JSON.stringify({ paths }) })
/** -> {branch, commit, turn} */
export const sessionChangesKeepBranch = (sessionId) => sessionChangesRequest(sessionId, '/keep-branch', { method: 'POST', body: '{}' })

/**
 * Open a folder on this machine in place, like "Open Folder" in VS Code: nothing is
 * uploaded, the agents read and edit the real project.
 */
// Read a web page ({ url }) or search the web ({ query }) on the server; the text is attached to
// the next message like an uploaded file, so every agent receives it
export async function addWebReference(sessionId, { url = '', query = '', language = '' } = {}) {
  try {
    const response = await fetch(apiUrl(`/api/uploads/${encodeURIComponent(sessionId)}/web`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(url ? { url } : { query, language: language || undefined })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      return failureResult('errors.api.web_reference_failed', response, data)
    }
    return {
      success: true,
      kind: data?.kind || 'web',
      name: data?.name,
      attachmentId: data?.attachment_id,
      mimeType: data?.mime_type,
      size: data?.size,
      url: data?.url || '',
      query: data?.query || ''
    }
  } catch (error) {
    return networkFailure(error)
  }
}

export async function openLocalProject(sessionId, path, { yamlFile = null } = {}) {
  try {
    const response = await fetch(apiUrl(`/api/uploads/${encodeURIComponent(sessionId)}/projects/open-local`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, yaml_file: yamlFile })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      return failureResult('errors.api.project_open_failed', response, data)
    }
    return {
      success: true,
      kind: 'project',
      name: data?.name,
      attachmentId: data?.attachment_id,
      mimeType: data?.mime_type,
      size: data?.total_size,
      fileCount: data?.file_count,
      workspacePath: data?.workspace_path,
      localPath: data?.local_path,
      skipped: data?.skipped || 0
    }
  } catch (error) {
    console.error('Error opening project folder:', error)
    return { success: false, message: error?.message || t('errors.api.network') }
  }
}

export const deleteSession = (sessionId) =>
  sessionsRequest(`/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })

// ---------------------------------------------------------------------------
// Provider connections (credentials registered once, referenced by nodes)
// ---------------------------------------------------------------------------

async function connectionsRequest(path, options, errorKey) {
  const response = await fetch(apiUrl(`/api/connections${path}`), {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) {
    throw await responseError(errorKey, response)
  }
  return response.json()
}

export const fetchConnectionVendors = () =>
  connectionsRequest('/vendors', {}, 'errors.api.connections_failed')

export const fetchConnections = () =>
  connectionsRequest('', {}, 'errors.api.connections_failed')

// Account connections only (CLI sign-in); Google sign-in goes through the OAuth flow.
export const createConnection = ({ vendor, label, authType = 'cli' }) =>
  connectionsRequest(
    '',
    {
      method: 'POST',
      body: JSON.stringify({ vendor, label, auth_type: authType })
    },
    'errors.api.connections_failed'
  )

export const setDefaultConnection = (id) =>
  connectionsRequest(
    '/default',
    { method: 'PUT', body: JSON.stringify({ connection_id: id }) },
    'errors.api.connections_failed'
  )

// Removes only the AgentDev record unless signOutCli is set (machine-wide CLI sign-out, opt-in).
export const deleteConnection = (id, { signOutCli = false } = {}) =>
  connectionsRequest(
    `/${encodeURIComponent(id)}${signOutCli ? '?sign_out_cli=true' : ''}`,
    { method: 'DELETE' },
    'errors.api.connections_failed'
  )

export const checkWorkflowConnections = (yamlContent) =>
  connectionsRequest(
    '/check',
    { method: 'POST', body: JSON.stringify({ yaml_content: yamlContent }) },
    'errors.api.connections_failed'
  )

// ---------------------------------------------------------------------------
// Workflow assistant (chat that explains, creates and edits workflows)
// ---------------------------------------------------------------------------

const ASSISTANT_ERROR_KEY = 'workflow_assistant.errors.request_failed'

// The chat route answers its own failures as {error: <code>, message}; keep the code so the panel
// can react to it (quota_exhausted, cancelled, ...).
async function assistantRequest(path, options = {}) {
  try {
    const response = await fetch(apiUrl(`/api/workflow-assistant${path}`), {
      headers: { 'Content-Type': 'application/json' },
      ...FRESH,
      ...options
    })
    const data = await response.json().catch(() => ({}))
    if (typeof data?.error === 'string') {
      const detail = typeof data.message === 'string' ? data.message : ''
      return {
        success: false,
        error: data.error,
        detail: detail || undefined,
        message: errorMessage(ASSISTANT_ERROR_KEY, detail),
        status: response.status
      }
    }
    if (response.ok) {
      return { success: true, ...data }
    }
    return failureResult(ASSISTANT_ERROR_KEY, response, data)
  } catch (error) {
    console.error('Workflow assistant request failed:', error)
    return networkFailure(error)
  }
}

// -> {success, providers: [{vendor, label, connection_id, model, available}]}
export const fetchAssistantProviders = () => assistantRequest('/providers')

// -> {success, reply, quick_replies, proposal, model_used, validation_errors}
//    or {success: false, error?: code, detail?, message, status?}
export const sendAssistantMessage = ({ vendor, model, workflow, messages, pendingYaml, requestId }) =>
  assistantRequest('/chat', {
    method: 'POST',
    body: JSON.stringify({
      vendor,
      model: model || null,
      workflow: workflow || null,
      messages,
      pending_yaml: pendingYaml || null,
      request_id: requestId
    })
  })

// Saved assistant conversations (one per chat; each belongs to a workflow or to "new workflow").
// -> {success, sessions: [{id, workflow, title, created_at, updated_at, message_count}]}
export const fetchAssistantSessions = (workflow) =>
  assistantRequest(`/sessions${workflow ? `?workflow=${encodeURIComponent(workflow)}` : ''}`)
// -> {success, id, workflow, title, messages, pending_message_id, ...}
export const fetchAssistantSession = (id) => assistantRequest(`/sessions/${encodeURIComponent(id)}`)
export const saveAssistantSession = (id, session) =>
  assistantRequest(`/sessions/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(session) })
export const deleteAssistantSession = (id) =>
  assistantRequest(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })

// -> {success, cancelled}
export const cancelAssistantRequest = (requestId) =>
  assistantRequest('/cancel', { method: 'POST', body: JSON.stringify({ request_id: requestId }) })

export const fetchCliStatus = (vendor) =>
  connectionsRequest(`/cli-status/${encodeURIComponent(vendor)}`, {}, 'errors.api.connections_failed')

export const fetchGoogleOAuthStatus = () =>
  connectionsRequest('/oauth/google/status', {}, 'errors.api.connections_failed')

export const startGoogleOAuth = (label) =>
  connectionsRequest('/oauth/google/start', { method: 'POST', body: JSON.stringify({ label }) }, 'errors.api.connections_failed')

export const pollGoogleOAuth = (state) =>
  connectionsRequest(`/oauth/google/poll?state=${encodeURIComponent(state)}`, {}, 'errors.api.connections_failed')

export const startCliLogin = (vendor, method = null) =>
  connectionsRequest('/cli-login/start', { method: 'POST', body: JSON.stringify({ vendor, method }) }, 'errors.api.connections_failed')

export const pollCliLogin = (sessionId) =>
  connectionsRequest(`/cli-login/${encodeURIComponent(sessionId)}`, {}, 'errors.api.connections_failed')

export const submitCliLoginCode = (sessionId, code) =>
  connectionsRequest(
    `/cli-login/${encodeURIComponent(sessionId)}/code`,
    { method: 'POST', body: JSON.stringify({ code }) },
    'errors.api.connections_failed'
  )

export const cancelCliLogin = (sessionId) =>
  connectionsRequest(`/cli-login/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }, 'errors.api.connections_failed')

export const fetchConnectionModels = (id) =>
  connectionsRequest(`/${encodeURIComponent(id)}/models`, {}, 'errors.api.connections_failed')

export const fetchConnectionAccount = (id) =>
  connectionsRequest(`/${encodeURIComponent(id)}/account`, {}, 'errors.api.connections_failed')

export const testConnection = (id) =>
  connectionsRequest(`/${encodeURIComponent(id)}/test`, { method: 'POST' }, 'errors.api.connections_failed')

// ---------------------------------------------------------------------------
// Shared skill library (workspace/skills/<name>/SKILL.md, ticked per agent)
// ---------------------------------------------------------------------------

async function skillsRequest(path, options = {}) {
  const response = await fetch(apiUrl(`/api/skills${path}`), {
    headers: { 'Content-Type': 'application/json' },
    ...FRESH,
    ...options
  })
  if (!response.ok) {
    throw await responseError('errors.api.skills_failed', response)
  }
  return response.json()
}

export const fetchSkills = async () => (await skillsRequest('')).skills || []

export const fetchSkill = (name) => skillsRequest(`/${encodeURIComponent(name)}`)

// category: a category id, 'auto' (guess from name/description), or null to keep what the file says.
// guide: { purpose, when, benefit, requires, paid } for people; {} removes it; null keeps it.
export const createSkill = ({ content, name = null, description = null, overwrite = false, category = null, guide = null }) =>
  skillsRequest('', { method: 'POST', body: JSON.stringify({ content, name, description, overwrite, category, guide }) })

export const updateSkill = (originalName, { content, name = null, description = null, category = null, guide = null }) =>
  skillsRequest(`/${encodeURIComponent(originalName)}`, {
    method: 'PUT',
    body: JSON.stringify({ content, name, description, category, guide })
  })

export const deleteSkill = (name) => skillsRequest(`/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const fetchSkillImportSource = (source = '') =>
  skillsRequest(`/import-source${source ? `?source=${encodeURIComponent(source)}` : ''}`)

export const importSkills = ({ names, source = null, overwrite = false }) =>
  skillsRequest('/import', { method: 'POST', body: JSON.stringify({ names, source, overwrite }) })

// ---------------------------------------------------------------------------
// Workflow Lab (readiness check + scenario evaluation)
// ---------------------------------------------------------------------------

// Lab errors carry `detail = {message, code, params}`: keep code/params on the Error so the UI can
// translate them (lab.errors.<code>); `message` stays the localized summary + server text.
async function labResponseError(response) {
  const body = await response.clone().json().catch(() => null)
  const error = await responseError('errors.api.lab_failed', response)
  const detail = body?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    if (detail.code) error.code = detail.code
    error.params = detail.params && typeof detail.params === 'object' ? detail.params : {}
    if (detail.message) error.serverMessage = String(detail.message)
  }
  return error
}

async function labRequest(path, options = {}) {
  const response = await fetch(apiUrl(`/api/lab${path}`), {
    headers: { 'Content-Type': 'application/json' },
    ...FRESH,
    ...options
  })
  if (!response.ok) {
    throw await labResponseError(response)
  }
  return response.json()
}

export const labCheck = (yamlFile) =>
  labRequest('/check', { method: 'POST', body: JSON.stringify({ yaml_file: yamlFile }) })

export const labEvaluate = ({ yamlFile, scenarios, repeats }) =>
  labRequest('/evaluate', { method: 'POST', body: JSON.stringify({ yaml_file: yamlFile, scenarios, repeats }) })

export const labGenerate = ({ yamlFile, count, language }) =>
  labRequest('/generate', { method: 'POST', body: JSON.stringify({ yaml_file: yamlFile, count, language }) })

export const labJob = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}`)

export const labJobs = (workflow) => labRequest(`/jobs?workflow=${encodeURIComponent(workflow)}`)

export const labDeleteJob = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })

export const labCancel = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST', body: '{}' })

/** Re-run only the unfinished runs of a job that a server restart or a cancel stopped. */
export const labResume = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST', body: '{}' })

/** What re-running a job's failed scenarios would cost: -> {scenarios: [index], runs, estimate_usd|null, cost_known} */
export const labRerunEstimate = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}/rerun-failed/estimate`)

/**
 * Starts a new job with only the failed scenarios of `jobId` (current YAML, same repeats, `rerun_of`).
 * Sent only after the user's explicit click. -> the new job (202); 409 `nothing_to_rerun`.
 */
export const labRerunFailed = (jobId) =>
  labRequest(`/jobs/${encodeURIComponent(jobId)}/rerun-failed`, { method: 'POST', body: JSON.stringify({ confirm: true }) })

/** What preparing a source fix will do: -> {enabled, forbidden: [...], gates: [...], steps: [...]} */
export const labPlatformFixInfo = () => labRequest('/platform-fix/info')

/**
 * Prepare (never apply) an AgentDev source fix for a job's platform findings: a separate git worktree +
 * branch with PLATFORM_FIX.md. -> {branch, worktree, brief_file, actions, next_steps}
 */
export const labPlatformFix = (jobId, { password }) =>
  labRequest(`/jobs/${encodeURIComponent(jobId)}/platform-fix`, {
    method: 'POST',
    body: JSON.stringify({ password, confirm: true })
  })

// --- Finishing a platform fix: verify its worktree, then commit + merge into main, or discard. Nothing is pushed. ---
const platformFixPath = (id) => `/platform-fixes/${encodeURIComponent(id)}`

/** Every platform-fix worktree on this machine: -> {items: [{id, branch, verify, mergeable, blockers, ...}]} */
export const labPlatformFixes = () => labRequest('/platform-fixes')

/** One platform fix + `report` (short markdown, shown as plain text). */
export const labPlatformFixDetail = (id) => labRequest(platformFixPath(id))

/** Start the verify gates in the background. -> {verify} (202); 409 `verify_running`. */
export const labPlatformFixVerify = (id) => labRequest(`${platformFixPath(id)}/verify`, { method: 'POST', body: '{}' })

/** Stop a running verify. -> {verify}; 409 `verify_not_running`. */
export const labPlatformFixCancelVerify = (id) => labRequest(`${platformFixPath(id)}/cancel`, { method: 'POST', body: '{}' })

/**
 * Commit the worktree, merge --no-ff into main, remove the worktree and delete the branch. Sent only after the
 * user's explicit confirmation + password. -> {commit, merge_commit, files, actions, next_steps}
 */
export const labPlatformFixMerge = (id, { password, message = '' }) =>
  labRequest(`${platformFixPath(id)}/merge`, {
    method: 'POST',
    body: JSON.stringify({ password, confirm: true, ...(message ? { message } : {}) })
  })

/** Remove the worktree and delete the branch without merging (confirmation + password). -> {actions} */
export const labPlatformFixDiscard = (id, { password }) =>
  labRequest(`${platformFixPath(id)}/discard`, { method: 'POST', body: JSON.stringify({ password, confirm: true }) })

// --- What a run produced (files under AgentDev/AgentDev_lab/<run>, older runs storage/warehouse/lab_*), its app preview, and storage cleanup ---
const labRunPath = (jobId, run) => `/jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(run)}`
const encodeRelPath = (path) => String(path || '').split('/').map(encodeURIComponent).join('/')

/** -> {available, root, total_bytes, file_count, truncated, files: [{path, size, kind}], project} */
// What every run of a job produced (type, file kinds, a running preview) for the product overview
export const labProducts = (jobId) => labRequest(`/jobs/${encodeURIComponent(jobId)}/products`)
// After an evaluation: offer to delete this workflow's older products (keeps this job and the latest passing one)
export const labCleanupSuggestion = (workflow, keepJob = '') =>
  labRequest(`/storage/suggestion?workflow=${encodeURIComponent(workflow)}&keep_job=${encodeURIComponent(keepJob)}`)
export const labCleanupWorkflow = (workflow, keepJob = '') =>
  labRequest('/storage/cleanup-workflow', { method: 'POST', body: JSON.stringify({ workflow, keep_job: keepJob }) })
export const labRunFiles = (jobId, run) => labRequest(`${labRunPath(jobId, run)}/files`)

/** Raw URL of one product file (img/video src, download link, text fetch). */
// Test accounts the user keeps for a run's app ("Tài khoản dùng thử")
export const labRunAccounts = (jobId, run) => labRequest(`${labRunPath(jobId, run)}/accounts`)
export const labRunAccountsSave = (jobId, run, accounts) =>
  labRequest(`${labRunPath(jobId, run)}/accounts`, { method: 'PUT', body: JSON.stringify({ accounts }) })
export const labRunArchiveUrl = (jobId, run) => apiUrl(`/api/lab${labRunPath(jobId, run)}/archive`)
export const labRunFileUrl = (jobId, run, path) =>
  apiUrl(`/api/lab${labRunPath(jobId, run)}/file?path=${encodeURIComponent(path)}`)

/** Static-site URL of a product file: relative assets of an HTML page resolve from here. */
export const labRunSiteUrl = (jobId, run, path = '') =>
  apiUrl(`/api/lab${labRunPath(jobId, run)}/site/${encodeRelPath(path)}`)

/** Text content of a product file; a file over the server's limit fails with status 413. */
export async function labRunFileText(jobId, run, path, { signal } = {}) {
  const response = await fetch(labRunFileUrl(jobId, run, path), { ...FRESH, signal })
  if (!response.ok) throw await labResponseError(response)
  return response.text()
}

/** Open the product folder (path '') or one file on this machine; reveal selects it in the file manager. */
export const labRunOpen = (jobId, run, { path = '', reveal = false } = {}) =>
  labRequest(`${labRunPath(jobId, run)}/open`, { method: 'POST', body: JSON.stringify({ path, reveal }) })

/** Delete what one run produced (409 while its job is still running). -> {deleted, freed_bytes} */
export const labRunDeleteOutputs = (jobId, run) => labRequest(`${labRunPath(jobId, run)}/outputs`, { method: 'DELETE' })

/** App preview ("Chạy thử"): start (or get the existing one), read its status, stop it. */
// Every POST under /api/lab must carry a JSON body (the server answers 400 otherwise).
export const labPreviewStart = (jobId, run) =>
  labRequest(`${labRunPath(jobId, run)}/preview`, { method: 'POST', body: '{}' })
export const labPreviewStatus = (jobId, run) => labRequest(`${labRunPath(jobId, run)}/preview`)
export const labPreviewStop = (jobId, run) => labRequest(`${labRunPath(jobId, run)}/preview`, { method: 'DELETE' })
/** Tell the server the preview is still being watched (it stops idle ones). -> {status, alive, idle_seconds} */
export const labPreviewHeartbeat = (jobId, run) =>
  labRequest(`${labRunPath(jobId, run)}/preview/heartbeat`, { method: 'POST', body: '{}' })

/** -> {total_bytes, run_dirs, oldest, orphan_dirs} for all lab_* result folders. */
export const labStorage = () => labRequest('/storage')

/** Delete result folders older than N days and/or not referenced by any job. -> {deleted, freed_bytes} */
export const labStorageCleanup = ({ olderThanDays = 0, orphansOnly = false } = {}) =>
  labRequest('/storage/cleanup', {
    method: 'POST',
    body: JSON.stringify({ older_than_days: olderThanDays, orphans_only: orphansOnly })
  })

/** Open a file of the session's opened project on this machine (nothing is downloaded or copied). */
export async function openLocalProjectFile(sessionId, relativePath, { reveal = false } = {}) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/local-files/open`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ relative_path: relativePath, reveal })
  })
  if (!response.ok) {
    // The caller wraps this in its own "could not open file: {error}" text, so no extra summary here.
    const body = await response.json().catch(() => null)
    const detail = extractErrorDetail(body) || httpStatusDetail(response)
    const error = new Error(localizeBackendError(detail) || detail || `HTTP ${response.status}`)
    error.status = response.status
    error.detail = detail
    throw error
  }
  return response.json()
}
