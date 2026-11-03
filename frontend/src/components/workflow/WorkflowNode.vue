<script>
/*
 * Shared walk-cycle ticker.
 *
 * One requestAnimationFrame loop drives every active sprite on the canvas
 * (instead of one setInterval per node), frame swaps are written straight to
 * the <img> element (no Vue re-render per step), and the loop pauses while the
 * tab is hidden or while a sprite is scrolled out of view.
 */
const WALK_CYCLE = [1, 2, 1, 3] // 1 -> 2 -> 1 -> 3 (classic 4-step pixel-art gait)
const WALK_STEP_MS = 180

const walkers = new Set()
let rafId = null
let intersectionObserver = null
const observedWalkers = new WeakMap()

const isDocumentHidden = () => typeof document !== 'undefined' && document.hidden

function tick(now) {
  rafId = null
  let anyRunning = false
  for (const walker of walkers) {
    if (!walker.visible) continue
    anyRunning = true
    if (now - walker.lastStep >= walker.stepMs) {
      walker.lastStep = now
      walker.step = (walker.step + 1) % WALK_CYCLE.length
      walker.onFrame(WALK_CYCLE[walker.step])
    }
  }
  if (anyRunning && !isDocumentHidden()) {
    rafId = requestAnimationFrame(tick)
  }
}

function scheduleTicker() {
  if (rafId !== null || isDocumentHidden() || typeof requestAnimationFrame !== 'function') return
  for (const walker of walkers) {
    if (walker.visible) {
      rafId = requestAnimationFrame(tick)
      return
    }
  }
}

function stopTicker() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopTicker()
    } else {
      // Resume without a burst of catch-up frames
      const now = performance.now()
      for (const walker of walkers) walker.lastStep = now
      scheduleTicker()
    }
  })
}

function getIntersectionObserver() {
  if (intersectionObserver || typeof IntersectionObserver === 'undefined') return intersectionObserver
  intersectionObserver = new IntersectionObserver((entries) => {
    let becameVisible = false
    for (const entry of entries) {
      const walker = observedWalkers.get(entry.target)
      if (!walker) continue
      walker.visible = entry.isIntersecting
      if (walker.visible) becameVisible = true
    }
    if (becameVisible) scheduleTicker()
  })
  return intersectionObserver
}

function observeWalker(walker, el) {
  unobserveWalker(walker)
  if (!el) return
  const observer = getIntersectionObserver()
  walker.el = el
  if (!observer) {
    walker.visible = true
    scheduleTicker()
    return
  }
  observedWalkers.set(el, walker)
  observer.observe(el)
}

function unobserveWalker(walker) {
  if (walker.el && intersectionObserver) {
    intersectionObserver.unobserve(walker.el)
    observedWalkers.delete(walker.el)
  }
  walker.el = null
}

function addWalker(walker) {
  walker.step = 0
  walker.lastStep = typeof performance !== 'undefined' ? performance.now() : 0
  walkers.add(walker)
  scheduleTicker()
}

function removeWalker(walker) {
  walkers.delete(walker)
  unobserveWalker(walker)
  if (walkers.size === 0) stopTicker()
}
</script>

<script setup>
import { computed, ref, onUnmounted, watch } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { getNodeStyles } from '@/utils/colorUtils.js'
import { spriteFetcher } from '@/utils/spriteFetcher.js'
import { isHeroSprite } from '@/utils/spriteCharacters.js'
import RichTooltip from '@/components/common/RichTooltip.vue'
import { getNodeHelp } from '@/utils/helpContent.js'
import { configStore } from '@/stores/configStore.js'
import { useI18n } from 'vue-i18n'

const { t, te } = useI18n()

const props = defineProps({
  id: {
    type: String,
    required: true,
  },
  data: {
    type: Object,
    required: true,
  },
  isActive: {
    type: Boolean,
    default: false,
  },
  sprite: {
    type: String,
    default: '',
  },
  // Org-chart info of a team workflow: { parent, depth, members }
  team: {
    type: Object,
    default: null,
  },
})

