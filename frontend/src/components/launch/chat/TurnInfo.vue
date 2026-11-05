<template>
  <span ref="rootRef" class="turn-info" @mouseenter="show" @mouseleave="hideSoon">
    <button
      ref="triggerRef"
      type="button"
      class="turn-info-btn"
      :aria-expanded="open"
      :aria-label="headline"
      @click="open ? close() : show()"
      @focus="show"
      @blur="hideSoon"
      @keydown.esc.stop="close"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><circle cx="12" cy="7.8" r="0.6" fill="currentColor" /></svg>
    </button>
    <Teleport to="body">
      <Transition name="turn-info">
        <div
          v-if="open"
          class="turn-info-pop"
          :class="`is-${tone}`"
          :style="popStyle"
          role="status"
          @mouseenter="cancelHide"
          @mouseleave="hideSoon"
        >
          <p class="turn-info-title"><span class="turn-info-dot" aria-hidden="true"></span>{{ headline }}</p>
          <dl class="turn-info-rows">
            <div v-if="startedAt" class="turn-info-row">
              <dt>{{ $t('launch.live.elapsed') }}</dt>
              <dd><LiveDuration :started-at="startedAt" :ended-at="endedAt || 0" /></dd>
            </div>
            <div v-if="steps" class="turn-info-row">
              <dt>{{ $t('launch.live.steps_label') }}</dt>
              <dd>{{ steps }}</dd>
            </div>
            <div v-if="usage" class="turn-info-row">
              <dt>{{ $t('launch.live.usage_label') }}</dt>
              <dd>{{ usage }}</dd>
            </div>
          </dl>
        </div>
      </Transition>
    </Teleport>
  </span>
</template>

<script setup>
// The numbers of a finished turn (time, steps, token use), tucked behind a small icon in the message box
// instead of a line that sits there after every answer. Hover, focus or click shows them.
import { onBeforeUnmount, ref } from 'vue'
import LiveDuration from '@/components/common/LiveDuration.js'

defineProps({
  headline: { type: String, default: '' },
  tone: { type: String, default: 'done' },
  startedAt: { type: Number, default: 0 },
  endedAt: { type: Number, default: 0 },
  steps: { type: Number, default: 0 },
  usage: { type: String, default: '' }
})

const open = ref(false)
const rootRef = ref(null)
const triggerRef = ref(null)
const popStyle = ref({})
let hideTimer = null

const place = () => {
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const width = Math.min(260, window.innerWidth - 16)
  const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8)
  popStyle.value = { left: `${left}px`, width: `${width}px`, bottom: `${window.innerHeight - rect.top + 8}px` }
}
const cancelHide = () => { clearTimeout(hideTimer); hideTimer = null }
const show = () => { cancelHide(); place(); open.value = true }
const close = () => { cancelHide(); open.value = false }
const hideSoon = () => { cancelHide(); hideTimer = setTimeout(close, 120) }
onBeforeUnmount(cancelHide)
</script>

<style scoped>
.turn-info { display: inline-flex; }
.turn-info-btn {
  position: relative;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: rgb(var(--ink) / 0.5);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.turn-info-btn::before { content: ''; position: absolute; inset: -6px; }
.turn-info-btn:hover,
.turn-info-btn[aria-expanded="true"] { background: rgb(var(--ink) / 0.08); color: var(--fg); }
.turn-info-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.turn-info-pop {
  position: fixed;
  z-index: 1000;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 2px 4px rgb(15 23 42 / 0.08), 0 18px 40px -12px rgb(15 23 42 / 0.4);
  font-size: 12.5px;
  color: rgb(var(--ink) / 0.75);
}
.turn-info-title { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-weight: 600; color: var(--fg); }
.turn-info-dot { width: 8px; height: 8px; border-radius: 50%; background: rgb(var(--ink) / 0.35); }
.is-done .turn-info-dot { background: var(--success, #3fb950); }
.turn-info-rows { margin: 0; display: grid; gap: 4px; }
.turn-info-row { display: flex; justify-content: space-between; gap: 12px; font-variant-numeric: tabular-nums; }
.turn-info-row dt { color: rgb(var(--ink) / 0.55); }
.turn-info-row dd { margin: 0; color: var(--fg); text-align: right; }

.turn-info-enter-active,
.turn-info-leave-active { transition: opacity 0.12s var(--ease-out), transform 0.12s var(--ease-out); }
.turn-info-enter-from,
.turn-info-leave-to { opacity: 0; transform: translateY(4px); }
@media (prefers-reduced-motion: reduce) {
  .turn-info-btn, .turn-info-enter-active, .turn-info-leave-active { transition: none; }
}
</style>
