<template>
  <div class="kanban">
    <header class="kb-bar">
      <div class="kb-title">
        <h2 :aria-label="`${$t('launch.board.title')}: ${workflowName || $t('launch.board.no_workflow')}`">{{ workflowName || $t('launch.board.no_workflow') }}</h2>
      </div>
      <div class="kb-meta">
        <StatusPill :tone="runTone" :label="stateLabel(runTone)" />
        <!-- Only the lead talked: nothing was delegated, so there is no progress to draw -->
        <span v-if="steps.length && chatOnly" class="kb-progress is-chat" :title="$t('launch.board.progress_hint')">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
          {{ $t('launch.dashboard.chat_only') }}
        </span>
        <span v-else-if="steps.length" class="kb-progress" :title="$t('launch.board.progress_hint')">
          <span class="kb-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progress"><span class="kb-progress-fill" :style="{ transform: `scaleX(${progress / 100})` }"></span></span>
          <template v-if="teamMode">{{ $t('launch.board.progress_team', { done: teamTasksDone, total: delegatedRuns.length, people: teamPeople }) }}</template>
          <template v-else>{{ $t('launch.board.progress', { done: doneCount, total: steps.length }) }}</template>
        </span>
        <span v-if="view.startedAt" class="kb-time">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          {{ formatSpan(elapsed) }}
        </span>
        <select
          v-if="multiTurn"
          v-model="turnFilter"
          class="kb-turns"
          :aria-label="$t('launch.board.turn_filter')"
          :title="$t('launch.board.turn_filter')"
        >
          <option value="all">{{ $t('launch.board.turn_all', { n: turns.length }) }}</option>
          <option v-for="turn in [...turns].reverse()" :key="turn.number" :value="turn.number">{{ turnLabel(turn) }}</option>
        </select>
        <div class="seg" role="radiogroup" :aria-label="$t('launch.board.group_by')">
          <button
            v-for="mode in ['team', 'step']"
            :key="mode"
            type="button"
            role="radio"
            :aria-checked="groupBy === mode"
            :class="{ active: groupBy === mode }"
            @click="setGroupBy(mode)"
          >
            {{ $t(`launch.board.group_${mode}`) }}
          </button>
        </div>
        <label class="kb-follow">
          <input v-model="follow" type="checkbox" />
          {{ $t('launch.board.follow') }}
        </label>
      </div>
    </header>

    <p v-if="!steps.length" class="kb-empty">{{ $t('launch.board.empty') }}</p>

    <div v-else class="kb-board" :class="{ 'fade-start': !scrollState.atStart, 'fade-end': !scrollState.atEnd }">
    <!-- Where you are on a board wider than the pane -->
    <div v-if="!scrollState.atStart || !scrollState.atEnd" class="kb-scrollbar">
      <span class="kb-range">{{ $t('launch.board.columns_range', { from: scrollState.first, to: scrollState.last, total: scrollState.total }) }}</span>
      <button type="button" class="kb-nav" :disabled="scrollState.atStart" :aria-label="$t('launch.board.scroll_prev')" :title="$t('launch.board.scroll_prev')" @click="scrollColumns(-1)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
      </button>
      <button type="button" class="kb-nav" :disabled="scrollState.atEnd" :aria-label="$t('launch.board.scroll_next')" :title="$t('launch.board.scroll_next')" @click="scrollColumns(1)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
      </button>
    </div>
    <div ref="scrollerEl" class="kb-columns" @scroll.passive="onColumnsScroll">
      <!-- Your request -->
      <section class="col col-task">
        <header class="col-head">
          <span class="col-icon is-you" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21a8 8 0 0 0-16 0" /><circle cx="12" cy="8" r="4" /></svg>
          </span>
          <div class="col-name">
            <strong>{{ $t('launch.board.you') }}</strong>
            <span>{{ $t('launch.board.request') }}</span>
          </div>
          <StatusPill compact :tone="view.task ? 'done' : 'todo'" :label="view.task ? $t('launch.board.sent') : $t('launch.board.todo')" />
        </header>
        <div class="col-body">
          <article
            v-for="turn in requestTurns"
            :key="`ask-${turn.number}`"
            class="card is-you"
            :class="{ 'is-past': showTurnTags && !turn.current }"
          >
            <div class="card-meta">
              <span class="card-kicker">{{ multiTurn ? turnLabel(turn) : $t('launch.board.task') }}</span>
              <time>{{ clock(turn.task.at) }}</time>
            </div>
            <p class="card-text" :class="turn.current || !showTurnTags ? 'clamp-8' : 'clamp-3'">{{ turn.task.text || '—' }}</p>
            <div v-if="turn.task.attachments.length" class="chips">
              <span v-for="(name, i) in turn.task.attachments" :key="`${i}-${name}`" class="chip"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21 11-8.5 8.5a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15 7" /></svg> {{ name }}</span>
            </div>
            <div v-if="turn.inputs" class="card-foot">{{ $t('launch.board.replies', { n: turn.inputs }) }}</div>
          </article>
          <div v-if="!requestTurns.length" class="placeholder">{{ $t('launch.board.task_placeholder') }}</div>
        </div>
      </section>

      <!-- Teams (or single steps) -->
      <section
        v-for="column in columns"
        :key="column.key"
        :ref="(el) => setColumnRef(column.key, el)"
        class="col"
        :class="`is-${column.status}`"
        :style="{ '--dept': column.color }"
      >
        <header class="col-head">
          <span class="col-icon" aria-hidden="true">
            <template v-if="column.members.length === 1">{{ column.members[0].index }}</template>
            <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6" /></svg>
          </span>
          <div class="col-name">
            <strong :title="column.title"><span class="col-dot" aria-hidden="true"></span>{{ column.title }}</strong>
            <span>{{ column.sub }}</span>
          </div>
          <StatusPill compact :tone="column.status" :label="stateLabel(column.status)" />
        </header>

        <!-- Members: who is in this team and how each one is doing -->
        <div class="members">
          <button
            v-for="member in column.members"
            :key="member.id"
            type="button"
            class="member"
            :class="[`is-${statusOf(member.id)}`, { active: memberFilter[column.key] === member.id }]"
            :title="`${$t('launch.board.step', { n: member.index })} · ${member.id} · ${stateLabel(statusOf(member.id))}`"
            :aria-label="`${member.id} · ${stateLabel(statusOf(member.id))}`"
            :aria-pressed="memberFilter[column.key] === member.id"
            @click="toggleMember(column.key, member.id)"
          >
            <span class="avatar">
              <img v-if="member.sprite" :src="member.sprite" alt="" />
              <span v-else>{{ initialsOf(member.id) }}</span>
            </span>
            <span class="member-state" aria-hidden="true"></span>
          </button>
          <span class="members-progress">
            <span class="mini-track"><span class="mini-fill" :style="{ width: `${column.progress}%` }"></span></span>
            {{ column.doneMembers }}/{{ column.members.length }}
          </span>
        </div>

        <div class="col-body">
          <!-- Working now / waiting for you -->
          <template v-if="column.active.length">
            <p class="section-label">{{ $t('launch.board.section_active') }}<span class="section-count">{{ column.active.length }}</span></p>
            <article
              v-for="task in column.active"
              :key="task.key"
              class="card"
              :class="`is-${task.status}`"
            >
              <div class="card-meta">
                <span class="assignee">
                  <span class="avatar sm"><img v-if="task.step.sprite" :src="task.step.sprite" alt="" /><span v-else>{{ initialsOf(task.step.id) }}</span></span>
                  <b :title="task.step.id">{{ task.step.id }}</b>
                  <span class="step-tag">B{{ task.step.index }}</span>
                </span>
                <span class="meta-end">
                  <time v-if="task.run">{{ formatSpan(now - task.run.startedAt) }}</time>
                  <StatusPill compact :tone="task.status" :label="stateLabel(task.status)" />
                </span>
              </div>
              <p v-if="task.run?.delegatedBy" class="card-from">{{ $t('launch.board.assigned_by', { lead: task.run.delegatedBy }) }}</p>
              <p class="card-title">{{ task.title }}</p>
              <p v-if="task.status === 'waiting'" class="activity is-wait">{{ $t('launch.board.waiting_text') }}</p>
              <p v-else-if="task.run?.activity" class="activity">
                <span class="spinner" aria-hidden="true"></span>
                {{ task.run.activity.kind === 'tool'
                  ? $t('launch.board.using_tool', { name: task.run.activity.name })
                  : $t('launch.board.thinking', { name: task.run.activity.name }) }}
              </p>
              <p v-else class="activity"><span class="spinner" aria-hidden="true"></span>{{ $t('launch.board.working') }}</p>
              <div v-if="task.run && (task.run.tools.length || task.run.models)" class="chips">
                <span v-if="task.run.models" class="chip is-model"><svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" aria-hidden="true"><path d="M12 2.5 14 10l7.5 2-7.5 2-2 7.5-2-7.5-7.5-2 7.5-2z" /></svg> {{ task.run.models }}</span>
                <span v-for="[name, count] in toolCounts(task.run.tools)" :key="name" class="chip">{{ name }}<b v-if="count > 1"> ×{{ count }}</b></span>
              </div>
            </article>
          </template>

          <!-- Next up: members that have not started yet -->
          <template v-if="column.queued.length">
            <p class="section-label">{{ $t(teamMode && view.task ? 'launch.board.section_unassigned' : 'launch.board.section_queued') }}<span class="section-count">{{ column.queued.length }}</span></p>
            <article v-for="step in column.queued" :key="`q-${step.id}`" class="card is-todo is-compact">
              <div class="card-meta">
                <span class="assignee">
                  <span class="avatar sm"><img v-if="step.sprite" :src="step.sprite" alt="" /><span v-else>{{ initialsOf(step.id) }}</span></span>
                  <b :title="step.id">{{ step.id }}</b>
                  <span class="step-tag">B{{ step.index }}</span>
                </span>
              </div>
              <p v-if="step.role && !teamMode" class="card-text clamp-2">{{ step.role }}</p>
            </article>
          </template>

          <!-- Done: every hand-over, newest first -->
          <template v-if="column.done.length">
            <p class="section-label">{{ $t('launch.board.section_done') }}<span class="section-count">{{ column.done.length }}</span></p>
            <article
              v-for="task in visibleDone(column)"
              :key="task.key"
              class="card"
              :class="[`is-${task.status}`, { 'is-open': opened.has(task.key) }]"
              role="button"
              tabindex="0"
              :aria-expanded="opened.has(task.key)"
              @click="toggleOpen(task.key)"
              @keydown.enter.prevent="toggleOpen(task.key)"
              @keydown.space.prevent="toggleOpen(task.key)"
            >
              <div class="card-meta">
                <span class="assignee">
                  <span class="avatar sm"><img v-if="task.step.sprite" :src="task.step.sprite" alt="" /><span v-else>{{ initialsOf(task.step.id) }}</span></span>
                  <b :title="task.step.id">{{ task.step.id }}</b>
                  <span class="step-tag">B{{ task.step.index }}<template v-if="task.run.index > 1"> · {{ $t('launch.board.run', { n: task.run.index }) }}</template></span>
                  <span v-if="showTurnTags" class="turn-tag">{{ $t('launch.board.turn', { n: task.run.turn }) }}</span>
                </span>
                <span class="meta-end">
                  <StatusPill v-if="task.status !== 'done'" compact :tone="task.status" :label="stateLabel(task.status)" />
                  <time :title="clock(task.run.endedAt)">{{ formatSpan(task.run.endedAt - task.run.startedAt) }}</time>
                </span>
              </div>
              <p v-if="task.run.delegatedBy" class="card-from">{{ $t('launch.board.assigned_by', { lead: task.run.delegatedBy }) }}</p>
              <p v-if="task.run.task" class="card-ask clamp-2" :title="task.run.task">{{ $t('launch.board.asked', { task: task.run.task }) }}</p>
              <p class="card-title">{{ task.title }}</p>
              <p v-if="task.body" class="card-text" :class="opened.has(task.key) ? '' : 'clamp-3'">{{ task.body }}</p>
              <div v-if="task.run.tools.length || task.run.models" class="chips">
                <span v-if="task.run.models" class="chip is-model"><svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" aria-hidden="true"><path d="M12 2.5 14 10l7.5 2-7.5 2-2 7.5-2-7.5-7.5-2 7.5-2z" /></svg> {{ task.run.models }}</span>
                <span v-for="[name, count] in toolCounts(task.run.tools)" :key="name" class="chip">{{ name }}<b v-if="count > 1"> ×{{ count }}</b></span>
                <span v-if="extraTools(task.run.tools)" class="chip is-more">+{{ extraTools(task.run.tools) }}</span>
              </div>
            </article>
            <button
              v-if="column.done.length > DONE_PREVIEW"
              type="button"
              class="more-btn"
              @click="toggleExpandedColumn(column.key)"
            >
              {{ expandedColumns.has(column.key)
                ? $t('launch.board.show_less')
                : $t('launch.board.show_more', { n: column.done.length - DONE_PREVIEW }) }}
            </button>
          </template>

          <div v-if="!column.active.length && !column.queued.length && !column.done.length" class="placeholder">
            {{ $t('launch.board.no_tasks_member') }}
          </div>
        </div>
      </section>

      <!-- Outcome -->
      <section class="col col-final" :class="`is-${view.outcome || 'todo'}`">
        <header class="col-head">
          <span class="col-icon is-flag" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21V4h11l-1.5 4L16 12H5" /></svg>
          </span>
          <div class="col-name">
            <strong>{{ $t('launch.board.result') }}</strong>
            <span>{{ $t('launch.board.result_sub') }}</span>
          </div>
          <StatusPill compact :tone="outcomeTone" :label="stateLabel(outcomeTone)" />
        </header>
        <div class="col-body">
          <article
            v-for="turn in resultTurns"
            :key="`result-${turn.number}`"
            class="card"
            :class="[`is-${turn.outcome}`, { 'is-past': showTurnTags && !turn.current }]"
          >
            <div class="card-meta">
              <span class="card-kicker">{{ stateLabel(turn.outcome) }}<template v-if="multiTurn"> · {{ turnLabel(turn) }}</template></span>
              <time>{{ clock(turn.endedAt) }}</time>
            </div>
            <p v-if="turn.summary || turn.error" class="card-text" :class="turn.current || !showTurnTags ? 'clamp-10' : 'clamp-3'">{{ turn.summary || turn.error }}</p>
            <div class="card-foot">
              {{ $t('launch.board.total_time', { time: formatSpan(turnSpan(turn, now)) }) }}
              <template v-if="turnTokens(turn)"> · {{ $t('launch.board.tokens', { n: turnTokens(turn).toLocaleString() }) }}</template>
            </div>
            <!-- Review works on the latest turn -->
            <button v-if="turn.current && turn.outcome === 'completed'" type="button" class="review-btn" @click.stop="$emit('review')">
              {{ $t('launch.board.go_review') }}
            </button>
          </article>
          <div v-if="!resultTurns.length" class="placeholder">{{ $t('launch.board.result_placeholder') }}</div>
        </div>
      </section>
    </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { combineTurns, formatSpan, sessionTurns, stepStatus, turnSpan, usageTotals } from '@/utils/runTracker.js'
