<template>
  <div class="kanban">
    <header class="kb-bar">
      <div class="kb-title">
        <span class="kb-eyebrow">{{ $t('launch.board.title') }}</span>
        <h2>{{ workflowName || $t('launch.board.no_workflow') }}</h2>
      </div>
      <div class="kb-meta">
        <span class="pill" :class="`is-${runTone}`">
          <span class="dot" aria-hidden="true"></span>{{ stateLabel(runTone) }}
        </span>
        <span v-if="steps.length" class="kb-progress" :title="$t('launch.board.progress_hint')">
          <span class="kb-progress-track"><span class="kb-progress-fill" :style="{ width: `${progress}%` }"></span></span>
          <template v-if="teamMode">{{ $t('launch.board.progress_team', { done: teamTasksDone, total: delegatedRuns.length, people: teamPeople }) }}</template>
          <template v-else>{{ $t('launch.board.progress', { done: doneCount, total: steps.length }) }}</template>
        </span>
        <span v-if="tracker.startedAt" class="kb-time">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          {{ formatSpan(elapsed) }}
        </span>
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

    <div v-else ref="scrollerEl" class="kb-columns">
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
          <span class="state-chip" :class="tracker.task ? 'is-done' : 'is-todo'">
            {{ tracker.task ? $t('launch.board.sent') : $t('launch.board.todo') }}
          </span>
        </header>
        <div class="col-body">
          <article v-if="tracker.task" class="card is-you">
            <div class="card-meta">
              <span class="card-kicker">{{ $t('launch.board.task') }}</span>
              <time>{{ clock(tracker.task.at) }}</time>
            </div>
            <p class="card-text clamp-8">{{ tracker.task.text || '—' }}</p>
            <div v-if="tracker.task.attachments.length" class="chips">
              <span v-for="name in tracker.task.attachments" :key="name" class="chip">📎 {{ name }}</span>
            </div>
            <div v-if="tracker.inputs" class="card-foot">{{ $t('launch.board.replies', { n: tracker.inputs }) }}</div>
          </article>
          <div v-else class="placeholder">{{ $t('launch.board.task_placeholder') }}</div>
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
            <strong :title="column.title">{{ column.title }}</strong>
            <span>{{ column.sub }}</span>
          </div>
          <span class="state-chip" :class="`is-${column.status}`">{{ stateLabel(column.status) }}</span>
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
            <p class="section-label">{{ $t('launch.board.section_active') }} · {{ column.active.length }}</p>
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
                <time v-if="task.run">{{ formatSpan(now - task.run.startedAt) }}</time>
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
                <span v-if="task.run.models" class="chip is-model">✦ {{ task.run.models }}</span>
                <span v-for="[name, count] in toolCounts(task.run.tools)" :key="name" class="chip">{{ name }}<b v-if="count > 1"> ×{{ count }}</b></span>
              </div>
            </article>
          </template>

          <!-- Next up: members that have not started yet -->
          <template v-if="column.queued.length">
            <p class="section-label">{{ $t(teamMode && tracker.task ? 'launch.board.section_unassigned' : 'launch.board.section_queued') }} · {{ column.queued.length }}</p>
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
            <p class="section-label">{{ $t('launch.board.section_done') }} · {{ column.done.length }}</p>
            <article
              v-for="task in visibleDone(column)"
              :key="task.key"
              class="card"
              :class="[`is-${task.status}`, { 'is-open': opened.has(task.key) }]"
              tabindex="0"
              :aria-expanded="opened.has(task.key)"
              @click="toggleOpen(task.key)"
              @keydown.enter.prevent="toggleOpen(task.key)"
            >
              <div class="card-meta">
                <span class="assignee">
                  <span class="avatar sm"><img v-if="task.step.sprite" :src="task.step.sprite" alt="" /><span v-else>{{ initialsOf(task.step.id) }}</span></span>
                  <b :title="task.step.id">{{ task.step.id }}</b>
                  <span class="step-tag">B{{ task.step.index }}<template v-if="task.run.index > 1"> · {{ $t('launch.board.run', { n: task.run.index }) }}</template></span>
                </span>
                <time :title="clock(task.run.endedAt)">{{ formatSpan(task.run.endedAt - task.run.startedAt) }}</time>
              </div>
              <p v-if="task.run.delegatedBy" class="card-from">{{ $t('launch.board.assigned_by', { lead: task.run.delegatedBy }) }}</p>
              <p v-if="task.run.task" class="card-ask clamp-2" :title="task.run.task">{{ $t('launch.board.asked', { task: task.run.task }) }}</p>
              <p class="card-title">{{ task.title }}</p>
              <p v-if="task.body" class="card-text" :class="opened.has(task.key) ? '' : 'clamp-3'">{{ task.body }}</p>
              <div v-if="task.run.tools.length || task.run.models" class="chips">
                <span v-if="task.run.models" class="chip is-model">✦ {{ task.run.models }}</span>
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
      <section class="col col-final" :class="`is-${tracker.outcome || 'todo'}`">
        <header class="col-head">
          <span class="col-icon is-flag" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21V4h11l-1.5 4L16 12H5" /></svg>
          </span>
          <div class="col-name">
            <strong>{{ $t('launch.board.result') }}</strong>
            <span>{{ $t('launch.board.result_sub') }}</span>
          </div>
          <span class="state-chip" :class="`is-${outcomeTone}`">{{ stateLabel(outcomeTone) }}</span>
        </header>
        <div class="col-body">
          <article v-if="tracker.outcome" class="card" :class="`is-${tracker.outcome}`">
            <div class="card-meta">
              <span class="card-kicker">{{ stateLabel(tracker.outcome) }}</span>
              <time>{{ clock(tracker.endedAt) }}</time>
            </div>
            <p v-if="tracker.summary || tracker.error" class="card-text clamp-10">{{ tracker.summary || tracker.error }}</p>
            <div class="card-foot">
              {{ $t('launch.board.total_time', { time: formatSpan(elapsed) }) }}
              <template v-if="totalTokens"> · {{ $t('launch.board.tokens', { n: totalTokens.toLocaleString() }) }}</template>
            </div>
            <button v-if="tracker.outcome === 'completed'" type="button" class="review-btn" @click.stop="$emit('review')">
              {{ $t('launch.board.go_review') }}
            </button>
          </article>
          <div v-else class="placeholder">{{ $t('launch.board.result_placeholder') }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatSpan, stepStatus, usageTotals } from '@/utils/runTracker.js'
