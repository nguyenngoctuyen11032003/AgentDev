<template>
  <aside class="session-sidebar" :class="{ collapsed }" :aria-label="t('launch.sessions.title')">
    <template v-if="!collapsed">
      <div class="sidebar-head">
        <h2 class="sidebar-title">{{ t('launch.sessions.title') }}</h2>
        <span class="sidebar-count" :title="t('launch.sessions.count', { n: sessions.length })" :aria-label="t('launch.sessions.count', { n: sessions.length })">{{ sessions.length }}</span>
      </div>

      <!-- Runs keep going while you work elsewhere: show what needs attention; each chip filters the list -->
      <div v-if="liveCounts.running || liveCounts.waiting" class="sidebar-live" role="group" :aria-label="t('launch.sessions.live_filter')">
        <button
          v-if="liveCounts.waiting"
          type="button"
          class="live-chip is-waiting"
          :class="{ on: activeFilter === 'waiting' }"
          :aria-pressed="activeFilter === 'waiting'"
          :title="activeFilter === 'waiting' ? t('launch.sessions.filter_clear') : t('launch.sessions.filter_waiting')"
          @click="toggleFilter('waiting')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          {{ t('launch.sessions.live_waiting', { n: liveCounts.waiting }) }}
          <svg v-if="activeFilter === 'waiting'" class="chip-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" /></svg>
        </button>
        <button
          v-if="liveCounts.running"
          type="button"
          class="live-chip is-running"
          :class="{ on: activeFilter === 'running' }"
          :aria-pressed="activeFilter === 'running'"
          :title="activeFilter === 'running' ? t('launch.sessions.filter_clear') : t('launch.sessions.filter_running')"
          @click="toggleFilter('running')"
        >
          <svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.55" /></svg>
          {{ t('launch.sessions.live_running', { n: liveCounts.running }) }}
          <svg v-if="activeFilter === 'running'" class="chip-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" /></svg>
        </button>
      </div>

      <div class="sidebar-search">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input
          ref="searchInputRef"
          v-model="query"
          type="text"
          autocomplete="off"
          :aria-label="t('launch.sessions.search')"
          :placeholder="t('launch.sessions.search')"
          @keydown.esc="query = ''"
        />
        <button
          v-if="query"
          type="button"
          class="search-clear"
          :title="t('launch.sessions.search_clear')"
          :aria-label="t('launch.sessions.search_clear')"
          @click="query = ''"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>

      <div class="sidebar-list">
        <!-- The session being prepared in this tab, before it is launched -->
        <button
          v-if="draft"
          type="button"
          class="session-item draft active"
          aria-current="true"
          :title="`${draftProject ? draftProject + ' · ' : ''}${workflowLabel(draft)}`"
          @click="emit('select', null)"
        >
          <span class="session-body">
            <span class="session-name">{{ t('launch.sessions.untitled') }}</span>
            <span class="session-sub">
              <StatusPill compact tone="idle" :label="t('launch.sessions.draft')" />
              <span class="session-flow">{{ draftProject || workflowLabel(draft) }}</span>
            </span>
          </span>
        </button>

        <section v-for="group in groups" :key="group.key" class="session-group">
          <div class="group-head" @contextmenu.prevent="openMenu($event, 'group', group)">
            <button type="button" class="group-toggle" :aria-expanded="isGroupOpen(group)" :title="groupTitle(group)" @click="toggleGroup(group.key)">
              <svg class="group-chevron" :class="{ closed: !isGroupOpen(group) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
              <svg v-if="group.isProject" class="group-folder" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
              <span class="group-text">
                <span class="group-name">{{ group.label }}</span>
                <span v-if="group.isProject && group.workflow" class="group-flow">{{ workflowLabel(group.workflow) }}</span>
              </span>
              <span class="group-meta">
                <span v-if="group.waiting" class="group-live waiting" :title="t('launch.sessions.live_waiting', { n: group.waiting })" :aria-label="t('launch.sessions.live_waiting', { n: group.waiting })">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>{{ group.waiting }}
                </span>
                <span v-if="group.running" class="group-live running" :title="t('launch.sessions.live_running', { n: group.running })" :aria-label="t('launch.sessions.live_running', { n: group.running })">
                  <svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.55" /></svg>{{ group.running }}
                </span>
                <span class="group-count" :title="t('launch.sessions.count', { n: group.items.length })">{{ t('launch.sessions.count', { n: group.items.length }) }}</span>
              </span>
            </button>
            <button
              type="button"
              class="icon-btn group-new"
              :title="newInLabel(group)"
              :aria-label="newInLabel(group)"
              @click="emit('new', group)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            </button>
          </div>

          <div v-show="isGroupOpen(group)" class="group-items">
            <div
              v-for="item in group.items"
              :key="item.session_id"
              class="session-item"
              :class="{ active: item.session_id === activeId }"
              role="button"
              tabindex="0"
              :title="itemTitle(item, group)"
              :aria-current="item.session_id === activeId ? 'true' : undefined"
              @click="emit('select', item)"
              @keydown.enter.prevent="emit('select', item)"
              @keydown.space.prevent="emit('select', item)"
              @contextmenu.prevent="openMenu($event, 'item', item)"
            >
              <span class="session-body">
                <input
                  v-if="editingId === item.session_id"
                  ref="renameInputRef"
                  v-model="editingTitle"
                  class="session-rename"
                  :aria-label="t('launch.sessions.rename')"
                  maxlength="120"
                  @click.stop
                  @keydown.enter.prevent="commitRename(item)"
                  @keydown.esc.prevent="editingId = null"
                  @blur="commitRename(item)"
                />
                <span v-else class="session-name">{{ item.title || t('launch.sessions.untitled') }}</span>
                <span class="session-sub">
                  <StatusPill compact :tone="statusTone(item.status)" :label="statusLabel(item.status)" />
                  <span v-if="waitsOnPlan(item)" class="plan-badge" :title="t('launch.plan.status')">{{ t('launch.sessions.awaiting_plan') }}</span>
                  <span v-else-if="item.resumable && !['completed', 'running', 'waiting_for_input', 'cancelling'].includes(item.status)" class="plan-badge" :title="interruptTitle(item)">{{ stoppedByYou(item) ? t('launch.sessions.stopped') : t('launch.sessions.interrupted') }}</span>
                  <time v-if="item.updated_at" class="session-time">{{ timeAgo(item.updated_at) }}</time>
                </span>
              </span>
              <span class="session-actions" @click.stop>
                <button type="button" class="icon-btn" :title="t('launch.sessions.rename')" :aria-label="t('launch.sessions.rename')" @click="startRename(item)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
                </button>
                <button type="button" class="icon-btn danger" :title="t('launch.sessions.delete')" :aria-label="t('launch.sessions.delete')" @click="emit('delete', item)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
                </button>
              </span>
            </div>
          </div>
        </section>

        <div v-if="!sessions.length && loading" class="sidebar-skeleton" role="status" :aria-label="t('launch.sessions.loading')">
          <div v-for="n in 4" :key="n" class="skeleton-row">
            <BaseSkeleton width="72%" height="13px" radius="4px" />
            <BaseSkeleton width="46%" height="18px" radius="99px" />
          </div>
        </div>
        <div v-else-if="!sessions.length && loadError" class="sidebar-empty is-error" role="alert">
          <p>{{ t('launch.sessions.load_error') }}</p>
          <button type="button" class="empty-action" @click="emit('retry')">{{ t('common.retry') }}</button>
        </div>
        <div v-else-if="!sessions.length && !draft" class="sidebar-empty is-first">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /><path d="M8 9h8M8 13h5" /></svg>
          <p class="empty-title">{{ t('launch.sessions.empty_title') }}</p>
          <p>{{ t('launch.sessions.empty') }}</p>
          <button type="button" class="empty-action" @click="emit('add-project')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg>
            {{ t('launch.sessions.add_project') }}
          </button>
        </div>
        <div v-else-if="(query || activeFilter) && !groups.length" class="sidebar-empty is-search" role="status">
          <p>{{ t('launch.sessions.no_results') }}</p>
          <button type="button" class="empty-action" @click="query = ''; liveFilter = null">{{ t('launch.sessions.filter_reset') }}</button>
        </div>
      </div>
    </template>

    <!-- Collapsed rail: icon-only shortcuts -->
    <template v-else>
      <nav class="sidebar-rail" :aria-label="t('launch.sessions.title')">
        <button type="button" class="rail-btn" :title="t('launch.sessions.expand')" :aria-label="t('launch.sessions.expand')" :aria-expanded="false" @click="emit('toggle')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /><path d="m13 10 2 2-2 2" /></svg>
          <span v-if="liveCounts.running || liveCounts.waiting" class="rail-dot" :class="{ waiting: liveCounts.waiting }" aria-hidden="true"></span>
        </button>
        <button type="button" class="rail-btn" :title="t('launch.sessions.search')" :aria-label="t('launch.sessions.search')" @click="openSearch">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        </button>
        <button type="button" class="rail-btn" :title="t('launch.sessions.add_project_hint')" :aria-label="t('launch.sessions.add_project')" @click="emit('add-project')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg>
        </button>
        <span v-if="liveCounts.running || liveCounts.waiting" class="rail-live" role="status" :title="[liveCounts.waiting && t('launch.sessions.live_waiting', { n: liveCounts.waiting }), liveCounts.running && t('launch.sessions.live_running', { n: liveCounts.running })].filter(Boolean).join(' · ')">
          <svg v-if="liveCounts.running" class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.55" /></svg>
          <span class="rail-live-n">{{ liveCounts.running + liveCounts.waiting }}</span>
        </span>
      </nav>
    </template>

    <Teleport to="body">
      <div
        v-if="menu"
        ref="menuRef"
        class="session-menu"
        role="menu"
        :style="{ left: `${menu.x}px`, top: `${menu.y}px` }"
        @contextmenu.prevent
      >
        <template v-if="menu.kind === 'item'">
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => emit('select', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>
            {{ t('launch.sessions.menu.open') }}
          </button>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => startRename(target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
            {{ t('launch.sessions.rename') }}
          </button>
          <div class="menu-sep"></div>
          <button type="button" class="menu-item danger" role="menuitem" @click="runMenu((target) => emit('delete', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
            {{ t('launch.sessions.delete') }}
          </button>
        </template>
        <template v-else>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => emit('new', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            {{ newInLabel(menu.target) }}
          </button>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => toggleGroup(target.key))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            {{ isGroupClosed(menu.target.key) ? t('launch.sessions.menu.expand') : t('launch.sessions.menu.collapse') }}
          </button>
          <div class="menu-sep"></div>
          <button type="button" class="menu-item danger" role="menuitem" @click="runMenu((target) => emit('delete-group', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
            {{ menu.target.isProject ? t('launch.sessions.menu.delete_project') : t('launch.sessions.menu.delete_group') }}
          </button>
        </template>
      </div>
    </Teleport>

    <div v-if="!collapsed" class="sidebar-foot">
      <button
        v-if="!collapsed"
        type="button"
        class="foot-new"
        :title="t('launch.sessions.add_project_hint')"
        @click="emit('add-project')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg>
        {{ t('launch.sessions.add_project') }}
      </button>
      <button
        type="button"
        class="icon-btn foot-toggle"
        :title="collapsed ? t('launch.sessions.expand') : t('launch.sessions.collapse')"
        :aria-label="collapsed ? t('launch.sessions.expand') : t('launch.sessions.collapse')"
        :aria-expanded="!collapsed"
        @click="emit('toggle')"
      >
        <svg :class="{ flipped: collapsed }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m11 17-5-5 5-5" /><path d="m18 17-5-5 5-5" /></svg>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseSkeleton from '@/components/ui/BaseSkeleton.vue'
import StatusPill from './StatusPill.vue'
import { isRestartInterruption } from './runStatus.js'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  // Workflow file of a session that is open in this tab but not launched yet
  draft: { type: String, default: '' },
  // Project the draft belongs to (shown on the draft row)
  draftProject: { type: String, default: '' },
  // Workflow each project uses for its next session: { [projectName]: yamlFile }
  projectWorkflows: { type: Object, default: () => ({}) },
  collapsed: { type: Boolean, default: false },
  // The list has not arrived yet: say so instead of "no sessions"
  loading: { type: Boolean, default: false },
  // The last load failed: say so (with a retry) instead of "no sessions yet"
  loadError: { type: Boolean, default: false }
})

