<template>
  <div class="review">
    <div class="review-body" :class="{ 'show-detail': showDetail && selected }">
      <!-- Queue -->
      <aside class="queue">
        <header class="queue-head">
          <span class="eyebrow">{{ $t('launch.review.eyebrow') }}</span>
          <h2>{{ $t('launch.review.title') }}</h2>
          <p>{{ $t('launch.review.subtitle') }}</p>
        </header>

        <section v-if="awaitingPlans.length" class="plans" :aria-label="$t('launch.plan.section')">
          <h3 class="plans-title">
            {{ $t('launch.plan.section') }}<span class="tab-count">{{ awaitingPlans.length }}</span>
          </h3>
          <ul class="plans-list">
            <li v-for="item in awaitingPlans" :key="item.session_id">
              <button type="button" class="plan-item" @click="$emit('open-session', item)">
                <span class="qi-top">
                  <span class="verdict-dot is-waiting" aria-hidden="true"></span>
                  <span class="qi-title" :title="item.title">{{ item.title || item.yaml_file }}</span>
                  <span class="plan-open">{{ $t('launch.plan.open') }} →</span>
                </span>
                <span class="qi-meta">
                  <span>{{ metaOf(item) }}</span>
                  <time>{{ ago(item.updated_at) }}</time>
                </span>
              </button>
            </li>
          </ul>
        </section>

        <div class="tabs" role="tablist">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            role="tab"
            :aria-selected="activeTab === tab.key"
            class="tab"
            :class="[`is-${tab.tone}`, { active: activeTab === tab.key }]"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}<span class="tab-count">{{ tab.count }}</span>
          </button>
        </div>

        <label class="search">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input v-model="query" type="search" :placeholder="$t('launch.review.search')" />
        </label>

        <ul v-if="queue.length" class="queue-list">
          <li v-for="item in queue" :key="item.session_id">
            <button
              type="button"
              class="queue-item"
              :class="{ active: item.session_id === selectedId }"
              @click="select(item.session_id)"
            >
              <span class="qi-top">
                <span class="verdict-dot" :class="`is-${verdictTone(item)}`" aria-hidden="true"></span>
                <span class="qi-title" :title="item.title">{{ item.title || item.yaml_file }}</span>
                <span v-if="roundOf(item.session_id) > 1" class="round">{{ $t('launch.review.round', { n: roundOf(item.session_id) }) }}</span>
              </span>
              <span class="qi-meta">
                <span>{{ metaOf(item) }}</span>
                <time>{{ ago(item.updated_at) }}</time>
              </span>
              <span v-if="item.review?.rating" class="stars-mini" :aria-label="$t('launch.review.rated', { n: item.review.rating })">
                <span v-for="n in 5" :key="n" :class="{ on: n <= item.review.rating }">★</span>
              </span>
            </button>
          </li>
        </ul>
        <div v-else class="queue-empty">
          <span aria-hidden="true">✓</span>
          <p>{{ emptyText }}</p>
        </div>
      </aside>

      <!-- Detail -->
      <section class="detail">
        <div v-if="!selected" class="detail-empty">
          <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 11l3 3 8-8" /><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" /></svg>
          <p>{{ $t('launch.review.pick') }}</p>
        </div>

        <template v-else>
          <header class="detail-head">
            <button type="button" class="link back" @click="showDetail = false">← {{ $t('launch.review.back') }}</button>
            <div class="dh-main">
              <div class="dh-tags">
                <span class="pill" :class="`is-${verdictTone(selected)}`"><span class="dot" aria-hidden="true"></span>{{ verdictLabel(selected) }}</span>
                <span v-if="roundOf(selected.session_id) > 1" class="round">{{ $t('launch.review.round', { n: roundOf(selected.session_id) }) }}</span>
              </div>
              <h3 :title="selected.title">{{ selected.title || selected.yaml_file }}</h3>
              <p class="dh-meta">
                <span v-for="part in detailMeta" :key="part.text" :title="part.title">{{ part.text }}</span>
              </p>
            </div>
            <button type="button" class="btn btn-ghost" @click="$emit('open-session', selected)">
              {{ $t('launch.review.open_session') }}
            </button>
          </header>

          <div v-if="loading" class="loading"><span class="spinner" aria-hidden="true"></span>{{ $t('launch.review.loading') }}</div>
          <p v-else-if="loadError" class="load-error">{{ loadError }}</p>

          <div v-else-if="digest" class="detail-grid">
            <div class="content">
              <!-- Previous round: what you asked to change -->
              <aside v-if="parent?.review" class="lineage">
                <strong>{{ $t('launch.review.lineage_title', { n: roundOf(parent.session_id) }) }}</strong>
                <p v-if="parent.review.tags?.length" class="lineage-tags">
                  <span v-for="tag in parent.review.tags" :key="tag" class="tag is-issue">{{ tagLabel(tag) }}</span>
                </p>
                <p v-if="parent.review.feedback" class="lineage-text">“{{ parent.review.feedback }}”</p>
                <button type="button" class="link" @click="select(parent.session_id)">{{ $t('launch.review.see_previous') }}</button>
              </aside>

              <section class="panel">
                <h4>{{ $t('launch.review.request') }}</h4>
                <p class="pre">{{ originalTask(digest.task?.text) || '—' }}</p>
                <div v-if="digest.task?.attachments?.length" class="chips">
                  <span v-for="(name, i) in digest.task.attachments" :key="`${i}-${name}`" class="chip">📎 {{ name }}</span>
                </div>
                <details v-if="digest.other_requests?.length" class="replies">
                  <summary>{{ $t('launch.review.other_requests', { n: digest.other_requests.length }) }}</summary>
                  <ol>
                    <li v-for="(text, i) in digest.other_requests" :key="i">{{ text }}</li>
                  </ol>
                </details>
                <details v-if="digest.replies.length" class="replies">
                  <summary>{{ $t('launch.review.replies', { n: digest.replies.length }) }}</summary>
                  <ol>
                    <li v-for="(reply, i) in digest.replies" :key="i">{{ reply }}</li>
                  </ol>
                </details>
              </section>

              <section class="panel is-result">
                <h4>
                  {{ $t('launch.review.delivered') }}
                  <span class="pill" :class="`is-${digest.outcome || 'idle'}`"><span class="dot" aria-hidden="true"></span>{{ outcomeLabel }}</span>
                </h4>
                <div v-if="resultSummary" class="md" v-html="render(resultSummary)"></div>
                <p v-else class="muted">{{ $t('launch.review.no_summary') }}</p>
                <p v-if="digest.error" class="load-error">{{ digest.error }}</p>
              </section>

              <section v-if="digest.files.length" class="panel">
                <h4>{{ $t('launch.review.files', { n: digest.files.length }) }}</h4>
                <ul class="files">
                  <li v-for="file in digest.files" :key="file.path">
                    <span class="change" :class="`is-${file.change}`">{{ changeLabel(file.change) }}</span>
                    <code :title="file.path">{{ file.path }}</code>
                    <span v-if="file.node_id" class="muted">{{ file.node_id }}</span>
                  </li>
                </ul>
              </section>

              <section v-if="digest.steps.length" class="panel">
                <h4>{{ $t('launch.review.handovers', { n: digest.steps.length }) }}</h4>
                <div class="handovers">
                  <details v-for="(step, i) in digest.steps" :key="step.node_id" class="handover" :open="i === digest.steps.length - 1">
                    <summary>
                      <span class="ho-index">{{ i + 1 }}</span>
                      <span class="ho-name">{{ step.node_id }}</span>
                      <span class="muted">
                        {{ step.runs > 1 ? $t('launch.board.runs', { n: step.runs }) + ' · ' : '' }}{{ stepTime(step) }}
                      </span>
                    </summary>
                    <div v-if="step.output" class="md" v-html="render(step.output)"></div>
                    <p v-else class="muted">{{ $t('launch.board.no_output') }}</p>
                  </details>
                </div>
              </section>
            </div>

            <!-- Verdict -->
            <aside class="verdict card">
              <template v-if="existing && !editing">
                <div class="verdict-done" :class="`is-${existing.verdict}`">
                  <span class="vd-icon" aria-hidden="true">{{ existing.verdict === 'approved' ? '✓' : '↻' }}</span>
                  <div>
                    <strong>{{ existing.verdict === 'approved' ? $t('launch.review.approved_title') : $t('launch.review.rework_title') }}</strong>
                    <span>{{ formatDate(existing.reviewed_at) }}</span>
                  </div>
                </div>
                <p v-if="existing.rating" class="stars-line">
                  <span v-for="n in 5" :key="n" :class="{ on: n <= existing.rating }">★</span>
                  <span class="muted">{{ ratingLabel(existing.rating) }}</span>
                </p>
                <p v-if="existing.tags?.length" class="tags-line">
                  <span v-for="tag in existing.tags" :key="tag" class="tag" :class="isIssue(tag) ? 'is-issue' : 'is-good'">{{ tagLabel(tag) }}</span>
                </p>
                <p v-if="existing.feedback" class="feedback-quote">“{{ existing.feedback }}”</p>
                <button v-if="reworkChild" type="button" class="btn btn-soft" @click="select(reworkChild.session_id)">
                  {{ $t('launch.review.see_rework', { n: roundOf(reworkChild.session_id), status: sessionStatusLabel(reworkChild.status) }) }}
                </button>
                <button type="button" class="link" @click="startEditing">{{ $t('launch.review.change') }}</button>
              </template>

              <template v-else>
                <h4>{{ $t('launch.review.your_review') }}</h4>
                <p class="muted small">{{ $t('launch.review.your_review_hint') }}</p>

                <div class="rating" role="radiogroup" :aria-label="$t('launch.review.quality')">
                  <button
                    v-for="n in 5"
                    :key="n"
                    type="button"
                    role="radio"
                    :aria-checked="form.rating === n"
                    :class="{ on: n <= (hoverRating || form.rating) }"
                    @mouseenter="hoverRating = n"
                    @mouseleave="hoverRating = 0"
                    @click="form.rating = n"
                  >★</button>
                  <span class="rating-label">{{ ratingLabel(hoverRating || form.rating) }}</span>
                </div>

                <p class="group-label">{{ $t('launch.review.good_points') }}</p>
                <div class="tag-pick">
                  <button v-for="tag in GOOD_TAGS" :key="tag" type="button" class="tag is-good" :class="{ on: form.tags.includes(tag) }" @click="toggleTag(tag)">{{ tagLabel(tag) }}</button>
                </div>
                <p class="group-label">{{ $t('launch.review.issues') }}</p>
                <div class="tag-pick">
                  <button v-for="tag in ISSUE_TAGS" :key="tag" type="button" class="tag is-issue" :class="{ on: form.tags.includes(tag) }" @click="toggleTag(tag)">{{ tagLabel(tag) }}</button>
                </div>

                <textarea
                  v-model="form.feedback"
                  rows="5"
                  class="feedback"
                  :placeholder="$t('launch.review.feedback_placeholder')"
                ></textarea>

                <label class="check">
                  <input v-model="autoRun" type="checkbox" />
                  <span>{{ $t('launch.review.auto_run') }}</span>
                </label>

                <details v-if="canRework" class="prompt-preview">
                  <summary>{{ $t('launch.review.preview_prompt') }}</summary>
                  <pre>{{ reworkPrompt }}</pre>
                </details>

                <div class="actions">
                  <button type="button" class="btn btn-approve" :disabled="saving || busy" @click="approve">
                    ✓ {{ $t('launch.review.approve') }}
                  </button>
                  <button
                    type="button"
                    class="btn btn-rework"
                    :disabled="saving || busy || !canRework"
                    :title="canRework ? '' : $t('launch.review.rework_needs')"
                    @click="rework"
                  >
                    ↻ {{ busy ? $t('launch.review.starting') : $t('launch.review.rework') }}
                  </button>
                </div>
                <p v-if="!canRework" class="muted small">{{ $t('launch.review.rework_needs') }}</p>
                <button v-if="existing" type="button" class="link" @click="editing = false">{{ $t('common.cancel') }}</button>
              </template>
            </aside>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import { fetchSessionDigest, saveSessionReview } from '@/api/client.js'
