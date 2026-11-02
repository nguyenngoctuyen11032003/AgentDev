<template>
  <div class="sprite-gallery">
    <header class="gallery-header">
      <h1 class="gallery-title">{{ $t('sprites.gallery.title') }}</h1>
      <p class="gallery-subtitle">{{ $t('sprites.gallery.subtitle') }}</p>
    </header>

    <div class="gallery-layout">
      <!-- Character grid -->
      <section class="gallery-grid" :aria-label="$t('sprites.gallery.character')">
        <button
          v-for="(character, index) in SPRITE_CHARACTERS"
          :key="character.id"
          type="button"
          class="character-card"
          :class="{ 'is-selected': character.id === selectedId, 'is-walking': character.id === hoveredId }"
          :style="cardStyle(character, index)"
          :aria-pressed="character.id === selectedId"
          @mouseenter="onCardEnter(character.id)"
          @mouseleave="onCardLeave(character.id)"
          @focus="onCardEnter(character.id)"
          @blur="onCardLeave(character.id)"
          @click="selectCharacter(character.id)"
        >
          <span class="card-stage">
            <span class="sprite-figure">
              <span class="sprite-ground" aria-hidden="true"></span>
              <img
                class="sprite-image"
                :src="cardSprite(character.id)"
                :alt="getCharacterName(character.id, t)"
                width="96"
                height="96"
                decoding="async"
                draggable="false"
              />
            </span>
          </span>
          <span class="card-body">
            <span class="card-name">{{ getCharacterName(character.id, t) }}</span>
            <span class="card-tagline">{{ $t('sprites.characters.' + character.id + '.tagline') }}</span>
            <span class="card-meta">
              <span class="accent-chip" :style="{ background: character.accent }" aria-hidden="true"></span>
              <span class="accent-hex">{{ character.accent }}</span>
            </span>
          </span>
        </button>
      </section>

      <!-- Detail / preview panel -->
      <aside class="detail-panel" ref="panelRef" :style="panelStyle">
        <div class="detail-heading">
          <span class="detail-label">{{ $t('sprites.gallery.character') }}</span>
          <h2 class="detail-name">{{ getCharacterName(selectedId, t) }}</h2>
          <p class="detail-tagline">{{ $t('sprites.characters.' + selectedId + '.tagline') }}</p>
        </div>

        <!-- Large preview; the dotted grid helps judge pixel crispness at any size -->
        <div class="preview-stage">
          <div class="preview-figure" :style="{ '--preview-size': previewSize + 'px' }">
            <span class="sprite-ground" aria-hidden="true"></span>
            <img
              class="sprite-image preview-image"
              :class="{ 'is-static': mode === 'walk' }"
              :src="previewPath"
              :alt="getCharacterName(selectedId, t)"
              decoding="async"
              draggable="false"
            />
          </div>
        </div>

        <!-- Direction: segmented control -->
        <div class="control-group">
          <span class="control-label" id="direction-label">{{ $t('sprites.gallery.direction') }}</span>
          <div class="segmented" role="radiogroup" aria-labelledby="direction-label">
            <button
              v-for="stance in SPRITE_STANCES"
              :key="stance"
              type="button"
              class="segment"
              :class="{ 'is-active': stance === direction }"
              role="radio"
              :aria-checked="stance === direction"
              @click="direction = stance"
            >
              <span class="segment-arrow" aria-hidden="true">{{ STANCE_ARROWS[stance] }}</span>
              <span class="segment-key">{{ stance }}</span>
            </button>
          </div>
        </div>

        <!-- Idle / walk toggle -->
        <div class="control-group">
          <span class="control-label" id="mode-label">{{ $t('sprites.gallery.frame') }}</span>
          <div class="segmented" role="radiogroup" aria-labelledby="mode-label">
            <button
              type="button"
              class="segment"
              :class="{ 'is-active': mode === 'idle' }"
              role="radio"
              :aria-checked="mode === 'idle'"
              @click="mode = 'idle'"
            >{{ $t('sprites.gallery.idle') }}</button>
            <button
              type="button"
              class="segment"
              :class="{ 'is-active': mode === 'walk' }"
              role="radio"
              :aria-checked="mode === 'walk'"
              @click="mode = 'walk'"
            >{{ $t('sprites.gallery.walk') }}</button>
          </div>
        </div>

        <!-- Size slider -->
        <div class="control-group">
          <label class="control-label control-label-row" for="preview-size">
            <span>{{ $t('sprites.gallery.preview_size') }}</span>
            <span class="control-value">{{ previewSize }}px</span>
          </label>
          <input
            id="preview-size"
            v-model.number="previewSize"
            class="size-slider"
            type="range"
            min="32"
            max="256"
            step="8"
          />
        </div>

        <!-- Copy path -->
        <div class="copy-row">
          <code class="path-code" :title="previewPath">{{ previewPath }}</code>
          <button type="button" class="copy-button" :class="{ 'is-copied': copied }" @click="copyPath">
            <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <span>{{ copied ? $t('sprites.gallery.copied') : $t('sprites.gallery.copy_path') }}</span>
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'SpriteGalleryView' })
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { SPRITE_CHARACTERS, getCharacterMeta, getCharacterName } from '@/utils/spriteCharacters'
import { buildSpritePath, SPRITE_STANCES, spriteFetcher } from '@/utils/spriteFetcher'