const emit = defineEmits(['select', 'new', 'add-project', 'rename', 'delete', 'delete-group', 'toggle', 'retry'])

const { t, te } = useI18n()

const query = ref('')
const editingId = ref(null)
const editingTitle = ref('')
const renameInputRef = ref(null)

const CLOSED_GROUPS_KEY = 'agentdev.sessions.closedGroups'
const readClosedGroups = () => {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLOSED_GROUPS_KEY) || '[]'))
  } catch {
    return new Set()
  }
}
const closedGroups = ref(readClosedGroups())
const isGroupClosed = (key) => closedGroups.value.has(key)
// The group holding the open session always shows it, even if the user collapsed it
const isGroupOpen = (group) => !isGroupClosed(group.key) || group.hasActive
const toggleGroup = (key) => {
  const next = new Set(closedGroups.value)
  next.has(key) ? next.delete(key) : next.add(key)
  closedGroups.value = next
  try {
    localStorage.setItem(CLOSED_GROUPS_KEY, JSON.stringify([...next]))
  } catch {
    // per-browser convenience only
  }
}

const workflowLabel = (file) => (file || '').replace(/\.ya?ml$/i, '') || '—'

const statusLabel = (status) => {
  const key = `launch.sessions.status.${status}`
  return te(key) ? t(key) : status || ''
}