import { buildSteps, initialsOf } from '@/utils/workflowSteps.js'
import { computeTeamLinks } from '@/utils/teamLinks.js'
import StatusPill from './StatusPill.vue'

const props = defineProps({
  graph: { type: Object, default: () => ({}) },
  spriteMap: { type: Map, default: () => new Map() },
  // runTracker state (see utils/runTracker.js)
  tracker: { type: Object, required: true },
  // raw workflow status string of the Launch view
  status: { type: String, default: '' },
  workflowName: { type: String, default: '' },
  visible: { type: Boolean, default: true }
})
defineEmits(['review'])

const { t, te } = useI18n()
const MAX_TOOL_CHIPS = 4
const DONE_PREVIEW = 4
const GROUP_KEY = 'agentdev.board.groupBy'

const readGroup = () => {
  try { return localStorage.getItem(GROUP_KEY) === 'step' ? 'step' : 'team' } catch { return 'team' }
}
const groupBy = ref(readGroup())
const setGroupBy = (mode) => {
  groupBy.value = mode
  try { localStorage.setItem(GROUP_KEY, mode) } catch { /* storage unavailable */ }
}

const scrollerEl = ref(null)
const columnEls = new Map()
const follow = ref(true)
const opened = reactive(new Set())
const expandedColumns = reactive(new Set())
const memberFilter = reactive({})
const now = ref(Date.now())