const { t } = useI18n()

/** Walk cycle order and timing (1 = idle, 2/3 = stride frames). */
const WALK_CYCLE = [1, 2, 1, 3]
const WALK_STEP_MS = 180
/** Slower stepping for users who prefer reduced motion. */
const WALK_STEP_REDUCED_MS = 600

/** Arrow glyphs for the direction segmented control (language neutral). */
const STANCE_ARROWS = { D: '↓', L: '←', R: '→', U: '↑' }

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Create a small interval-driven walker that reports the current frame.
 * @param {(frame: number) => void} onFrame
 */
function createWalker(onFrame) {
  let timer = null
  let step = 0
  return {
    start() {
      if (timer) return
      step = 0
      onFrame(WALK_CYCLE[0])
      const stepMs = prefersReducedMotion() ? WALK_STEP_REDUCED_MS : WALK_STEP_MS
      timer = setInterval(() => {
        step = (step + 1) % WALK_CYCLE.length
        onFrame(WALK_CYCLE[step])
      }, stepMs)
    },
    stop() {
      if (timer) clearInterval(timer)
      timer = null
      step = 0
      onFrame(1)
    }
  }
}

/* ---------- Card grid: hover walk cycle ---------- */

const hoveredId = ref(null)
const hoverFrame = ref(1)
const hoverWalker = createWalker((frame) => { hoverFrame.value = frame })

const cardSprite = (id) =>
  buildSpritePath(id, 'D', id === hoveredId.value ? hoverFrame.value : 1)

const onCardEnter = (id) => {
  spriteFetcher.preloadCharacter(id)
  if (hoveredId.value === id) return
  hoverWalker.stop()
  hoveredId.value = id
  hoverWalker.start()
}

const onCardLeave = (id) => {
  if (hoveredId.value !== id) return
  hoverWalker.stop()
  hoveredId.value = null
}

/** Per-card CSS variables: pastel tint, accent and a staggered idle bob. */
const cardStyle = (character, index) => ({
  '--card-tint': character.accentSoft,
  '--card-accent': character.accent,
  '--idle-delay': '-' + ((index * 0.37) % 2.4).toFixed(2) + 's'
})

/* ---------- Detail panel ---------- */

const panelRef = ref(null)
const selectedId = ref(SPRITE_CHARACTERS[0]?.id ?? 1)
const direction = ref('D')
const mode = ref('idle')
const previewFrame = ref(1)
const previewSize = ref(192)
const previewWalker = createWalker((frame) => { previewFrame.value = frame })

const selectedMeta = computed(() => getCharacterMeta(selectedId.value) || {})

const panelStyle = computed(() => ({
  '--card-tint': selectedMeta.value.accentSoft || 'transparent',
  '--card-accent': selectedMeta.value.accent || 'var(--accent-sky)'
}))

const previewPath = computed(() =>
  buildSpritePath(selectedId.value, direction.value, mode.value === 'walk' ? previewFrame.value : 1)
)

const selectCharacter = (id) => {
  selectedId.value = id
  spriteFetcher.preloadCharacter(id)
  // On narrow layouts the panel sits below the grid; bring it into view.
  if (typeof window !== 'undefined' && window.innerWidth < 960 && panelRef.value) {
    panelRef.value.scrollIntoView({
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      block: 'nearest'
    })
  }
}

watch(mode, (value) => {
  if (value === 'walk') previewWalker.start()
  else previewWalker.stop()
})

/* ---------- Copy path ---------- */

const copied = ref(false)
let copiedTimer = null

const copyPath = async () => {
  const text = previewPath.value
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      // Fallback for insecure contexts: a transient textarea + execCommand
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    copied.value = true
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 1600)
  } catch (error) {
    console.warn('Failed to copy sprite path', error)
  }
}

/* ---------- Lifecycle ---------- */