import { formatSpan } from '@/utils/runTracker.js'
import { toast } from '@/utils/toast.js'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  // session to show first (e.g. the run that just finished)
  focusId: { type: String, default: '' },
  // a rework run is being started by the Launch view
  busy: { type: Boolean, default: false },
  visible: { type: Boolean, default: true }
})
const emit = defineEmits(['open-session', 'rework', 'reviewed', 'pending-count'])

const { t, te, locale } = useI18n()

const GOOD_TAGS = ['on_target', 'quality', 'complete', 'fast']
const ISSUE_TAGS = ['off_target', 'missing', 'bugs', 'performance', 'ui', 'tests', 'docs']
const FINISHED = ['completed', 'error', 'cancelled']
const ORIGINAL_START = '### ORIGINAL TASK'
const ORIGINAL_END = '### END ORIGINAL TASK'
const SUMMARY_IN_PROMPT = 1500

const md = new MarkdownIt({ html: false, linkify: true, typographer: true })
// Wide tables in a report scroll sideways instead of squeezing a column per letter
md.renderer.rules.table_open = () => '<div class="md-table"><table>\n'
md.renderer.rules.table_close = () => '</table></div>\n'
const renderCache = new Map()
const render = (text) => {
  if (!renderCache.has(text)) {
    if (renderCache.size > 200) renderCache.clear()
    renderCache.set(text, md.render(text || ''))
  }
  return renderCache.get(text)
}

