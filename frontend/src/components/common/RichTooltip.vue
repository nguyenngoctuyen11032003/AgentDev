<template>
  <div
    ref="wrapperRef"
    class="tooltip-wrapper"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @focus="handleFocus"
    @blur="handleBlur"
    @keydown.space.prevent="handleKeyboardActivate"
    @keydown.enter.prevent="handleKeyboardActivate"
    @keydown.escape="handleDismiss"
  >
    <slot></slot>

    <teleport to="body">
      <transition name="tooltip-fade">
        <div
          v-if="isVisible"
          ref="tooltipRef"
          class="rich-tooltip"
          :class="[`tooltip-${placement}`, { 'tooltip-keyboard-active': keyboardActive }]"
          :style="tooltipStyle"
          role="tooltip"
          @mouseenter="handleTooltipMouseEnter"
          @mouseleave="handleTooltipMouseLeave"
        >
          <div class="tooltip-content">
            <h4 v-if="content.title" class="tooltip-title">{{ $t(content.title) }}</h4>
            <template v-if="content.descriptions && content.descriptions.length">
              <p v-for="(desc, index) in content.descriptions" :key="'desc-'+index" class="tooltip-description">{{ $t(desc) }}</p>
            </template>
            <p v-else-if="content.description" class="tooltip-description">{{ $t(content.description) }}</p>
            <ul v-if="content.examples && content.examples.length" class="tooltip-examples">
              <li v-for="(example, index) in content.examples" :key="index">{{ $t(example) }}</li>
            </ul>
            <a
              v-if="content.learnMoreUrl"
              :href="content.learnMoreUrl"
              target="_blank"
              rel="noopener"
              class="tooltip-learn-more"
              @click="handleLearnMore"
            >
              {{ $t('components.rich_tooltip.learn_more') }}
            </a>
          </div>
          <div class="tooltip-arrow" :data-placement="placement"></div>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  content: {
    type: Object,
    required: true,
    validator: (value) => {
      return value && typeof value.description === 'string'
    }
  },
  delay: {
    type: Number,
    default: 500
  },
  placement: {
    type: String,
    default: 'top',
    validator: (value) => ['top', 'bottom', 'left', 'right'].includes(value)
  }
})

const isVisible = ref(false)
const tooltipRef = ref(null)
const wrapperRef = ref(null)
const tooltipStyle = ref({})
const keyboardActive = ref(false)

// Plain (non-reactive) bookkeeping: timers and flags never drive rendering.
let hoverTimeout = null
let leaveTimeout = null
let resizeRaf = 0
let mouseInTooltip = false
let listenersAttached = false

const handleMouseEnter = () => {
  keyboardActive.value = false
  clearTimeout(leaveTimeout)
  clearTimeout(hoverTimeout)
  hoverTimeout = setTimeout(() => {
    showTooltip()
  }, props.delay)
}

const handleMouseLeave = () => {
  clearTimeout(hoverTimeout)
  // Delay hiding to allow moving into tooltip
  clearTimeout(leaveTimeout)
  leaveTimeout = setTimeout(() => {
    if (!mouseInTooltip) {
      hideTooltip()
    }
  }, 100)
}

const handleFocus = () => {
  // Don't auto-show on focus, wait for keyboard activation
}

const handleBlur = () => {
  if (keyboardActive.value) {
    hideTooltip()
    keyboardActive.value = false
  }
}

const handleKeyboardActivate = () => {
  keyboardActive.value = true
  showTooltip()
}

const handleDismiss = () => {
  hideTooltip()
  keyboardActive.value = false
}

const handleTooltipMouseEnter = () => {
  mouseInTooltip = true
}

const handleTooltipMouseLeave = () => {
  mouseInTooltip = false
  hideTooltip()
}

const handleLearnMore = () => {
  // Keep tooltip open when clicking learn more
  // The link will open in new tab
}

const showTooltip = async () => {
  if (isVisible.value) return
  isVisible.value = true
  attachListeners()
  await nextTick()
  calculatePosition()
}

const hideTooltip = () => {
  if (!isVisible.value) return
  isVisible.value = false
  detachListeners()
  // The last computed position is kept so the leave transition fades out in
  // place instead of jumping to the element's static (end-of-body) position.
}

