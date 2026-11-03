<template>
  <div class="dash">
    <!-- Hero: what is running and how far it is -->
    <section class="hero card">
      <div class="hero-main">
        <h2 :aria-label="`${$t('launch.dashboard.title')}: ${workflowName || $t('launch.board.no_workflow')}`">{{ workflowName || $t('launch.board.no_workflow') }}</h2>
        <p class="hero-task" :title="tracker.task?.text || ''">
          {{ tracker.task?.text || $t('launch.dashboard.no_task') }}
        </p>
        <div class="hero-tags">
          <StatusPill :tone="runTone" :label="stateLabel(runTone)" />
          <span v-if="currentStep" class="tag">
            {{ $t('launch.dashboard.now_at', { n: currentStep.index, name: currentStep.id }) }}
          </span>
          <span v-if="multiTurn && currentTurn" class="tag">{{ $t('launch.dashboard.turn_of', { n: currentTurn.number, total: turns.length }) }}</span>
          <span v-if="tracker.startedAt" class="tag">{{ $t('launch.dashboard.started', { time: clock(tracker.startedAt) }) }}</span>
        </div>
      </div>
      <!-- Progress is a meter with its numbers beside it, not a hero figure -->
      <!-- Only the lead replied: say so plainly instead of drawing an empty meter -->
      <p v-if="noTasks" class="hero-chat-only">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        {{ $t('launch.dashboard.chat_only') }}
      </p>
      <div v-else class="hero-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progress" :aria-label="$t('launch.dashboard.progress_aria', { p: progress })">
        <div class="hp-line">
          <span class="hp-count">{{ teamMode ? $t('launch.dashboard.tasks_of', { done: teamTasksDone, total: delegatedRuns.length }) : $t('launch.dashboard.done_of', { done: doneCount, total: steps.length }) }}</span>
          <span class="hp-pct">{{ progress }}%</span>
        </div>
        <div class="hp-track"><div class="hp-fill" :style="{ transform: `scaleX(${progress / 100})` }"></div></div>
      </div>
    </section>

    <!-- KPIs -->
    <section class="kpis card">
      <dl v-for="kpi in kpis" :key="kpi.key" class="kpi">
        <dt class="kpi-label">{{ kpi.label }}</dt>
        <dd class="kpi-value">{{ kpi.value }}</dd>
        <dd class="kpi-sub" :title="kpi.sub">{{ kpi.sub }}</dd>
      </dl>
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
              <td><StatusPill :tone="row.tone" :label="stateLabel(row.tone)" /></td>
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
      <ol v-if="steps.length" class="pipeline" :class="{ 'is-short': shownSteps.length <= 3 }">
        <li v-for="step in shownSteps" :key="step.id" class="pipe-step" :class="`is-${statusOf(step.id)}`" :style="{ '--dept': step.color }">
          <span class="pipe-node" :title="stateLabel(statusOf(step.id))">
            <svg v-if="statusOf(step.id) === 'done'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>
            <svg v-else-if="statusOf(step.id) === 'error'" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" /></svg>
            <template v-else>{{ step.index }}</template>
          </span>
          <span class="pipe-name" :title="step.id">{{ step.id }}</span>
          <span class="pipe-sub">{{ pipeSub(step) }}</span>
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
        <div v-if="session.startedAt && steps.length" ref="ganttEl" class="gantt" @mouseleave="tip = null">
          <!-- Bar color = department (same as the office rooms and board columns) -->
          <ul v-if="ganttDepts.length" class="gantt-legend" :aria-label="$t('launch.dashboard.legend')">
            <li v-for="dept in ganttDepts" :key="dept.id" :style="{ '--dept': dept.color }"><span class="legend-swatch" aria-hidden="true"></span>{{ deptLabel(dept.id) }}</li>
          </ul>
          <div v-for="step in shownSteps" :key="step.id" class="gantt-row" :style="{ '--dept': step.color }">
            <span class="gantt-label" :title="step.id"><b>{{ step.index }}</b>{{ step.id }}</span>
            <span class="gantt-track">
              <span
                v-for="run in runsOf(step.id)"
                :key="`${run.turn}-${run.index}`"
                class="gantt-bar"
                :class="{ 'is-live': !run.endedAt, 'is-past': multiTurn && run.turn !== currentTurn?.number }"
                :style="barStyle(run)"
                role="img"
                tabindex="0"
                :aria-label="`${barLabel(step, run)} · ${deptLabel(step.dept)}`"
                @mouseenter="showTip($event, step, run)"
                @focus="showTip($event, step, run)"
                @blur="tip = null"
              ></span>
            </span>
          </div>
          <div class="gantt-axis"><span>0s</span><span>{{ formatSpan(span / 2) }}</span><span>{{ formatSpan(span) }}</span></div>
          <div v-if="tip" class="gantt-tip" role="tooltip" :style="{ left: `${tip.x}px`, top: `${tip.y}px` }">
            <span class="tip-head"><span class="legend-swatch" :style="{ '--dept': tip.color }" aria-hidden="true"></span><b>{{ tip.name }}</b></span>
            <span class="tip-row">{{ tip.dept }}</span>
            <span class="tip-row">{{ tip.detail }}</span>
          </div>
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
            <span class="feed-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in eventIcon(event.kind)" :key="i" :d="d" /></svg>
            </span>
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
                  <svg v-if="row.depth" class="branch" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 4v8a4 4 0 0 0 4 4h9" /><path d="m15 12 4 4-4 4" /></svg>
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
              <td><StatusPill :tone="row.status" :label="stateLabel(row.status)" /></td>
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
                  <span class="share-track"><span class="share-fill" :style="{ transform: `scaleX(${row.share / 100})` }"></span></span>
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
          :aria-pressed="filter === bucket.key"
          @click="filter = filter === bucket.key ? '' : bucket.key"
        >
          <span>{{ bucket.label }}</span>
          <strong>{{ bucket.count }}</strong>
        </button>
      </div>
      <ul v-if="recentSessions.length" class="work-list">
        <li v-for="item in recentSessions" :key="item.session_id">
          <button type="button" class="work-item" :class="{ current: item.session_id === currentSessionId }" @click="$emit('open-session', item)">
            <StatusPill :tone="sessionTone(item.status)" :label="sessionLabel(item.status)" />
            <span class="work-title" :title="item.title">{{ item.title || item.yaml_file }}</span>
            <span class="work-meta">{{ workMeta(item) }}</span>
            <time>{{ ago(item.updated_at) }}</time>
          </button>
        </li>
      </ul>
      <p v-else class="empty">
        {{ $t('launch.dashboard.no_sessions') }}
        <button v-if="filter" type="button" class="empty-action" @click="filter = ''">{{ $t('launch.sessions.search_clear') }}</button>
      </p>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { combineTurns, formatCost, formatSpan, sessionTurns, stepDuration, stepStatus, turnSpan, usageTotals } from '@/utils/runTracker.js'