const STATUS_TONE = {
  running: 'working',
  cancelling: 'working',
  waiting_for_input: 'waiting',
  completed: 'done',
  error: 'error',
  cancelled: 'cancelled',
  idle: 'idle'
}
const statusTone = (status) => STATUS_TONE[status] || 'idle'

// Tooltip: the full title and the workflow a narrow row cannot show
// The server stores its reason in English ("Workflow execution cancelled", "Interrupted by a server restart"):
// say it in the UI language, and call a stop the user asked for a stop, not an interruption
const USER_STOP_RE = /cancel|stopped by the user|user requested/i
const stoppedByYou = (item) => USER_STOP_RE.test(String(item.interrupt_reason || ''))
const interruptTitle = (item) => {
  const reason = String(item.interrupt_reason || '')
  if (stoppedByYou(item)) return t('launch.sessions.stopped_hint')
  if (isRestartInterruption(reason)) return t('launch.sessions.interrupted_restart')
  return t('launch.resume.banner')
}

const itemTitle = (item, group) =>
  [item.title || t('launch.sessions.untitled'), group.isProject ? workflowLabel(item.yaml_file) : '', statusLabel(item.status)]
    .filter(Boolean)
    .join('\n')

// A stopped or failed run no longer waits on its plan (older saved sessions still say so)
const waitsOnPlan = (item) => Boolean(item.awaiting_plan) && !['cancelled', 'error'].includes(item.status)