// Position is computed once per show (and once per frame on resize), never on mousemove.
const calculatePosition = () => {
  if (!tooltipRef.value || !wrapperRef.value) return

  const wrapper = wrapperRef.value.getBoundingClientRect()
  const tooltip = tooltipRef.value.getBoundingClientRect()
  const viewport = {
    width: window.innerWidth,
    height: window.innerHeight
  }

  const offset = 12 // Distance from target element
  let top = 0
  let left = 0

  // Calculate initial position based on preferred placement
  switch (props.placement) {
    case 'top':
      top = wrapper.top - tooltip.height - offset
      left = wrapper.left + (wrapper.width / 2) - (tooltip.width / 2)
      break
    case 'bottom':
      top = wrapper.bottom + offset
      left = wrapper.left + (wrapper.width / 2) - (tooltip.width / 2)
      break
    case 'left':
      top = wrapper.top + (wrapper.height / 2) - (tooltip.height / 2)
      left = wrapper.left - tooltip.width - offset
      break
    case 'right':
      top = wrapper.top + (wrapper.height / 2) - (tooltip.height / 2)
      left = wrapper.right + offset
      break
  }

  // Adjust if tooltip would go off-screen
  if (left < 10) {
    left = 10
  } else if (left + tooltip.width > viewport.width - 10) {
    left = viewport.width - tooltip.width - 10
  }

  if (top < 10) {
    // If it would go above viewport, flip to bottom
    if (props.placement === 'top') {
      top = wrapper.bottom + offset
    } else {
      top = 10
    }
  } else if (top + tooltip.height > viewport.height - 10) {
    // If it would go below viewport, flip to top
    if (props.placement === 'bottom') {
      top = wrapper.top - tooltip.height - offset
    } else {
      top = viewport.height - tooltip.height - 10
    }
  }

  tooltipStyle.value = {
    top: `${top}px`,
    left: `${left}px`
  }
}

// Listen to scroll and zoom events to dismiss tooltip
const handleScroll = (event) => {
  if (event.target instanceof Element && event.target.closest('[data-local-scroll]')) {
    return
  }

  if (isVisible.value && !keyboardActive.value) {
    hideTooltip()
  }
}

// Re-position at most once per frame while the window is being resized
const handleResize = () => {
  if (!isVisible.value || resizeRaf) return
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = 0
    if (isVisible.value) calculatePosition()
  })
}

// Window listeners are only attached while a tooltip is actually shown, so a
// page with many tooltips does not run N scroll handlers on every scroll event.
const attachListeners = () => {
  if (listenersAttached) return
  listenersAttached = true
  window.addEventListener('scroll', handleScroll, { capture: true, passive: true })
  window.addEventListener('resize', handleResize, { passive: true })
}

const detachListeners = () => {
  if (!listenersAttached) return
  listenersAttached = false
  window.removeEventListener('scroll', handleScroll, { capture: true })
  window.removeEventListener('resize', handleResize)
  if (resizeRaf) {
    cancelAnimationFrame(resizeRaf)
    resizeRaf = 0
  }
}

onBeforeUnmount(() => {
  clearTimeout(hoverTimeout)
  clearTimeout(leaveTimeout)
  detachListeners()
})
</script>

<style scoped>
.tooltip-wrapper {
  display: inline-block;
  position: relative;
}

.rich-tooltip {
  position: fixed;
  z-index: var(--z-tooltip);
  max-width: 320px;
  background: rgb(var(--panel-26) / 0.98);
  color: var(--fg);
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 4px 20px rgb(var(--shade) / 0.4), 0 0 0 1px rgb(var(--ink) / 0.1);
  font-size: 13px;
  line-height: 1.5;
  pointer-events: auto;
}

.tooltip-keyboard-active {
  outline: 2px solid var(--accent-blue-2);
  outline-offset: 2px;
}

.tooltip-content {
  position: relative;
}

.tooltip-title {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-strong);
}

.tooltip-description {
  margin: 0 0 8px 0;
  color: var(--text-2);
}

.tooltip-examples {
  margin: 8px 0;
  padding-left: 20px;
  color: var(--text-soft-2);
  font-size: 12px;
}

.tooltip-examples li {
  margin: 4px 0;
}

.tooltip-learn-more {
  display: inline-block;
  margin-top: 8px;
  color: var(--accent-blue-2);
  text-decoration: none;
  font-weight: 500;
  font-size: 12px;
  transition: color 0.2s;
}

.tooltip-learn-more:hover {
  color: var(--accent-mint-2);
  text-decoration: underline;
}

.tooltip-arrow {
  position: absolute;
  width: 10px;
  height: 10px;
  background: inherit;
  transform: rotate(45deg);
}

.tooltip-top .tooltip-arrow {
  bottom: -5px;
  left: 50%;
  transform: translateX(-50%) rotate(45deg);
}

.tooltip-bottom .tooltip-arrow {
  top: -5px;
  left: 50%;
  transform: translateX(-50%) rotate(45deg);
}

.tooltip-left .tooltip-arrow {
  right: -5px;
  top: 50%;
  transform: translateY(-50%) rotate(45deg);
}

.tooltip-right .tooltip-arrow {
  left: -5px;
  top: 50%;
  transform: translateY(-50%) rotate(45deg);
}

/* Light theme: opaque card with a visible edge; mint hover is < 4.5:1 on white */
:root[data-theme="light"] .rich-tooltip {
  background: var(--surface);
  box-shadow: 0 6px 20px rgb(var(--shade) / 0.3), 0 0 0 1px var(--line-4);
}
:root[data-theme="light"] .tooltip-learn-more:hover {
  color: var(--accent-indigo-2);
}

/* Enter/leave animate only opacity + transform (compositor-only). The backdrop
   blur is suspended while animating so the compositor does not re-blur the
   backdrop every frame; it applies once the tooltip has settled. */
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
  backdrop-filter: none;
}

.tooltip-fade-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}

.tooltip-fade-leave-to {
  opacity: 0;
}
</style>