import { buildSteps, initialsOf } from '@/utils/workflowSteps.js'
import { buildOrgChart, computeTeamLinks } from '@/utils/teamLinks.js'
import StatusPill from './StatusPill.vue'

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

// Under the step name: its department while it waits, else its state and how long it took
const pipeSub = (step) => {
  const status = statusOf(step.id)
  if (status === 'todo') return deptLabel(step.dept)
  const time = formatSpan(durationOf(step.id))
  return status === 'done' ? time : `${stateLabel(status)} · ${time}`
}

const barLabel = (step, run) =>
  `${step.id} · ${multiTurn.value ? `${t('launch.board.turn', { n: run.turn })} · ` : ''}${t('launch.board.run', { n: run.index })} · ${formatSpan((run.endedAt || now.value) - run.startedAt)}`

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

// Drawn icons (one stroke style), path data per event kind
const ICONS = {
  task: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z'],
  start: ['M7 5v14l11-7z'],
  end: ['M5 12.5l4.5 4.5L19 7'],
  tool: ['M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z'],
  handoff: ['M5 12h14', 'M13 6l6 6-6 6'],
  waiting: ['M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3', 'M12 17h.01'],
  input: ['M9 14 4 9l5-5', 'M4 9h10.5a5.5 5.5 0 0 1 0 11H11'],
  completed: ['M5 21V4h11l-1.5 4L16 12H5'],
  cancelled: ['M7 7h10v10H7z'],
  error: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M12 8v5', 'M12 16.5v.01']
}
const eventIcon = (kind) => ICONS[kind] || ['M12 11.5v1']

