/**
 * Metadata for the 13 pixel-art chibi characters shipped in `/public/sprites`.
 * Each character has 4 stances (D/L/R/U) and 3 frames (1 = idle, 2/3 = walk).
 * Display names and taglines live in the i18n locales under `sprites.characters.<id>`.
 */

/** Neutral fallback used when an unknown character id is requested. */
const DEFAULT_CHARACTER = Object.freeze({
  id: 0,
  key: 'unknown',
  accent: '#8A8F98',
  accentSoft: 'rgba(138, 143, 152, 0.16)',
  hair: 'unknown',
  outfit: 'unknown',
  vibe: 'calm'
})

/**
 * Static descriptors for every character.
 * `accent` is picked from the dominant hair/outfit color of the D-1 frame and kept
 * pastel-leaning so it reads on a white background; `accentSoft` is a light tint for chips/backgrounds.
 * `key` is the lowercase English name from `sprites.characters.<id>.name` in en.json.
 * @type {ReadonlyArray<{id:number,key:string,accent:string,accentSoft:string,hair:string,outfit:string,vibe:string}>}
 */
export const SPRITE_CHARACTERS = Object.freeze([
  { id: 1, key: 'kai', accent: '#5FBF8E', accentSoft: 'rgba(95, 191, 142, 0.16)', hair: 'green short hair', outfit: 'blue sweater, yellow and purple legs', vibe: 'curious' },
  { id: 2, key: 'bruno', accent: '#9B6BD6', accentSoft: 'rgba(155, 107, 214, 0.16)', hair: 'purple long hair, beard', outfit: 'green shirt, pink pants', vibe: 'wise' },
  { id: 3, key: 'momo', accent: '#F28BB6', accentSoft: 'rgba(242, 139, 182, 0.16)', hair: 'pink hair', outfit: 'white and red top, green shorts', vibe: 'cheerful' },
  { id: 4, key: 'lily', accent: '#A98BE0', accentSoft: 'rgba(169, 139, 224, 0.16)', hair: 'blonde braided long hair', outfit: 'purple top, red pants', vibe: 'gentle' },
  { id: 5, key: 'nilo', accent: '#5B8DE8', accentSoft: 'rgba(91, 141, 232, 0.16)', hair: 'blue curly hair', outfit: 'pink top, dark pants', vibe: 'dreamy' },
  { id: 6, key: 'hazel', accent: '#B5835A', accentSoft: 'rgba(181, 131, 90, 0.16)', hair: 'brown ponytail', outfit: 'pink top with brown strap', vibe: 'steady' },
  { id: 7, key: 'sunny', accent: '#F2A93B', accentSoft: 'rgba(242, 169, 59, 0.16)', hair: 'blonde bob', outfit: 'orange-yellow top, purple pants', vibe: 'bright' },
  { id: 8, key: 'ruby', accent: '#D9674F', accentSoft: 'rgba(217, 103, 79, 0.16)', hair: 'auburn hair with braid', outfit: 'pink top, green pants', vibe: 'bold' },
  { id: 9, key: 'zane', accent: '#E05A5A', accentSoft: 'rgba(224, 90, 90, 0.16)', hair: 'blue swept hair', outfit: 'red top, green pants', vibe: 'cool' },
  { id: 10, key: 'theo', accent: '#6FB7E6', accentSoft: 'rgba(111, 183, 230, 0.16)', hair: 'dark-blonde dreadlocks', outfit: 'light-blue top, green pants', vibe: 'chill' },
  { id: 11, key: 'milo', accent: '#5A74C4', accentSoft: 'rgba(90, 116, 196, 0.16)', hair: 'light-brown curly hair', outfit: 'blue top, pink pants', vibe: 'playful' },
  { id: 12, key: 'rosa', accent: '#B05A8C', accentSoft: 'rgba(176, 90, 140, 0.16)', hair: 'dark-red big curly hair', outfit: 'purple top, red pants', vibe: 'lively' },
  { id: 13, key: 'nathan', accent: '#3E5BA9', accentSoft: 'rgba(62, 91, 169, 0.16)', hair: 'neat black side-swept hair', outfit: 'navy zip jacket, black pants, Canon camera', vibe: 'focused' }
])

/**
 * Character rendered with the "hero" aura / motion-trail effects
 * (see `assets/styles/heroSprite.css`).
 */
export const HERO_CHARACTER_ID = 13

/** True for the hero character id or any of its sprite paths. */
export function isHeroSprite(idOrPath) {
  if (typeof idOrPath === 'string' && idOrPath.includes('/')) {
    return new RegExp(`/sprites/${HERO_CHARACTER_ID}-`).test(idOrPath)
  }
  return Number(idOrPath) === HERO_CHARACTER_ID
}

/**
 * Look up a character's metadata by id.
 * @param {number|string} id - Character id (1-13).
 * @returns {{id:number,key:string,accent:string,accentSoft:string,hair:string,outfit:string,vibe:string}} Metadata, or a neutral default for unknown ids.
 */
export function getCharacterMeta(id) {
  const numericId = Number(id)
  return SPRITE_CHARACTERS.find((c) => c.id === numericId) || DEFAULT_CHARACTER
}

/**
 * Resolve the localized display name of a character.
 * @param {number|string} id - Character id (1-13).
 * @param {(key: string) => string} t - vue-i18n translate function.
 * @returns {string} Localized name from `sprites.characters.<id>.name`.
 */
export function getCharacterName(id, t) {
  return t(`sprites.characters.${id}.name`)
}

/**
 * Build the public path of a sprite frame.
 * Mirrors `buildSpritePath` in `spriteFetcher.js`; keep both in sync.
 * @param {number|string} id - Character id (1-13).
 * @param {string} [stance='D'] - Facing direction ('D', 'L', 'R', 'U').
 * @param {number} [frame=1] - Frame number (1 = idle, 2/3 = walk).
 * @returns {string} Image path such as `/sprites/3-D-1.png`.
 */
export const SPRITE_PATH = (id, stance = 'D', frame = 1) => `/sprites/${id}-${stance}-${frame}.png`
