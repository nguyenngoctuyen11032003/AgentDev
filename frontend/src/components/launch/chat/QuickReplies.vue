<template>
  <div v-if="items.length" class="quick-replies" :class="{ 'show-keys': altHeld }" role="toolbar" :aria-label="label">
    <button
      v-for="(item, index) in items"
      :key="item.key"
      type="button"
      class="quick-reply"
      :class="{ 'is-primary': item.primary }"
      :disabled="disabled || item.disabled"
      :title="shortcutTitle(item, index)"
      @click="$emit('pick', item)"
    >
      <span class="quick-reply-label">{{ item.label }}</span>
      <kbd v-if="showKeys && index < 9" class="quick-reply-key" aria-hidden="true">Alt {{ index + 1 }}</kbd>
    </button>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
// What makes sense to say next in the current state of the run (plan to approve, team at work,
// finished, failed): one click either acts (approve, continue) or puts an editable text in the
// box. Alt+1..9 picks the n-th chip (handled by the page, which owns the keyboard).
defineProps({
  // [{ key, label, primary?, disabled?, hint? }]
  items: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: '' },
  showKeys: { type: Boolean, default: true }
})
defineEmits(['pick'])

// Shortcut badges stay out of the way: they show on hover/focus, or for all chips while Alt is held
const altHeld = ref(false)
const onKey = (event) => { altHeld.value = event.key === 'Alt' ? event.type === 'keydown' : event.altKey }
const onBlur = () => { altHeld.value = false }
onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('keyup', onKey)
  window.addEventListener('blur', onBlur)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('keyup', onKey)
  window.removeEventListener('blur', onBlur)
})

const shortcutTitle = (item, index) => {
  const key = index < 9 ? `Alt+${index + 1}` : ''
  return [item.hint || item.label, key].filter(Boolean).join(' · ')
}
</script>

<style scoped>
.quick-replies {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 8px;
}
.quick-reply {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  min-height: 28px;
  padding: 3px 11px;
  border-radius: 999px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: transparent;
  color: rgb(var(--ink) / 0.78);
  font: inherit;
  font-size: 12.5px;
  line-height: 1.3;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.quick-reply-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quick-reply:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  color: var(--fg);
}
.quick-reply.is-primary {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--fg);
  font-weight: 600;
}
.quick-reply:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.quick-reply:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
/* A corner badge that takes no room, so nothing shifts when it shows */
.quick-reply { position: relative; }
.quick-reply-key {
  position: absolute;
  top: -9px;
  right: -4px;
  font: inherit;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: rgb(var(--ink) / 0.7);
  box-shadow: 0 2px 6px -2px rgb(15 23 42 / 0.3);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transform: translateY(2px);
  transition: opacity 0.12s var(--ease-out), transform 0.12s var(--ease-out);
}
.quick-reply:hover .quick-reply-key,
.quick-reply:focus-visible .quick-reply-key,
.show-keys .quick-reply-key {
  opacity: 1;
  transform: none;
}
@media (pointer: coarse) {
  .quick-reply { min-height: 40px; }
  .quick-reply-key { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .quick-reply, .quick-reply-key { transition: none; }
}
</style>
