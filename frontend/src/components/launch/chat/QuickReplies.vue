<template>
  <div v-if="items.length" class="quick-replies" role="toolbar" :aria-label="label">
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
  min-height: 30px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  line-height: 1.3;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}
.quick-reply-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quick-reply:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-raised));
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
}
.quick-reply.is-primary {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  background: color-mix(in srgb, var(--accent) 14%, var(--surface-raised));
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
.quick-reply-key {
  font: inherit;
  font-size: 10.5px;
  padding: 0 4px;
  border-radius: 4px;
  border: 1px solid var(--border);
  color: rgb(var(--ink) / 0.5);
}
@media (pointer: coarse) {
  .quick-reply { min-height: 40px; }
  .quick-reply-key { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .quick-reply { transition: none; }
}
</style>
