<template>
  <div class="lab-view">
    <!-- ================================================================ header -->
    <header class="hero">
      <div class="hero-text">
        <p class="hero-kicker">
          <span class="kicker-dot" aria-hidden="true"></span>
          {{ tr('lab.kicker', 'Kiểm định quy trình') }}
        </p>
        <h1 class="hero-title">{{ $t('lab.title') }}</h1>
        <p class="hero-sub">{{ $t('lab.subtitle') }}</p>
      </div>
      <router-link to="/batch-run" target="_blank" rel="noopener" class="btn">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" /></svg>
        {{ $t('lab.batch_link').replace(/\s*→\s*$/, '') }}
        <svg class="ext" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
      </router-link>
    </header>

    <!-- ================================================================ control bar -->
    <section class="control card">
      <label class="field picker-field">
        <span class="field-label">{{ $t('lab.workflow_label') }}</span>
        <span class="select-wrap">
          <svg class="select-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3" /><path d="M7 15h10" /></svg>
          <select v-model="workflow" :disabled="isRunning">
            <option value="" disabled>{{ $t('lab.workflow_placeholder') }}</option>
            <option v-for="wf in workflows" :key="wf.name" :value="wf.name">{{ wf.name.replace(/\.ya?ml$/, '') }}</option>
          </select>
          <svg class="select-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </span>
      </label>

      <dl v-if="workflow" class="metrics">
        <div class="metric">
          <dt>{{ tr('lab.summary.config', 'Cấu hình') }}</dt>
          <dd>
            <span v-if="checking" class="muted">{{ $t('lab.checking') }}</span>
            <span v-else-if="health" :class="['health-tag', health]">
              <span class="dot" aria-hidden="true"></span>
              {{ tr(`lab.health.${health}`, { pass: 'Sẵn sàng', warn: 'Có cảnh báo', fail: 'Cần sửa' }[health]) }}
            </span>
            <span v-else class="muted">—</span>
          </dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.scenarios', 'Kịch bản') }}</dt>
          <dd>{{ filledScenarios }}<span class="unit">/{{ scenarios.length }}</span></dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.runs', 'Lượt chạy') }}</dt>
          <dd>{{ plannedRuns }}<span class="unit"> × {{ repeats }}</span></dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.last', 'Tỷ lệ đạt') }}</dt>
          <dd>
            <span v-if="passPct !== null" :class="['rate', job.verdict]">{{ passPct }}%</span>
            <span v-else-if="isRunning" class="muted">{{ progressPct }}%</span>
            <span v-else class="muted">—</span>
          </dd>
        </div>
      </dl>
    </section>

    <!-- ================================================================ empty state -->
    <section v-if="!workflow" class="intro card" :aria-label="tr('lab.how_it_works', 'Cách kiểm định')">
      <div class="intro-head">
        <h2 class="intro-heading">{{ tr('lab.how_it_works', 'Cách kiểm định') }}</h2>
        <p class="intro-cta">{{ tr('lab.empty_cta', 'Chọn một quy trình ở trên để bắt đầu.') }}</p>
      </div>
      <ol class="intro-steps">
        <li class="intro-step">
          <span class="icon-tile sky" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
          </span>
          <div>
            <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 1 }) }}</p>
            <h3 class="intro-title">{{ stripNo($t('lab.check_title')) }}</h3>
            <p class="intro-desc">{{ $t('lab.check_hint') }}</p>
          </div>
        </li>
        <li class="intro-step">
          <span class="icon-tile indigo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3" /><path d="M7 15h10" /></svg>
          </span>
          <div>
            <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 2 }) }}</p>
            <h3 class="intro-title">{{ stripNo($t('lab.eval_title')) }}</h3>
            <p class="intro-desc">{{ $t('lab.eval_hint') }}</p>
          </div>
        </li>
      </ol>
    </section>

    <!-- ================================================================ workspace -->
    <div v-else class="workspace">
      <div class="main-col">
        <!-- Scenarios -->
        <section class="card panel">
          <header class="panel-head">
            <span class="icon-tile indigo" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3" /><path d="M7 15h10" /></svg>
            </span>
            <div class="panel-text">
              <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 2 }) }}</p>
              <h2 class="panel-title">{{ stripNo($t('lab.eval_title')) }}</h2>
              <p class="panel-hint">{{ $t('lab.eval_hint') }}</p>
            </div>
          </header>

          <ol class="scenario-list">
            <li v-for="(sc, index) in scenarios" :key="sc.key" class="scenario">
              <div class="scenario-head">
                <span class="scenario-no" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                <input
                  v-model="sc.name"
                  class="scenario-name"
                  :aria-label="$t('lab.scenario_name', { n: index + 1 })"
                  :placeholder="$t('lab.scenario_name', { n: index + 1 })"
                  :disabled="isRunning"
                />
                <button
                  v-if="scenarios.length > 1"
                  type="button"
                  class="icon-btn danger"
                  :title="$t('lab.remove')"
                  :aria-label="`${$t('lab.remove')} ${sc.name || $t('lab.scenario_name', { n: index + 1 })}`"
                  :disabled="isRunning"
                  @click="removeScenario(index)"
                >
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
                </button>
              </div>
              <div class="scenario-fields">
                <label class="field">
                  <span class="field-label">{{ $t('lab.prompt_label') }}</span>
                  <textarea v-model="sc.prompt" rows="3" :placeholder="$t('lab.prompt_placeholder')" :disabled="isRunning"></textarea>
                </label>
                <label class="field">
                  <span class="field-label">{{ $t('lab.criteria_label') }}</span>
                  <textarea v-model="sc.criteria" rows="3" :placeholder="$t('lab.criteria_placeholder')" :disabled="isRunning"></textarea>
                </label>
              </div>
            </li>
          </ol>

          <div class="scenario-tools">
            <button type="button" class="btn subtle" :disabled="isRunning || scenarios.length >= 20" @click="addScenario()">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              {{ $t('lab.add_scenario') }}
            </button>
            <button type="button" class="btn subtle" :disabled="isRunning" @click="addSamples">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></svg>
              {{ $t('lab.add_samples') }}
            </button>
            <label class="repeat">
              {{ $t('lab.repeats') }}
              <span class="select-wrap small">
                <select v-model.number="repeats" :disabled="isRunning">
                  <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
                </select>
                <svg class="select-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
              </span>
            </label>
          </div>

          <footer class="run-bar">
            <p class="run-note">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
              {{ $t('lab.cost_note', { runs: plannedRuns }) }}
            </p>
            <button v-if="!isRunning" type="button" class="btn primary" :disabled="!plannedRuns || starting" @click="startEval">
              <span v-if="starting" class="spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
              {{ $t('lab.eval_run') }}
            </button>
            <button v-else type="button" class="btn danger-ghost" @click="stopEval">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
              {{ $t('lab.eval_stop') }}
            </button>
          </footer>
          <p v-if="evalError" class="error" role="alert">{{ evalError }}</p>
        </section>

        <!-- Results -->
        <section v-if="job" class="card panel results" aria-live="polite">
          <header class="panel-head">
            <span class="icon-tile mint" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18" /><path d="m7 15 4-4 3 3 5-6" /></svg>
            </span>
            <div class="panel-text">
              <h2 class="panel-title">{{ tr('lab.results_title', 'Kết quả') }}</h2>
              <p class="panel-hint">{{ $t(`lab.job_status.${job.status}`) }} · {{ job.done }}/{{ job.total }}</p>
            </div>
          </header>

          <div v-if="job.status === 'completed'" :class="['verdict', job.verdict]">
            <div class="ring" :style="{ '--p': passPct + '%' }">
              <span>{{ passPct }}<small>%</small></span>
            </div>
            <div class="verdict-text">
              <strong>{{ $t(`lab.verdict.${job.verdict}`) }}</strong>
              <span>{{ $t('lab.verdict_detail', { rate: passPct, threshold: Math.round(job.threshold * 100), errors: job.errors }) }}</span>
            </div>
          </div>
          <div v-else class="progress">
            <div class="progress-row">
              <span class="progress-label">
                <span v-if="isRunning" class="pulse" aria-hidden="true"></span>
                {{ $t(`lab.job_status.${job.status}`) }}
              </span>
              <span class="progress-num">{{ job.done }}/{{ job.total }}</span>
            </div>
            <div class="bar" role="progressbar" :aria-valuenow="progressPct" aria-valuemin="0" aria-valuemax="100">
              <div class="fill" :style="{ transform: `scaleX(${job.total ? job.done / job.total : 0})` }"></div>
            </div>
          </div>

          <dl class="kpis">
            <div class="kpi">
              <dt>{{ tr('lab.kpi.passed', 'Đạt') }}</dt>
              <dd>{{ job.passed }}<span class="unit">/{{ job.done }}</span></dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.time', 'Thời gian') }}</dt>
              <dd>{{ job.duration_seconds }}<span class="unit">s</span></dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.tokens', 'Token') }}</dt>
              <dd>{{ job.total_tokens.toLocaleString() }}</dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.cost', 'Chi phí') }}</dt>
              <dd>{{ job.cost_usd ? `$${job.cost_usd.toFixed(2)}` : '—' }}</dd>
            </div>
          </dl>

          <ul v-if="repeats > 1 || job.scenarios.some((s) => s.runs > 1)" class="stability">
            <li v-for="s in job.scenarios" :key="s.index">
              <span class="stab-name">{{ scenarioLabel(s.index) }}</span>
              <span class="num">{{ s.passed }}/{{ s.runs }}</span>
              <span :class="s.stable === false ? 'warn-text' : 'ok-text'">{{ s.stable === null ? '' : s.stable ? $t('lab.stable') : $t('lab.unstable') }}</span>
            </li>
          </ul>

          <div class="runs">
            <details v-for="(r, i) in job.results" :key="i" :class="['run', r.status]" @toggle="onRunToggle(i, $event)">
              <summary>
                <span class="run-dot" aria-hidden="true"></span>
                <span class="run-title">{{ scenarioLabel(r.scenario) }} <span class="run-attempt">· {{ $t('lab.attempt', { n: r.repeat }) }}</span></span>
                <span class="pill">{{ $t(`lab.run_status.${r.status}`) }}</span>
                <span class="run-meta">{{ r.seconds ? `${r.seconds}s` : '' }}{{ r.tokens ? ` · ${r.tokens.toLocaleString()} token` : '' }}</span>
                <svg class="run-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
              </summary>
              <div class="run-body">
                <p v-if="r.judge?.reason" class="judge"><strong>{{ $t('lab.judge') }}:</strong> {{ r.judge.reason }}</p>
                <p v-if="r.error" class="error">{{ r.error }}</p>
                <p v-if="r.agents && Object.keys(r.agents).length" class="meta-line">
                  <strong>{{ $t('lab.agents_used') }}:</strong>
                  {{ Object.entries(r.agents).map(([n, c]) => (c > 1 ? `${n} ×${c}` : n)).join(', ') }}
                </p>
                <div v-if="r.questions?.length" class="meta-line">
                  <strong>{{ $t('lab.questions_asked') }}:</strong>
                  <ul><li v-for="(q, qi) in r.questions" :key="qi">{{ q.node }}: {{ q.question }}</li></ul>
                </div>
                <!-- Rendered only once the run is opened: long answers stay out of the DOM until needed -->
                <div v-if="r.answer && openRuns.has(i)" class="answer markdown-body" v-html="render(r.answer)"></div>
              </div>
            </details>
          </div>
        </section>
      </div>

      <!-- Config health (sticky side panel) -->
      <aside class="side-col">
        <section class="card panel health-panel">
          <header class="panel-head compact">
            <span class="icon-tile sky" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
            </span>
            <div class="panel-text">
              <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 1 }) }}</p>
              <h2 class="panel-title">{{ stripNo($t('lab.check_title')) }}</h2>
            </div>
            <button
              type="button"
              class="icon-btn"
              :title="$t('lab.check_run')"
              :aria-label="$t('lab.check_run')"
              :disabled="checking"
              @click="runCheck"
            >
              <span v-if="checking" class="spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" /><path d="M21 3v5h-5" /></svg>
            </button>
          </header>
          <p class="panel-hint">{{ $t('lab.check_hint') }}</p>

          <p v-if="checkError" class="error" role="alert">{{ checkError }}</p>

          <template v-if="report">
            <div class="meter" role="img" :aria-label="`${checkCounts.pass} ${$t('lab.status.pass')}, ${checkCounts.warn} ${$t('lab.status.warn')}, ${checkCounts.fail} ${$t('lab.status.fail')}`">
              <span v-for="s in ['pass', 'warn', 'fail']" v-show="checkCounts[s]" :key="s" :class="['seg', s]" :style="{ flexGrow: checkCounts[s] }"></span>
            </div>
            <div class="chips">
              <span v-for="s in ['pass', 'warn', 'fail']" v-show="checkCounts[s]" :key="s" :class="['chip', s]">
                <span class="chip-count">{{ checkCounts[s] }}</span>
                {{ $t(`lab.status.${s}`) }}
              </span>
              <span class="chip-total">/ {{ checkTotal }}</span>
            </div>
            <ul class="check-list">
              <li v-for="item in report.checks" :key="item.id" :class="['check-item', item.status]">
                <span class="status-icon" role="img" :aria-label="$t(`lab.status.${item.status}`)">
                  <svg v-if="item.status === 'pass'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5 9-10" /></svg>
                  <svg v-else-if="item.status === 'warn'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v6M12 17h.01" /></svg>
                  <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7l10 10M17 7 7 17" /></svg>
                </span>
                <div class="check-text">
                  <span class="check-name">{{ $t(`lab.checks.${item.id}.title`) }}</span>
                  <span v-if="item.status !== 'pass'" class="check-detail">
                    {{ $t(`lab.checks.${item.id}.problem`) }}
                    <code v-if="item.detail">{{ item.detail }}</code>
                  </span>
                </div>
              </li>
            </ul>
          </template>
          <div v-else-if="checking" class="skeleton" aria-hidden="true">
            <span v-for="n in 5" :key="n"></span>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import { fetchWorkflowNames, labCancel, labCheck, labEvaluate, labJob } from '@/api/client'