// ---------------------------------------------------------------- timeline legend + tooltip
const ganttDepts = computed(() => {
  const seen = new Map()
  for (const step of shownSteps.value) if (runsOf(step.id).length && !seen.has(step.dept)) seen.set(step.dept, { id: step.dept, color: step.color })
  return [...seen.values()]
})
const ganttEl = ref(null)
const tip = ref(null)
const showTip = (event, step, run) => {
  const box = ganttEl.value?.getBoundingClientRect()
  const bar = event.currentTarget.getBoundingClientRect()
  if (!box) return
  const x = Math.min(Math.max(bar.left + bar.width / 2 - box.left, 90), box.width - 90)
  tip.value = {
    x,
    y: bar.top - box.top,
    name: step.id,
    color: step.color,
    dept: deptLabel(step.dept),
    detail: `${multiTurn.value ? `${t('launch.board.turn', { n: run.turn })} · ` : ''}${t('launch.board.run', { n: run.index })} · ${formatSpan((run.endedAt || now.value) - run.startedAt)}${run.endedAt ? '' : ` · ${stateLabel('working')}`}`
  }
}

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
  --ok: var(--success);
  --run: var(--accent);
  --wait: var(--warn);
  --err: var(--danger);
  --muted: var(--fg-muted);
  --line: var(--border);
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 16px 16px 24px calc(var(--inset-left, 0px) + 34px);
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: var(--fg);
  font-family: inherit;
  scrollbar-width: thin;
  transition: padding-left 0.25s var(--ease-out);
}

/* Sections keep their content height: the page scrolls, cards never get squeezed
   (the figures strip used to collapse to its 2px divider on short panes) */
.dash > * { flex-shrink: 0; }

.card {
  border-radius: var(--radius-lg);
  border: 1px solid var(--line);
  background: var(--surface);
}

.muted { color: var(--muted); font-size: var(--fs-xs); }

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin: 0;
  padding: 18px 4px;
  font-size: 13px;
  color: var(--muted);
  text-align: center;
}

.empty-action {
  min-height: 40px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.empty-action:hover { border-color: var(--accent); }

button:focus-visible,
.gantt-bar:focus-visible,
.feed:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 9px;
  border-radius: 99px;
  border: 1px solid var(--line);
  color: var(--fg-muted);
  font-size: var(--fs-xs);
  font-weight: 550;
  white-space: nowrap;
}

/* ---------- header ---------- */
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px 28px;
  padding: 16px 20px;
}

.hero-main { min-width: 0; flex: 1 1 320px; }

.hero-main h2 { margin: 0 0 4px; font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }

.hero-task {
  margin: 0 0 10px;
  max-width: 80ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--fg-muted);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
}

.hero-tags { display: flex; flex-wrap: wrap; gap: 6px; }

/* progress meter: numbers next to the bar, never a hero figure */
.hero-progress { flex: 0 1 280px; min-width: 200px; display: flex; flex-direction: column; gap: 8px; }
.hp-line { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; font-size: 13px; }
.hp-count { color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.hp-pct { font-weight: 700; font-variant-numeric: tabular-nums; }
.hp-track { height: 8px; border-radius: 99px; background: rgb(var(--ink) / 0.1); overflow: hidden; }
.hp-fill { height: 100%; border-radius: inherit; background: var(--run); transform-origin: left center; transition: transform 0.25s var(--ease-out); }

.hero-chat-only {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  border: 1px dashed var(--line);
  font-size: 13px;
  color: var(--fg-muted);
}
.hero-chat-only svg { flex: none; }

/* ---------- figures: one strip, a divider between items ---------- */
/* Each item draws its right and bottom hairline; the card clips the outer ones, so a
   short last row leaves plain surface rather than a filled gap */
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  overflow: hidden;
}

.kpis .kpi { position: relative; }
.kpis .kpi::after {
  content: '';
  position: absolute;
  z-index: 1;
  inset: 0 -1px -1px 0;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  pointer-events: none;
}

.kpi {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  margin: 0;
  padding: 12px 16px;
  background: var(--surface);
}

.kpi dd { margin: 0; }
.kpi-label { font-size: var(--fs-xs); font-weight: 600; color: var(--muted); }
.kpi-value { font-size: 18px; font-weight: 700; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }

.kpi-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-xs);
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

