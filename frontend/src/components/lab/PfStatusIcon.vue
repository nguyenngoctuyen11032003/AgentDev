<template>
  <svg :class="['pf-icon', tone]" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path v-if="tone === 'ok'" d="m5 12.5 4.5 4.5L19 7.5" />
    <path v-else-if="tone === 'bad'" d="M6 6l12 12M18 6 6 18" />
    <path v-else-if="tone === 'live'" d="M12 3a9 9 0 1 0 9 9" />
    <path v-else-if="tone === 'warn'" d="M12 7v6M12 17h.01" />
    <circle v-else cx="12" cy="12" r="7" stroke-dasharray="3 3" />
  </svg>
</template>

<script setup>
// Decorative status glyph (the status is always also written as text next to it).
defineProps({ tone: { type: String, default: 'muted' } })
</script>

<style scoped>
.pf-icon { flex: none; color: var(--fg-muted); }
.pf-icon.ok { color: var(--success); }
.pf-icon.bad { color: var(--danger); }
.pf-icon.live { color: var(--accent); animation: pf-spin 1s linear infinite; }
.pf-icon.warn { color: var(--warn); }
@keyframes pf-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .pf-icon.live { animation: none; } }
</style>