const { t, te } = useI18n()
const route = useRoute()
const router = useRouter()
// Some lab strings are newer than the locale files: fall back to Vietnamese until they are added.
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
// Polling replaces the job every 2 s; cache rendered answers so the same text is never parsed twice.
const renderCache = new Map()
const render = (text) => {
  const key = text || ''
  let html = renderCache.get(key)
  if (html === undefined) {
    html = md.render(key)
    if (renderCache.size > 200) renderCache.clear()
    renderCache.set(key, html)
  }
  return html
}
const openRuns = ref(new Set())
const onRunToggle = (index, event) => {
  const next = new Set(openRuns.value)
  if (event.target.open) next.add(index)
  else next.delete(index)
  openRuns.value = next
}
// Step titles carry their own "1. " prefix; the intro cards show the number in a badge instead.
const stripNo = (text) => String(text).replace(/^\d+\.\s*/, '')

const workflows = ref([])
const workflow = ref('')
const report = ref(null)
const checking = ref(false)
const checkError = ref('')

let keySeq = 1
const newScenario = (data = {}) => reactive({ key: keySeq++, name: '', prompt: '', criteria: '', ...data })
const scenarios = ref([newScenario()])
const repeats = ref(1)
const job = ref(null)
const evalError = ref('')
const starting = ref(false)
// Scenarios exactly as sent with the run (blank prompts dropped), so result indexes match the backend's.
const submitted = ref([])
let pollTimer = null
let pollErrors = 0
let unmounted = false
const MAX_POLL_ERRORS = 3