const steps = computed(() => buildSteps(props.graph, props.spriteMap))

// ---------------------------------------------------------------- turns
// Every turn of the session (a follow-up message is a new turn): the board shows them all,
// newest first, or one picked in the header
const turns = computed(() => sessionTurns(props.tracker))
const multiTurn = computed(() => turns.value.length > 1)
const turnFilter = ref('all') // 'all' | turn number
const shownTurns = computed(() => {
  if (turnFilter.value === 'all') return turns.value
  const picked = turns.value.filter((turn) => turn.number === turnFilter.value)
  return picked.length ? picked : turns.value
})
// A new session has other turns: back to all of them
watch(turns, (list) => {
  if (turnFilter.value !== 'all' && !list.some((turn) => turn.number === turnFilter.value)) turnFilter.value = 'all'
})
// The tracker was reset (another session, a new draft): no filter or opened card carries
// over. Only a reset replaces the list of turns (a new turn is pushed onto it), and a
// reset followed by a replay can land on the same turn number, so the list is watched.
const clearViewState = () => {
  turnFilter.value = 'all'
  for (const key of Object.keys(memberFilter)) delete memberFilter[key]
  opened.clear()
  expandedColumns.clear()
}
watch(() => props.tracker?.turns, clearViewState)
watch(
  () => props.tracker?.turn || 0,
  (turn, previous) => {
    if (turn === 0 || turn < previous) clearViewState()
  }
)
const view = computed(() => combineTurns(shownTurns.value))
const newestFirst = computed(() => [...shownTurns.value].reverse())
const requestTurns = computed(() => newestFirst.value.filter((turn) => turn.task))
const resultTurns = computed(() => newestFirst.value.filter((turn) => turn.outcome))
const showTurnTags = computed(() => multiTurn.value && shownTurns.value.length > 1)
const turnLabel = (turn) =>
  turn.current ? t('launch.board.turn_current', { n: turn.number }) : t('launch.board.turn', { n: turn.number })
