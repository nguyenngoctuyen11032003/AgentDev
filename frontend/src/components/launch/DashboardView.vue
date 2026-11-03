<template>
  <div class="dash">
    <!-- Hero: what is running and how far it is -->
    <section class="hero card">
      <div class="ring" :style="{ '--p': progress }" role="img" :aria-label="$t('launch.dashboard.progress_aria', { p: progress })">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle class="ring-track" cx="60" cy="60" r="52" />
          <circle class="ring-fill" cx="60" cy="60" r="52" :style="{ strokeDashoffset: ringOffset }" />
        </svg>
        <div class="ring-text">
          <strong>{{ noTasks ? '—' : `${progress}%` }}</strong>
          <span v-if="noTasks">{{ $t('launch.dashboard.chat_only') }}</span>
          <span v-else-if="teamMode">{{ $t('launch.dashboard.tasks_of', { done: teamTasksDone, total: delegatedRuns.length }) }}</span>
          <span v-else>{{ $t('launch.dashboard.done_of', { done: doneCount, total: steps.length }) }}</span>
        </div>
      </div>
      <div class="hero-main">
        <span class="eyebrow">{{ $t('launch.dashboard.title') }}</span>
        <h2>{{ workflowName || $t('launch.board.no_workflow') }}</h2>
        <p class="hero-task" :title="tracker.task?.text || ''">
          {{ tracker.task?.text || $t('launch.dashboard.no_task') }}
        </p>
        <div class="hero-tags">
          <span class="pill" :class="`is-${runTone}`"><span class="dot" aria-hidden="true"></span>{{ stateLabel(runTone) }}</span>
          <span v-if="currentStep" class="pill is-neutral">
            {{ $t('launch.dashboard.now_at', { n: currentStep.index, name: currentStep.id }) }}
          </span>
          <span v-if="multiTurn && currentTurn" class="pill is-turn">{{ $t('launch.dashboard.turn_of', { n: currentTurn.number, total: turns.length }) }}</span>
          <span v-if="tracker.startedAt" class="pill is-neutral">{{ $t('launch.dashboard.started', { time: clock(tracker.startedAt) }) }}</span>
        </div>
      </div>
    </section>

    <!-- KPIs -->
    <section class="kpis">
      <article v-for="kpi in kpis" :key="kpi.key" class="kpi card">
        <span class="kpi-label">{{ kpi.label }}</span>
        <strong class="kpi-value">{{ kpi.value }}</strong>
        <span class="kpi-sub">{{ kpi.sub }}</span>
      </article>
    </section>

    <!-- Turns of this session, newest first; the current one is marked -->
    <section v-if="multiTurn" class="card block">
      <header class="block-head">
        <h3>{{ $t('launch.dashboard.turns') }}</h3>
        <span class="muted">{{ $t('launch.dashboard.turns_sub', { n: turns.length }) }}</span>
      </header>
      <div class="table-wrap">
        <table class="agents turns">
          <thead>
            <tr>
              <th>#</th>
              <th>{{ $t('launch.dashboard.col_request') }}</th>
              <th>{{ $t('launch.dashboard.col_status') }}</th>
              <th class="num">{{ $t('launch.dashboard.col_tasks') }}</th>
              <th class="num">{{ $t('launch.dashboard.col_tokens') }}</th>
              <th>{{ $t('launch.dashboard.col_time') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in turnRows" :key="row.turn.number" :class="{ 'is-current': row.turn.current }">
              <td class="idx">{{ row.turn.number }}</td>
              <td class="turn-ask">
                <span :title="row.turn.task?.text || ''">{{ row.turn.task?.text || '—' }}</span>
                <small v-if="row.turn.current" class="turn-now">{{ $t('launch.dashboard.turn_now') }}</small>
              </td>
              <td><span class="pill" :class="`is-${row.tone}`"><span class="dot" aria-hidden="true"></span>{{ stateLabel(row.tone) }}</span></td>
              <td class="num">{{ row.tasks ? `${row.tasksDone}/${row.tasks}` : '—' }}</td>
              <td class="num" :title="row.cost !== null ? formatCost(row.cost) : ''">{{ row.tokens ? row.tokens.toLocaleString() : '—' }}</td>
              <td>{{ row.turn.startedAt ? formatSpan(row.span) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Pipeline -->
    <section class="card block">
      <header class="block-head">
        <h3>{{ $t('launch.dashboard.pipeline') }}</h3>
        <span class="muted">{{ teamMode && idleCount ? $t('launch.dashboard.pipeline_team_sub', { n: idleCount }) : $t('launch.dashboard.pipeline_sub') }}</span>
      </header>
      <ol v-if="steps.length" class="pipeline">
        <li v-for="step in shownSteps" :key="step.id" class="pipe-step" :class="`is-${statusOf(step.id)}`" :style="{ '--dept': step.color }">
          <span class="pipe-node" :title="stateLabel(statusOf(step.id))">
            <svg v-if="statusOf(step.id) === 'done'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>
            <template v-else>{{ step.index }}</template>
          </span>
          <span class="pipe-name" :title="step.id">{{ step.id }}</span>
          <span class="pipe-sub">{{ statusOf(step.id) === 'todo' ? deptLabel(step.dept) : formatSpan(durationOf(step.id)) }}</span>
        </li>
      </ol>
      <p v-else class="empty">{{ $t('launch.board.empty') }}</p>
    </section>

    <div class="grid-2">
      <!-- Timeline -->
      <section class="card block">
        <header class="block-head">
          <h3>{{ $t('launch.dashboard.timeline') }}</h3>
          <!-- Across several messages the axis also spans the waits between them: say so, so it
               is not read as the run time card's figure -->
          <span
            v-if="session.startedAt && multiTurn"
            class="muted"
            :title="$t('launch.dashboard.timeline_wall_hint')"
          >{{ $t('launch.dashboard.timeline_wall', { time: formatSpan(span) }) }}</span>
          <span v-else class="muted">{{ session.startedAt ? formatSpan(span) : '' }}</span>
        </header>
        <div v-if="session.startedAt && steps.length" class="gantt">
          <div v-for="step in shownSteps" :key="step.id" class="gantt-row" :style="{ '--dept': step.color }">
            <span class="gantt-label" :title="step.id"><b>{{ step.index }}</b>{{ step.id }}</span>
            <span class="gantt-track">
              <span
                v-for="run in runsOf(step.id)"
                :key="`${run.turn}-${run.index}`"
                class="gantt-bar"
                :class="{ 'is-live': !run.endedAt, 'is-past': multiTurn && run.turn !== currentTurn?.number }"
                :style="barStyle(run)"
                :title="`${step.id} · ${multiTurn ? `${$t('launch.board.turn', { n: run.turn })} · ` : ''}${$t('launch.board.run', { n: run.index })} · ${formatSpan((run.endedAt || now) - run.startedAt)}`"
              ></span>
            </span>
          </div>
          <div class="gantt-axis"><span>0s</span><span>{{ formatSpan(span / 2) }}</span><span>{{ formatSpan(span) }}</span></div>
        </div>
        <p v-else class="empty">{{ $t('launch.dashboard.no_run') }}</p>
      </section>

      <!-- Activity feed -->
      <section class="card block">
        <header class="block-head">
          <h3>{{ $t('launch.dashboard.activity') }}</h3>
          <span class="muted">{{ $t('launch.dashboard.events', { n: session.events.length }) }}</span>
        </header>
        <ol v-if="feed.length" class="feed">
          <li v-for="event in feed" :key="event.id" class="feed-item" :class="`is-${event.kind}`">
            <span class="feed-icon" aria-hidden="true">{{ eventIcon(event.kind) }}</span>
            <span class="feed-text">
              <span v-html="eventText(event)"></span>
              <small v-if="event.text && !['task', 'input'].includes(event.kind)">{{ event.text }}</small>
            </span>
            <time>{{ clock(event.at) }}</time>
          </li>
        </ol>
        <p v-else class="empty">{{ $t('launch.dashboard.no_activity') }}</p>
      </section>
    </div>

    <!-- Agents -->
    <section class="card block">
      <header class="block-head">
        <h3>{{ $t('launch.dashboard.agents') }}</h3>
        <span class="muted">{{ $t('launch.dashboard.agents_sub', { n: steps.length }) }}</span>
      </header>
      <div class="table-wrap">
        <table class="agents">
          <thead>
            <tr>
              <th>#</th>
              <th>{{ $t('launch.dashboard.col_agent') }}</th>
              <th>{{ $t('launch.dashboard.col_status') }}</th>
              <th v-if="hasOrg" class="num" :title="$t('launch.dashboard.col_chain_hint')">{{ $t('launch.dashboard.col_chain') }}</th>
              <th class="num">{{ $t('launch.dashboard.col_runs') }}</th>
              <th class="num">{{ $t('launch.dashboard.col_models') }}</th>
              <th class="num">{{ $t('launch.dashboard.col_tools') }}</th>
              <th v-if="usage.tokens" class="num">{{ $t('launch.dashboard.col_tokens') }}</th>
              <th>{{ $t('launch.dashboard.col_time') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in agentRows" :key="row.step.id" :style="{ '--dept': row.step.color }">
              <td class="idx">{{ row.step.index }}</td>
              <td>
                <span class="agent-cell" :style="{ paddingLeft: `${row.depth * 18}px` }">
                  <span v-if="row.depth" class="branch" aria-hidden="true">↳</span>
                  <span class="avatar" aria-hidden="true">
                    <img v-if="row.step.sprite" :src="row.step.sprite" alt="" />
                    <span v-else>{{ initialsOf(row.step.id) }}</span>
                  </span>
                  <span class="agent-name">
                    <strong :title="row.step.id">{{ row.step.id }}</strong>
                    <small>{{ deptLabel(row.step.dept) }}<template v-if="row.step.model"> · {{ row.step.model }}</template></small>
                    <small v-if="row.reportsTo || row.teamSize" class="chain-line">
                      <template v-if="row.reportsTo">{{ $t('launch.dashboard.reports_to', { name: row.reportsTo }) }}</template>
                      <template v-if="row.reportsTo && row.teamSize"> · </template>
                      <template v-if="row.teamSize">{{ $t('launch.dashboard.leads_team', { n: row.teamSize }) }}</template>
                    </small>
                  </span>
                </span>
              </td>
              <td><span class="pill" :class="`is-${row.status}`"><span class="dot" aria-hidden="true"></span>{{ stateLabel(row.status) }}</span></td>
              <td v-if="hasOrg" class="num">
                <template v-if="row.reportsTo">{{ row.assigned }} / {{ row.reported }}</template>
                <template v-else>—</template>
              </td>
              <td class="num">{{ row.runs }}</td>
              <td class="num">{{ row.models }}</td>
              <td class="num">{{ row.tools }}</td>
              <td v-if="usage.tokens" class="num" :title="usage.nodes[row.step.id]?.cost ? formatCost(usage.nodes[row.step.id].cost) : ''">{{ usage.nodes[row.step.id]?.tokens ? usage.nodes[row.step.id].tokens.toLocaleString() : '—' }}</td>
              <td>
                <span class="share">
                  <span class="share-track"><span class="share-fill" :style="{ width: `${row.share}%` }"></span></span>
                  <span class="share-text">{{ row.runs ? formatSpan(row.duration) : '—' }}</span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- All work -->
    <section class="card block">
      <header class="block-head">
        <h3>{{ $t('launch.dashboard.all_work') }}</h3>
        <span class="muted">{{ $t('launch.dashboard.sessions_count', { n: sessions.length }) }}</span>
      </header>
      <div class="work-stats">
        <button
          v-for="bucket in buckets"
          :key="bucket.key"
          type="button"
          class="work-stat"
          :class="[`is-${bucket.tone}`, { active: filter === bucket.key }]"
          @click="filter = filter === bucket.key ? '' : bucket.key"
        >
          <strong>{{ bucket.count }}</strong>
          <span>{{ bucket.label }}</span>
        </button>
      </div>
      <ul v-if="recentSessions.length" class="work-list">
        <li v-for="item in recentSessions" :key="item.session_id">
          <button type="button" class="work-item" :class="{ current: item.session_id === currentSessionId }" @click="$emit('open-session', item)">
            <span class="pill" :class="`is-${sessionTone(item.status)}`"><span class="dot" aria-hidden="true"></span>{{ sessionLabel(item.status) }}</span>
            <span class="work-title" :title="item.title">{{ item.title || item.yaml_file }}</span>
            <span class="work-meta">{{ workMeta(item) }}</span>
            <time>{{ ago(item.updated_at) }}</time>
          </button>
        </li>
      </ul>
      <p v-else class="empty">{{ $t('launch.dashboard.no_sessions') }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { combineTurns, formatCost, formatSpan, sessionTurns, stepDuration, stepStatus, turnSpan, usageTotals } from '@/utils/runTracker.js'
import { buildSteps, initialsOf } from '@/utils/workflowSteps.js'
import { buildOrgChart, computeTeamLinks } from '@/utils/teamLinks.js'

const props = defineProps({
  graph: { type: Object, default: () => ({}) },
  spriteMap: { type: Map, default: () => new Map() },
  tracker: { type: Object, required: true },
  status: { type: String, default: '' },
  workflowName: { type: String, default: '' },
  // every saved session (sidebar list) for the "all work" overview
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: String, default: '' },
  visible: { type: Boolean, default: true }
})
defineEmits(['open-session'])

const { t, te, locale } = useI18n()
const RING_LENGTH = 2 * Math.PI * 52
const FEED_LIMIT = 14
const WORK_LIMIT = 8

const now = ref(Date.now())
const filter = ref('')

const steps = computed(() => buildSteps(props.graph, props.spriteMap))

// The figures cover every turn of the session (a follow-up message is a new turn); the
// hero and the turn list point out the current one
const turns = computed(() => sessionTurns(props.tracker))
const multiTurn = computed(() => turns.value.length > 1)
const session = computed(() => combineTurns(turns.value))
const currentTurn = computed(() => turns.value[turns.value.length - 1] || null)
// Working time: the pauses between turns do not count
const workTime = computed(() => turns.value.reduce((sum, turn) => sum + turnSpan(turn, now.value), 0))
const turnRows = computed(() =>
  [...turns.value].reverse().map((turn) => {
    const runs = Object.values(turn.nodes || {}).flatMap((node) => node.runs)
    const delegated = runs.filter((run) => run.delegatedBy)
    const cost = usageTotals(turn.tokenUsage)
    return {
      turn,
      tone: turn.outcome || (isLive.value && turn.current ? 'working' : 'idle'),
      tasks: delegated.length,
      tasksDone: delegated.filter((run) => run.endedAt).length,
      tokens: cost.tokens,
      cost: cost.cost,
      span: turnSpan(turn, now.value)
    }
  })
)

const nodeOf = (id) => session.value.nodes[id]
const runsOf = (id) => nodeOf(id)?.runs || []
const statusOf = (id) => stepStatus(nodeOf(id))
const durationOf = (id) => stepDuration(nodeOf(id), now.value)

const doneCount = computed(() => steps.value.filter((s) => statusOf(s.id) === 'done').length)

// Team workflow: the lead decides who works, so progress is counted in delegated tasks and
// the step lists show the people who took part (not twelve empty rows)
const teamMode = computed(() => computeTeamLinks(props.graph?.nodes, props.graph?.edges).length > 0)
const delegatedRuns = computed(() =>
  Object.values(session.value.nodes).flatMap((node) => node.runs.filter((run) => run.delegatedBy))
)
const teamTasksDone = computed(() => delegatedRuns.value.filter((run) => run.endedAt).length)
const involved = computed(() => steps.value.filter((s) => runsOf(s.id).length || statusOf(s.id) === 'waiting'))
const shownSteps = computed(() => (teamMode.value && involved.value.length ? involved.value : steps.value))
const idleCount = computed(() => steps.value.length - shownSteps.value.length)

// A team turn where the lead only answered (nobody was handed a task): no progress to show
const noTasks = computed(() => teamMode.value && delegatedRuns.value.length === 0)

const progress = computed(() => {
  if (noTasks.value) return 0
  if (session.value.outcome === 'completed') return 100
  if (teamMode.value) {
    const total = delegatedRuns.value.length
    return total ? Math.round((teamTasksDone.value / total) * 100) : 0
  }
  return steps.value.length ? Math.round((doneCount.value / steps.value.length) * 100) : 0
})
const ringOffset = computed(() => RING_LENGTH * (1 - progress.value / 100))

const isLive = computed(() => props.status === 'Running...' || props.status === 'Waiting for input...')
const runTone = computed(() => {
  if (props.status === 'Waiting for input...') return 'waiting'
  if (isLive.value) return 'working'
  return session.value.outcome || 'idle'
})

const currentStep = computed(() => {
  const live = steps.value.filter((s) => ['working', 'waiting'].includes(statusOf(s.id)))
  return live[live.length - 1] || null
})

const span = computed(() => {
  if (!session.value.startedAt) return 0
  return Math.max(1000, (session.value.endedAt || now.value) - session.value.startedAt)
})

const allRuns = computed(() => Object.values(session.value.nodes).flatMap((node) => node.runs))
const totals = computed(() => ({
  models: allRuns.value.reduce((sum, run) => sum + run.models, 0),
  tools: allRuns.value.reduce((sum, run) => sum + run.tools.length, 0),
  runs: allRuns.value.length
}))

const usage = computed(() => usageTotals(session.value.tokenUsage))
const totalTokens = computed(() => usage.value.tokens)

const kpis = computed(() => {
  const working = steps.value.filter((s) => statusOf(s.id) === 'working')
  const waiting = steps.value.some((s) => statusOf(s.id) === 'waiting') || props.status === 'Waiting for input...'
  const progressKpi = teamMode.value
    ? {
        key: 'progress',
        label: t('launch.dashboard.kpi_tasks'),
        value: noTasks.value ? '—' : `${teamTasksDone.value}/${delegatedRuns.value.length}`,
        sub: noTasks.value ? t('launch.dashboard.chat_only') : t('launch.dashboard.kpi_people', { n: involved.value.length, total: steps.value.length })
      }
    : {
        key: 'progress',
        label: t('launch.dashboard.kpi_progress'),
        value: `${doneCount.value}/${steps.value.length}`,
        sub: t('launch.dashboard.kpi_progress_sub', { p: progress.value })
      }
  return [
    progressKpi,
    {
      key: 'time',
      label: t('launch.dashboard.kpi_time'),
      value: session.value.startedAt ? formatSpan(workTime.value) : '—',
      sub: multiTurn.value
        ? t('launch.dashboard.kpi_time_turns', { n: turns.value.length, time: formatSpan(turnSpan(currentTurn.value, now.value)) })
        : session.value.endedAt ? t('launch.dashboard.kpi_time_done') : isLive.value ? t('launch.dashboard.kpi_time_live') : '—'
    },
    {
      key: 'active',
      label: t('launch.dashboard.kpi_active'),
      value: waiting ? t('launch.dashboard.kpi_you') : String(working.length),
      sub: waiting
        ? t('launch.dashboard.kpi_waiting_sub')
        : working.map((s) => s.id).join(', ') || t('launch.dashboard.kpi_none')
    },
    {
      key: 'calls',
      label: t('launch.dashboard.kpi_calls'),
      value: String(totals.value.models),
      sub: t('launch.dashboard.kpi_runs', { n: totals.value.runs })
    },
    {
      key: 'tools',
      label: t('launch.dashboard.kpi_tools'),
      value: String(totals.value.tools),
      sub: topTool.value ? t('launch.dashboard.kpi_top_tool', { name: topTool.value }) : t('launch.dashboard.kpi_none')
    },
    {
      key: 'usage',
      label: t('launch.dashboard.kpi_usage'),
      value: totalTokens.value ? totalTokens.value.toLocaleString() : '—',
      sub: usage.value.cost !== null
        ? t('launch.dashboard.kpi_cost', { cost: formatCost(usage.value.cost) })
        : session.value.outcome ? t('launch.dashboard.kpi_no_cost') : t('launch.dashboard.kpi_usage_later')
    }
  ]
})

const topTool = computed(() => {
  const counts = new Map()
  for (const run of allRuns.value) for (const name of run.tools) counts.set(name, (counts.get(name) || 0) + 1)
  let best = ''
  let max = 0
  for (const [name, count] of counts) if (count > max) [best, max] = [name, count]
  return best
})

// Chain of command (team leads) and how often work moved along it during this run
const org = computed(() => buildOrgChart(props.graph))
const hasOrg = computed(() => org.value.size > 0)
const handoffStats = computed(() => {
  const stats = new Map()
  const bump = (id, key) => {
    if (!stats.has(id)) stats.set(id, { assigned: 0, reported: 0 })
    stats.get(id)[key] += 1
  }
  for (const event of session.value.events) {
    if (event.kind !== 'handoff') continue
    if (org.value.get(event.target)?.parent === event.nodeId) bump(event.target, 'assigned')
    else if (org.value.get(event.nodeId)?.parent === event.target) bump(event.nodeId, 'reported')
  }
  return stats
})

const agentRows = computed(() => {
  const rows = steps.value.map((step) => {
    const runs = runsOf(step.id)
    const unit = org.value.get(step.id)
    return {
      step,
      depth: unit?.depth || 0,
      reportsTo: unit?.parent || '',
      teamSize: unit?.members.length || 0,
      assigned: handoffStats.value.get(step.id)?.assigned || 0,
      reported: handoffStats.value.get(step.id)?.reported || 0,
      status: statusOf(step.id),
      runs: runs.length,
      models: runs.reduce((sum, run) => sum + run.models, 0),
      tools: runs.reduce((sum, run) => sum + run.tools.length, 0),
      duration: durationOf(step.id)
    }
  })
  const longest = Math.max(1, ...rows.map((row) => row.duration))
  return rows.map((row) => ({ ...row, share: Math.round((row.duration / longest) * 100) }))
})

const barStyle = (run) => {
  const start = session.value.startedAt || run.startedAt
  const left = ((run.startedAt - start) / span.value) * 100
  const width = (((run.endedAt || now.value) - run.startedAt) / span.value) * 100
  return { left: `${Math.max(0, Math.min(99.5, left))}%`, width: `${Math.max(0.6, Math.min(100 - left, width))}%` }
}

// ---------------------------------------------------------------- activity feed
const feed = computed(() => session.value.events.slice(-FEED_LIMIT).reverse())

const ICONS = { task: '✎', start: '▶', end: '✓', tool: '⚙', handoff: '→', waiting: '?', input: '↩', completed: '★', cancelled: '■', error: '!' }
const eventIcon = (kind) => ICONS[kind] || '•'

const escapeHtml = (text) =>
  String(text ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch])

const eventText = (event) => {
  const name = `<b>${escapeHtml(event.nodeId)}</b>`
  const target = `<b>${escapeHtml(event.target)}</b>`
  switch (event.kind) {
    case 'task': return t('launch.dashboard.ev_task', { text: escapeHtml(event.text) })
    case 'start': return t('launch.dashboard.ev_start', { name })
    case 'end': return t('launch.dashboard.ev_end', { name })
    case 'tool': return t('launch.dashboard.ev_tool', { name, tool: `<code>${escapeHtml(event.text)}</code>` })
    case 'handoff': return t('launch.dashboard.ev_handoff', { name, target })
    case 'waiting': return event.nodeId ? t('launch.dashboard.ev_waiting', { name }) : t('launch.dashboard.ev_waiting_any')
    case 'input': return t('launch.dashboard.ev_input', { text: escapeHtml(event.text) })
    case 'completed': return t('launch.dashboard.ev_completed')
    case 'cancelled': return t('launch.dashboard.ev_cancelled')
    case 'error': return t('launch.dashboard.ev_error')
    default: return escapeHtml(event.kind)
  }
}

// ---------------------------------------------------------------- all sessions
const SESSION_TONE = {
  running: 'working',
  // Stop was pressed and the run is winding down
  cancelling: 'working',
  waiting_for_input: 'waiting',
  completed: 'completed',
  error: 'error',
  cancelled: 'cancelled',
  idle: 'idle'
}
const BUCKET_STATUSES = {
  active: ['running', 'waiting_for_input', 'cancelling'],
  completed: ['completed'],
  stopped: ['error', 'cancelled'],
  draft: ['idle']
}
const sessionTone = (status) => SESSION_TONE[status] || 'idle'
const sessionLabel = (status) => {
  if (status === 'cancelling') return t('launch.sessions.status.cancelling')
  return stateLabel(sessionTone(status) === 'idle' ? 'draft' : sessionTone(status))
}

const buckets = computed(() => {
  const count = (statuses) => props.sessions.filter((s) => statuses.includes(s.status)).length
  return [
    { key: 'active', tone: 'working', label: t('launch.dashboard.bucket_active'), count: count(BUCKET_STATUSES.active) },
    { key: 'completed', tone: 'completed', label: t('launch.dashboard.bucket_done'), count: count(BUCKET_STATUSES.completed) },
    { key: 'stopped', tone: 'error', label: t('launch.dashboard.bucket_stopped'), count: count(BUCKET_STATUSES.stopped) },
    { key: 'draft', tone: 'idle', label: t('launch.dashboard.bucket_draft'), count: count(BUCKET_STATUSES.draft) }
  ]
})

const recentSessions = computed(() =>
  props.sessions
    .filter((s) => !filter.value || BUCKET_STATUSES[filter.value].includes(s.status))
    .slice(0, WORK_LIMIT)
)

const workMeta = (item) => {
  const workflow = (item.yaml_file || '').replace(/\.ya?ml$/i, '')
  const project = item.projects?.[0]?.name?.replace(/\/$/, '')
  return [project, workflow].filter(Boolean).join(' · ')
}

// ---------------------------------------------------------------- formatting
const stateLabel = (state) => {
  const key = `launch.board.states.${state}`
  return te(key) ? t(key) : state
}
const deptLabel = (dept) => {
  const key = `launch.office.rooms.${dept}`
  return te(key) ? t(key) : dept
}
const clockFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const clock = (ms) => (ms ? clockFormat.format(new Date(ms)) : '')

const ago = (seconds) => {
  if (!seconds) return ''
  const diff = Math.round((seconds * 1000 - now.value) / 1000)
  const rtf = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  const abs = Math.abs(diff)
  if (abs < 60) return rtf.format(diff, 'second')
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  return rtf.format(Math.round(diff / 86400), 'day')
}

// Live clock while the run is going and the view is on screen
let timer = null
const syncTimer = () => {
  const needed = props.visible && isLive.value
  if (needed && !timer) {
    now.value = Date.now()
    timer = setInterval(() => { now.value = Date.now() }, 1000)
  } else if (!needed && timer) {
    clearInterval(timer)
    timer = null
  }
  if (!needed) now.value = Date.now()
}
watch(() => [props.visible, isLive.value], syncTimer, { immediate: true })
onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<style scoped>
.dash {
  --ok: #22c55e;
  --run: var(--accent-sky);
  --wait: #f59e0b;
  --err: var(--danger);
  --muted: var(--text-muted-4);
  --line: rgb(var(--ink) / 0.09);
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 16px 16px 24px calc(var(--inset-left, 0px) + 34px);
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
  scrollbar-width: thin;
  transition: padding-left 0.25s ease;
}

.card {
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--surface-1);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.05), 0 8px 24px -18px rgb(0 0 0 / 0.35);
}

.muted { color: var(--muted); font-size: 12px; }
.empty { margin: 0; padding: 18px 4px; font-size: 13px; color: var(--muted); text-align: center; }

/* ---------- pills ---------- */
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

.pill.is-neutral { --tone: var(--text-muted-6); font-weight: 550; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.is-working { --tone: var(--run); }
.is-waiting { --tone: var(--wait); }
.is-done,
.is-completed { --tone: var(--ok); }
.is-error { --tone: var(--err); }
.is-cancelled { --tone: var(--text-muted-6); }
.is-todo,
.is-idle { --tone: var(--muted); }

.pill.is-working .dot,
.pill.is-waiting .dot { animation: pulse 1.4s ease-in-out infinite; }

@keyframes pulse {
  50% { opacity: 0.35; transform: scale(0.8); }
}

/* ---------- hero ---------- */
.hero {
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 18px 22px;
  background:
    radial-gradient(120% 140% at 0% 0%, color-mix(in srgb, var(--accent-sky) 12%, transparent), transparent 60%),
    radial-gradient(90% 120% at 100% 100%, color-mix(in srgb, var(--accent-mint) 10%, transparent), transparent 60%),
    var(--surface-1);
}

.ring {
  position: relative;
  flex: none;
  width: 112px;
  height: 112px;
}

.ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring circle { fill: none; stroke-width: 10; }
.ring-track { stroke: rgb(var(--ink) / 0.08); }

.ring-fill {
  stroke: var(--accent-sky);
  stroke-linecap: round;
  stroke-dasharray: 326.73;
  transition: stroke-dashoffset 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.ring-text {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  text-align: center;
}

.ring-text strong { font-size: 24px; font-weight: 720; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.ring-text span { font-size: 11px; color: var(--muted); }

.hero-main { min-width: 0; flex: 1; }

.eyebrow {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.hero-main h2 { margin: 2px 0 4px; font-size: 21px; font-weight: 700; letter-spacing: -0.02em; }

.hero-task {
  margin: 0 0 10px;
  max-width: 80ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-soft-1, var(--text-1));
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
}

.hero-tags { display: flex; flex-wrap: wrap; gap: 6px; }

/* ---------- KPIs ---------- */
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}

.kpi {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 14px 16px;
}

.kpi-label { font-size: 12px; font-weight: 600; color: var(--muted); }
.kpi-value { font-size: 24px; font-weight: 720; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }

.kpi-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--muted);
}

/* ---------- blocks ---------- */
.block { padding: 14px 16px 16px; min-width: 0; }

.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.block-head h3 { margin: 0; font-size: 14px; font-weight: 680; }

.grid-2 {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 14px;
}

/* ---------- pipeline ---------- */
.pipeline {
  display: flex;
  margin: 0;
  padding: 4px 0 2px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: thin;
}

.pipe-step {
  --dept: var(--accent-sky);
  position: relative;
  flex: 1 0 104px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 0 6px;
  text-align: center;
}

/* connector to the next step */
.pipe-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 14px;
  left: calc(50% + 17px);
  right: calc(-50% + 17px);
  height: 2px;
  border-radius: 2px;
  background: rgb(var(--ink) / 0.12);
}

.pipe-step.is-done:not(:last-child)::after { background: var(--ok); }

.pipe-node {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  border: 2px solid rgb(var(--ink) / 0.15);
  background: var(--surface-1);
  font-variant-numeric: tabular-nums;
  transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease, opacity 0.3s ease;
}

.pipe-step.is-done .pipe-node { color: #fff; border-color: var(--ok); background: var(--ok); }
.pipe-step.is-working .pipe-node { color: var(--run); border-color: var(--run); box-shadow: 0 0 0 5px color-mix(in srgb, var(--run) 18%, transparent); animation: glow 1.6s ease-in-out infinite; }
.pipe-step.is-waiting .pipe-node { color: var(--wait); border-color: var(--wait); box-shadow: 0 0 0 5px color-mix(in srgb, var(--wait) 18%, transparent); }
.pipe-step.is-error .pipe-node { color: #fff; border-color: var(--err); background: var(--err); }

@keyframes glow {
  50% { box-shadow: 0 0 0 9px color-mix(in srgb, var(--run) 6%, transparent); }
}

.pipe-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 620;
}

.pipe-sub { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---------- gantt ---------- */
.gantt { display: flex; flex-direction: column; gap: 7px; }

.gantt-row {
  --dept: var(--accent-sky);
  display: grid;
  grid-template-columns: minmax(90px, 160px) 1fr;
  align-items: center;
  gap: 10px;
}

.gantt-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.gantt-label b {
  display: inline-block;
  min-width: 18px;
  margin-right: 6px;
  color: var(--dept);
  font-variant-numeric: tabular-nums;
}

.gantt-track {
  position: relative;
  height: 14px;
  border-radius: 7px;
  background: rgb(var(--ink) / 0.05);
}

.gantt-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 7px;
  background: var(--dept);
  opacity: 0.85;
  transition: width 0.8s linear;
}

.gantt-bar.is-live {
  background: linear-gradient(90deg, var(--dept), color-mix(in srgb, var(--dept) 45%, transparent));
  opacity: 1;
  animation: breathe 1.6s ease-in-out infinite;
}

@keyframes breathe {
  50% { opacity: 0.65; }
}

.gantt-axis {
  display: flex;
  justify-content: space-between;
  margin-left: calc(min(160px, 30%) + 10px);
  font-size: 10.5px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

/* ---------- feed ---------- */
.feed {
  display: flex;
  flex-direction: column;
  max-height: 300px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
  scrollbar-width: thin;
}

.feed-item {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: start;
  gap: 9px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--line);
  font-size: 12.5px;
  animation: slide 0.25s ease-out;
}

.feed-item:last-child { border-bottom: 0; }

@keyframes slide {
  from { opacity: 0; transform: translateY(-4px); }
}

.feed-icon {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  font-size: 11px;
  color: var(--tone, var(--muted));
  background: color-mix(in srgb, var(--tone, var(--muted)) 13%, transparent);
}

.feed-item.is-start { --tone: var(--run); }
.feed-item.is-end,
.feed-item.is-completed { --tone: var(--ok); }
.feed-item.is-waiting { --tone: var(--wait); }
.feed-item.is-error { --tone: var(--err); }
.feed-item.is-handoff,
.feed-item.is-task,
.feed-item.is-input { --tone: var(--accent-indigo); }

.feed-text { min-width: 0; line-height: 1.45; }
.feed-text :deep(b) { font-weight: 650; }
.feed-text :deep(code) { font-size: 11.5px; padding: 0 4px; border-radius: 4px; background: rgb(var(--ink) / 0.07); }

.feed-text small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 11.5px;
}

.feed-item time { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---------- agents table ---------- */
.table-wrap { overflow-x: auto; }

.agents {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.agents th {
  padding: 0 10px 8px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-align: left;
  color: var(--muted);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

.agents td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}

.agents tr:last-child td { border-bottom: 0; }
.turns .idx { color: var(--accent-indigo); }
.turns tr.is-current td { background: color-mix(in srgb, var(--accent-indigo) 8%, transparent); }
.turns tr.is-current .idx { box-shadow: inset 3px 0 0 var(--accent-indigo); }
.turn-ask { max-width: 420px; }
.turn-ask span {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.turn-now {
  display: inline-block;
  margin-top: 3px;
  padding: 1px 7px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--accent-indigo) 16%, transparent);
  color: var(--accent-indigo);
  font-size: 10.5px;
  font-weight: 650;
}
.pill.is-turn { --tone: var(--accent-indigo); }
.gantt-bar.is-past { opacity: 0.4; }
.agents tbody tr:hover td { background: rgb(var(--ink) / 0.025); }
.agents .num { text-align: right; font-variant-numeric: tabular-nums; }
.agents .idx { width: 28px; color: var(--dept); font-weight: 700; font-variant-numeric: tabular-nums; }

.agent-cell { display: flex; align-items: center; gap: 9px; min-width: 180px; }
.agent-cell .branch { color: var(--muted, #8a8f98); font-size: 14px; margin-right: -3px; }
.agent-name .chain-line { display: block; opacity: 0.85; }

.avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  overflow: hidden;
  font-size: 11px;
  font-weight: 700;
  color: var(--dept);
  background: color-mix(in srgb, var(--dept) 14%, rgb(var(--ink) / 0.04));
}

.avatar img { width: 26px; height: 26px; object-fit: contain; image-rendering: pixelated; }

.agent-name { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.agent-name strong { font-weight: 620; }
.agent-name small { color: var(--muted); font-size: 11.5px; }

.share { display: flex; align-items: center; gap: 8px; min-width: 140px; }
.share-track { flex: 1; height: 6px; border-radius: 99px; background: rgb(var(--ink) / 0.07); overflow: hidden; }
.share-fill { display: block; height: 100%; border-radius: inherit; background: var(--dept); transition: width 0.6s ease; }
.share-text { min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }

/* ---------- all work ---------- */
.work-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.work-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 11px;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--tone, var(--muted)) 6%, transparent);
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.work-stat strong { font-size: 20px; font-weight: 720; color: var(--tone); font-variant-numeric: tabular-nums; }
.work-stat span { font-size: 12px; color: var(--muted); }
.work-stat:hover,
.work-stat.active { border-color: color-mix(in srgb, var(--tone) 55%, transparent); background: color-mix(in srgb, var(--tone) 12%, transparent); }

.work-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }

.work-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 9px 8px;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}

.work-list li:last-child .work-item { border-bottom: 0; }
.work-item:hover { background: rgb(var(--ink) / 0.03); }
.work-item.current { background: color-mix(in srgb, var(--accent-sky) 8%, transparent); }

.work-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }

.work-meta {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

.work-item time { color: var(--muted); font-size: 11.5px; white-space: nowrap; }

@media (prefers-reduced-motion: reduce) {
  .pill .dot,
  .pipe-node,
  .gantt-bar,
  .feed-item { animation: none !important; transition: none; }
}

@media (max-width: 1100px) {
  .grid-2 { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .dash { padding: 10px; }
  .hero { flex-direction: column; align-items: flex-start; }
  .work-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .work-item { grid-template-columns: auto minmax(0, 1fr); }
  .work-meta,
  .work-item time { display: none; }
}
</style>
