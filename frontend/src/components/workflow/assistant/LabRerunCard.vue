<template>
  <section class="rerun-card" :aria-labelledby="titleId" :aria-busy="loading || starting ? 'true' : 'false'">
    <h3 :id="titleId" class="rerun-title">{{ $t('lab.rerun.title') }}</h3>
    <p class="rerun-intro">{{ $t('lab.rerun.intro') }}</p>

    <p v-if="loading" class="rerun-status" role="status">{{ $t('lab.rerun.loading') }}</p>

    <div v-else-if="errorCode" class="rerun-error" role="alert">
      <p class="rerun-error-title">{{ $t(`lab.rerun.errors.${errorCode}`) }}</p>
      <p class="rerun-hint">{{ $t(`lab.rerun.hints.${errorCode}`) }}</p>
      <div class="rerun-actions">
        <button v-if="canRetry" type="button" class="btn-ghost" @click="retry">{{ $t('lab.rerun.retry') }}</button>
        <RouterLink :to="labLink()" class="btn-ghost">{{ $t('lab.rerun.open_lab') }}</RouterLink>
        <button type="button" class="btn-ghost" @click="emit('dismiss')">{{ $t('lab.rerun.dismiss') }}</button>
      </div>
    </div>

    <template v-else-if="estimate">
      <p v-if="!runs" class="rerun-status">{{ $t('lab.rerun.empty') }}</p>
      <template v-else>
        <p class="rerun-summary">
          {{ $t('lab.rerun.summary', { scenarios: scenarioCount, runs }) }} ·
          <span>{{ costKnown ? $t('lab.rerun.cost', { cost: costText }) : $t('lab.rerun.cost_unknown') }}</span>
        </p>
        <p class="rerun-note">{{ $t('lab.rerun.paid_note') }}</p>
      </template>
      <div class="rerun-actions">
        <button v-if="runs" type="button" class="btn-primary" :disabled="starting" @click="start">
          {{ starting ? $t('lab.rerun.starting') : costKnown ? $t('lab.rerun.run', { runs, cost: costText }) : $t('lab.rerun.run_unknown', { runs }) }}
        </button>
        <button type="button" class="btn-ghost" :disabled="starting" @click="emit('dismiss')">{{ $t('lab.rerun.dismiss') }}</button>
      </div>
    </template>
  </section>
</template>

<script setup>
// After a Lab-sourced fix was applied: re-run only the source job's failed scenarios. The cost
// estimate is fetched first; nothing runs until the user clicks the run button.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { labRerunEstimate, labRerunFailed } from '@/api/client.js'
import { formatRerunValue, rerunErrorCode } from '@/utils/labRerun.js'

const props = defineProps({
  // {labJobId, workflow}: the Lab job whose failed scenarios are re-run, and its workflow (no .yaml)
  offer: { type: Object, required: true }
})
const emit = defineEmits(['dismiss', 'started'])
const router = useRouter()

const titleId = `lab-rerun-title-${Math.random().toString(36).slice(2, 9)}`
const loading = ref(false)
const starting = ref(false)
const estimate = ref(null)
// Code of the last failure (estimate or start); Retry always fetches a fresh estimate first.
const errorCode = ref('')
let alive = true
let token = 0

const runs = computed(() => Number(estimate.value?.runs) || 0)
const scenarioCount = computed(() => (Array.isArray(estimate.value?.scenarios) ? estimate.value.scenarios.length : 0))
const costKnown = computed(() => !!estimate.value?.cost_known && typeof estimate.value?.estimate_usd === 'number')
const costText = computed(() => (costKnown.value ? formatRerunValue('cost_usd', estimate.value.estimate_usd) : ''))
// Nothing to retry when the server said there is nothing failed left.
const canRetry = computed(() => errorCode.value !== 'nothing_to_rerun')

const labLink = (jobId) => ({
  path: '/lab',
  query: { workflow: `${props.offer.workflow}.yaml`, ...(jobId ? { job: jobId } : {}) }
})

async function loadEstimate() {
  const mine = ++token
  loading.value = true
  errorCode.value = ''
  estimate.value = null
  try {
    const data = await labRerunEstimate(props.offer.labJobId)
    if (!alive || mine !== token) return
    estimate.value = data && typeof data === 'object' ? data : { scenarios: [], runs: 0 }
  } catch (error) {
    if (alive && mine === token) errorCode.value = rerunErrorCode(error)
  } finally {
    if (alive && mine === token) loading.value = false
  }
}

async function start() {
  if (starting.value || !runs.value) return
  starting.value = true
  const jobId = props.offer.labJobId
  try {
    const created = await labRerunFailed(jobId)
    if (!alive) return
    emit('started', created)
    router.push(labLink(created?.id))
  } catch (error) {
    if (alive) errorCode.value = rerunErrorCode(error)
  } finally {
    if (alive) starting.value = false
  }
}

const retry = () => loadEstimate()

watch(() => props.offer?.labJobId, (id) => { if (id) loadEstimate() }, { immediate: true })
onBeforeUnmount(() => {
  alive = false
})
</script>

<style scoped>
.rerun-card {
  margin: 10px 0 4px;
  padding: 11px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent-sky) 40%, transparent);
  background: color-mix(in srgb, var(--accent-sky) 7%, transparent);
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-1);
}

.rerun-title {
  margin: 0 0 2px;
  font-size: 13.5px;
  font-weight: 650;
}

.rerun-intro,
.rerun-summary,
.rerun-note,
.rerun-status,
.rerun-hint,
.rerun-error-title {
  margin: 0 0 6px;
}

.rerun-note,
.rerun-hint,
.rerun-status {
  font-size: 12.5px;
  color: var(--text-muted-1);
}

.rerun-error-title {
  font-weight: 600;
  color: var(--danger);
}

.rerun-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.btn-ghost,
.btn-primary {
  padding: 6px 12px;
  border-radius: 9px;
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgb(var(--ink) / 0.14);
  text-decoration: none;
}

.btn-ghost {
  background: transparent;
  color: var(--text-1);
}

.btn-ghost:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.06);
}

.btn-primary {
  background: var(--accent-sky);
  border-color: transparent;
  color: #05141f;
}

:root[data-theme="light"] .btn-primary {
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
}

.btn-ghost:disabled,
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost:focus-visible,
.btn-primary:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}
</style>