// ---------------------------------------------------------------- queue
const activeTab = ref('pending')
const query = ref('')
const selectedId = ref('')

const verdictOf = (item) => item?.review?.verdict || 'pending'
// Only a run that did work needs a review: something was handed to another agent or files
// changed. A plain question answered by the lead alone does not wait in "pending".
// session id -> { at: updated_at, work: boolean }, read from each run's digest
const workCache = reactive(new Map())
const didWork = (data) => Boolean(data && ((data.files?.length || 0) > 0 || (data.steps?.length || 0) > 1))
const workOf = (item) => {
  // The sessions list says it directly (has_work); the digest scan is only for older backends
  if (typeof item.has_work === 'boolean') return item.has_work
  const known = workCache.get(item.session_id)
  return known && known.at === item.updated_at ? known.work : null // null: not known yet
}
// A plan waiting for your approval is not a finished result: it has its own section.
// A stopped or failed run no longer waits on its plan (older saved sessions still say so).
const waitsOnPlan = (item) => Boolean(item.awaiting_plan) && !['cancelled', 'error'].includes(item.status)
const isPending = (item) =>
  item.status === 'completed' && verdictOf(item) === 'pending' && !waitsOnPlan(item) && workOf(item) !== false
const awaitingPlans = computed(() => props.sessions.filter(waitsOnPlan))