/* Cards size to their content: a two-row timeline does not stretch to the feed's height */
.grid-2 {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  align-items: start;
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
  --dept: var(--accent);
  position: relative;
  flex: 1 0 112px;
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
  background: rgb(var(--ink) / 0.14);
}

.pipe-step.is-done:not(:last-child)::after { background: var(--ok); }

/* A short list (a lead who only replied, a 2-3 step flow) sits left at its natural width */
.pipeline.is-short .pipe-step { flex: 0 1 160px; }

.pipe-node {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--muted);
  border: 2px solid rgb(var(--ink) / 0.2);
  background: var(--surface);
  font-variant-numeric: tabular-nums;
  transition: background-color 0.3s var(--ease-out), border-color 0.3s var(--ease-out), color 0.3s var(--ease-out);
}

.pipe-step.is-done .pipe-node { color: var(--on-success); border-color: var(--ok); background: var(--ok); }
.pipe-step.is-working .pipe-node { color: var(--run); border-color: var(--run); box-shadow: 0 0 0 4px color-mix(in srgb, var(--run) 18%, transparent); }
.pipe-step.is-waiting .pipe-node { color: var(--wait); border-color: var(--wait); box-shadow: 0 0 0 4px color-mix(in srgb, var(--wait) 18%, transparent); }
.pipe-step.is-error .pipe-node { color: var(--on-danger); border-color: var(--err); background: var(--err); }

.pipe-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 620;
}

.pipe-sub { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--fs-xs); color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---------- gantt ---------- */
.gantt { position: relative; display: flex; flex-direction: column; gap: 8px; }

.gantt-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin: 0 0 4px;
  padding: 0;
  list-style: none;
  font-size: var(--fs-xs);
  color: var(--fg-muted);
}
.gantt-legend li { display: inline-flex; align-items: center; gap: 6px; }

.legend-swatch {
  width: 10px;
  height: 10px;
  flex: none;
  border-radius: 3px;
  background: var(--dept);
}

.gantt-tip {
  position: absolute;
  z-index: 5;
  transform: translate(-50%, calc(-100% - 8px));
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 150px;
  max-width: 240px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--surface-raised);
  box-shadow: 0 8px 24px rgb(var(--shade) / 0.3);
  font-size: var(--fs-xs);
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  animation: tip-in 0.15s var(--ease-out);
}
.tip-head { display: inline-flex; align-items: center; gap: 6px; color: var(--fg); font-size: 13px; }
.tip-head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 650; }

@keyframes tip-in { from { opacity: 0; } }