const turnTokens = (turn) => usageTotals(turn.tokenUsage).tokens

const nodeOf = (id) => view.value.nodes[id]
const statusOf = (id) => stepStatus(nodeOf(id))
const doneCount = computed(() => steps.value.filter((s) => statusOf(s.id) === 'done').length)

// A team workflow (a lead delegates to members) does not run every step: the lead picks who
// works. Progress is then counted in tasks handed over, and members nobody asked are
// "not assigned" rather than "next up".
const teamMode = computed(() => computeTeamLinks(props.graph?.nodes, props.graph?.edges).length > 0)
const delegatedRuns = computed(() =>
  Object.values(view.value.nodes).flatMap((node) => node.runs.filter((run) => run.delegatedBy))
)
const teamTasksDone = computed(() => delegatedRuns.value.filter((run) => run.endedAt).length)
const teamPeople = computed(() =>
  Object.entries(view.value.nodes).filter(([, node]) => node.runs.length).length
)
const progress = computed(() => {
  if (teamMode.value) {
    const total = delegatedRuns.value.length
    return total ? Math.round((teamTasksDone.value / total) * 100) : view.value.outcome ? 100 : 0
  }
  return steps.value.length ? Math.round((doneCount.value / steps.value.length) * 100) : 0
})

// A team turn where the lead only replied: no bar (a full bar would claim work that never happened)
const chatOnly = computed(() => teamMode.value && !delegatedRuns.value.length)

const isLive = computed(() => props.status === 'Running...' || props.status === 'Waiting for input...')
// Working time of the shown turns (the pauses between turns do not count)
const elapsed = computed(() => shownTurns.value.reduce((sum, turn) => sum + turnSpan(turn, now.value), 0))
const runTone = computed(() => {
  if (props.status === 'Waiting for input...') return 'waiting'
  if (isLive.value) return 'working'
  return view.value.outcome || 'idle'
})
const outcomeTone = computed(() => view.value.outcome || (isLive.value ? 'working' : 'todo'))


