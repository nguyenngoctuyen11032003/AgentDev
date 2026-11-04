<template>
  <div class="live-progress" :class="`is-${tone}`" role="status" aria-live="polite">
    <span class="live-dot" aria-hidden="true"></span>
    <span class="live-main">
      <template v-if="lead">
        <span class="live-who" :title="lead.id">{{ lead.id }}</span>
        <span v-if="lead.doing" class="live-doing">{{ lead.doing }}</span>
      </template>
      <span v-else class="live-doing">{{ headline }}</span>
      <span v-if="others.length" class="live-more" :title="others.map((w) => `${w.id}: ${w.doing}`).join('\n')">
        {{ $t('launch.live.others', { n: others.length }) }}
      </span>
    </span>
    <span class="live-meta">
      <span v-if="startedAt" class="live-fact" :title="$t('launch.live.elapsed')">
        <LiveDuration :started-at="startedAt" :ended-at="endedAt || 0" />
      </span>
      <span v-if="steps" class="live-fact">{{ $t('launch.live.steps', { n: steps }) }}</span>
      <button
        v-if="issues"
        type="button"
        class="live-fact live-issues"
        :title="$t('launch.live.issues_hint')"
        @click="$emit('show-issues')"
      >{{ $t('launch.live.issues', { n: issues }) }}</button>
      <span v-if="usage" class="live-fact">{{ usage }}</span>
    </span>
  </div>
</template>

<script setup>
// One line above the message box: who is working on what right now, for how long, how many
// steps so far and how many tool problems are still open; the token use once the turn reports it.
import { computed } from 'vue'
import LiveDuration from '@/components/common/LiveDuration.js'

const props = defineProps({
  // Working agents, most recently active first: [{ id, doing }]
  workers: { type: Array, default: () => [] },
  headline: { type: String, default: '' },
  // running | waiting | done | danger | muted
  tone: { type: String, default: 'running' },
  startedAt: { type: Number, default: 0 },
  endedAt: { type: Number, default: 0 },
  steps: { type: Number, default: 0 },
  issues: { type: Number, default: 0 },
  usage: { type: String, default: '' }
})
defineEmits(['show-issues'])

const lead = computed(() => props.workers[0] || null)
const others = computed(() => props.workers.slice(1))
</script>

<style scoped>
.live-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin: 0 0 8px;
  padding: 6px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface-raised);
  font-size: 12.5px;
  line-height: 1.35;
  color: rgb(var(--ink) / 0.75);
}
.live-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgb(var(--ink) / 0.35);
}
.is-running .live-dot {
  background: var(--accent);
  animation: live-pulse 1.6s ease-in-out infinite;
}
.is-waiting .live-dot { background: var(--warn); }
.is-done .live-dot { background: var(--success, #3fb950); }
.is-danger .live-dot { background: var(--danger); }
.live-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}
.live-who {
  font-weight: 600;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 40%;
}
.live-doing {
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.live-more {
  flex: none;
  color: rgb(var(--ink) / 0.5);
}
.live-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--ink) / 0.55);
}
.live-fact + .live-fact::before {
  content: '·';
  margin-right: 8px;
  color: rgb(var(--ink) / 0.3);
}
.live-issues {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: var(--warn);
  cursor: pointer;
}
.live-issues:hover { text-decoration: underline; }
.live-issues:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: 4px;
}
@media (max-width: 520px) {
  .live-progress { flex-wrap: wrap; }
  .live-meta { width: 100%; padding-left: 16px; }
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
@media (prefers-reduced-motion: reduce) {
  .is-running .live-dot { animation: none; }
}
</style>