const byId = computed(() => new Map(props.sessions.map((item) => [item.session_id, item])))
// A rework run points back to the run it redoes (review.rework_session_id on the parent)
const parentOf = computed(() => {
  const map = new Map()
  for (const item of props.sessions) {
    const child = item.review?.rework_session_id
    if (child) map.set(child, item.session_id)
  }
  return map
})
const roundOf = (id, depth = 0) => {
  const parent = parentOf.value.get(id)
  return parent && depth < 20 ? roundOf(parent, depth + 1) + 1 : 1
}

const tabs = computed(() => {
  const finished = props.sessions.filter((s) => FINISHED.includes(s.status))
  return [
    { key: 'pending', tone: 'waiting', label: t('launch.review.tab_pending'), count: finished.filter(isPending).length },
    { key: 'rework', tone: 'rework', label: t('launch.review.tab_rework'), count: finished.filter((s) => verdictOf(s) === 'rework').length },
    { key: 'approved', tone: 'completed', label: t('launch.review.tab_approved'), count: finished.filter((s) => verdictOf(s) === 'approved').length },
    { key: 'all', tone: 'idle', label: t('launch.review.tab_all'), count: finished.length }
  ]
})

const queue = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.sessions
    .filter((s) => FINISHED.includes(s.status))
    .filter((s) => {
      if (activeTab.value === 'pending') return isPending(s)
      if (activeTab.value === 'rework') return verdictOf(s) === 'rework'
      if (activeTab.value === 'approved') return verdictOf(s) === 'approved'
      return true
    })
    .filter((s) => !q || `${s.title} ${s.yaml_file} ${s.projects?.[0]?.name || ''}`.toLowerCase().includes(q))
})

// Learn which unreviewed runs did work, newest first, one digest at a time (only while the
// view is open, and only for the latest runs: older ones stay in the queue until opened)
const WORK_SCAN_LIMIT = 30
let scanning = false
const scanWork = async () => {
  if (scanning || !props.visible) return
  scanning = true
  try {
    const candidates = props.sessions
      .filter((s) => s.status === 'completed' && verdictOf(s) === 'pending' && typeof s.has_work !== 'boolean')
      .slice(0, WORK_SCAN_LIMIT)
    for (const item of candidates) {
      if (!props.visible) break
      if (workOf(item) !== null) continue
      try {
        const data = await fetchSessionDigest(item.session_id)
        workCache.set(item.session_id, { at: item.updated_at, work: didWork(data?.digest) })
      } catch {
        // unknown stays in the queue
        workCache.set(item.session_id, { at: item.updated_at, work: true })
      }
    }
  } finally {
    scanning = false
  }
}
watch(() => [props.visible, props.sessions], () => { scanWork() }, { immediate: true })
// The Launch view's badge shows the same count as the "pending" tab
watch(() => tabs.value[0].count, (count) => emit('pending-count', count), { immediate: true })

const emptyText = computed(() =>
  activeTab.value === 'pending' ? t('launch.review.empty_pending') : t('launch.review.empty')
)

const selected = computed(() => byId.value.get(selectedId.value) || null)
const parent = computed(() => byId.value.get(parentOf.value.get(selectedId.value)) || null)
const reworkChild = computed(() => byId.value.get(selected.value?.review?.rework_session_id) || null)

// Once you pick something yourself, the focused run no longer takes over the selection
// (until another session is opened)
const touched = ref(false)
// Too narrow for the list and the detail side by side: one at a time (the CSS decides when)
const showDetail = ref(false)
const select = (id) => {
  touched.value = true
  selectedId.value = id
  showDetail.value = true
}
watch(() => props.focusId, () => { touched.value = false })

// Open on the run you were looking at, else the first one waiting for review
watch(
  () => [props.visible, props.focusId, queue.value.length],
  () => {
    if (!props.visible) return
    const focus = byId.value.get(props.focusId)
    if (focus && FINISHED.includes(focus.status) && selectedId.value !== focus.session_id && !touched.value) {
      selectedId.value = focus.session_id
      showDetail.value = true
      if (isPending(focus)) activeTab.value = 'pending'
      return
    }
    if (!selected.value && queue.value.length) selectedId.value = queue.value[0].session_id
  },
  { immediate: true }
)

// ---------------------------------------------------------------- detail
const digest = ref(null)
// The delivered result. The backend's own wrap-up ("Workflow finished with N node outputs
// ...") tells a reviewer nothing: then it is the entry agent's (the lead's) last hand-over.
const TECHNICAL_SUMMARY = /^Workflow (finished|completed) with \d+/i
const resultSummary = computed(() => {
  const summary = (digest.value?.summary || '').trim()
  if (summary && !TECHNICAL_SUMMARY.test(summary)) return summary
  return digest.value?.steps?.find((step) => step.output)?.output || summary
})
const loading = ref(false)
const loadError = ref('')
let loadSeq = 0