import { buildSteps, initialsOf } from '@/utils/workflowSteps.js'
import { computeTeamLinks } from '@/utils/teamLinks.js'

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
const nodeOf = (id) => props.tracker.nodes[id]
const statusOf = (id) => stepStatus(nodeOf(id))
const doneCount = computed(() => steps.value.filter((s) => statusOf(s.id) === 'done').length)

// A team workflow (a lead delegates to members) does not run every step: the lead picks who
// works. Progress is then counted in tasks handed over, and members nobody asked are
// "not assigned" rather than "next up".
const teamMode = computed(() => computeTeamLinks(props.graph?.nodes, props.graph?.edges).length > 0)
const delegatedRuns = computed(() =>
  Object.values(props.tracker.nodes).flatMap((node) => node.runs.filter((run) => run.delegatedBy))
)
const teamTasksDone = computed(() => delegatedRuns.value.filter((run) => run.endedAt).length)
const teamPeople = computed(() =>
  Object.entries(props.tracker.nodes).filter(([, node]) => node.runs.length).length
)
const progress = computed(() => {
  if (teamMode.value) {
    const total = delegatedRuns.value.length
    return total ? Math.round((teamTasksDone.value / total) * 100) : props.tracker.outcome ? 100 : 0
  }
  return steps.value.length ? Math.round((doneCount.value / steps.value.length) * 100) : 0
})

const isLive = computed(() => props.status === 'Running...' || props.status === 'Waiting for input...')
const elapsed = computed(() =>
  props.tracker.startedAt ? (props.tracker.endedAt || now.value) - props.tracker.startedAt : 0
)
const runTone = computed(() => {
  if (props.status === 'Waiting for input...') return 'waiting'
  if (isLive.value) return 'working'
  return props.tracker.outcome || 'idle'
})
const outcomeTone = computed(() => props.tracker.outcome || (isLive.value ? 'working' : 'todo'))