onMounted(() => {
  spriteFetcher.preloadCharacter(selectedId.value)
  // Warm the remaining frames lazily so direction switches never flash.
  spriteFetcher.preloadAll()
})

onBeforeUnmount(() => {
  hoverWalker.stop()
  previewWalker.stop()
  if (copiedTimer) clearTimeout(copiedTimer)
})
</script>

<style scoped>
.sprite-gallery {
  box-sizing: border-box;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px 56px;
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
}

/* ---------- Header ---------- */

.gallery-header {
  margin-bottom: 28px;
}

.gallery-title {
  margin: 0 0 6px;
  font-size: 28px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo));
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  width: fit-content;
}

/* Light theme: deeper gradient so the title stays crisp on white */
:root[data-theme="light"] .gallery-title {
  background: linear-gradient(90deg, #047857, #0369a1, #4338ca);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.gallery-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-muted-4);
  max-width: 60ch;
}

/* ---------- Layout ---------- */

.gallery-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
  align-items: start;
}

@media (max-width: 960px) {
  .gallery-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* ---------- Card grid ---------- */

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
}

.character-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  margin: 0;
  padding: 0;
  border-radius: 18px;
  border: 1px solid rgb(var(--ink) / 0.08);
  /* accentSoft is a translucent pastel; layer it over the surface token */
  background:
    linear-gradient(180deg, var(--card-tint) 0%, transparent 100%),
    var(--surface-1);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.08), 0 8px 24px -12px rgb(var(--shade) / 0.25);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.25s ease, border-color 0.25s ease;
}

/* Light theme: stack the tint twice so the pastel reads on white */
:root[data-theme="light"] .character-card {
  background:
    linear-gradient(180deg, var(--card-tint) 0%, transparent 100%),
    linear-gradient(180deg, var(--card-tint) 0%, transparent 70%),
    var(--surface-1);
  border-color: var(--line-4);
}

.character-card:hover,
.character-card:focus-visible {
  transform: translateY(-4px);
  box-shadow: 0 2px 4px rgb(var(--shade) / 0.08), 0 18px 36px -14px rgb(var(--shade) / 0.35);
  border-color: color-mix(in srgb, var(--card-accent) 45%, transparent);
}

.character-card:focus-visible {
  outline: 2px solid var(--card-accent);
  outline-offset: 2px;
}

.character-card.is-selected {
  border-color: color-mix(in srgb, var(--card-accent) 70%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--card-accent) 22%, transparent),
    0 12px 28px -14px rgb(var(--shade) / 0.35);
}

.card-stage {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: 132px;
  padding-bottom: 14px;
}

/* ---------- Sprite figure (shared by cards and preview) ---------- */

.sprite-figure {
  --sprite-size: 96px;
  position: relative;
  display: inline-flex;
  align-items: flex-end;
  justify-content: center;
  height: var(--sprite-size);
}

.sprite-ground {
  position: absolute;
  left: 50%;
  bottom: calc(var(--sprite-size) * -0.07);
  width: calc(var(--sprite-size) * 0.62);
  height: calc(var(--sprite-size) * 0.16);
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(ellipse at center, rgb(var(--shade) / 0.38) 0%, rgb(var(--shade) / 0.16) 45%, rgb(var(--shade) / 0) 72%);
  pointer-events: none;
  animation: sprite-shadow-breathe 2.4s ease-in-out infinite;
  animation-delay: var(--idle-delay, 0s);
}

.sprite-image {
  position: relative;
  display: block;
  height: var(--sprite-size);
  width: auto;
  max-width: none;
  object-fit: contain;
  object-position: 50% 100%;
  /* Keep the pixel art crisp when scaled */
  image-rendering: crisp-edges;
  image-rendering: pixelated;
  -ms-interpolation-mode: nearest-neighbor;
  transform-origin: 50% 100%;
  animation: sprite-idle-bob 2.4s ease-in-out infinite;
  animation-delay: var(--idle-delay, 0s);
  user-select: none;
  -webkit-user-drag: none;
}

/* While walking, the stride frames carry the motion; stop the bob */
.character-card.is-walking .sprite-image,
.sprite-image.is-static {
  animation: none;
  transform: none;
}

.character-card.is-walking .sprite-ground {
  animation: none;
}

/* ---------- Card body ---------- */

.card-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px 14px;
  border-top: 1px solid rgb(var(--ink) / 0.05);
}

.card-name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.card-tagline {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted-4);
}

.card-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.accent-chip {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(var(--ink) / 0.12);
  flex: none;
}

.accent-hex {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10.5px;
  letter-spacing: 0.02em;
  color: var(--text-muted-5);
  text-transform: lowercase;
}