.gantt-row {
  --dept: var(--accent);
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
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

/* Recessive scale: hairlines at 0 / 50 / 100% instead of a filled lane */
.gantt-track {
  position: relative;
  height: 20px;
  background:
    linear-gradient(var(--line), var(--line)) 0 0 / 1px 100% no-repeat,
    linear-gradient(var(--line), var(--line)) 50% 0 / 1px 100% no-repeat,
    linear-gradient(var(--line), var(--line)) 100% 0 / 1px 100% no-repeat;
}

/* Thin mark: 12px bar, 4px corners, 2px surface ring so touching runs stay apart */
.gantt-bar {
  position: absolute;
  top: 4px;
  bottom: 4px;
  min-width: 6px;
  border-radius: 4px;
  background: var(--dept);
  box-shadow: 0 0 0 2px var(--surface);
  cursor: default;
  transition: opacity 0.15s var(--ease-out), box-shadow 0.15s var(--ease-out);
}

.gantt-bar::before { content: ''; position: absolute; inset: -4px -2px; }

.gantt-bar:hover,
.gantt-bar:focus-visible { box-shadow: 0 0 0 2px var(--surface), 0 0 0 3px var(--fg); outline: none; }

/* still running: hatched, so it differs from a finished bar without colour */
.gantt-bar.is-live {
  background-image: repeating-linear-gradient(135deg, rgb(0 0 0 / 0.22) 0 4px, transparent 4px 8px);
  background-color: var(--dept);
  opacity: 1;
  animation: breathe 1.6s ease-in-out infinite;
}

@keyframes breathe {
  50% { opacity: 0.7; }
}

.gantt-axis {
  display: flex;
  justify-content: space-between;
  margin-left: calc(min(160px, 30%) + 10px);
  font-size: var(--fs-xs);
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
  padding: 8px 2px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
  animation: slide 0.25s var(--ease-out);
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
  font-size: var(--fs-xs);
  color: var(--tone, var(--muted));
  background: color-mix(in srgb, var(--tone, var(--muted)) 14%, transparent);
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
.feed-text :deep(code) { font-size: var(--fs-xs); padding: 0 4px; border-radius: 4px; background: rgb(var(--ink) / 0.08); }

.feed-text small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: var(--fs-xs);
}

.feed-item time { font-size: var(--fs-xs); color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---------- agents table ---------- */
.table-wrap { overflow-x: auto; }

.agents {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.agents th {
  padding: 0 10px 8px;
  font-size: var(--fs-xs);
  font-weight: 600;
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
.turns tr.is-current td { background: color-mix(in srgb, var(--accent-indigo) 9%, transparent); }
.turn-ask { max-width: 420px; }
.turn-ask span {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.turn-now {
  display: inline-block;
  margin-top: 3px;
  padding: 1px 8px;
  border-radius: 99px;
  border: 1px solid color-mix(in srgb, var(--accent-indigo) 40%, transparent);
  color: var(--accent-indigo);
  font-size: var(--fs-xs);
  font-weight: 650;
}
.gantt-bar.is-past { opacity: 0.45; }
.agents tbody tr:hover td { background: rgb(var(--ink) / 0.03); }
.agents .num { text-align: right; font-variant-numeric: tabular-nums; }
.agents .idx { width: 28px; color: var(--muted); font-weight: 700; font-variant-numeric: tabular-nums; }

.agent-cell { display: flex; align-items: center; gap: 9px; min-width: 180px; }
.agent-cell .branch { flex: none; color: var(--muted); margin-right: -3px; }
.agents td:last-child { font-variant-numeric: tabular-nums; }
.agent-name .chain-line { display: block; }

.avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  overflow: hidden;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--fg);
  background: color-mix(in srgb, var(--dept) 22%, rgb(var(--ink) / 0.04));
}

.avatar img { width: 26px; height: 26px; object-fit: contain; image-rendering: pixelated; }

.agent-name { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.agent-name strong { font-weight: 620; }
.agent-name small { color: var(--muted); font-size: var(--fs-xs); }

.share { display: flex; align-items: center; gap: 8px; min-width: 120px; }
.share-track { flex: 1; height: 6px; border-radius: 99px; background: rgb(var(--ink) / 0.09); overflow: hidden; }
.share-fill { display: block; height: 100%; border-radius: inherit; background: var(--dept); transform-origin: left center; transition: transform 0.25s var(--ease-out); }
.share-text { min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }

/* ---------- all work ---------- */
.work-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

/* a filter: label and count on one line, the active one outlined */
.work-stat {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 14px;
  border-radius: 99px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s var(--ease-out), background-color 0.15s var(--ease-out);
}

.work-stat strong { font-weight: 700; font-variant-numeric: tabular-nums; }
.work-stat span { color: var(--muted); }
.work-stat:hover { border-color: var(--accent); }
.work-stat.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.work-stat.active span { color: var(--fg); }

.work-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }

.work-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 44px;
  padding: 8px;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.work-list li:last-child .work-item { border-bottom: 0; }
.work-item:hover { background: rgb(var(--ink) / 0.04); }
.work-item.current { background: color-mix(in srgb, var(--accent) 9%, transparent); }

.work-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }

.work-meta {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

.work-item time { color: var(--muted); font-size: var(--fs-xs); white-space: nowrap; }

@media (prefers-reduced-motion: reduce) {
  .gantt-bar,
  .hp-fill,
  .pipe-node,
  .share-fill { transition: none; }
  .gantt-bar.is-live,
  .gantt-tip,
  .feed-item { animation: none; }
}

@media (max-width: 1100px) {
  .grid-2 { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  /* top room keeps the floating sidebar toggle off the heading */
  .dash { padding: 48px 10px 10px; }
  .hero { flex-direction: column; align-items: stretch; }
  .hero-main { flex: 0 0 auto; }
  .hero-progress { flex-basis: auto; min-width: 0; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .work-item { grid-template-columns: auto minmax(0, 1fr); }
  .work-meta,
  .work-item time { display: none; }
}
</style>