const totalTokens = computed(() => usageTotals(props.tracker.tokenUsage).tokens)

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
        done.push({ key: `${step.id}#${run.index}`, step, run, status: run.status, title: title || t('launch.board.no_output'), body })
      }
    }
    done.sort((a, b) => b.run.endedAt - a.run.endedAt)

    const statuses = members.map((m) => statusOf(m.id))
    const doneMembers = statuses.filter((s) => s === 'done').length
    let status = statuses.reduce((best, s) => (statusRank[s] > statusRank[best] ? s : best), 'todo')
    if (status === 'done' && doneMembers < members.length) status = 'working'
    if (!isLive.value && status === 'working') status = props.tracker.outcome || 'todo'

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
  --kb-ok: #22c55e;
  --kb-run: var(--accent-sky);
  --kb-wait: #f59e0b;
  --kb-err: var(--danger);
  --kb-muted: var(--text-muted-4);
  --kb-line: rgb(var(--ink) / 0.09);
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 14px 16px 12px calc(var(--inset-left, 0px) + 34px);
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
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

.kb-eyebrow {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--kb-muted);
}

.kb-title h2 {
  margin: 2px 0 0;
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
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky));
  transition: width 0.5s ease;
}

.seg {
  display: inline-flex;
  padding: 3px;
  border-radius: 9px;
  background: rgb(var(--ink) / 0.06);
}

.seg button {
  padding: 4px 11px;
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
  color: var(--text-1);
  background: var(--surface-1);
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
}

.kb-follow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.kb-follow input { margin: 0; accent-color: var(--accent-sky); }

.kb-empty { margin: auto; color: var(--kb-muted); font-size: 14px; }

/* ---------- pills ---------- */
.pill,
.state-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 11.5px;
  font-weight: 650;
  white-space: nowrap;
  color: var(--tone, var(--kb-muted));
  background: color-mix(in srgb, var(--tone, var(--kb-muted)) 14%, transparent);
}

.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

.is-working { --tone: var(--kb-run); }
.is-waiting { --tone: var(--kb-wait); }
.is-done,
.is-completed { --tone: var(--kb-ok); }
.is-error { --tone: var(--kb-err); }
.is-cancelled { --tone: var(--text-muted-6); }
.is-todo,
.is-idle { --tone: var(--kb-muted); }

.pill.is-working .dot,
.pill.is-waiting .dot { animation: pulse 1.4s ease-in-out infinite; }

@keyframes pulse {
  50% { opacity: 0.35; transform: scale(0.8); }
}

/* ---------- columns ---------- */
.kb-columns {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 2px 10px;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
}

.col {
  --dept: var(--accent-sky);
  position: relative;
  flex: 0 0 300px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 14px;
  border: 1px solid var(--kb-line);
  background: rgb(var(--ink) / 0.025);
  scroll-snap-align: start;
  overflow: hidden;
  transition: border-color 0.25s, box-shadow 0.25s;
}

.col::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: var(--dept);
  opacity: 0.6;
}

.col.is-working {
  border-color: color-mix(in srgb, var(--kb-run) 50%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--kb-run) 22%, transparent),
    0 14px 34px -20px color-mix(in srgb, var(--kb-run) 70%, transparent);
}

.col.is-working::before {
  opacity: 1;
  background: linear-gradient(90deg, transparent, var(--kb-run), transparent);
  background-size: 200% 100%;
  animation: sweep 1.6s linear infinite;
}

.col.is-waiting { border-color: color-mix(in srgb, var(--kb-wait) 60%, transparent); }

@keyframes sweep {
  from { background-position: 200% 0; }
  to { background-position: 0 0; }
}

.col-task::before { background: var(--accent-indigo); }
.col-final::before { background: var(--kb-ok); }
.col-final.is-error::before { background: var(--kb-err); }

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
  color: var(--dept);
  background: color-mix(in srgb, var(--dept) 15%, transparent);
  font-variant-numeric: tabular-nums;
}

.col-icon.is-you { color: var(--accent-indigo); background: color-mix(in srgb, var(--accent-indigo) 15%, transparent); }
.col-icon.is-flag { color: var(--kb-ok); background: color-mix(in srgb, var(--kb-ok) 15%, transparent); }

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
  font-size: 11.5px;
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
  padding: 0;
  border: 0;
  border-radius: 11px;
  background: transparent;
  cursor: pointer;
}