const projectName = (item) => (item.projects?.[0]?.name || '').replace(/\/+$/, '')

const liveCounts = computed(() => {
  let running = 0
  let waiting = 0
  for (const item of props.sessions) {
    if (item.status === 'running' || item.status === 'cancelling') running += 1
    else if (item.status === 'waiting_for_input') waiting += 1
  }
  return { running, waiting }
})

// Live chips double as filters; a filter whose sessions all finished turns itself off
const liveFilter = ref(null)
const activeFilter = computed(() => (liveFilter.value && liveCounts.value[liveFilter.value] ? liveFilter.value : null))
const toggleFilter = (kind) => {
  liveFilter.value = activeFilter.value === kind ? null : kind
}
const matchesFilter = (item) => {
  if (activeFilter.value === 'running') return item.status === 'running' || item.status === 'cancelling'
  if (activeFilter.value === 'waiting') return item.status === 'waiting_for_input'
  return true
}

// Rail search: expand the sidebar, then focus the search box
const searchInputRef = ref(null)
const pendingSearch = ref(false)
const openSearch = () => {
  pendingSearch.value = true
  emit('toggle')
}
watch(
  () => props.collapsed,
  async (collapsed) => {
    if (collapsed || !pendingSearch.value) return
    pendingSearch.value = false
    await nextTick()
    searchInputRef.value?.focus()
  }
)

const newInLabel = (group) =>
  group.isProject
    ? t('launch.sessions.new_in_project', { name: group.label, workflow: workflowLabel(group.workflow) })
    : t('launch.sessions.new_in', { name: group.label })

const groupTitle = (group) =>
  group.isProject ? `${group.label} · ${t('launch.sessions.project_workflow', { workflow: workflowLabel(group.workflow) })}` : group.label

