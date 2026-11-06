<template>
  <section class="rerun-compare" aria-labelledby="lab-rerun-compare-title">
    <div class="rc-head">
      <h3 id="lab-rerun-compare-title" class="rc-title">{{ $t('lab.rerun.compare.title') }}</h3>
      <button v-if="sourceId" type="button" class="rc-link" @click="emit('open-source', sourceId)">
        {{ $t('lab.rerun.compare.source') }}
      </button>
    </div>
    <p class="rc-note">{{ $t('lab.rerun.compare.note') }}</p>
    <table v-if="rows.length" class="rc-table">
      <caption class="sr-only">{{ $t('lab.rerun.compare.title') }}</caption>
      <thead>
        <tr>
          <th scope="col">{{ $t('lab.rerun.compare.metric') }}</th>
          <th scope="col">{{ $t('lab.rerun.compare.before') }}</th>
          <th scope="col">{{ $t('lab.rerun.compare.after') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key" :class="{ worse: row.worse }">
          <th scope="row">{{ row.perRun ? $t('lab.rerun.compare.cost_per_run') : $t(`lab.rerun.compare.${row.key}`) }}</th>
          <td>{{ formatRerunValue(row.key, row.before) }}</td>
          <td>
            {{ formatRerunValue(row.key, row.after) }}
            <span v-if="row.worse" class="rc-flag">{{ $t('lab.rerun.compare.worse') }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="rc-note">{{ $t('lab.rerun.compare.empty') }}</p>
  </section>
</template>

<script setup>
// Before/after of a rerun job (only the failed scenarios of `rerun_of`, after a fix): got-worse flags highlighted.
import { computed } from 'vue'
import { formatRerunValue, rerunCompareRows } from '@/utils/labRerun.js'

const props = defineProps({
  compare: { type: Object, required: true },
  sourceId: { type: String, default: '' }
})
const emit = defineEmits(['open-source'])
const rows = computed(() => rerunCompareRows(props.compare))
</script>

<style scoped>
.rerun-compare { margin: 0 0 16px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--tint-2); }
.rc-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 12px; }
.rc-title { margin: 0; font-size: 14px; }
.rc-link { padding: 0; border: 0; background: none; font: inherit; font-size: 13px; font-weight: 600; color: var(--accent); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.rc-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.rc-note { margin: 4px 0 8px; font-size: 12.5px; color: var(--fg-muted); }
.rc-table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
.rc-table th, .rc-table td { padding: 5px 8px; text-align: left; border-top: 1px solid var(--line); }
.rc-table thead th { border-top: 0; font-size: 12px; font-weight: 600; color: var(--fg-muted); }
.rc-table tbody th { font-weight: 500; }
.rc-table tr.worse td:last-child { color: var(--danger); font-weight: 600; }
.rc-flag { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 6px; font-size: 11.5px; background: color-mix(in srgb, var(--danger) 12%, transparent); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