.member .avatar {
  box-shadow: 0 0 0 2px var(--surface-1), 0 0 0 3.5px var(--tone, rgb(var(--ink) / 0.15));
  transition: transform 0.15s, opacity 0.2s;
}

.member.is-todo .avatar { opacity: 0.5; --tone: rgb(var(--ink) / 0.15); }
.member:hover .avatar { transform: translateY(-1px); }
.member.active .avatar { box-shadow: 0 0 0 2px var(--surface-1), 0 0 0 4px var(--dept); }

.member-state {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 2px solid var(--surface-1);
  background: var(--tone, transparent);
}

.member.is-todo .member-state { display: none; }
.member.is-working .member-state { animation: pulse 1.4s ease-in-out infinite; }

.members-progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  font-size: 11.5px;
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
  font-size: 11px;
  font-weight: 700;
  color: var(--dept);
  background: color-mix(in srgb, var(--dept) 14%, var(--surface-1));
}

.avatar img { width: 26px; height: 26px; object-fit: contain; image-rendering: pixelated; }
.avatar.sm { width: 22px; height: 22px; border-radius: 7px; font-size: 9.5px; }
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
  margin: 4px 2px 0;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--kb-muted);
}

.section-label:first-child { margin-top: 0; }

/* ---------- cards ---------- */
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 11px 10px 13px;
  border-radius: 11px;
  border: 1px solid var(--kb-line);
  background: var(--surface-1);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.06);
  animation: card-in 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
  outline: none;
}

.card[tabindex] { cursor: pointer; }
.card[tabindex]:hover { border-color: color-mix(in srgb, var(--dept) 45%, var(--kb-line)); }
.card:focus-visible { box-shadow: 0 0 0 2px var(--accent-sky); }

.card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--tone, var(--kb-line));
}

.card.is-working { border-color: color-mix(in srgb, var(--kb-run) 40%, var(--kb-line)); }

.card.is-waiting {
  border-color: color-mix(in srgb, var(--kb-wait) 50%, transparent);
  background: color-mix(in srgb, var(--kb-wait) 7%, var(--surface-1));
}

.card.is-you::before { background: var(--accent-indigo); }
.card.is-compact { gap: 4px; padding-top: 8px; padding-bottom: 8px; background: transparent; box-shadow: none; border-style: dashed; }

@keyframes card-in {
  from { opacity: 0; transform: translateY(6px); }
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11.5px;
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
  color: var(--text-1);
}

.step-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 10.5px;
  font-weight: 650;
  color: var(--dept);
  background: color-mix(in srgb, var(--dept) 12%, transparent);
}

.card-kicker { font-weight: 650; color: var(--tone, var(--text-1)); }

.card-title {
  margin: 0;
  font-size: 13px;
  font-weight: 620;
  line-height: 1.4;
  color: var(--text-1);
}

.card-ask {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted-7);
  font-style: italic;
}

.card-from {
  margin: 0 0 2px;
  font-size: 11px;
  color: var(--kb-muted);
}

.card-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-soft-1, var(--text-1));
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
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--text-soft-1, var(--text-1));
  background: rgb(var(--ink) / 0.06);
}

.chip b { font-weight: 600; color: var(--kb-muted); }
.chip.is-model { color: var(--accent-indigo); background: color-mix(in srgb, var(--accent-indigo) 12%, transparent); font-family: inherit; }
.chip.is-more { color: var(--kb-muted); }

.card-foot {
  padding-top: 6px;
  border-top: 1px dashed var(--kb-line);
  font-size: 11.5px;
  color: var(--kb-muted);
}

.more-btn,
.review-btn {
  padding: 7px 10px;
  border-radius: 9px;
  border: 1px dashed var(--kb-line);
  background: transparent;
  color: var(--kb-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.more-btn:hover { color: var(--text-1); border-color: var(--dept); }

.review-btn {
  border-style: solid;
  border-color: transparent;
  color: #0b1220;
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky));
}

:root[data-theme='light'] .review-btn { color: #fff; }
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
  .col.is-working::before,
  .pill .dot,
  .member-state,
  .spinner { animation: none; }
}

@media (max-width: 640px) {
  .kanban { padding: 10px; }
  .col { flex-basis: 86vw; }
}
</style>