// Expose hover events so parent can highlight edges
defineEmits(['hover', 'leave'])

// The <img> that shows the sprite (only one of the two template branches is mounted)
const spriteImgRef = ref(null)
let walker = null

// Random phase offset so neighbouring sprites do not bob in sync
const idleDelay = `-${(Math.random() * 2.4).toFixed(2)}s`

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Compute properties for reactivity
const nodeType = computed(() => props.data?.type || 'unknown')
// Display name of the node type; falls back to the raw type id when no translation exists
const nodeTypeLabel = computed(() => {
  const key = `components.workflow_node.types.${nodeType.value}`
  return /^[A-Za-z0-9_-]+$/.test(nodeType.value) && te(key) ? t(key) : nodeType.value
})
const nodeId = computed(() => props.data?.id || props.id)
const nodeDescription = computed(() => props.data?.description || '')
const isActive = computed(() => props.isActive)
const dynamicStyles = computed(() => getNodeStyles(nodeType.value))

// Palette variables are also applied to the sprite wrapper so the halo,
// shadow and working indicator can reuse the node's gradient/shadow colours.
const spriteStyles = computed(() => ({
  ...dynamicStyles.value,
  '--idle-delay': idleDelay,
}))

const nodeHelpContent = computed(() => getNodeHelp(nodeType.value))

const shouldShowTooltip = computed(() => configStore.ENABLE_HELP_TOOLTIPS && nodeHelpContent.value)

// Sprite path rendered by Vue: the idle frame of the bound character while active,
// the original sprite otherwise. The walk cycle swaps frames directly on the DOM.
const currentSprite = computed(() => {
  if (!props.sprite) return ''

  if (isActive.value) {
    return spriteFetcher.fetchSprite(nodeId.value, 'D', 1)
  }
  // When not active, use the original frame (1)
  return props.sprite
})

// Hero character: aura while idle, motion trail while the walk cycle runs
const isHero = computed(() => isHeroSprite(currentSprite.value))
const figureClass = computed(() =>
  isHero.value ? ['hero-sprite', 'hero-D', { 'is-moving': isActive.value }] : null
)
const figureStyle = computed(() =>
  isHero.value ? { '--hero-sprite': `url("${currentSprite.value}")` } : null
)

const applyFrame = (frame) => {
  const img = spriteImgRef.value
  if (!img) return
  const src = spriteFetcher.fetchSprite(nodeId.value, 'D', frame)
  if (img.getAttribute('src') !== src) img.setAttribute('src', src)
}

// Make sure all frames of the bound character are cached before we animate
watch(
  () => props.sprite,
  (sprite) => {
    if (!sprite) return
    const character = spriteFetcher.getCharacter(nodeId.value)
    if (character) spriteFetcher.preloadCharacter(character)
  },
  { immediate: true }
)

// Start/stop walking animation based on active state
const startWalking = () => {
  if (walker) return

  // Reduced motion: no walk cycle at all, the sprite simply stays on its idle frame
  if (prefersReducedMotion()) {
    applyFrame(1)
    return
  }

  walker = {
    stepMs: WALK_STEP_MS,
    step: 0,
    lastStep: 0,
    visible: false,
    el: null,
    onFrame: applyFrame,
  }
  observeWalker(walker, spriteImgRef.value)
  addWalker(walker)
}

const stopWalking = () => {
  if (!walker) return
  removeWalker(walker)
  walker = null
  applyFrame(1) // Back to the idle frame
}

// Watch for active state changes
watch(
  isActive,
  (newActive) => {
    if (newActive) {
      startWalking()
    } else {
      stopWalking()
    }
  },
  { immediate: true }
)

// The <img> is re-created when the tooltip wrapper toggles; keep the observer on the live element
watch(spriteImgRef, (el) => {
  if (walker) observeWalker(walker, el)
})

// Cleanup on unmount
onUnmounted(() => {
  stopWalking()
})
</script>