// Sessions with a project folder are grouped by project, the others by workflow.
// Groups keep the order of their most recently updated session.
const groups = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const byKey = new Map()
  for (const item of props.sessions) {
    const project = projectName(item)
    if (!matchesFilter(item)) continue
    if (
      needle &&
      ![item.title, item.yaml_file, project].some((text) => (text || '').toLowerCase().includes(needle))
    ) {
      continue
    }
    const key = project ? `project:${project}` : `workflow:${item.yaml_file || ''}`
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        isProject: Boolean(project),
        label: project || workflowLabel(item.yaml_file),
        // A project runs the workflow chosen for it, else the one of its latest session
        workflow: (project && props.projectWorkflows[project]) || item.yaml_file || '',
        items: [],
        running: 0,
        waiting: 0,
        hasActive: false
      })
    }
    const group = byKey.get(key)
    group.items.push(item)
    if (item.status === 'running' || item.status === 'cancelling') group.running += 1
    else if (item.status === 'waiting_for_input') group.waiting += 1
    if (item.session_id === props.activeId) group.hasActive = true
  }
  return [...byKey.values()]
})

// ---------------------------------------------------------------- right-click menu
const menu = ref(null)
const menuRef = ref(null)
const MENU_WIDTH = 210
const MENU_HEIGHT = 160

const openMenu = (event, kind, target) => {
  // Keep the menu inside the window
  const x = Math.min(event.clientX, window.innerWidth - MENU_WIDTH - 8)
  const y = Math.min(event.clientY, window.innerHeight - MENU_HEIGHT - 8)
  menu.value = { kind, target, x: Math.max(8, x), y: Math.max(8, y) }
}
const closeMenu = () => {
  menu.value = null
}
// Read the target before closing: the menu state is cleared by closeMenu
const runMenu = (action) => {
  const target = menu.value?.target
  closeMenu()
  action(target)
}
const onPointerDown = (event) => {
  if (menu.value && !menuRef.value?.contains(event.target)) closeMenu()
}
const onKeydown = (event) => {
  if (event.key === 'Escape') closeMenu()
}
onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('blur', closeMenu)
  window.addEventListener('resize', closeMenu)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown, true)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('blur', closeMenu)
  window.removeEventListener('resize', closeMenu)
})

// Relative times refresh once a minute
const nowSec = ref(Date.now() / 1000)
const clock = setInterval(() => {
  nowSec.value = Date.now() / 1000
}, 60_000)
onBeforeUnmount(() => clearInterval(clock))

const timeAgo = (seconds) => {
  if (!seconds) return ''
  const diff = Math.max(0, nowSec.value - seconds)
  if (diff < 60) return t('launch.sessions.ago.now')
  if (diff < 3600) return t('launch.sessions.ago.minutes', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('launch.sessions.ago.hours', { n: Math.floor(diff / 3600) })
  return t('launch.sessions.ago.days', { n: Math.floor(diff / 86400) })
}

const startRename = async (item) => {
  editingId.value = item.session_id
  editingTitle.value = item.title || ''
  await nextTick()
  const input = Array.isArray(renameInputRef.value) ? renameInputRef.value[0] : renameInputRef.value
  input?.focus()
  input?.select()
}

const commitRename = (item) => {
  if (editingId.value !== item.session_id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  if (title && title !== item.title) {
    emit('rename', item, title)
  }
}
</script>

<style scoped>
.session-sidebar {
  flex: 0 0 260px;
  width: 260px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--fg-muted);
  font-size: 13px;
  overflow: hidden;
  transition: flex-basis 0.25s var(--ease-out), width 0.25s var(--ease-out);
}

.session-sidebar *,
.session-sidebar *::before {
  box-sizing: border-box;
}

.session-sidebar.collapsed {
  flex-basis: 52px;
  width: 52px;
}

.sidebar-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 14px 14px 8px;
}

.sidebar-title {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.3;
  color: var(--fg);
}

.group-count {
  flex: none;
  font-size: var(--fs-xs);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--fg-subtle);
  white-space: nowrap;
}

.sidebar-count {
  min-width: 22px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 650;
  line-height: 20px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--fg);
  background: rgb(var(--ink) / 0.1);
}

/* ---------- search ---------- */
.sidebar-search {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 40px;
  margin: 0 10px 8px;
  padding: 0 4px 0 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg);
}

.sidebar-search:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.search-icon { width: 14px; height: 14px; flex: none; color: var(--fg-subtle); }