const isRunning = computed(() => job.value && ['queued', 'running'].includes(job.value.status))
const plannedRuns = computed(() => scenarios.value.filter((s) => s.prompt.trim()).length * repeats.value)
const scenarioLabel = (index) => submitted.value[index]?.name?.trim() || t('lab.scenario_name', { n: index + 1 })

// Summary strip + health panel
const checkCounts = computed(() => {
  const counts = { pass: 0, warn: 0, fail: 0 }
  for (const c of report.value?.checks || []) counts[c.status] = (counts[c.status] || 0) + 1
  return counts
})
const checkTotal = computed(() => checkCounts.value.pass + checkCounts.value.warn + checkCounts.value.fail)
const health = computed(() => {
  if (!report.value) return null
  if (checkCounts.value.fail) return 'fail'
  if (checkCounts.value.warn) return 'warn'
  return 'pass'
})
const passPct = computed(() => (job.value?.status === 'completed' ? Math.round(job.value.pass_rate * 100) : null))
const progressPct = computed(() => (job.value?.total ? Math.round((job.value.done / job.value.total) * 100) : 0))
const filledScenarios = computed(() => scenarios.value.filter((s) => s.prompt.trim()).length)

// Scenarios are kept per workflow in this browser so a test suite can be re-run after changes.
const storageKey = (name) => `agentdev.lab.scenarios.${name}`
function saveScenarios(name = workflow.value) {
  clearTimeout(saveTimer)
  saveTimer = null
  if (!name) return
  try {
    const data = scenarios.value.map(({ name, prompt, criteria }) => ({ name, prompt, criteria }))
    localStorage.setItem(storageKey(name), JSON.stringify({ scenarios: data, repeats: repeats.value }))
  } catch {
    // storage unavailable: scenarios simply aren't remembered
  }
}
// Typing in a scenario must not serialize + write storage on every keystroke: save once typing pauses.
let saveTimer = null
let pendingSave = false
function scheduleSave() {
  pendingSave = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    pendingSave = false
    saveScenarios()
  }, 400)
}
function flushSave(name) {
  if (!pendingSave) return
  pendingSave = false
  saveScenarios(name)
}
function loadScenarios(name) {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(name)) || 'null')
    if (saved?.scenarios?.length) {
      scenarios.value = saved.scenarios.map((s) => newScenario(s))
      repeats.value = saved.repeats || 1
      return
    }
  } catch {
    // ignore unreadable storage
  }
  scenarios.value = [newScenario()]
  repeats.value = 1
}