<template>
  <RichTooltip v-if="shouldShowTooltip" :content="nodeHelpContent" placement="top">
    <div class="workflow-node-container" :class="{ 'is-active': isActive }">
      <div v-if="props.sprite" class="workflow-node-sprite" :style="spriteStyles">
        <span v-if="isActive" class="sprite-halo" aria-hidden="true"></span>
        <div class="sprite-figure" :class="figureClass" :style="figureStyle">
          <img
            ref="spriteImgRef"
            :src="currentSprite"
            :alt="$t('components.workflow_node.sprite_alt', { id: nodeId })"
            class="node-sprite-image"
            draggable="false"
          />
        </div>
        <span v-if="isActive" class="sprite-working" aria-hidden="true">
          <i></i><i></i><i></i>
        </span>
      </div>
      <div
        class="workflow-node"
        :class="{ 'workflow-node-active': isActive }"
        :data-type="nodeType"
        :style="dynamicStyles"
        @mouseenter="$emit('hover', nodeId)"
        @mouseleave="$emit('leave', nodeId)"
      >
        <div class="workflow-node-header">
          <span class="workflow-node-type">{{ nodeTypeLabel }}</span>
          <span class="workflow-node-id">{{ nodeId }}</span>
        </div>
        <div v-if="nodeDescription" class="workflow-node-description">
          {{ nodeDescription }}
        </div>
        <div v-if="team && (team.members.length || team.parent)" class="node-team">
          <span v-if="team.members.length" class="team-chip is-lead">{{ $t('components.workflow_node.team_lead', { n: team.members.length }) }}</span>
          <span v-if="team.parent" class="team-chip" :title="team.parent">{{ $t('components.workflow_node.member_of', { name: team.parent }) }}</span>
        </div>

        <Handle
          id="source"
          type="source"
          :position="Position.Right"
          class="workflow-node-handle"
        />
        <Handle
          id="target"
          type="target"
          :position="Position.Left"
          class="workflow-node-handle"
        />
      </div>
    </div>
  </RichTooltip>
  <div v-else class="workflow-node-container" :class="{ 'is-active': isActive }">
    <div v-if="props.sprite" class="workflow-node-sprite" :style="spriteStyles">
      <span v-if="isActive" class="sprite-halo" aria-hidden="true"></span>
      <div class="sprite-figure" :class="figureClass" :style="figureStyle">
        <img
          ref="spriteImgRef"
          :src="currentSprite"
          :alt="$t('components.workflow_node.sprite_alt', { id: nodeId })"
          class="node-sprite-image"
          draggable="false"
        />
      </div>
      <span v-if="isActive" class="sprite-working" aria-hidden="true">
        <i></i><i></i><i></i>
      </span>
    </div>
    <div
      class="workflow-node"
      :class="{ 'workflow-node-active': isActive }"
      :data-type="nodeType"
      :style="dynamicStyles"
      @mouseenter="$emit('hover', nodeId)"
      @mouseleave="$emit('leave', nodeId)"
    >
      <div class="workflow-node-header">
        <span class="workflow-node-type">{{ nodeTypeLabel }}</span>
        <span class="workflow-node-id">{{ nodeId }}</span>
      </div>
      <div v-if="nodeDescription" class="workflow-node-description">
        {{ nodeDescription }}
      </div>
      <div v-if="team && (team.members.length || team.parent)" class="node-team">
        <span v-if="team.members.length" class="team-chip is-lead">{{ $t('components.workflow_node.team_lead', { n: team.members.length }) }}</span>
        <span v-if="team.parent" class="team-chip" :title="team.parent">{{ $t('components.workflow_node.member_of', { name: team.parent }) }}</span>
      </div>

      <Handle
        id="source"
        type="source"
        :position="Position.Right"
        class="workflow-node-handle"
      />
      <Handle
        id="target"
        type="target"
        :position="Position.Left"
        class="workflow-node-handle"
      />
    </div>
  </div>
</template>

<style scoped>
.workflow-node-container {
  position: relative;
  /* The sprite stands above the card; never clip it */
  overflow: visible;
}