// ---------------------------------------------------------------- task text
// A hand-over usually opens with a heading or a summary line: that is the task title.
const cleanLine = (line) =>
  line
    .replace(/^\s{0,3}(#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)/, '')
    .replace(/[*_`~]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()

// Card previews are plain text: markdown tables become "cell · cell" lines and their
// |---| separator rows disappear
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/
const plainLine = (line) => {
  if (TABLE_RULE.test(line)) return null
  if (/^\s*\|/.test(line)) {
    return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()).filter(Boolean).join(' · ')
  }
  return line
}
const splitOutput = (text) => {
  const lines = String(text || '').split('\n').map(plainLine).filter((line) => line !== null)
  const index = lines.findIndex((line) => cleanLine(line).length > 2)
  if (index === -1) return { title: '', body: '' }
  const title = cleanLine(lines[index])
  return {
    title: title.length > 110 ? `${title.slice(0, 109)}…` : title,
    body: lines.slice(index + 1).join('\n').replace(/\*\*|__|`/g, '').trim()
  }
}

// ---------------------------------------------------------------- columns
const statusRank = { working: 4, waiting: 5, error: 3, cancelled: 2, done: 1, todo: 0 }

const deptLabel = (dept) => {
  const key = `launch.office.rooms.${dept}`
  return te(key) ? t(key) : dept
}

const groups = computed(() => {
  if (groupBy.value === 'step') {
    return steps.value.map((step) => ({ key: step.id, title: step.id, color: step.color, members: [step], single: true }))
  }
  const byDept = new Map()
  for (const step of steps.value) {
    if (!byDept.has(step.dept)) byDept.set(step.dept, { key: step.dept, title: deptLabel(step.dept), color: step.color, members: [] })
    byDept.get(step.dept).members.push(step)
  }
  // Teams appear in the order their first member works in the workflow
  return [...byDept.values()]
})

const columns = computed(() =>
  groups.value.map((group) => {
    const filterId = memberFilter[group.key]
    const members = group.members
    const shown = filterId ? members.filter((m) => m.id === filterId) : members
    const active = []
    const queued = []
    const done = []
    for (const step of shown) {
      const node = nodeOf(step.id)
      const status = statusOf(step.id)
      const runs = node?.runs || []
      const open = runs.find((run) => !run.endedAt)
      if (status === 'waiting' || open) {
        active.push({
          key: `${step.id}#live`,
          step,
          run: open || null,
          status: status === 'waiting' ? 'waiting' : 'working',
          // A delegated task is titled by what the lead asked for
        })
      } else if (!runs.length) {
        queued.push(step)
      }
      for (const run of runs) {
        if (!run.endedAt) continue
        const { title, body } = splitOutput(run.output)
        done.push({ key: `${step.id}#${run.turn}.${run.index}`, step, run, status: run.status, title: title || noOutputLabel(run.status), body })
      }
    }
    done.sort((a, b) => b.run.endedAt - a.run.endedAt)

    const statuses = members.map((m) => statusOf(m.id))
    const doneMembers = statuses.filter((s) => s === 'done').length
    let status = statuses.reduce((best, s) => (statusRank[s] > statusRank[best] ? s : best), 'todo')
    // In a pipeline the members not started yet are still to come. In a team the lead
    // picks who works: members nobody asked do not keep the team "working".
    const pending = teamMode.value ? 0 : statuses.filter((s) => s === 'todo').length
    if (status === 'done' && pending) status = 'working'
    if (!isLive.value && status === 'working') status = view.value.outcome || 'todo'

    const indexes = members.map((m) => m.index)
    const sub = group.single
      ? [deptLabel(members[0].dept), members[0].model].filter(Boolean).join(' · ')
      : t('launch.board.team_sub', { n: members.length, steps: indexes.join(', ') })

    return {
      ...group,
      title: group.single ? members[0].id : group.title,
      sub,
      status,
      active,
      queued,
      done,
      doneMembers,
      progress: Math.round((doneMembers / members.length) * 100)
    }
  })
)

// A run cut short handed nothing over: do not call it "done"
const noOutputLabel = (status) => {
  if (status === 'cancelled') return t('launch.board.no_output_cancelled')
  if (status === 'error') return t('launch.board.no_output_error')
  return t('launch.board.no_output')
}

const visibleDone = (column) =>
  expandedColumns.has(column.key) ? column.done : column.done.slice(0, DONE_PREVIEW)

const toggleOpen = (key) => (opened.has(key) ? opened.delete(key) : opened.add(key))
const toggleExpandedColumn = (key) => (expandedColumns.has(key) ? expandedColumns.delete(key) : expandedColumns.add(key))
const toggleMember = (columnKey, id) => {
  memberFilter[columnKey] = memberFilter[columnKey] === id ? '' : id
}

const stateLabel = (state) => {
  const key = `launch.board.states.${state}`
  return te(key) ? t(key) : state
}

const clockFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const clock = (ms) => (ms ? clockFormat.format(new Date(ms)) : '')

const toolCounts = (tools) => {
  const counts = new Map()
  for (const name of tools) counts.set(name, (counts.get(name) || 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_TOOL_CHIPS)
}
const extraTools = (tools) => Math.max(0, new Set(tools).size - MAX_TOOL_CHIPS)

const setColumnRef = (key, el) => {
  if (el) columnEls.set(key, el)
  else columnEls.delete(key)
}

// Keep the team that is working (or waiting for you) in view, like a live board
const focusColumn = computed(() => {
  const live = columns.value.filter((c) => ['working', 'waiting'].includes(c.status))
  return live.length ? live[live.length - 1].key : ''
})
watch(focusColumn, async (key) => {
  if (!key || !follow.value || !props.visible) return
  await nextTick()
  columnEls.get(key)?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
})

// ---------------------------------------------------------------- horizontal scroll affordance
// Which columns are in view (1-based), and whether there is more board on either side
const scrollState = reactive({ atStart: true, atEnd: true, first: 1, last: 1, total: 0 })
let scrollFrame = 0
const measureScroll = () => {
  scrollFrame = 0
  const el = scrollerEl.value
  if (!el) return
  const cols = [...el.children]
  const left = el.scrollLeft
  const right = left + el.clientWidth
  let first = 0
  let last = 0
  cols.forEach((col, i) => {
    const start = col.offsetLeft // .kb-columns is the offsetParent (position: relative)
    const end = start + col.offsetWidth
    // a column counts as "in view" once most of it shows
    if (Math.min(end, right) - Math.max(start, left) > col.offsetWidth * 0.6) {
      if (!first) first = i + 1
      last = i + 1
    }
  })
  scrollState.total = cols.length
  scrollState.first = first || 1
  scrollState.last = last || first || 1
  scrollState.atStart = left <= 2
  scrollState.atEnd = right >= el.scrollWidth - 2
}
const onColumnsScroll = () => {
  if (!scrollFrame) scrollFrame = requestAnimationFrame(measureScroll)
}
const scrollColumns = (dir) => {
  const el = scrollerEl.value
  if (!el) return
  const col = el.children[0]
  const step = col ? col.offsetWidth + 12 : el.clientWidth * 0.8
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  el.scrollBy({ left: dir * step, behavior: reduce ? 'auto' : 'smooth' })
}
let scrollObserver = null
watch(scrollerEl, (el, old) => {
  if (old) scrollObserver?.unobserve(old)
  if (!el) return
  if (!scrollObserver && typeof ResizeObserver !== 'undefined') scrollObserver = new ResizeObserver(onColumnsScroll)
  scrollObserver?.observe(el)
  onColumnsScroll()
})
watch(() => [columns.value.length, props.visible], () => nextTick(onColumnsScroll))
onBeforeUnmount(() => {
  scrollObserver?.disconnect()
  if (scrollFrame) cancelAnimationFrame(scrollFrame)
})

// Live clock for running durations; idle while hidden or finished
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
.kanban {
  --kb-ok: var(--success);
  --kb-run: var(--accent);
  --kb-wait: var(--warn);
  --kb-err: var(--danger);
  --kb-muted: var(--fg-muted);
  --kb-line: var(--border);
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 14px 16px 12px calc(var(--inset-left, 0px) + 34px);
  color: var(--fg);
  font-family: inherit;
  transition: padding-left 0.25s ease;
}

/* ---------- top bar ---------- */
.kb-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px 18px;
  padding: 2px 2px 12px;
}

.kb-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 680;
  letter-spacing: -0.015em;
}

