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
 * @param {number} character - Character index (1-12).
 * @param {string} stance - Stance ('D', 'L', 'R', 'U').
 * @param {number} frame - Frame number (1, 2, 3).
 * @returns {string} Image path.
 */
export function buildSpritePath(character, stance = 'D', frame = 1) {
  return `/sprites/${character}-${stance}-${frame}.png`
}

export class SpriteFetcher {
  constructor() {
    // Available character list (1-12)
    this.availableCharacters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    // Map of characters already bound to node_id
    this.nodeCharacterMap = new Map()
    // Unassigned character pool for random allocation
    this.unassignedCharacters = [...this.availableCharacters]
    // Cache of preloaded Image objects keyed by sprite path.
    // Keeping a reference prevents the browser from evicting them early.
    this.preloadedImages = new Map()
    // Characters whose 12 frames have already been requested
    this.preloadedCharacters = new Set()
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
        // If no character is bound, choose one at random.
        if (this.unassignedCharacters.length === 0) {
          // If all characters are assigned, pick one from the assigned pool.
          character = this.availableCharacters[Math.floor(Math.random() * this.availableCharacters.length)]
        } else {
          // Pick randomly from the unassigned pool.
          const randomIndex = Math.floor(Math.random() * this.unassignedCharacters.length)
          character = this.unassignedCharacters[randomIndex]
          this.unassignedCharacters.splice(randomIndex, 1)
        }

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
   * Get the character bound to a node, if any.
   * @param {string} node_id - Node ID.
   * @returns {number|null} Character index (1-12) or null when unbound.
   */
  getCharacter(node_id) {
    if (!node_id) return null
    return this.nodeCharacterMap.has(node_id) ? this.nodeCharacterMap.get(node_id) : null
  }

  /**
   * Preload all 12 frames (4 stances x 3 frames) of a character.
   * Safe to call repeatedly; frames are only requested once.
   * @param {number} character - Character index (1-12).
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

    // Skip the network work when already warmed up or when not in a browser (SSR/tests).
    if (this.preloadedCharacters.has(character) || typeof Image === 'undefined') {
      return paths
    }
    this.preloadedCharacters.add(character)

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
      preloadedCharacters: [...this.preloadedCharacters].sort((a, b) => a - b)
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