// The latest run per workflow is remembered for this tab, so a reload shows its results again
// (the run itself lives in the server's memory until the server restarts).
const jobKey = (name) => `agentdev.lab.job.${name}`
const LAST_WORKFLOW_KEY = 'agentdev.lab.workflow'
function rememberJob(name, id, list) {
  try {
    sessionStorage.setItem(jobKey(name), JSON.stringify({ id, submitted: list }))
  } catch {
    // storage unavailable: results are simply not restored after a reload
  }
}
async function restoreJob(name) {
  let saved = null
  try {
    saved = JSON.parse(sessionStorage.getItem(jobKey(name)) || 'null')
  } catch {
    saved = null
  }
  if (!saved?.id) return
  try {
    const data = await labJob(saved.id)
    if (unmounted || workflow.value !== name || job.value) return
    submitted.value = Array.isArray(saved.submitted) ? saved.submitted : []
    lastJobSnapshot = JSON.stringify(data)
    pollErrors = 0
    job.value = data
    if (isRunning.value) schedulePoll(1500)
  } catch {
    // Gone (server restarted): forget it
    try {
      sessionStorage.removeItem(jobKey(name))
    } catch {
      // ignore
    }
  }
}

watch(workflow, (name, previous) => {
  flushSave(previous) // edits made just before switching still belong to the previous workflow
  openRuns.value = new Set()
  report.value = null
  checkError.value = ''
  stopPolling()
  job.value = null
  submitted.value = []
  if (name) {
    // Keep the choice in the address bar and for the next visit
    if (route.query.workflow !== name) router.replace({ query: { ...route.query, workflow: name } })
    try {
      localStorage.setItem(LAST_WORKFLOW_KEY, name)
    } catch {
      // ignore
    }
    loadScenarios(name)
    runCheck()
    restoreJob(name)
  }
})
watch([scenarios, repeats], scheduleSave, { deep: true })

