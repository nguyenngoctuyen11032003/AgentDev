<template>
  <!-- Quality of a run (or the average of a job) per rubric dimension: requirements, correctness, craft, ... -->
  <div v-if="rows.length" class="quality">
    <p class="quality-head">
      <strong>{{ $t('lab.quality.title') }}</strong>
      <span v-if="domain" class="quality-tag">{{ $t(`lab.quality.domain.${domainKey}`) }}</span>
      <span v-if="scopeKey" class="quality-tag">{{ $t(`lab.quality.scope.${scopeKey}`) }}</span>
      <span v-if="runs > 1" class="quality-sub">{{ $t('lab.quality.average', { n: runs }) }}</span>
    </p>
    <ul class="quality-list">
      <li v-for="row in rows" :key="row.key" :class="['quality-row', row.tone]">
        <span class="quality-name">{{ $t(`lab.quality.dim.${row.key}`) }}</span>
        <span class="quality-bar" aria-hidden="true"><span :style="{ width: row.score * 10 + '%' }"></span></span>
        <span class="quality-score">{{ $t('lab.quality.score', { n: row.score }) }}</span>
        <span v-if="row.note" class="quality-note">{{ row.note }}</span>
      </li>
    </ul>
    <template v-if="missing.length">
      <p class="quality-label">{{ $t('lab.quality.missing') }}</p>
      <ul class="quality-items">
        <li v-for="(m, i) in missing" :key="`m${i}`">{{ m }}</li>
      </ul>
    </template>
    <template v-if="fixes.length">
      <p class="quality-label">{{ $t('lab.quality.fixes') }}</p>
      <ul class="quality-items">
        <li v-for="(f, i) in fixes" :key="`f${i}`">{{ f }}</li>
      </ul>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { qualityRows } from './labQuality.js'

const props = defineProps({
  // { key: number } (job average) or { key: { score, note } } (one run)
  dimensions: { type: Object, default: () => ({}) },
  domain: { type: String, default: '' },
  scope: { type: String, default: '' },
  runs: { type: Number, default: 0 },
  missing: { type: Array, default: () => [] },
  fixes: { type: Array, default: () => [] }
})

const rows = computed(() => qualityRows(props.dimensions))
const domainKey = computed(() => (['code', 'video', 'content'].includes(props.domain) ? props.domain : 'general'))
const scopeKey = computed(() => (['small', 'medium', 'large'].includes(props.scope) ? props.scope : ''))
</script>

<style scoped>
.quality { margin: 10px 0 0; }
.quality-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 6px; font-size: 13px; color: var(--fg); }
.quality-tag { padding: 1px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 600; background: var(--tint-2); color: var(--fg-muted); }
.quality-sub { font-size: 12px; color: var(--fg-muted); }
.quality-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.quality-row {
  --tone: var(--success);
  display: grid; grid-template-columns: minmax(120px, 190px) minmax(60px, 1fr) auto; align-items: center; gap: 4px 10px; font-size: 13px;
}
.quality-row.mid { --tone: var(--warn); }
.quality-row.low { --tone: var(--danger); }
.quality-name { color: var(--fg); }
.quality-bar { height: 6px; border-radius: 999px; background: var(--tint-2); overflow: hidden; }
.quality-bar span { display: block; height: 100%; border-radius: inherit; background: var(--tone); }
.quality-score { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--fg); }
.quality-note { grid-column: 1 / -1; font-size: 12.5px; line-height: 1.5; color: var(--fg-muted); }
.quality-label { margin: 8px 0 2px; font-size: 13px; font-weight: 600; color: var(--fg); }
.quality-items { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; color: var(--fg-muted); }
@media (max-width: 560px) {
  .quality-row { grid-template-columns: 1fr auto; }
  .quality-bar { grid-column: 1 / -1; grid-row: 2; }
}
</style>
