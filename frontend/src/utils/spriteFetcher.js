/**
 * SpriteFetcher manages sprite image selection.
 * It provides random sprite selection and tracks used sprites to avoid duplicates.
 * It also preloads sprite frames so that frame swaps during animations never flash.
 */

/** Facing directions available for every character. */
export const SPRITE_STANCES = ['D', 'L', 'R', 'U']

/** Animation frames available for every stance (1 = idle, 2/3 = walk). */
export const SPRITE_FRAMES = [1, 2, 3]

/**
 * Build the public path of a sprite frame.
 * @param {number} character - Character index (1-13).
 * @param {string} stance - Stance ('D', 'L', 'R', 'U').
 * @param {number} frame - Frame number (1, 2, 3).
 * @returns {string} Image path.
 */
export function buildSpritePath(character, stance = 'D', frame = 1) {
  return `/sprites/${character}-${stance}-${frame}.png`
}

const CHARACTER_COUNT = 13

/** Valid character id from a YAML `mascot` value, or null. */
export function parseMascot(value) {
  const number = Number(value)
  return Number.isInteger(number) && number >= 1 && number <= CHARACTER_COUNT ? number : null
}

// Stable string hash (FNV-1a) so a node id always maps to the same starting character.
function hashString(text) {
  let hash = 2166136261
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

// First character not in `used`, probing from the id's hash; falls back to the hash slot.
function pickCharacter(nodeId, used) {
  const start = hashString(String(nodeId)) % CHARACTER_COUNT
  for (let i = 0; i < CHARACTER_COUNT; i++) {
    const character = ((start + i) % CHARACTER_COUNT) + 1
    if (!used.has(character)) return character
  }
  return start + 1
}

/**
 * Characters for a workflow's nodes: a node's own `mascot` always wins, the rest get a
 * deterministic character (same every load, in every view) that no other node uses yet.
 * @param {Array<{id?: string, mascot?: number}>} nodes - YAML graph nodes, in file order.
 * @returns {Map<string, number>} node id -> character id.
 */
export function resolveMascots(nodes) {
  const result = new Map()
  const used = new Set()
  const list = (nodes || []).filter((node) => node?.id)
  for (const node of list) {
    const chosen = parseMascot(node.mascot)
    if (chosen && !result.has(node.id)) {
      result.set(node.id, chosen)
      used.add(chosen)
    }
  }
  for (const node of list) {
    if (result.has(node.id)) continue
    const character = pickCharacter(node.id, used)
    result.set(node.id, character)
    used.add(character)
  }
  return result
}

export class SpriteFetcher {
  constructor() {
    // Available character list (1-13)
    this.availableCharacters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    // Map of characters already bound to node_id
    this.nodeCharacterMap = new Map()
    // Unassigned character pool for random allocation
    this.unassignedCharacters = [...this.availableCharacters]
    // Cache of preloaded Image objects keyed by sprite path.
    // Keeping a reference prevents the browser from evicting them early.
    this.preloadedImages = new Map()
    // Characters whose 12 frames have already been requested, with the priority
    // they were requested at ('low' = bulk warm-up, 'high' = bound to a node).
    this.preloadedCharacters = new Map()
    // Whether a lazy "preload everything" pass has been scheduled
    this.preloadAllScheduled = false
  }

  /**
   * Get a random sprite image path.
   * @param {string} node_id - Node ID used to bind a character.
   * @param {string} stance - Stance ('D', 'L', 'R', 'U').
   * @param {number} frame - Frame number (1, 2, 3).
   * @returns {string} Image path.
   */
  fetchSprite(node_id = null, stance = 'D', frame = 1) {
    let character

    if (node_id) {
      // Use the bound character if this node already has one.
      if (this.nodeCharacterMap.has(node_id)) {
        character = this.nodeCharacterMap.get(node_id)
      } else {
        // Nodes outside the loaded workflow (e.g. inside a subgraph) still get a stable,
        // preferably unused character instead of a random one.
        character = pickCharacter(node_id, new Set(this.nodeCharacterMap.values()))
        this.unassignedCharacters = this.unassignedCharacters.filter((c) => c !== character)

        // Bind the character to the node and warm up its frames.
        this.nodeCharacterMap.set(node_id, character)
        this.preloadCharacter(character)
      }
    } else {
      // If no node_id is specified, select a random character.
      character = this.availableCharacters[Math.floor(Math.random() * this.availableCharacters.length)]
    }

    // Build the sprite path.
    return buildSpritePath(character, stance, frame)
  }

  /**
   * Bind every node of a workflow to its character (see `resolveMascots`), replacing
   * earlier bindings so the editor, launch and office views all agree.
   * @param {Array<{id?: string, mascot?: number}>} nodes - YAML graph nodes.
   */
  bindNodes(nodes) {
    const resolved = resolveMascots(nodes)
    this.nodeCharacterMap = new Map(resolved)
    const used = new Set(resolved.values())
    this.unassignedCharacters = this.availableCharacters.filter((c) => !used.has(c))
    for (const character of used) this.preloadCharacter(character)
    return resolved
  }

  /**
   * Character to suggest for a new node: an unused one, stable for the given id.
   * @param {string} [node_id]
   * @returns {number}
   */
  suggestCharacter(node_id = '') {
    const used = new Set(this.nodeCharacterMap.values())
    return pickCharacter(node_id || `node-${used.size}`, used)
  }

  /** Node ids currently bound to `character`, other than `exceptId`. */
  nodesUsing(character, exceptId = null) {
    const ids = []
    for (const [id, bound] of this.nodeCharacterMap) {
      if (bound === character && id !== exceptId) ids.push(id)
    }
    return ids
  }

  /**
   * Get the character bound to a node, if any.
   * @param {string} node_id - Node ID.
   * @returns {number|null} Character index (1-13) or null when unbound.
   */
  getCharacter(node_id) {
    if (!node_id) return null
    return this.nodeCharacterMap.has(node_id) ? this.nodeCharacterMap.get(node_id) : null
  }

  /**
   * Preload all 12 frames (4 stances x 3 frames) of a character.
   * Safe to call repeatedly; frames are only requested once.
   * @param {number} character - Character index (1-13).
   * @param {Object} [options]
   * @param {boolean} [options.lowPriority=false] - Fetch with low network priority (bulk warm-up).
   * @param {boolean} [options.decode=true] - Also decode the frames off the critical path.
   * @returns {string[]} Paths of the frames belonging to the character.
   */
  preloadCharacter(character, { lowPriority = false, decode = true } = {}) {
    const paths = []
    if (!character) return paths

    for (const stance of SPRITE_STANCES) {
      for (const frame of SPRITE_FRAMES) {
        paths.push(buildSpritePath(character, stance, frame))
      }
    }

    // Nothing to do outside a browser (SSR/tests).
    if (typeof Image === 'undefined') return paths

    const mode = lowPriority ? 'low' : 'high'
    const current = this.preloadedCharacters.get(character)

    // Already requested at this priority (or higher): nothing more to do.
    if (current === 'high' || current === mode) return paths

    this.preloadedCharacters.set(character, mode)

    // Upgrade: the frames were already requested by the low-priority bulk pass,
    // so bump the pending requests and decode the cached images instead of refetching.
    if (current === 'low') {
      for (const path of paths) {
        const img = this.preloadedImages.get(path)
        if (!img) continue
        if ('fetchPriority' in img) img.fetchPriority = 'high'
        if (decode && typeof img.decode === 'function') {
          img.decode().catch(() => {})
        }
      }
      return paths
    }

    for (const path of paths) {
      if (this.preloadedImages.has(path)) continue
      const img = new Image()
      img.decoding = 'async'
      // Bulk warm-ups must never compete with app code or visible assets.
      if (lowPriority && 'fetchPriority' in img) img.fetchPriority = 'low'
      img.src = path
      this.preloadedImages.set(path, img)
      // Decode off the critical path so the first frame swap of a bound
      // character never pays the decode cost on the main thread during paint.
      if (decode && typeof img.decode === 'function') {
        img.decode().catch(() => {})
      }
    }

    return paths
  }

  /**
   * Lazily preload every frame of every character (144 images).
   * Work is spread across idle callbacks so it never blocks the UI.
   * @returns {Promise<void>} Resolves once all characters have been requested.
   */
  preloadAll() {
    if (this.preloadAllScheduled) return Promise.resolve()
    this.preloadAllScheduled = true

    const queue = [...this.availableCharacters]
    const schedule = (fn) => {
      if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(fn, { timeout: 1500 })
      } else {
        setTimeout(fn, 50)
      }
    }

    return new Promise((resolve) => {
      const step = () => {
        const character = queue.shift()
        if (character === undefined) {
          resolve()
          return
        }
        this.preloadCharacter(character, { lowPriority: true, decode: false })
        schedule(step)
      }
      schedule(step)
    })
  }

  /**
   * Get current usage status.
   * @returns {Object} Usage status summary.
   */
  getStatus() {
    return {
      totalCharacters: this.availableCharacters.length,
      assignedNodes: this.nodeCharacterMap.size,
      unassignedCount: this.unassignedCharacters.length,
      nodeCharacterMap: Object.fromEntries(this.nodeCharacterMap),
      unassignedCharacters: [...this.unassignedCharacters].sort((a, b) => a - b),
      preloadedCharacters: [...this.preloadedCharacters.keys()].sort((a, b) => a - b)
    }
  }

  /**
   * Reset usage state and clear used sprite records.
   * Preloaded images are kept because they remain valid.
   */
  reset() {
    this.nodeCharacterMap.clear()
    this.unassignedCharacters = [...this.availableCharacters]
    console.log('Sprite usage state reset')
  }
}

// Create a singleton instance.
export const spriteFetcher = new SpriteFetcher()
