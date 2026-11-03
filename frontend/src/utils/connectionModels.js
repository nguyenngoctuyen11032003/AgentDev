import { fetchConnectionModels, fetchConnectionVendors, fetchConnections } from '@/api/client'

// Models a node can pick for its selected connection: what the connected account really offers
// (Claude/Codex account catalog, or Gemini's live listing for Google sign-in).
// Cached briefly so opening several node forms does not refetch every time.
const TTL_MS = 60_000
const cache = new Map() // connectionId -> { at, promise }

export function invalidateConnectionModels() {
  cache.clear()
}

// Last resort when the server cannot be reached: the vendor's static catalog.
async function catalogFallback(connectionId) {
  try {
    const [vendors, connections] = await Promise.all([fetchConnectionVendors(), fetchConnections()])
    const connection = connections.connections.find((item) => item.id === connectionId)
    const vendor = vendors.vendors.find((item) => item.id === connection?.vendor)
    const models = (vendor?.models || []).map((id) => ({ id, name: id, primary: true }))
    return { models, source: 'catalog', ok: false }
  } catch {
    return { models: [], source: 'catalog', ok: false }
  }
}

/**
 * @returns {Promise<{models: {id: string, name: string, primary: boolean}[], source: 'account'|'api'|'catalog', ok: boolean}>}
 */
export function modelsForConnection(connectionId) {
  if (!connectionId) return Promise.resolve({ models: [], source: 'catalog', ok: false })
  const hit = cache.get(connectionId)
  if (hit && Date.now() - hit.at < TTL_MS) return hit.promise
  const promise = fetchConnectionModels(connectionId)
    .then((data) => ({
      models: Array.isArray(data.models) ? data.models : [],
      source: data.source || 'catalog',
      ok: data.ok !== false
    }))
    .catch(() => catalogFallback(connectionId))
  cache.set(connectionId, { at: Date.now(), promise })
  // A failed lookup should be retried next time instead of being cached for a minute.
  promise.then((result) => {
    if (!result.ok && cache.get(connectionId)?.promise === promise) cache.delete(connectionId)
  })
  return promise
}