function addScenario(data) {
  scenarios.value.push(newScenario(data))
}
function removeScenario(index) {
  scenarios.value.splice(index, 1)
}
function addSamples() {
  const samples = [
    { name: t('lab.sample1_name'), prompt: t('lab.sample1_prompt'), criteria: t('lab.sample1_criteria') },
    { name: t('lab.sample2_name'), prompt: t('lab.sample2_prompt'), criteria: t('lab.sample2_criteria') }
  ]
  if (scenarios.value.length === 1 && !scenarios.value[0].prompt.trim()) scenarios.value = []
  samples.forEach((s) => addScenario(s))
}

async function runCheck() {
  if (!workflow.value) return
  checking.value = true
  checkError.value = ''
  try {
    report.value = await labCheck(workflow.value)
  } catch (error) {
    checkError.value = error.message
  } finally {
    checking.value = false
  }
}

function stopPolling() {
  clearTimeout(pollTimer)
  pollTimer = null
}

function schedulePoll(delay) {
  stopPolling()
  if (!unmounted) pollTimer = setTimeout(poll, delay)
}

// The run only lives in the server's memory: after a restart it is gone and polling would never end.
function markJobLost() {
  const message = tr('lab.job_lost', 'Không còn theo dõi được lượt chạy này (máy chủ có thể đã khởi động lại). Hãy chạy lại.')
  job.value = { ...job.value, status: 'error', error: message }
  evalError.value = message
}

async function poll() {
  pollTimer = null
  if (!job.value || unmounted) return
  const id = job.value.id
  try {
    const data = await labJob(id)
    if (unmounted || job.value?.id !== id) return
    // Nothing changed since the last poll: keep the same object so nothing re-renders.
    const snapshot = JSON.stringify(data)
    if (snapshot !== lastJobSnapshot) {
      lastJobSnapshot = snapshot
      job.value = data
    }
    pollErrors = 0
    evalError.value = ''
  } catch (error) {
    if (unmounted || job.value?.id !== id) return
    pollErrors += 1
    if (error.status === 404 || pollErrors >= MAX_POLL_ERRORS) {
      markJobLost()
      return
    }
    evalError.value = error.message
  }
  // Background tab: nobody is watching, poll less often.
  if (isRunning.value) schedulePoll(document.hidden ? 6000 : 2000)
}
let lastJobSnapshot = ''

async function startEval() {
  if (starting.value || isRunning.value) return
  evalError.value = ''
  const list = scenarios.value
    .filter((s) => s.prompt.trim())
    .map(({ name, prompt, criteria }) => ({ name, prompt, criteria }))
  starting.value = true
  try {
    const started = await labEvaluate({ yamlFile: workflow.value, scenarios: list, repeats: repeats.value })
    if (unmounted) return
    submitted.value = list
    pollErrors = 0
    job.value = started
    rememberJob(workflow.value, started.id, list)
    schedulePoll(1500)
  } catch (error) {
    evalError.value = error.message
  } finally {
    starting.value = false
  }
}

async function stopEval() {
  if (!job.value) return
  try {
    job.value = await labCancel(job.value.id)
  } catch (error) {
    if (error.status === 404) markJobLost()
    else evalError.value = error.message
  }
}

onMounted(async () => {
  try {
    // Only the names are shown: one request instead of one per workflow
    workflows.value = (await fetchWorkflowNames()).map((name) => ({ name }))
  } catch (error) {
    checkError.value = error.message
  }
  let preset = route.query.workflow
  if (!preset) {
    try {
      preset = localStorage.getItem(LAST_WORKFLOW_KEY)
    } catch {
      preset = null
    }
  }
  if (preset && workflows.value.some((w) => w.name === preset)) workflow.value = preset
})
onBeforeUnmount(() => {
  unmounted = true
  stopPolling()
  flushSave()
})
</script>

<style scoped>
.lab-view {
  --line: rgb(var(--ink) / 0.08);
  --line-strong: rgb(var(--ink) / 0.14);
  --tint: rgb(var(--ink) / 0.035);
  --tint-2: rgb(var(--ink) / 0.06);
  --warn: #f59e0b;
  --radius: 14px;
  box-sizing: border-box; width: 100%; max-width: 1240px; margin: 0 auto; padding: 40px 32px 88px;
  color: var(--text-1); font-family: 'Inter', system-ui, sans-serif; font-variant-numeric: tabular-nums;
}
:root[data-theme='light'] .lab-view { --warn: #b45309; }

/* ================================================================ header */
.hero { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-end; justify-content: space-between; margin-bottom: 24px; }
.hero-kicker {
  display: inline-flex; align-items: center; gap: 8px; margin: 0 0 10px; padding: 4px 10px 4px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 650; letter-spacing: 0.04em; color: var(--accent-sky);
  background: rgb(var(--accent-sky-rgb) / 0.1); box-shadow: inset 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.22);
}
.kicker-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 3px rgb(var(--accent-sky-rgb) / 0.2); }
.hero-title { margin: 0 0 8px; font-size: 30px; line-height: 1.15; font-weight: 750; letter-spacing: -0.03em; color: var(--text-strong); }
.hero-sub { margin: 0; max-width: 70ch; font-size: 14.5px; line-height: 1.65; color: var(--text-muted-4); }
.ext { opacity: 0.6; }