const load = async (id) => {
  digest.value = null
  loadError.value = ''
  if (!id) return
  const seq = ++loadSeq
  loading.value = true
  try {
    const data = await fetchSessionDigest(id)
    const item = byId.value.get(id)
    if (item) workCache.set(id, { at: item.updated_at, work: didWork(data.digest) })
    if (seq === loadSeq) digest.value = data.digest
  } catch (error) {
    if (seq === loadSeq) loadError.value = error?.message || String(error)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}
const existing = computed(() => {
  const review = selected.value?.review
  return review && review.verdict !== 'pending' ? review : null
})
const editing = ref(false)

const detailMeta = computed(() => {
  const item = selected.value
  if (!item) return []
  const parts = []
  const project = item.projects?.[0]?.name?.replace(/\/$/, '')
  if (project) parts.push({ text: `📁 ${project}` })
  parts.push({ text: item.yaml_file.replace(/\.ya?ml$/i, '') })
  // The time the team worked (its runs added up), like the dashboard's run time card, not
  // first-to-last message; older backends only give that span
  const data = digest.value
  const span = data?.started_at && data?.ended_at ? data.ended_at - data.started_at : 0
  const work = data?.active_ms > 0 ? data.active_ms : span
  if (work) parts.push({ text: t('launch.review.run_time', { time: formatSpan(work) }), title: t('launch.review.run_time_hint') })
  const tokens = data?.token_usage?.total_tokens
  if (Number.isFinite(tokens)) parts.push({ text: t('launch.board.tokens', { n: tokens.toLocaleString() }) })
  parts.push({ text: formatDate(item.updated_at) })
  return parts
})

const outcomeLabel = computed(() => {
  const key = `launch.board.states.${digest.value?.outcome || 'idle'}`
  return te(key) ? t(key) : digest.value?.outcome
})

const stepTime = (step) =>
  step.started_at && step.ended_at ? formatSpan(step.ended_at - step.started_at) : ''

// ---------------------------------------------------------------- verdict form
const form = reactive({ rating: 0, tags: [], feedback: '' })
const hoverRating = ref(0)
const autoRun = ref(true)
const saving = ref(false)

const resetForm = () => {
  const review = selected.value?.review
  form.rating = review?.rating || 0
  form.tags = [...(review?.tags || [])]
  form.feedback = review?.feedback || ''
  editing.value = false
  hoverRating.value = 0
}
const startEditing = () => {
  resetForm()
  editing.value = true
}

watch(
  selectedId,
  (id) => {
    load(id)
    resetForm()
  },
  { immediate: true }
)

const toggleTag = (tag) => {
  const index = form.tags.indexOf(tag)
  if (index === -1) form.tags.push(tag)
  else form.tags.splice(index, 1)
}

const isIssue = (tag) => ISSUE_TAGS.includes(tag)
const issueTags = computed(() => form.tags.filter(isIssue))
const canRework = computed(() => !!form.feedback.trim() || issueTags.value.length > 0)

const tagLabel = (tag) => {
  const key = `launch.review.tags.${tag}`
  return te(key) ? t(key) : tag
}
const ratingLabel = (n) => (n ? t(`launch.review.ratings.${n}`) : t('launch.review.rate_hint'))
const changeLabel = (change) => {
  const key = `launch.review.change_${change}`
  return te(key) ? t(key) : change
}

// The first task of a chain, without the wrapping a previous rework added
const originalTask = (text) => {
  const value = text || ''
  const start = value.indexOf(ORIGINAL_START)
  const end = value.indexOf(ORIGINAL_END)
  if (start !== -1 && end > start) return value.slice(start + ORIGINAL_START.length, end).trim()
  return value.trim()
}

const reworkPrompt = computed(() => {
  if (!selected.value || !digest.value) return ''
  const round = roundOf(selected.value.session_id) + 1
  const summary = (resultSummary.value || '').trim()
  const lines = [
    t('launch.review.prompt.header', { n: round }),
    '',
    ORIGINAL_START,
    originalTask(digest.value.task?.text),
    ORIGINAL_END,
    '',
    t('launch.review.prompt.not_accepted')
  ]
  if (issueTags.value.length) lines.push(t('launch.review.prompt.issues', { list: issueTags.value.map(tagLabel).join(', ') }))
  if (form.feedback.trim()) lines.push(t('launch.review.prompt.feedback'), form.feedback.trim())
  if (summary) {
    lines.push('', t('launch.review.prompt.previous'))
    lines.push(summary.length > SUMMARY_IN_PROMPT ? `${summary.slice(0, SUMMARY_IN_PROMPT)}…` : summary)
  }
  lines.push('', t('launch.review.prompt.instruction'))
  return lines.join('\n')
})

const payload = (verdict) => ({ verdict, rating: form.rating, tags: [...form.tags], feedback: form.feedback.trim() })

const approve = async () => {
  if (!selected.value) return
  saving.value = true
  try {
    await saveSessionReview(selected.value.session_id, payload('approved'))
    toast.success(t('launch.review.approved_toast'))
    editing.value = false
    emit('reviewed')
  } catch (error) {
    toast.error(t('launch.review.save_failed'), { detail: error?.message })
  } finally {
    saving.value = false
  }
}

const rework = async () => {
  if (!selected.value || !canRework.value) return
  if (autoRun.value) {
    // The Launch view starts the new run in the same project, then records the link
    emit('rework', {
      session: selected.value,
      prompt: reworkPrompt.value,
      review: payload('rework'),
      round: roundOf(selected.value.session_id) + 1
    })
    editing.value = false
    return
  }
  saving.value = true
  try {
    await saveSessionReview(selected.value.session_id, payload('rework'))
    toast.success(t('launch.review.rework_saved'))
    editing.value = false
    emit('reviewed')
  } catch (error) {
    toast.error(t('launch.review.save_failed'), { detail: error?.message })
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- labels
const verdictTone = (item) => {
  if (item.status === 'error') return 'error'
  if (item.status === 'cancelled') return 'cancelled'
  const verdict = verdictOf(item)
  if (verdict === 'pending' && workOf(item) === false) return 'completed'
  return verdict === 'approved' ? 'completed' : verdict === 'rework' ? 'rework' : 'waiting'
}
const verdictLabel = (item) => {
  const tone = verdictTone(item)
  if (tone === 'error' || tone === 'cancelled') return t(`launch.board.states.${tone}`)
  // A Q&A-only run never waits for review: say so instead of "Chờ duyệt"
  if (verdictOf(item) === 'pending' && workOf(item) === false) return t('launch.dashboard.chat_only')
  return t(`launch.review.verdict_${verdictOf(item)}`)
}
const sessionStatusLabel = (status) => {
  const map = { running: 'working', waiting_for_input: 'waiting', idle: 'draft' }
  const key = `launch.board.states.${map[status] || status}`
  return te(key) ? t(key) : status
}

const metaOf = (item) => {
  const project = item.projects?.[0]?.name?.replace(/\/$/, '')
  return [project, (item.yaml_file || '').replace(/\.ya?ml$/i, '')].filter(Boolean).join(' · ')
}

const dateFormat = computed(() => new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }))
const formatDate = (seconds) => (seconds ? dateFormat.value.format(new Date(seconds * 1000)) : '')
const ago = (seconds) => {
  if (!seconds) return ''
  const diff = Math.round(seconds - Date.now() / 1000)
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  const abs = Math.abs(diff)
  if (abs < 60) return rtf.format(diff, 'second')
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  return rtf.format(Math.round(diff / 86400), 'day')
}
</script>

<style scoped>
.review {
  --ok: #22c55e;
  --wait: #f59e0b;
  --rework: #f97316;
  --err: var(--danger);
  --muted: var(--text-muted-4);
  --line: rgb(var(--ink) / 0.09);
  height: 100%;
  box-sizing: border-box;
  /* Bottom room for the floating view switcher, so it never covers the last lines */
  padding: 14px 16px 64px calc(var(--inset-left, 0px) + 34px);
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
  transition: padding-left 0.25s ease;
  /* Sized by the room left next to the chat panel, not by the window */
  container-type: inline-size;
}

.review-body {
  height: 100%;
  display: grid;
  grid-template-columns: minmax(260px, 330px) minmax(0, 1fr);
  gap: 14px;
}

/* Only beside a narrow space: the list, then the picked work with a way back */
.back { display: none; text-align: left; }

.card,
.queue,
.detail {
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--surface-1);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.05), 0 8px 24px -18px rgb(0 0 0 / 0.35);
}