/* ---------- Detail panel ---------- */

.detail-panel {
  position: sticky;
  top: 71px; /* 55px sidebar + 16px breathing room */
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px;
  border-radius: 20px;
  border: 1px solid rgb(var(--ink) / 0.08);
  background:
    linear-gradient(180deg, var(--card-tint) 0%, transparent 55%),
    var(--surface-1);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.08), 0 12px 32px -16px rgb(var(--shade) / 0.3);
  transition: background 0.3s ease, border-color 0.3s ease;
}

:root[data-theme="light"] .detail-panel {
  border-color: var(--line-4);
}

:root[data-theme="light"] .card-body {
  border-top-color: var(--line-1);
}

:root[data-theme="light"] .preview-stage,
:root[data-theme="light"] .copy-button {
  border-color: var(--line-4);
}

/* The light border overrides above out-rank the accent states; restore them */
:root[data-theme="light"] .character-card:hover,
:root[data-theme="light"] .character-card:focus-visible,
:root[data-theme="light"] .copy-button:hover {
  border-color: color-mix(in srgb, var(--card-accent) 60%, transparent);
}

:root[data-theme="light"] .character-card.is-selected,
:root[data-theme="light"] .copy-button.is-copied {
  border-color: color-mix(in srgb, var(--card-accent) 80%, transparent);
}

@media (max-width: 960px) {
  .detail-panel {
    position: static;
  }
}

.detail-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted-4);
}

.detail-name {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-1);
}

.detail-tagline {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--text-muted-4);
}

/* Preview stage with a faint dot grid so pixel edges are easy to judge */
.preview-stage {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  min-height: 160px;
  padding: 24px 12px 28px;
  border-radius: 14px;
  border: 1px solid rgb(var(--ink) / 0.07);
  background-color: var(--surface-4);
  background-image: radial-gradient(rgb(var(--ink) / 0.09) 1px, transparent 1px);
  background-size: 12px 12px;
  overflow: auto;
}

.preview-figure {
  --sprite-size: var(--preview-size, 192px);
  position: relative;
  display: inline-flex;
  align-items: flex-end;
  justify-content: center;
  height: var(--sprite-size);
  transition: height 0.15s ease;
}

.preview-image {
  animation-delay: -0.6s;
}

/* ---------- Controls ---------- */

.control-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.control-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft-1);
}

.control-label-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.control-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-muted-4);
}

.segmented {
  display: flex;
  padding: 3px;
  gap: 2px;
  border-radius: 10px;
  background: rgb(var(--ink) / 0.06);
}

.segment {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted-4);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.segment:hover {
  color: var(--text-1);
}

.segment.is-active {
  background: var(--surface-1);
  color: var(--text-1);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.12), 0 0 0 1px color-mix(in srgb, var(--card-accent) 40%, transparent);
}

.segment:focus-visible {
  outline: 2px solid var(--card-accent);
  outline-offset: 1px;
}

.segment-arrow {
  font-size: 13px;
  line-height: 1;
}

.segment-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px;
}

/* Range slider themed with the character accent */
.size-slider {
  width: 100%;
  margin: 0;
  accent-color: var(--card-accent);
  cursor: pointer;
}

/* ---------- Copy row ---------- */

.copy-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.path-code {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgb(var(--ink) / 0.06);
  color: var(--text-soft-1);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.copy-button {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: var(--surface-1);
  color: var(--text-1);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.15s ease;
}

.copy-button:hover {
  border-color: color-mix(in srgb, var(--card-accent) 60%, transparent);
  transform: translateY(-1px);
}

.copy-button:focus-visible {
  outline: 2px solid var(--card-accent);
  outline-offset: 1px;
}

.copy-button.is-copied {
  background: color-mix(in srgb, var(--card-accent) 22%, var(--surface-1));
  border-color: color-mix(in srgb, var(--card-accent) 70%, transparent);
  color: var(--text-1);
}

/* ---------- Keyframes ---------- */

@keyframes sprite-idle-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

@keyframes sprite-shadow-breathe {
  0%, 100% { transform: translateX(-50%) scale(1); opacity: 1; }
  50% { transform: translateX(-50%) scale(0.92); opacity: 0.8; }
}

/* ---------- Reduced motion ---------- */

@media (prefers-reduced-motion: reduce) {
  .sprite-image,
  .sprite-ground {
    animation: none;
  }

  .character-card,
  .character-card:hover,
  .character-card:focus-visible,
  .copy-button:hover {
    transform: none;
  }

  .preview-figure {
    transition: none;
  }
}
</style>
