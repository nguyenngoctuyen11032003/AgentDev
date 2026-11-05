<template>
  <div class="lab-workbench">
    <div class="lab-tabs" role="tablist" :aria-label="$t('lab.tabs.label')" @keydown="onTabKey">
      <button
        v-for="item in TABS"
        :id="`lab-tab-${item}`"
        :key="item"
        ref="tabRefs"
        type="button"
        role="tab"
        class="lab-tab"
        :class="{ 'is-active': tab === item }"
        :aria-selected="tab === item"
        :aria-controls="`lab-panel-${item}`"
        :tabindex="tab === item ? 0 : -1"
        @click="select(item)"
      >{{ $t(`lab.tabs.${item}`) }}</button>
    </div>
    <div v-show="tab === LAB_TAB.SCORE" id="lab-panel-score" role="tabpanel" aria-labelledby="lab-tab-score">
      <LabView />
    </div>
    <!-- Mounted on first visit and then only hidden: leaving the tab must not abort a running batch -->
    <div
      v-if="batchVisited"
      v-show="tab === LAB_TAB.BATCH"
      id="lab-panel-batch"
      role="tabpanel"
      aria-labelledby="lab-tab-batch"
      class="lab-batch-host"
    >
      <component :is="BatchRunView" :key="batchAttempt" />
    </div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, h, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import LabView from '@/views/LabView.vue'
import { LAB_TAB, LAB_TABS as TABS, labTabFromQuery, nextLabTab } from '@/views/labTabs.js'

// Batch Run is heavy and only needed on its tab: load it on demand
const { t } = useI18n()
const batchAttempt = ref(0)
const batchVisited = ref(false)
const retryBatch = () => { batchAttempt.value += 1 }
const BatchRunView = computed(() => {
  batchAttempt.value // a retry builds a fresh loader
  return defineAsyncComponent({
    loader: () => import('@/views/BatchRunView.vue'),
    delay: 0,
    loadingComponent: { render: () => h('p', { class: 'lab-tab-loading', role: 'status' }, t('lab.tabs.loading')) },
    errorComponent: {
      render: () =>
        h('div', { class: 'lab-tab-loading lab-tab-error', role: 'alert' }, [
          h('p', t('lab.tabs.load_failed')),
          h('button', { type: 'button', class: 'lab-tab-retry', onClick: retryBatch }, t('lab.tabs.retry'))
        ])
    }
  })
})

const route = useRoute()
const router = useRouter()
const tabRefs = ref([])
const tab = computed(() => labTabFromQuery(route.query.tab))
watch(tab, (value) => { if (value === LAB_TAB.BATCH) batchVisited.value = true }, { immediate: true })

const select = (value) => {
  if (value === tab.value) return
  const query = { ...route.query }
  if (value === LAB_TAB.SCORE) delete query.tab
  else query.tab = value
  router.replace({ query })
}

const onTabKey = (event) => {
  const next = nextLabTab(tab.value, event.key)
  if (!next) return
  event.preventDefault()
  select(next)
  nextTick(() => document.getElementById(`lab-tab-${next}`)?.focus())
}
</script>

<style scoped>
.lab-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 20px 0;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.lab-tab {
  min-height: 44px;
  padding: 0 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
}
.lab-tab:hover { color: var(--fg); }
.lab-tab.is-active { color: var(--fg); border-bottom-color: var(--accent); }
.lab-tab:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
/* Batch Run is built as a full-height page under the shared bar: leave room for the tab strip */
.lab-batch-host :deep(.launch-view) { height: calc(100 * var(--dvh) - 55px - 53px); }
.lab-batch-host :deep(.lab-tab-loading) { padding: 24px 20px; color: var(--fg-muted); }
.lab-batch-host :deep(.lab-tab-error) { color: var(--fg); }
.lab-batch-host :deep(.lab-tab-retry) {
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--fg);
  font: inherit;
  cursor: pointer;
}
.lab-batch-host :deep(.lab-tab-retry:focus-visible) { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