.muted { color: var(--muted); }
.small { font-size: 12px; margin: 0; }

/* ---------- pills & tones ---------- */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 11.5px;
  font-weight: 650;
  white-space: nowrap;
  color: var(--tone, var(--muted));
  background: color-mix(in srgb, var(--tone, var(--muted)) 14%, transparent);
}

.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.is-waiting { --tone: var(--wait); }
.is-rework { --tone: var(--rework); }
.is-completed,
.is-approved { --tone: var(--ok); }
.is-error { --tone: var(--err); }
.is-cancelled,
.is-idle { --tone: var(--muted); }

.round {
  padding: 1px 7px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--rework);
  background: color-mix(in srgb, var(--rework) 13%, transparent);
  white-space: nowrap;
}

/* ---------- queue ---------- */
.queue {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.queue-head { padding: 16px 16px 10px; }

.eyebrow {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.queue-head h2 { margin: 2px 0 4px; font-size: 18px; font-weight: 700; letter-spacing: -0.015em; }
.queue-head p { margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--muted); }

.tabs {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  padding: 0 12px 10px;
}

.tab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
}

.tab-count {
  min-width: 20px;
  padding: 0 6px;
  border-radius: 99px;
  font-size: 11px;
  text-align: center;
  color: var(--tone, var(--muted));
  background: color-mix(in srgb, var(--tone, var(--muted)) 14%, transparent);
  font-variant-numeric: tabular-nums;
}

.tab.active {
  color: var(--text-1);
  border-color: color-mix(in srgb, var(--tone, var(--accent-sky)) 55%, transparent);
  background: color-mix(in srgb, var(--tone, var(--accent-sky)) 9%, transparent);
}

.plans {
  --tone: var(--wait);
  margin: 0 12px 10px;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--wait) 40%, transparent);
  background: color-mix(in srgb, var(--wait) 7%, transparent);
}

.plans-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 2px 6px;
  font-size: 12.5px;
  font-weight: 650;
}

.plans-list { margin: 0; padding: 0; list-style: none; max-height: 180px; overflow-y: auto; }