.workflow-node-description {
  /* Ensure long descriptions wrap instead of overflowing */
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-width: 200px;
  display: block;
}

/* ---------------------------------------------------------------------------
 * Sprite: a chibi character standing on top of the node card
 * ------------------------------------------------------------------------- */
.workflow-node-sprite {
  /* Public sizing knobs */
  --sprite-size: 60px;          /* rendered height of the character */
  --sprite-overlap: 7px;        /* how far the feet dip below the card's top edge */
  --sprite-shadow-w: calc(var(--sprite-size) * 0.62);
  --sprite-shadow-h: calc(var(--sprite-size) * 0.16);
  --sprite-halo-size: calc(var(--sprite-size) * 1.25);
  --idle-delay: 0s;
  /* Palette fallbacks (overridden by getNodeStyles via inline vars) */
  --node-gradient: linear-gradient(135deg, var(--accent-indigo), var(--accent-sky), var(--accent-green-1));
  --node-shadow-color: rgb(var(--accent-sky-rgb) / 0.5);
  --node-text-gradient: linear-gradient(135deg, var(--accent-indigo), var(--accent-sky), var(--accent-green-1));

  position: absolute;
  /* Anchor by the feet so the sprite height never affects the offset */
  bottom: calc(100% - var(--sprite-overlap));
  left: 50%;
  transform: translateX(-50%);
  width: var(--sprite-size);
  height: var(--sprite-size);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  z-index: 10;
  pointer-events: none;
  user-select: none;
}

/* Soft elliptical ground shadow that keeps the character grounded */
.workflow-node-sprite::before {
  content: '';
  position: absolute;
  left: 50%;
  bottom: calc(var(--sprite-shadow-h) * -0.45);
  width: var(--sprite-shadow-w);
  height: var(--sprite-shadow-h);
  transform: translateX(-50%);
  transform-origin: 50% 50%;
  border-radius: 50%;
  background: radial-gradient(ellipse at center, rgb(var(--shade) / 0.42) 0%, rgb(var(--shade) / 0.18) 45%, rgb(var(--shade) / 0) 72%);
  filter: blur(1.5px);
  opacity: 0.9;
  z-index: 0;
  animation: sprite-shadow-breathe 2.4s ease-in-out infinite;
  animation-delay: var(--idle-delay);
}