.kb-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  font-size: 12.5px;
  color: var(--kb-muted);
}

.kb-progress,
.kb-time {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-variant-numeric: tabular-nums;
}

.kb-progress-track {
  width: 110px;
  height: 6px;
  border-radius: 99px;
  background: rgb(var(--ink) / 0.1);
  overflow: hidden;
}

.kb-progress-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--kb-run);
  transform-origin: left center;
  transition: transform 0.25s var(--ease-out);
}

.kb-progress.is-chat svg { flex: none; }

.seg {
  display: inline-flex;
  padding: 3px;
  border-radius: 9px;
  background: rgb(var(--ink) / 0.06);
}

.seg button {
  min-height: 32px;
  padding: 4px 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--kb-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.seg button.active {
  color: var(--fg);
  background: var(--surface-raised);
  box-shadow: inset 0 0 0 1px var(--border);
}

.kb-turns {
  min-height: 36px;
  padding: 4px 8px;
  border: 1px solid rgb(var(--ink) / 0.12);
  border-radius: 8px;
  background: var(--surface);
  color: var(--fg);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.turn-tag {
  padding: 1px 6px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--accent-indigo) 14%, transparent);
  color: var(--accent-indigo);
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
}

.card.is-past { opacity: 0.78; }

.kb-follow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  cursor: pointer;
}