/* The input itself has no outline: the wrapper shows the focus ring instead */
.sidebar-search:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.sidebar-search input {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--fg);
  font: inherit;
}

.sidebar-search input::placeholder { color: var(--fg-subtle); }

.search-clear {
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
}
.search-clear svg { width: 13px; height: 13px; }
.search-clear:hover { background: rgb(var(--ink) / 0.1); color: var(--fg); }
.search-clear:focus-visible,
.empty-action:focus-visible,
.group-toggle:focus-visible,
.session-item:focus-visible,
.icon-btn:focus-visible,
.foot-new:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

/* ---------- live summary ---------- */
.sidebar-live {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 12px 8px;
}

.live-chip {
  --tone: var(--fg-muted);
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 2px 10px 2px 8px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--tone) 32%, transparent);
  background: color-mix(in srgb, var(--tone) 12%, transparent);
  color: var(--tone-ink, var(--tone));
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 650;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}
.live-chip::before { content: ''; position: absolute; inset: -6px -2px; }
.live-chip svg { width: 13px; height: 13px; flex: none; }
.live-chip .chip-x { width: 11px; height: 11px; margin-left: 1px; }
.live-chip:hover { background: color-mix(in srgb, var(--tone) 20%, transparent); }
.live-chip.on {
  border-color: var(--tone);
  background: color-mix(in srgb, var(--tone) 22%, transparent);
}
.live-chip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.live-chip.is-waiting { --tone: var(--warn); }
.live-chip.is-running { --tone: var(--accent); }
:root[data-theme='light'] .live-chip { --tone-ink: color-mix(in srgb, var(--tone) 80%, #000); }

.spin { animation: sb-spin 1.1s linear infinite; }
@keyframes sb-spin { to { transform: rotate(360deg); } }

/* ---------- list ---------- */
.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px 6px 8px;
  scrollbar-width: thin;
}

.session-group + .session-group { margin-top: 6px; }

.group-head {
  display: flex;
  align-items: center;
}

.group-toggle {
  flex: 1;
  min-width: 0;
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  text-align: left;
}

.group-toggle:hover { color: var(--fg); }

.group-chevron { width: 13px; height: 13px; flex: none; transition: transform 0.2s var(--ease-out); }
.group-chevron.closed { transform: rotate(-90deg); }

.group-folder { width: 15px; height: 15px; flex: none; color: var(--fg-subtle); }

/* Project name on line 1, the workflow it runs on line 2: both can ellipsize on their own */
.group-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.group-name,
.group-flow {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-flow {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--fg-subtle);
}

.group-meta { margin-left: auto; flex: none; display: inline-flex; align-items: center; gap: 4px; }

/* Live counts read as icon + number (spinner = running, clock = waiting for you), never a bare badge */
.group-live {
  flex: none;
  height: 20px;
  padding: 0 6px 0 4px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--fs-xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.group-live svg { width: 12px; height: 12px; flex: none; }
.group-live.running { color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
.group-live.waiting { color: var(--warn); background: color-mix(in srgb, var(--warn) 14%, transparent); }
:root[data-theme='light'] .group-live.running { color: color-mix(in srgb, var(--accent) 80%, #000); }
:root[data-theme='light'] .group-live.waiting { color: color-mix(in srgb, var(--warn) 80%, #000); }

.group-new { opacity: 0; }
.group-head:hover .group-new,
.group-head:focus-within .group-new,
.group-new:focus-visible { opacity: 1; }
@media (hover: none) { .group-new { opacity: 1; } }

/* ---------- rows ---------- */
.session-item {
  position: relative;
  width: 100%;
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}

.session-item + .session-item { margin-top: 2px; }
.session-item:hover { background: rgb(var(--ink) / 0.06); }

/* Selected: a quiet tint and a full hairline, no stripe on one side */
.session-item.active {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  color: var(--fg);
}

.session-item.draft { margin-bottom: 6px; }

.session-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg);
  font-weight: 600;
  line-height: 1.3;
}

.session-sub {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  color: var(--fg-subtle);
}

.session-sub :deep(.status-pill) { flex: 0 1 auto; min-width: 0; }

.session-time {
  flex: none;
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.session-flow { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* The lead's plan waits for your approval */
.plan-badge {
  flex: none;
  padding: 0 7px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 650;
  line-height: 18px;
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
}

.session-rename {
  width: 100%;
  height: 28px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--accent);
  background: var(--bg);
  color: var(--fg);
  font: inherit;
  font-weight: 600;
}

.session-rename:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

/* Hover actions sit over the end of the row instead of pushing the title around */
.session-actions {
  position: absolute;
  top: 6px;
  right: 6px;
  display: none;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-raised);
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions { display: inline-flex; }

@media (hover: none) {
  .session-actions { position: static; display: inline-flex; border: none; background: transparent; padding: 0; }
}

.icon-btn {
  position: relative;
  width: 28px;
  height: 28px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
}

.icon-btn::before { content: ''; position: absolute; inset: -6px; }
@media (pointer: coarse) { .icon-btn { width: 44px; height: 44px; } }
.icon-btn svg { width: 14px; height: 14px; }
.icon-btn:hover { background: rgb(var(--ink) / 0.1); color: var(--fg); }
.icon-btn.danger:hover { color: var(--danger); }

/* ---------- loading and empty ---------- */
.sidebar-skeleton { display: flex; flex-direction: column; gap: 4px; padding: 6px 2px; }
.skeleton-row { display: flex; flex-direction: column; gap: 8px; padding: 9px 10px; }

.sidebar-empty {
  margin: 12px 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--fg-muted);
}
.sidebar-empty p { margin: 0 0 10px; }

.sidebar-empty.is-first {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  margin: 16px 8px;
  padding: 16px 14px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
}
.sidebar-empty.is-first p { margin: 0 0 8px; }
.sidebar-empty .empty-icon { width: 22px; height: 22px; margin-bottom: 8px; color: var(--fg-subtle); }
.sidebar-empty .empty-title { margin: 0 0 2px; font-size: 14px; font-weight: 650; color: var(--fg); }

.empty-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.empty-action svg { width: 14px; height: 14px; flex: none; }
.empty-action:hover { border-color: var(--accent); }

/* ---------- collapsed rail ---------- */
.sidebar-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 0;
}

.rail-btn {
  position: relative;
  width: 40px;
  height: 40px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.rail-btn svg { width: 18px; height: 18px; }
.rail-btn:hover { background: rgb(var(--ink) / 0.08); color: var(--fg); }
.rail-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }

.rail-dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 2px var(--surface);
}
.rail-dot.waiting { background: var(--warn); }

.rail-live {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin-top: 6px;
  padding: 6px 0;
  width: 32px;
  border-radius: var(--radius-sm);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-size: var(--fs-xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.rail-live svg { width: 13px; height: 13px; }
:root[data-theme='light'] .rail-live { color: color-mix(in srgb, var(--accent) 80%, #000); }

/* Teleported to <body>, so these rules are not tied to the sidebar box */
.session-menu {
  position: fixed;
  z-index: var(--z-backdrop);
  min-width: 190px;
  max-width: 260px;
  display: flex;
  flex-direction: column;
  padding: 4px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  box-shadow: 0 12px 32px rgb(var(--shade) / 0.45);
  font-size: 13px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.menu-item svg { width: 15px; height: 15px; flex: none; }
.menu-item:hover,
.menu-item:focus-visible { background: rgb(var(--ink) / 0.08); color: var(--fg); outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.menu-item:hover:not(:focus-visible) { outline: none; }
.menu-item.danger { color: var(--danger); }
.menu-item.danger:hover { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); }

.menu-sep { height: 1px; margin: 4px 6px; background: var(--border); }

.sidebar-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid var(--border);
}

.collapsed .sidebar-foot {
  flex-direction: column;
  margin-top: auto;
  border-top: none;
}

.foot-new {
  flex: 1;
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.foot-new svg { width: 14px; height: 14px; }
.foot-new:hover { border-color: var(--accent); }

.foot-toggle svg { transition: transform 0.25s var(--ease-out); }
.foot-toggle svg.flipped { transform: rotate(180deg); }

@media (max-width: 900px) {
  .session-sidebar:not(.collapsed) { flex-basis: 210px; width: 210px; }
}

@media (prefers-reduced-motion: reduce) {
  .session-sidebar,
  .session-item,
  .group-chevron,
  .live-chip,
  .rail-btn,
  .foot-toggle svg { transition: none; }
  .spin { animation: none; }
}
</style>
