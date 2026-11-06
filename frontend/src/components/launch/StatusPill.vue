<template>
  <span class="status-pill" :class="[`is-${kind}`, { compact: compact || size === 'sm' }]" :title="title || undefined">
    <svg class="sp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <template v-if="kind === 'working'"><path d="M21 12a9 9 0 1 1-6.2-8.55" /></template>
      <template v-else-if="kind === 'waiting'"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></template>
      <template v-else-if="kind === 'done'"><path d="M5 12.5l4.5 4.5L19 7" /></template>
      <template v-else-if="kind === 'error'"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.01" /></template>
      <template v-else-if="kind === 'rework'"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16" /><path d="M3 21v-5h5" /></template>
      <template v-else-if="kind === 'cancelled'"><rect x="6" y="6" width="12" height="12" rx="2" /></template>
      <template v-else-if="kind === 'skipped'"><circle cx="12" cy="12" r="9" /><path d="M8 12h8" /></template>
      <template v-else><circle cx="12" cy="12" r="8" stroke-dasharray="3 4" /></template>
    </svg>
    <span class="sp-label"><slot>{{ label }}</slot></span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

// A state is never shown by colour alone: every tone has its own icon and a text label.
const props = defineProps({
  tone: { type: String, default: 'idle' },
  label: { type: String, default: '' },
  title: { type: String, default: '' },
  compact: { type: Boolean, default: false },
  // 'sm' (20px, lists and table cells) | 'md' (24px, headers); `compact` is an alias for 'sm'
  size: { type: String, default: 'md' }
})

const ALIAS = { completed: 'done', approved: 'done', draft: 'idle', todo: 'idle' }
const kind = computed(() => ALIAS[props.tone] || props.tone)
</script>

<style scoped>
.status-pill {
  --tone: var(--fg-muted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  min-height: 24px;
  padding: 2px 9px 2px 7px;
  border-radius: 99px;
  border: 1px solid color-mix(in srgb, var(--tone) 32%, transparent);
  background: color-mix(in srgb, var(--tone) 12%, transparent);
  color: var(--tone-ink, var(--tone));
  font-size: var(--fs-xs);
  font-weight: 650;
  line-height: 1.2;
  white-space: nowrap;
  transition: color 0.2s var(--ease-out), background-color 0.2s var(--ease-out), border-color 0.2s var(--ease-out);
}

.status-pill.compact { min-height: 20px; padding: 1px 7px 1px 5px; }

/* Light theme: the tone's own hue, darkened, keeps every label >= 5.4:1 on its tint
   (plain amber/green measured 3.9:1 on the page background). */
:root[data-theme='light'] .status-pill { --tone-ink: color-mix(in srgb, var(--tone) 80%, #000); }

.is-working { --tone: var(--accent); }
.is-waiting { --tone: var(--warn); }
.is-done { --tone: var(--success); }
.is-error { --tone: var(--danger); }
.is-rework { --tone: color-mix(in srgb, var(--warn) 60%, var(--danger)); }
.is-cancelled,
.is-skipped,
.is-idle { --tone: var(--fg-muted); --tone-ink: color-mix(in srgb, var(--fg-muted) 65%, var(--fg)); }

.sp-icon { width: 13px; height: 13px; flex: none; }
.is-working .sp-icon { animation: sp-spin 1.1s linear infinite; }
.sp-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; }

@keyframes sp-spin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
  .is-working .sp-icon { animation: none; }
  .status-pill { transition: none; }
}
</style>