.plan-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 7px 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.plan-item:hover { background: color-mix(in srgb, var(--wait) 12%, transparent); }

.plan-open { flex: none; font-size: 11.5px; font-weight: 600; color: var(--wait); }

.search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 12px 8px;
  padding: 0 10px;
  height: 34px;
  border-radius: 9px;
  border: 1px solid var(--line);
  color: var(--muted);
}

.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
}

.search:focus-within { border-color: var(--accent-sky); }

.queue-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 4px 8px 10px;
  list-style: none;
  overflow-y: auto;
  scrollbar-width: thin;
}

.queue-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  margin-bottom: 4px;
  padding: 10px 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.queue-item:hover { background: rgb(var(--ink) / 0.04); }

.queue-item.active {
  border-color: color-mix(in srgb, var(--accent-sky) 45%, transparent);
  background: color-mix(in srgb, var(--accent-sky) 9%, transparent);
}

.qi-top { display: flex; align-items: center; gap: 8px; min-width: 0; }

.verdict-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tone, var(--muted));
}

.verdict-dot.is-waiting { box-shadow: 0 0 0 3px color-mix(in srgb, var(--wait) 22%, transparent); }

.qi-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 620;
}

.qi-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding-left: 16px;
  font-size: 11.5px;
  color: var(--muted);
}

.qi-meta span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qi-meta time { flex: none; }

.stars-mini { padding-left: 16px; font-size: 11px; letter-spacing: 1px; color: rgb(var(--ink) / 0.18); }
.stars-mini .on { color: #f5b301; }

.queue-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.queue-empty span {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  font-size: 20px;
  color: var(--ok);
  background: color-mix(in srgb, var(--ok) 12%, transparent);
}

/* ---------- detail ---------- */
.detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
}

.detail-empty {
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 14px;
}

.detail-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px 16px;
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--surface-1) 92%, transparent);
  backdrop-filter: blur(8px);
}

/* The title block takes the row; the button drops below it rather than over the badge */
.dh-main { flex: 1 1 240px; min-width: 0; }
.dh-main h3 { overflow-wrap: anywhere; }
.dh-meta span { white-space: nowrap; }
.dh-tags { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.dh-main h3 { margin: 0 0 6px; font-size: 18px; font-weight: 700; letter-spacing: -0.015em; }

.dh-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.loading,
.load-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 20px;
  font-size: 13px;
  color: var(--muted);
}

.load-error { color: var(--err); margin: 8px 0 0; }

.spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, currentColor 25%, transparent);
  border-top-color: currentColor;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  align-items: start;
  gap: 16px;
  padding: 16px 20px 20px;
}

.content { display: flex; flex-direction: column; gap: 14px; min-width: 0; }

.panel {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgb(var(--ink) / 0.015);
}

.panel h4 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 680;
  letter-spacing: 0.01em;
}

.panel.is-result { border-color: color-mix(in srgb, var(--ok) 30%, var(--line)); }

.pre {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.chip { padding: 2px 8px; border-radius: 6px; font-size: 11.5px; background: rgb(var(--ink) / 0.06); }

.replies { margin-top: 10px; font-size: 12.5px; color: var(--muted); }
.replies summary { cursor: pointer; }
.replies ol { margin: 8px 0 0; padding-left: 20px; color: var(--text-1); }
.replies li { margin-bottom: 4px; white-space: pre-wrap; }

.lineage {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--rework) 40%, transparent);
  background: color-mix(in srgb, var(--rework) 7%, transparent);
  font-size: 12.5px;
}

.lineage strong { color: var(--rework); }
.lineage-tags { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0 0; }
.lineage-text { margin: 8px 0 0; line-height: 1.5; font-style: italic; }

.md { font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.md :deep(h1),
.md :deep(h2),
.md :deep(h3) { margin: 12px 0 6px; font-size: 14px; }
.md :deep(p) { margin: 0 0 8px; }
.md :deep(ul),
.md :deep(ol) { margin: 0 0 8px; padding-left: 20px; }
.md :deep(code) { font-size: 12px; padding: 1px 5px; border-radius: 5px; background: rgb(var(--ink) / 0.07); }
.md :deep(pre) { overflow-x: auto; padding: 10px 12px; border-radius: 9px; background: rgb(var(--ink) / 0.06); }
.md :deep(pre code) { padding: 0; background: none; }
.md :deep(.md-table) { max-width: 100%; overflow-x: auto; margin: 0 0 8px; }
.md :deep(table) { border-collapse: collapse; font-size: 12px; }
.md :deep(th) { white-space: nowrap; }
.md :deep(td) { min-width: 64px; max-width: 320px; vertical-align: top; }
.md :deep(th),
.md :deep(td) { padding: 4px 8px; border: 1px solid var(--line); }

.files { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: 12.5px; }
.files li { display: flex; align-items: center; gap: 10px; min-width: 0; }
.files code { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }

.change {
  flex: none;
  width: 44px;
  padding: 1px 0;
  border-radius: 5px;
  font-size: 10.5px;
  font-weight: 700;
  text-align: center;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, transparent);
}

.change.is-created { --tone: var(--ok); }
.change.is-updated { --tone: var(--accent-sky); }
.change.is-deleted { --tone: var(--err); }

