<template>
  <section class="rerun-card" :aria-labelledby="titleId" :aria-busy="loading || starting ? 'true' : 'false'">
    <h3 :id="titleId" class="rerun-title">{{ $t('lab.rerun.title') }}</h3>
    <p class="rerun-intro">{{ $t('lab.rerun.intro') }}</p>

    <p v-if="loading" class="rerun-status" role="status">{{ $t('lab.rerun.loading') }}</p>

    <div v-else-if="errorInfo" class="rerun-error" role="alert">
      <p class="rerun-error-title">{{ errorText.title }}</p>
      <p class="rerun-hint">{{ errorText.hint }}</p>
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
          {{ $t('lab.rerun.summary', { scenarios: $t('lab.rerun.scenario_count', { n: scenarioCount }, scenarioCount), runs: $t('lab.rerun.run_count', { n: runs }, runs) }) }} ·
          <span>{{ costKnown ? $t('lab.rerun.cost', { cost: costText }) : $t('lab.rerun.cost_unknown') }}</span>
        </p>
        <p class="rerun-note">{{ $t('lab.rerun.paid_note') }}</p>
      </template>
      <div class="rerun-actions">
        <button v-if="runs" type="button" class="btn-primary" :disabled="starting" @click="start">
          {{ starting ? $t('lab.rerun.starting') : costKnown ? $t('lab.rerun.run', { runs, cost: costText }, runs) : $t('lab.rerun.run_unknown', { runs }, runs) }}
        </button>
        <button type="button" class="btn-ghost" :disabled="starting" @click="emit('dismiss')">{{ $t('lab.rerun.dismiss') }}</button>
      </div>
    </template>
  </section>
</template>

<script setup>
// After a Lab-sourced fix was applied: re-run only the source job's failed scenarios. The cost
// estimate is fetched first; nothing runs until the user clicks the run button.
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'
import { labRerunEstimate, labRerunFailed } from '@/api/client.js'
import { useWorkflowAssistant } from '@/composables/useWorkflowAssistant.js'
import { formatRerunValue, rerunCanRetry, rerunError, rerunErrorText } from '@/utils/labRerun.js'

const props = defineProps({
  // {labJobId, workflow}: the Lab job whose failed scenarios are re-run, and its workflow (no .yaml)
  offer: { type: Object, required: true }
})
const emit = defineEmits(['dismiss', 'started'])
const router = useRouter()
const { t, te } = useI18n()
// Undo of the fix waits while the paid start request is on its way.
const { setRerunStarting } = useWorkflowAssistant()

const titleId = `lab-rerun-title-${useId()}`
const loading = ref(false)
const starting = ref(false)
const estimate = ref(null)
// The last failure (estimate or start) as {code, fallback, params}; Retry always fetches a fresh estimate first.
const errorInfo = ref(null)
const errorText = computed(() => (errorInfo.value ? rerunErrorText(errorInfo.value, { t, te }) : { title: '', hint: '' }))
let alive = true
let token = 0

const runs = computed(() => Number(estimate.value?.runs) || 0)
const scenarioCount = computed(() => (Array.isArray(estimate.value?.scenarios) ? estimate.value.scenarios.length : 0))
const costKnown = computed(() => !!estimate.value?.cost_known && typeof estimate.value?.estimate_usd === 'number')
const costText = computed(() => (costKnown.value ? formatRerunValue('cost_usd', estimate.value.estimate_usd) : ''))
// No Retry when it cannot help (nothing failed is left, or a job too old to re-run).
const canRetry = computed(() => !!errorInfo.value && rerunCanRetry(errorInfo.value))

const labLink = (jobId) => ({
  path: '/lab',
  // The bare workflow key: the Lab matches it to its .yaml or .yml file.
  query: { workflow: props.offer.workflow, ...(jobId ? { job: jobId } : {}) }
})

async function loadEstimate() {
  const mine = ++token
  loading.value = true
  errorInfo.value = null
  estimate.value = null
  try {
    const data = await labRerunEstimate(props.offer.labJobId)
    if (!alive || mine !== token) return
    estimate.value = data && typeof data === 'object' ? data : { scenarios: [], runs: 0 }
  } catch (error) {
    if (alive && mine === token) errorInfo.value = rerunError(error)
  } finally {
    if (alive && mine === token) loading.value = false
  }
}

async function start() {
  if (starting.value || !runs.value) return
  starting.value = true
  setRerunStarting(true)
  const jobId = props.offer.labJobId
  try {
    const created = await labRerunFailed(jobId)
    if (!alive) return
    emit('started', created)
    router.push(labLink(created?.id))
  } catch (error) {
    if (alive) errorInfo.value = rerunError(error)
  } finally {
    // Always, even when the card is gone: Undo stays blocked only while the request is on its way.
    setRerunStarting(false)
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
  /* Plain --danger is 4.48:1 on the tinted card in light theme: pull it toward the text color. */
  color: color-mix(in srgb, var(--danger) 85%, var(--text-1));
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

@media (max-width: 720px) {
  .btn-ghost,
  .btn-primary {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
  }
}
</style>
