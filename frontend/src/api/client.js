import i18n from '@/i18n'

const apiUrl = (path) => path

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

// Localized summary, optionally followed by the backend detail.
const errorMessage = (key, detail) => {
  const summary = t(key)
  return detail ? t('errors.with_detail', { summary, detail }) : summary
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
  error.detail = detail
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
export async function fetchWorkflowsWithDesc() {
  try {
    const response = await fetch(apiUrl('/api/workflows'))
    if (!response.ok) {
      throw await responseError('errors.api.load_workflows_failed', response)
    }
    const data = await response.json()

    // Fetch YAML descriptions by filename
    const filesWithDesc = await Promise.all(
      data.workflows.map(async (filename) => {
        try {
          const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(filename)}/desc`))
          const fileData = await response.json()
          return {
            name: filename,
            description: fileData.description || t('workflow_list.no_description')
          }
        } catch {
          return { name: filename, description: t('workflow_list.no_description') }
        }
      })
    )

    return {
      success: true,
      workflows: filesWithDesc
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
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(filename)}/get`))
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
    const response = await fetch(apiUrl(`/api/workflows/${encodeURIComponent(yamlFilename)}/get`))

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
    const response = await fetch(apiUrl(`/api/vuegraphs/${encodeURIComponent(key)}`))
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
// Project (whole folder) uploads
// ---------------------------------------------------------------------------

// Keep each multipart request small enough for the backend form parser and
// slow connections; a project is sent as many of these batches.
const PROJECT_BATCH_MAX_FILES = 50
const PROJECT_BATCH_MAX_BYTES = 8 * 1024 * 1024

const splitIntoBatches = (entries) => {
  const batches = []
  let current = []
  let currentBytes = 0
  for (const entry of entries) {
    const size = entry.file?.size || 0
    if (current.length && (current.length >= PROJECT_BATCH_MAX_FILES || currentBytes + size > PROJECT_BATCH_MAX_BYTES)) {
      batches.push(current)
      current = []
      currentBytes = 0
    }
    current.push(entry)
    currentBytes += size
  }
  if (current.length) batches.push(current)
  return batches
}

/**
 * Upload a whole project folder, keeping its structure.
 *
 * @param {string} sessionId
 * @param {string} projectName  top-level folder name
 * @param {{file: File, path: string}[]} entries  path is relative to the project root
 * @param {(progress: {uploadedFiles: number, totalFiles: number}) => void} [onProgress]
 */
export async function uploadProject(sessionId, projectName, entries, onProgress) {
  try {
    if (!sessionId) {
      throw new Error(t('errors.api.missing_session_id'))
    }
    if (!entries?.length) {
      throw new Error(t('errors.api.empty_project'))
    }
    const base = `/api/uploads/${encodeURIComponent(sessionId)}/projects`

    const createResponse = await fetch(apiUrl(base), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: projectName })
    })
    const created = await createResponse.json().catch(() => ({}))
    if (!createResponse.ok || !created?.project_id) {
      return failureResult('errors.api.project_upload_failed', createResponse, created)
    }
    const projectUrl = `${base}/${encodeURIComponent(created.project_id)}`

    let uploadedFiles = 0
    let failedFiles = 0
    const failedPaths = []
    onProgress?.({ uploadedFiles, totalFiles: entries.length })
    for (const batch of splitIntoBatches(entries)) {
      const formData = new FormData()
      for (const { file, path } of batch) {
        formData.append('files', file, file.name)
        formData.append('paths', path)
      }
      const response = await fetch(apiUrl(`${projectUrl}/files`), { method: 'POST', body: formData })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        return failureResult('errors.api.project_upload_failed', response, data)
      }
      // The backend skips single files it cannot write and reports them here.
      failedFiles += data?.failed || 0
      failedPaths.push(...(data?.failed_paths || []))
      uploadedFiles += batch.length
      onProgress?.({ uploadedFiles, totalFiles: entries.length })
    }

    const finalizeResponse = await fetch(apiUrl(`${projectUrl}/finalize`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    })
    const data = await finalizeResponse.json().catch(() => ({}))
    if (!finalizeResponse.ok) {
      return failureResult('errors.api.project_upload_failed', finalizeResponse, data)
    }
    return {
      success: true,
      message: t('common.api_success.project_uploaded'),
      kind: 'project',
      name: data?.name,
      attachmentId: data?.attachment_id,
      mimeType: data?.mime_type,
      size: data?.total_size,
      fileCount: data?.file_count,
      workspacePath: data?.workspace_path,
      failedFiles,
      failedPaths
    }
  } catch (error) {
    console.error('Error uploading project:', error)
    return {
      success: false,
      message: error?.message || t('errors.api.network')
    }
  }
}

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

export const createConnection = ({ vendor, label, apiKey, baseUrl = '', authType = 'api_key' }) =>
  connectionsRequest(
    '',
    {
      method: 'POST',
      body: JSON.stringify({ vendor, label, api_key: apiKey, base_url: baseUrl, auth_type: authType })
    },
    'errors.api.connections_failed'
  )

export const deleteConnection = (id) =>
  connectionsRequest(`/${encodeURIComponent(id)}`, { method: 'DELETE' }, 'errors.api.connections_failed')

export const checkWorkflowConnections = (yamlContent) =>
  connectionsRequest(
    '/check',
    { method: 'POST', body: JSON.stringify({ yaml_content: yamlContent }) },
    'errors.api.connections_failed'
  )

export const fetchCliStatus = (vendor) =>
  connectionsRequest(`/cli-status/${encodeURIComponent(vendor)}`, {}, 'errors.api.connections_failed')

export const fetchGoogleOAuthStatus = () =>
  connectionsRequest('/oauth/google/status', {}, 'errors.api.connections_failed')

export const startGoogleOAuth = (label) =>
  connectionsRequest('/oauth/google/start', { method: 'POST', body: JSON.stringify({ label }) }, 'errors.api.connections_failed')

export const pollGoogleOAuth = (state) =>
  connectionsRequest(`/oauth/google/poll?state=${encodeURIComponent(state)}`, {}, 'errors.api.connections_failed')

export const startCliLogin = (vendor) =>
  connectionsRequest('/cli-login/start', { method: 'POST', body: JSON.stringify({ vendor }) }, 'errors.api.connections_failed')

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

export const testConnection = (id) =>
  connectionsRequest(`/${encodeURIComponent(id)}/test`, { method: 'POST' }, 'errors.api.connections_failed')