.handovers { display: flex; flex-direction: column; gap: 6px; }

.handover {
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-1);
}

.handover summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  font-size: 13px;
  cursor: pointer;
  list-style: none;
}

.handover summary::-webkit-details-marker { display: none; }
.handover[open] summary { border-bottom: 1px solid var(--line); }
.handover .md,
.handover > p { padding: 10px 14px; margin: 0; }

.ho-index {
  display: grid;
  place-items: center;
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-sky);
  background: color-mix(in srgb, var(--accent-sky) 13%, transparent);
}

.ho-name { flex: 1; min-width: 0; font-weight: 620; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---------- verdict ---------- */
.verdict {
  position: sticky;
  top: 92px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

.verdict h4 { margin: 0; font-size: 14px; font-weight: 700; }

.rating { display: flex; align-items: center; gap: 2px; }

.rating button {
  padding: 0 2px;
  border: 0;
  background: transparent;
  font-size: 26px;
  line-height: 1;
  color: rgb(var(--ink) / 0.15);
  cursor: pointer;
  transition: transform 0.12s, color 0.12s;
}

.rating button.on { color: #f5b301; }
.rating button:hover { transform: scale(1.12); }
.rating-label { margin-left: 8px; font-size: 12.5px; font-weight: 600; color: var(--muted); }

.group-label {
  margin: 4px 0 0;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--muted);
}

.tag-pick,
.tags-line { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }

.tag {
  padding: 4px 10px;
  border-radius: 99px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
}

span.tag { cursor: default; }
.tag.is-good { --tone: var(--ok); }
.tag.is-issue { --tone: var(--rework); }
.tag.on,
span.tag {
  color: var(--tone);
  border-color: color-mix(in srgb, var(--tone) 55%, transparent);
  background: color-mix(in srgb, var(--tone) 12%, transparent);
}

.tag:not(.on):hover { border-color: color-mix(in srgb, var(--tone) 45%, transparent); }

.feedback {
  box-sizing: border-box;
  width: 100%;
  resize: vertical;
  min-height: 96px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: rgb(var(--ink) / 0.02);
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
}

.feedback:focus { outline: none; border-color: var(--accent-sky); }

.check { display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; cursor: pointer; }
.check input { margin: 2px 0 0; accent-color: var(--rework); }

.prompt-preview { font-size: 12px; color: var(--muted); }
.prompt-preview summary { cursor: pointer; }

.prompt-preview pre {
  max-height: 220px;
  margin: 8px 0 0;
  padding: 10px;
  overflow: auto;
  border-radius: 8px;
  background: rgb(var(--ink) / 0.05);
  color: var(--text-1);
  font-size: 11.5px;
  white-space: pre-wrap;
}

.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 2px; }

.btn {
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  transition: filter 0.15s, border-color 0.15s, opacity 0.15s;
}

.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-ghost { flex: none; }
.btn-ghost:hover { border-color: var(--accent-sky); }
.btn-approve { border-color: transparent; color: #fff; background: var(--ok); }
.btn-rework { border-color: transparent; color: #fff; background: var(--rework); }
.btn-approve:hover:not(:disabled),
.btn-rework:hover:not(:disabled) { filter: brightness(1.08); }
.btn-soft { color: var(--rework); border-color: color-mix(in srgb, var(--rework) 45%, transparent); background: color-mix(in srgb, var(--rework) 8%, transparent); }

.link {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  color: var(--accent-sky);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.link:hover { text-decoration: underline; }

.verdict-done {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 11px;
  background: color-mix(in srgb, var(--tone) 10%, transparent);
}

.verdict-done.is-approved { --tone: var(--ok); }
.verdict-done.is-rework { --tone: var(--rework); }
.verdict-done div { display: flex; flex-direction: column; font-size: 12px; color: var(--muted); }
.verdict-done strong { font-size: 14px; color: var(--tone); }

.vd-icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  background: var(--tone);
}

.stars-line { display: flex; align-items: center; gap: 2px; margin: 0; font-size: 18px; color: rgb(var(--ink) / 0.15); }
.stars-line .on { color: #f5b301; }
.stars-line .muted { margin-left: 8px; font-size: 12.5px; }
.feedback-quote { margin: 0; padding: 10px 12px; border-left: 3px solid var(--line); font-size: 13px; line-height: 1.5; font-style: italic; }

@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
}

@media (max-width: 1280px) {
  .detail-grid { grid-template-columns: 1fr; }
  .verdict { position: static; }
}

/* Two columns of detail only when the space beside the chat really has room for them */
@container (max-width: 1060px) {
  .detail-grid { grid-template-columns: 1fr; }
  .verdict { position: static; }
}

/* No room for the list and a readable detail side by side: show one, then the other */
@container (max-width: 760px) {
  .review-body { grid-template-columns: minmax(0, 1fr); }
  .review-body.show-detail .queue,
  .review-body:not(.show-detail) .detail { display: none; }
  .back { display: inline; flex-basis: 100%; }
}

@media (max-width: 760px) {
  .review { padding: 10px; }
}
</style>
