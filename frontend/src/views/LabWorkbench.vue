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
    <div v-if="tab === LAB_TAB.BATCH" id="lab-panel-batch" role="tabpanel" aria-labelledby="lab-tab-batch" class="lab-batch-host">
      <Suspense>
        <BatchRunView />
        <template #fallback>
          <p class="lab-tab-loading" role="status">{{ $t('lab.tabs.loading') }}</p>
        </template>
      </Suspense>
    </div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LabView from '@/views/LabView.vue'
import { LAB_TAB, LAB_TABS as TABS, labTabFromQuery, nextLabTab } from '@/views/labTabs.js'

// Batch Run is heavy and only needed on its tab: load it on demand
const BatchRunView = defineAsyncComponent(() => import('@/views/BatchRunView.vue'))

const route = useRoute()
const router = useRouter()
const tabRefs = ref([])
const tab = computed(() => labTabFromQuery(route.query.tab))

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
.lab-tab-loading { padding: 24px 20px; color: var(--fg-muted); }
</style>