/* ================================================================ cards */
.card {
  border-radius: var(--radius); background: var(--surface-1);
  box-shadow: inset 0 0 0 1px var(--line), 0 1px 2px rgb(0 0 0 / 0.04), 0 12px 32px -24px rgb(0 0 0 / 0.35);
}
.icon-tile {
  display: grid; flex: none; place-items: center; width: 36px; height: 36px; border-radius: 10px;
  --c: var(--accent-sky-rgb); color: rgb(var(--c)); background: rgb(var(--c) / 0.12); box-shadow: inset 0 0 0 1px rgb(var(--c) / 0.22);
}
.icon-tile.indigo { --c: var(--accent-indigo-rgb); }
.icon-tile.mint { --c: var(--accent-mint-rgb); }
.step-label { margin: 0 0 2px; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted-4); }
.muted { color: var(--text-muted-4); font-weight: 500; }

/* ================================================================ control bar */
.control { display: flex; align-items: stretch; gap: 0; margin-bottom: 20px; overflow: hidden; }
.picker-field { flex: 1 1 320px; min-width: 240px; padding: 16px 20px; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(104px, auto)); margin: 0; border-left: 1px solid var(--line); }
.metric { display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 14px 20px; border-left: 1px solid var(--line); }
.metric:first-child { border-left: 0; }
.metric dt { font-size: 11px; font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted-4); white-space: nowrap; }
.metric dd { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.02em; color: var(--text-strong); white-space: nowrap; }
.metric dd .muted { font-size: 14px; }
.unit { font-size: 13px; font-weight: 600; color: var(--text-muted-4); letter-spacing: 0; }
.rate.ready { color: var(--accent-mint); }
.rate.not_ready { color: var(--danger); }
.health-tag { display: inline-flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 650; }
.health-tag .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 22%, transparent); }
.health-tag.pass { color: var(--accent-mint); }
.health-tag.warn { color: var(--warn); }
.health-tag.fail { color: var(--danger); }

/* ================================================================ empty state */
.intro { padding: 28px; }
.intro-head { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; justify-content: space-between; margin-bottom: 20px; }
.intro-heading { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-strong); }
.intro-cta { margin: 0; font-size: 13px; color: var(--text-muted-4); }
.intro-steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; position: relative; }
.intro-step { display: flex; gap: 14px; align-items: flex-start; padding: 20px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.intro-title { margin: 0 0 6px; font-size: 15.5px; font-weight: 650; color: var(--text-strong); }
.intro-desc { margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--text-muted-4); }

/* ================================================================ workspace */
.workspace { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px; align-items: start; }
.main-col { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
.side-col { position: sticky; top: 20px; min-width: 0; }
.panel { padding: 22px 24px; }
.panel-head { display: flex; gap: 14px; align-items: flex-start; margin-bottom: 18px; }
.panel-head.compact { margin-bottom: 10px; align-items: center; }
.panel-text { flex: 1; min-width: 0; }
.panel-title { margin: 0; font-size: 16px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-strong); }
.panel-hint { margin: 4px 0 0; font-size: 13px; color: var(--text-muted-4); line-height: 1.55; }
.health-panel > .panel-hint { margin: 0 0 16px; }

/* ================================================================ fields */
.field { display: flex; flex-direction: column; gap: 6px; margin: 0; min-width: 0; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text-muted-6); }
.select-wrap { position: relative; display: block; }
.select-wrap select { width: 100%; appearance: none; -webkit-appearance: none; padding-right: 38px; }
.select-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted-4); pointer-events: none; }
.picker-field select { padding-left: 38px; font-weight: 600; font-size: 14px; min-height: 42px; }
.select-chevron { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted-4); pointer-events: none; }
.field select, .field textarea, .scenario-name, .repeat select {
  box-sizing: border-box; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line-strong); background: var(--tint);
  color: var(--text-1); font-size: 13.5px; font-family: inherit; transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
}
.field textarea { resize: vertical; line-height: 1.55; min-height: 84px; }
.field select:hover:not(:disabled), .field textarea:hover:not(:disabled), .scenario-name:hover:not(:disabled), .repeat select:hover:not(:disabled) { border-color: rgb(var(--ink) / 0.24); }
.field select:focus-visible, .field textarea:focus-visible, .scenario-name:focus-visible, .repeat select:focus-visible {
  outline: none; border-color: var(--accent-sky); background: var(--surface-1); box-shadow: 0 0 0 3px rgb(var(--accent-sky-rgb) / 0.2);
}
.field select:disabled, .field textarea:disabled, .scenario-name:disabled, .repeat select:disabled { opacity: 0.55; cursor: not-allowed; }
.field textarea::placeholder, .scenario-name::placeholder { color: var(--text-muted-4); opacity: 0.8; }