.kb-follow input { width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
.seg button:focus-visible,
.kb-turns:focus-visible,
.kb-follow input:focus-visible,
.member:focus-visible,
.more-btn:focus-visible,
.review-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.meta-end { display: inline-flex; align-items: center; gap: 8px; flex: none; }
.chip svg { vertical-align: -1px; }

.kb-empty { margin: auto; max-width: 42ch; padding: 24px; text-align: center; line-height: 1.5; color: var(--kb-muted); font-size: 14px; }

/* ---------- tones (status pills live in StatusPill) ---------- */
.is-you { --tone: var(--accent-indigo); }
.is-working { --tone: var(--kb-run); }
.is-waiting { --tone: var(--kb-wait); }
.is-done,
.is-completed { --tone: var(--kb-ok); }
.is-error { --tone: var(--kb-err); }
.is-cancelled { --tone: var(--text-muted-6); }
.is-todo,
.is-idle { --tone: var(--kb-muted); }

@keyframes pulse {
  50% { opacity: 0.35; transform: scale(0.8); }
}

/* ---------- columns ---------- */
.kb-board {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* Edge fades say "more board this way"; they never block clicks */
.kb-board::before,
.kb-board::after {
  content: '';
  position: absolute;
  top: 38px; /* below the column range row, which shows whenever a fade does */
  bottom: 10px;
  z-index: 2;
  width: 40px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s var(--ease-out);
}
.kb-board::before { left: 0; background: linear-gradient(to right, var(--kb-fade-bg, var(--bg)), transparent); }
.kb-board::after { right: 0; background: linear-gradient(to left, var(--kb-fade-bg, var(--bg)), transparent); }
.kb-board.fade-start::before,
.kb-board.fade-end::after { opacity: 1; }

.kb-scrollbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  min-height: 36px;
  margin: -4px 0 6px;
  height: 36px;
  font-size: 12px;
  color: var(--kb-muted);
  font-variant-numeric: tabular-nums;
}

.kb-range { margin-right: 6px; }

.kb-nav {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--kb-line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--fg);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), opacity 0.15s var(--ease-out);
}
.kb-nav::before { content: ''; position: absolute; inset: -4px -2px; }
.kb-nav svg { width: 16px; height: 16px; }
.kb-nav:hover:not(:disabled) { background: var(--surface-raised); }
.kb-nav:disabled { opacity: 0.4; cursor: default; }
.kb-nav:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.kb-columns {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 2px 10px;
  scroll-snap-type: x proximity;
  scroll-padding-inline: 2px;
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
}

.col {
  --dept: var(--accent-sky);
  position: relative;
  flex: 0 0 clamp(280px, calc((100% - 36px) / 4), 340px);
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 14px;
  border: 1px solid var(--kb-line);
  background: rgb(var(--ink) / 0.025);
  scroll-snap-align: start;
  overflow: hidden;
  transition: border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
}

.col.is-working {
  border-color: color-mix(in srgb, var(--kb-run) 50%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--kb-run) 22%, transparent),
    0 14px 34px -20px color-mix(in srgb, var(--kb-run) 70%, transparent);
}

.col.is-waiting { border-color: color-mix(in srgb, var(--kb-wait) 60%, transparent); }

/* Department identity: one small dot beside the name (same color as the office room) */
.col-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 7px;
  border-radius: 50%;
  vertical-align: 1px;
  background: var(--dept);
}

.col-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 12px 10px;
}

.col-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--fg);
  background: color-mix(in srgb, var(--dept) 24%, transparent);
  font-variant-numeric: tabular-nums;
}

.col-icon.is-you { color: var(--accent-indigo); background: color-mix(in srgb, var(--accent-indigo) 16%, transparent); }
.col-icon.is-flag { color: var(--kb-ok); background: color-mix(in srgb, var(--kb-ok) 16%, transparent); }

.col-name {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.col-name strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 680;
}

.col-name span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--kb-muted);
}

.col-task .col-head,
.col-final .col-head { border-bottom: 1px solid var(--kb-line); }

/* ---------- members strip ---------- */
.members {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 0 12px 10px;
  border-bottom: 1px solid var(--kb-line);
}

.member {
  position: relative;
  padding: 5px;
  border: 0;
  border-radius: 11px;
  background: transparent;
  cursor: pointer;
}

.member .avatar {
  box-shadow: 0 0 0 2px var(--surface), 0 0 0 3.5px var(--tone, rgb(var(--ink) / 0.15));
  transition: transform 0.15s, opacity 0.2s;
}

.member.is-todo .avatar { opacity: 0.5; --tone: rgb(var(--ink) / 0.15); }
.member:hover .avatar { transform: translateY(-1px); }
.member.active .avatar { box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--dept); }

.member-state {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 2px solid var(--surface);
  background: var(--tone, transparent);
}

.member.is-todo .member-state { display: none; }
.member.is-working .member-state { animation: pulse 1.4s ease-in-out infinite; }

.members-progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  font-size: 12px;
  color: var(--kb-muted);
  font-variant-numeric: tabular-nums;
}

.mini-track {
  width: 44px;
  height: 4px;
  border-radius: 99px;
  background: rgb(var(--ink) / 0.1);
  overflow: hidden;
}

.mini-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--kb-ok);
  transition: width 0.5s ease;
}

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
  background: color-mix(in srgb, var(--dept) 22%, var(--surface));
}

