import { fetchConnectionVendors, fetchConnections } from '@/api/client'

// Model suggestions for a node, derived from its selected connection's vendor.
// Cached briefly so opening several node forms does not refetch every time.
const TTL_MS = 30_000
let cache = null

async function load() {
  if (cache && Date.now() - cache.at < TTL_MS) return cache.data
  const [vendors, connections] = await Promise.all([fetchConnectionVendors(), fetchConnections()])
  const data = { vendors: vendors.vendors, connections: connections.connections }
  cache = { at: Date.now(), data }
  return data
}

export function invalidateConnectionModels() {
  cache = null
}

export async function modelsForConnection(connectionId) {
  if (!connectionId) return []
  try {
    const { vendors, connections } = await load()
    const connection = connections.find((item) => item.id === connectionId)
    const vendor = vendors.find((item) => item.id === connection?.vendor)
    return vendor ? vendor.models : []
  } catch {
    return []
  }
}