/* ================================================================ buttons */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; border-radius: 10px; padding: 0 16px;
  font-size: 13.5px; font-weight: 600; font-family: inherit; cursor: pointer; border: 0; background: var(--surface-1);
  box-shadow: inset 0 0 0 1px var(--line-strong), 0 1px 2px rgb(0 0 0 / 0.05); color: var(--text-1);
  text-decoration: none; white-space: nowrap; transition: background-color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
}
.btn:hover:not(:disabled) { color: var(--text-1); background: var(--tint-2); }
.btn:active:not(:disabled) { transform: translateY(1px); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.subtle { min-height: 34px; padding: 0 12px; font-size: 13px; background: transparent; box-shadow: inset 0 0 0 1px var(--line); }
.btn.subtle:hover:not(:disabled) { background: var(--tint-2); }
.btn.primary {
  min-height: 42px; padding: 0 20px; color: #05141f; box-shadow: 0 1px 0 rgb(255 255 255 / 0.25) inset, 0 6px 16px -6px rgb(var(--accent-sky-rgb) / 0.6);
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent-sky) 92%, white), var(--accent-sky));
}
.btn.primary:hover:not(:disabled) { background: var(--accent-sky); filter: brightness(1.05); }
:root[data-theme='light'] .btn.primary { color: #fff; }
.btn.danger-ghost { background: transparent; color: var(--danger); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 45%, transparent); }
.btn.danger-ghost:hover { background: color-mix(in srgb, var(--danger) 10%, transparent); }
.icon-btn {
  display: grid; place-items: center; flex: none; width: 34px; height: 34px; border-radius: 9px; border: 0; cursor: pointer;
  color: var(--text-muted-4); background: transparent; transition: color 0.15s ease, background-color 0.15s ease;
}
.icon-btn:hover:not(:disabled) { color: var(--text-1); background: var(--tint-2); }
.icon-btn.danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn:focus-visible, .icon-btn:focus-visible, .run summary:focus-visible { outline: 2px solid var(--accent-sky); outline-offset: 2px; }
.error { color: var(--danger); font-size: 13px; margin: 12px 0 0; line-height: 1.5; }
.spinner { width: 13px; height: 13px; border-radius: 50%; border: 2px solid color-mix(in srgb, currentColor 30%, transparent); border-top-color: currentColor; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ================================================================ scenarios */
.scenario-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.scenario { padding: 14px 16px 16px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); transition: box-shadow 0.15s ease; }
.scenario:focus-within { box-shadow: inset 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.45); }
.scenario-head { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.scenario-no { flex: none; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; color: var(--accent-indigo); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
.scenario-name { flex: 1; min-width: 0; padding: 6px 8px; font-size: 14px; font-weight: 650; border-color: transparent; background: transparent; }
.scenario-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.scenario-fields textarea { background: var(--surface-1); }
.scenario-tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
.repeat { display: flex; gap: 10px; align-items: center; font-size: 13px; color: var(--text-muted-4); margin-left: auto; }
.select-wrap.small select { padding: 6px 30px 6px 12px; min-width: 64px; }
.select-wrap.small .select-chevron { right: 9px; }
.run-bar {
  display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  margin: 20px -24px -22px; padding: 16px 24px; border-top: 1px solid var(--line);
  background: var(--tint); border-radius: 0 0 var(--radius) var(--radius);
}
.run-note { display: flex; gap: 8px; align-items: flex-start; flex: 1; min-width: 220px; margin: 0; font-size: 12.5px; line-height: 1.55; color: var(--text-muted-4); }
.run-note svg { flex: none; margin-top: 2px; }
.panel > .error:last-child { margin-top: 30px; }

/* ================================================================ config health */
.meter { display: flex; gap: 3px; height: 6px; margin-bottom: 12px; }
.seg { border-radius: 999px; min-width: 6px; }
.seg.pass { background: var(--accent-mint); }
.seg.warn { background: var(--warn); }
.seg.fail { background: var(--danger); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.chip-count { font-weight: 750; }
.chip.pass { color: var(--accent-mint); background: color-mix(in srgb, var(--accent-mint) 12%, transparent); }
.chip.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); }
.chip.fail { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.chip-total { font-size: 12px; color: var(--text-muted-4); }
.check-list { list-style: none; margin: 0 -8px; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.check-item { --tone: var(--accent-mint); display: flex; gap: 10px; align-items: flex-start; padding: 8px; border-radius: 9px; }
.check-item.warn { --tone: var(--warn); background: color-mix(in srgb, var(--warn) 7%, transparent); }
.check-item.fail { --tone: var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); }
.status-icon { flex: none; width: 20px; height: 20px; display: grid; place-items: center; border-radius: 50%; color: var(--tone); background: color-mix(in srgb, var(--tone) 16%, transparent); }
.check-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; padding-top: 1px; }
.check-name { font-weight: 600; font-size: 13px; }
.check-item.pass .check-name { font-weight: 500; color: var(--text-muted-6); }
.check-detail { font-size: 12.5px; color: var(--text-muted-4); line-height: 1.5; overflow-wrap: anywhere; }
.check-detail code { display: block; margin-top: 6px; padding: 7px 9px; border-radius: 7px; background: var(--tint-2); white-space: pre-wrap; word-break: break-word; font-size: 11.5px; color: var(--text-1); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
.skeleton { display: flex; flex-direction: column; gap: 10px; }
.skeleton span { height: 14px; border-radius: 6px; background: linear-gradient(90deg, var(--tint), var(--tint-2), var(--tint)); background-size: 200% 100%; animation: shimmer 1.4s ease-in-out infinite; }
.skeleton span:nth-child(2n) { width: 75%; }
@keyframes shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }

/* ================================================================ results */
.verdict {
  --tone: var(--accent-mint); display: flex; align-items: center; gap: 20px; padding: 18px 20px; border-radius: 12px; margin-bottom: 14px;
  background: color-mix(in srgb, var(--tone) 8%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 30%, transparent);
}
.verdict.not_ready { --tone: var(--danger); }
.verdict-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.verdict-text strong { font-size: 16px; color: var(--tone); }
.verdict-text span { font-size: 13.5px; color: var(--text-muted-6); line-height: 1.5; }
.ring {
  flex: none; width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; position: relative;
  background: conic-gradient(var(--tone) var(--p), color-mix(in srgb, var(--tone) 16%, transparent) 0);
}
.ring::before { content: ''; position: absolute; inset: 7px; border-radius: 50%; background: var(--surface-1); }
.ring span { position: relative; font-size: 19px; font-weight: 750; color: var(--text-strong); }
.ring small { font-size: 11px; font-weight: 600; margin-left: 1px; color: var(--text-muted-4); }
.progress { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.progress-row { display: flex; justify-content: space-between; font-size: 13px; }
.progress-label { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; }
.progress-num { color: var(--text-muted-4); }
.pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-sky); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.35; transform: scale(0.8); } }
.bar { height: 6px; border-radius: 999px; background: var(--tint-2); overflow: hidden; }
/* scaleX instead of width: the bar animates on the compositor, no layout per frame */
.fill { width: 100%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent-sky), var(--accent-indigo)); transform-origin: 0 50%; transition: transform 0.4s ease; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0 0 14px; }
.kpi { padding: 12px 14px; border-radius: 11px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.kpi dt { font-size: 11px; font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted-4); margin-bottom: 4px; }
.kpi dd { margin: 0; font-size: 18px; font-weight: 700; color: var(--text-strong); letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stability { list-style: none; margin: 0 0 14px; padding: 4px 0; border-radius: 11px; box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; }
.stability li { display: grid; grid-template-columns: 1fr auto auto; gap: 16px; align-items: center; padding: 8px 14px; }
.stability li + li { border-top: 1px solid var(--line); }
.stab-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { font-weight: 650; }
.warn-text { color: var(--warn); font-weight: 600; }
.ok-text { color: var(--accent-mint); font-weight: 600; }

.runs { border-radius: 11px; box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
.run { --tone: var(--text-muted-4); }
.run + .run { border-top: 1px solid var(--line); }
.run.passed { --tone: var(--accent-mint); }
.run.failed, .run.error { --tone: var(--danger); }
.run.running { --tone: var(--accent-sky); }
.run summary { display: flex; gap: 10px; align-items: center; cursor: pointer; font-size: 13px; padding: 11px 14px; list-style: none; transition: background-color 0.15s ease; }
.run summary:hover { background: var(--tint); }
.run summary::-webkit-details-marker { display: none; }
.run[open] summary { background: var(--tint); }
.run-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--tone); }
.run-title { flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-attempt { font-weight: 500; color: var(--text-muted-4); }
.run-meta { color: var(--text-muted-4); font-size: 12px; white-space: nowrap; }
.run-chevron { flex: none; color: var(--text-muted-4); transition: transform 0.2s ease; }
.run[open] .run-chevron { transform: rotate(180deg); }
.pill { flex: none; font-size: 11px; font-weight: 650; padding: 2px 9px; border-radius: 999px; color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, transparent); }
.run-body { padding: 2px 14px 14px 32px; }
.judge, .meta-line { font-size: 13px; line-height: 1.6; margin: 10px 0 0; color: var(--text-muted-6); }
.judge strong, .meta-line strong { color: var(--text-1); }
.meta-line ul { margin: 4px 0 0; padding-left: 18px; }
.answer { margin: 12px 0 0; padding: 14px 16px; border-radius: 10px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; max-height: 380px; overflow: auto; }

/* ================================================================ responsive */
@media (max-width: 1080px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .side-col { position: static; order: -1; }
  .control { flex-wrap: wrap; }
  .metrics { flex: 1 1 100%; border-left: 0; border-top: 1px solid var(--line); grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .lab-view { padding: 28px 16px 64px; }
  .hero-title { font-size: 26px; }
  .intro { padding: 18px; }
  .intro-steps { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric:nth-child(3) { border-left: 0; }
  .metric:nth-child(n + 3) { border-top: 1px solid var(--line); }
  .panel { padding: 16px; }
  .run-bar { margin: 16px -16px -16px; padding: 14px 16px; }
  .run-bar .btn { width: 100%; }
  .scenario-fields { grid-template-columns: 1fr; }
  .repeat { margin-left: 0; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .run-meta { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .spinner { animation-duration: 2s; }
  .pulse, .skeleton span { animation: none; }
  .fill, .run-chevron, .btn, .scenario, .run summary { transition: none; }
}
</style>