.avatar img { width: 26px; height: 26px; object-fit: contain; image-rendering: pixelated; }
.avatar.sm { width: 22px; height: 22px; border-radius: 7px; font-size: 12px; }
.avatar.sm img { width: 19px; height: 19px; }

/* ---------- body ---------- */
.col-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 2px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-muted);
}

.section-count {
  min-width: 20px;
  padding: 0 6px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 650;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--fg);
  background: rgb(var(--ink) / 0.08);
}

.section-label:first-child { margin-top: 0; }

/* ---------- cards ---------- */
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 11px;
  border: 1px solid var(--kb-line);
  background: var(--surface);
  animation: card-in 0.2s var(--ease-out);
  transition: border-color 0.15s var(--ease-out);
}

.card[tabindex] { cursor: pointer; }
.card[tabindex]:hover { border-color: color-mix(in srgb, var(--dept) 45%, var(--kb-line)); }
.card:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.card.is-working { border-color: color-mix(in srgb, var(--kb-run) 45%, var(--kb-line)); }
.card.is-error { border-color: color-mix(in srgb, var(--kb-err) 50%, var(--kb-line)); }

.card.is-waiting {
  border-color: color-mix(in srgb, var(--kb-wait) 50%, transparent);
  background: color-mix(in srgb, var(--kb-wait) 7%, var(--surface));
}

.card.is-you { border-color: color-mix(in srgb, var(--accent-indigo) 40%, var(--kb-line)); }
.card.is-compact { gap: 4px; padding-top: 8px; padding-bottom: 8px; background: transparent; box-shadow: none; border-style: dashed; }

@keyframes card-in {
  from { opacity: 0; transform: translateY(6px); }
}

.card-meta {
  flex-wrap: wrap;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--kb-muted);
}

.card-meta time { flex: none; font-variant-numeric: tabular-nums; }

.assignee {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.assignee b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 620;
  color: var(--fg);
}

.step-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 650;
  color: var(--fg);
  background: color-mix(in srgb, var(--dept) 20%, transparent);
}

.card-kicker { font-weight: 650; color: var(--tone, var(--fg)); }

.card-title {
  margin: 0;
  font-size: 13px;
  font-weight: 620;
  line-height: 1.4;
  color: var(--fg);
}

.card-ask {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--fg-muted);
  font-style: italic;
}

.card-from {
  margin: 0 0 2px;
  font-size: var(--fs-xs);
  color: var(--kb-muted);
}

.card-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--fg-muted);
  white-space: pre-wrap;
  word-break: break-word;
}

.clamp-2,
.clamp-3,
.clamp-8,
.clamp-10 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.clamp-2 { -webkit-line-clamp: 2; line-clamp: 2; }
.clamp-3 { -webkit-line-clamp: 3; line-clamp: 3; }
.clamp-8 { -webkit-line-clamp: 8; line-clamp: 8; }
.clamp-10 { -webkit-line-clamp: 10; line-clamp: 10; }

.activity {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  font-size: 12px;
  font-weight: 550;
  color: var(--kb-run);
}

.activity.is-wait { color: var(--kb-wait); }

.spinner {
  width: 11px;
  height: 11px;
  flex: none;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, currentColor 25%, transparent);
  border-top-color: currentColor;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.chips { display: flex; flex-wrap: wrap; gap: 5px; }

.chip {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: var(--fs-xs);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--fg-muted);
  background: rgb(var(--ink) / 0.06);
}

.chip b { font-weight: 600; color: var(--kb-muted); }
.chip.is-model { color: var(--accent-indigo); background: color-mix(in srgb, var(--accent-indigo) 12%, transparent); font-family: inherit; }
.chip.is-more { color: var(--kb-muted); }

.card-foot {
  padding-top: 6px;
  border-top: 1px dashed var(--kb-line);
  font-size: 12px;
  color: var(--kb-muted);
}

.more-btn,
.review-btn {
  min-height: 40px;
  padding: 7px 12px;
  border-radius: 9px;
  border: 1px dashed var(--kb-line);
  background: transparent;
  color: var(--kb-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.more-btn:hover { color: var(--fg); border-color: var(--dept); }

.review-btn {
  border-style: solid;
  border-color: transparent;
  color: var(--on-accent);
  background: var(--accent);
}

.review-btn:hover { filter: brightness(1.06); }

.placeholder {
  display: grid;
  place-items: center;
  min-height: 92px;
  padding: 14px;
  border-radius: 11px;
  border: 1px dashed var(--kb-line);
  font-size: 12px;
  line-height: 1.5;
  text-align: center;
  color: var(--kb-muted);
}

@media (prefers-reduced-motion: reduce) {
  .card,
  .member-state,
  .spinner { animation: none; }
  .kb-progress-fill,
  .kb-board::before,
  .kb-board::after,
  .col,
  .card { transition: none; }
}

@media (pointer: coarse) {
  .member { padding: 7px; }
  .seg button,
  .kb-turns,
  .kb-follow { min-height: 44px; }
}

@media (max-width: 640px) {
  .kanban { padding: 48px 10px 10px; }
  .col { flex-basis: min(86vw, 320px); }
}
</style>