/* Wrapper used for hover lift so it does not fight the idle keyframes on the image */
.sprite-figure {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: 100%;
  transform-origin: 50% 100%;
  transition: transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Subtle contact shadow + a faint rim so the figure reads as a figure, not an icon.
   Set on the image itself (not the wrapper): the image's idle bob is a transform,
   so the filtered image is rasterised once and just moved, instead of the wrapper
   re-filtering its animated child every frame. Hero sprites bring their own glow. */
.sprite-figure:not(.hero-sprite) .node-sprite-image {
  filter: drop-shadow(0 3px 2px rgb(var(--shade) / 0.35)) drop-shadow(0 0 1px rgb(var(--ink) / 0.18));
}

.node-sprite-image {
  display: block;
  height: var(--sprite-size);
  width: auto;
  max-width: var(--sprite-size);
  object-fit: contain;
  object-position: 50% 100%;
  /* Keep the pixel art crisp when scaled up */
  image-rendering: crisp-edges;
  image-rendering: pixelated;
  -ms-interpolation-mode: nearest-neighbor;
  transform-origin: 50% 100%;
  animation: sprite-idle-bob 2.4s ease-in-out infinite;
  animation-delay: var(--idle-delay);
}

/* Hover: a gentle lift, in sync with the card lifting underneath */
.workflow-node-container:hover .sprite-figure {
  transform: translateY(-2px) scale(1.04);
}

/* ---------------------------------------------------------------------------
 * Active state: halo, walk cycle (JS driven) and a "working" indicator
 * ------------------------------------------------------------------------- */
.workflow-node-container.is-active .node-sprite-image {
  /* The walk cycle provides the motion; stop the idle bob */
  animation: none;
}

.workflow-node-container.is-active .workflow-node-sprite::before {
  animation: none;
  transform: translateX(-50%) scaleX(1.05);
  opacity: 1;
}

.sprite-halo {
  position: absolute;
  left: 50%;
  bottom: calc(var(--sprite-size) * 0.08);
  width: var(--sprite-halo-size);
  height: var(--sprite-halo-size);
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(circle at center, var(--node-shadow-color) 0%, transparent 68%);
  filter: blur(4px) saturate(1.2);
  opacity: 0.85;
  z-index: 1;
  animation: sprite-halo-pulse 2s ease-in-out infinite;
}

/* Gradient ring on the halo for a little more definition */
.sprite-halo::after {
  content: '';
  position: absolute;
  inset: 18%;
  border-radius: 50%;
  background: var(--node-gradient);
  opacity: 0.35;
  filter: blur(6px);
}

/* Three bouncing dots floating next to the head */
.sprite-working {
  position: absolute;
  top: calc(var(--sprite-size) * -0.08);
  left: calc(50% + var(--sprite-size) * 0.26);
  display: flex;
  gap: 3px;
  align-items: flex-end;
  padding: 3px 5px;
  border-radius: 999px;
  /* Solid pill instead of backdrop-filter: a backdrop blur over a sprite that
     changes every walk step would re-blur on every frame */
  background: rgb(var(--panel-20) / 0.8);
  box-shadow: 0 0 0 1px rgb(var(--ink) / 0.12), 0 2px 6px rgb(var(--shade) / 0.35);
  z-index: 3;
  animation: sprite-working-in 0.3s var(--ease-out) both;
}

.sprite-working i {
  display: block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--node-gradient);
  filter: brightness(1.25);
  animation: sprite-dot-bounce 1.1s ease-in-out infinite;
}

/* Light theme: pastel dots vanish on the white pill; use the saturated palette twin */
:root[data-theme="light"] .sprite-working i {
  background: var(--node-text-gradient);
  filter: none;
}

.sprite-working i:nth-child(2) {
  animation-delay: 0.15s;
}

.sprite-working i:nth-child(3) {
  animation-delay: 0.3s;
}

/* ---------------------------------------------------------------------------
 * Keyframes
 * ------------------------------------------------------------------------- */
@keyframes sprite-idle-bob {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1.5px);
  }
}

@keyframes sprite-shadow-breathe {
  0%, 100% {
    transform: translateX(-50%) scaleX(1);
    opacity: 0.9;
  }
  50% {
    transform: translateX(-50%) scaleX(0.92);
    opacity: 0.72;
  }
}

@keyframes sprite-halo-pulse {
  0%, 100% {
    transform: translateX(-50%) scale(0.92);
    opacity: 0.65;
  }
  50% {
    transform: translateX(-50%) scale(1.08);
    opacity: 0.95;
  }
}

@keyframes sprite-dot-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.7;
  }
  30% {
    transform: translateY(-3px);
    opacity: 1;
  }
}

@keyframes sprite-working-in {
  from {
    opacity: 0;
    transform: translateY(4px) scale(0.8);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* ---------------------------------------------------------------------------
 * Accessibility: respect reduced motion
 * ------------------------------------------------------------------------- */
@media (prefers-reduced-motion: reduce) {
  .node-sprite-image,
  .workflow-node-sprite::before,
  .sprite-halo,
  .sprite-working,
  .sprite-working i {
    animation: none !important;
  }

  .sprite-figure {
    transition: none;
  }
}

/* ---------------------------------------------------------------------------
 * Org-chart chips (team leads and who they report to)
 * ------------------------------------------------------------------------- */
.node-team {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.team-chip {
  max-width: 100%;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.02em;
  color: var(--text-muted-6);
  background: rgb(var(--ink) / 0.06);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.12);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.team-chip.is-lead {
  color: var(--text-strong);
  background: rgb(var(--ink) / 0.1);
  box-shadow: inset 0 0 0 1px var(--node-shadow-color);
}
</style>
