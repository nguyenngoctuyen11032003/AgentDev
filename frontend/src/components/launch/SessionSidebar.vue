<template>
  <aside class="session-sidebar" :class="{ collapsed }" :aria-label="t('launch.sessions.title')">
    <template v-if="!collapsed">
      <div class="sidebar-head">
        <span class="sidebar-title">{{ t('launch.sessions.title') }}</span>
        <span class="sidebar-count">{{ sessions.length }}</span>
      </div>

      <!-- Runs keep going while you work elsewhere: show what needs attention -->
      <div v-if="liveCounts.running || liveCounts.waiting" class="sidebar-live" role="status">
        <span v-if="liveCounts.waiting" class="live-chip waiting">
          <span class="session-dot status-waiting_for_input"></span>{{ t('launch.sessions.live_waiting', { n: liveCounts.waiting }) }}
        </span>
        <span v-if="liveCounts.running" class="live-chip running">
          <span class="session-dot status-running"></span>{{ t('launch.sessions.live_running', { n: liveCounts.running }) }}
        </span>
      </div>

      <div class="sidebar-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input v-model="query" type="text" :placeholder="t('launch.sessions.search')" />
      </div>

      <div class="sidebar-list">
        <!-- The session being prepared in this tab, before it is launched -->
        <button
          v-if="draft"
          type="button"
          class="session-item draft active"
          @click="emit('select', null)"
        >
          <span class="session-dot status-idle"></span>
          <span class="session-body">
            <span class="session-name">{{ t('launch.sessions.untitled') }}</span>
            <span class="session-sub"><template v-if="draftProject">{{ draftProject }} · </template>{{ workflowLabel(draft) }} · {{ t('launch.sessions.draft') }}</span>
          </span>
        </button>

        <section v-for="group in groups" :key="group.key" class="session-group">
          <div class="group-head" @contextmenu.prevent="openMenu($event, 'group', group)">
            <button type="button" class="group-toggle" :aria-expanded="isGroupOpen(group)" :title="groupTitle(group)" @click="toggleGroup(group.key)">
              <svg class="group-chevron" :class="{ closed: !isGroupOpen(group) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
              <svg v-if="group.isProject" class="group-folder" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
              <span class="group-name">{{ group.label }}</span>
              <span v-if="group.isProject && group.workflow" class="group-flow">{{ workflowLabel(group.workflow) }}</span>
              <span class="group-meta">
                <span v-if="group.waiting" class="group-live waiting" :title="t('launch.sessions.live_waiting', { n: group.waiting })">{{ group.waiting }}</span>
                <span v-if="group.running" class="group-live running" :title="t('launch.sessions.live_running', { n: group.running })">{{ group.running }}</span>
                <span class="group-count">{{ group.items.length }}</span>
              </span>
            </button>
            <button
              type="button"
              class="icon-btn group-new"
              :title="newInLabel(group)"
              :aria-label="newInLabel(group)"
              @click="emit('new', group)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14" /></svg>
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
              @click="emit('select', item)"
              @keydown.enter.prevent="emit('select', item)"
              @contextmenu.prevent="openMenu($event, 'item', item)"
            >
              <span class="session-dot" :class="`status-${item.status}`" :title="statusLabel(item.status)"></span>
              <span class="session-body">
                <input
                  v-if="editingId === item.session_id"
                  ref="renameInputRef"
                  v-model="editingTitle"
                  class="session-rename"
                  maxlength="120"
                  @click.stop
                  @keydown.enter.prevent="commitRename(item)"
                  @keydown.esc.prevent="editingId = null"
                  @blur="commitRename(item)"
                />
                <span v-else class="session-name" :title="item.title">{{ item.title || t('launch.sessions.untitled') }}</span>
                <span class="session-sub">
                  <template v-if="group.isProject">{{ workflowLabel(item.yaml_file) }} · </template>{{ statusLabel(item.status) }} · {{ timeAgo(item.updated_at) }}
                </span>
              </span>
              <span class="session-actions" @click.stop>
                <button type="button" class="icon-btn" :title="t('launch.sessions.rename')" :aria-label="t('launch.sessions.rename')" @click="startRename(item)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
                </button>
                <button type="button" class="icon-btn danger" :title="t('launch.sessions.delete')" :aria-label="t('launch.sessions.delete')" @click="emit('delete', item)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
                </button>
              </span>
            </div>
          </div>
        </section>

        <p v-if="!sessions.length && !draft" class="sidebar-empty">{{ t('launch.sessions.empty') }}</p>
        <p v-else-if="query && !groups.length" class="sidebar-empty">{{ t('launch.sessions.no_results') }}</p>
      </div>
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
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>
            {{ t('launch.sessions.menu.open') }}
          </button>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => startRename(target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
            {{ t('launch.sessions.rename') }}
          </button>
          <div class="menu-sep"></div>
          <button type="button" class="menu-item danger" role="menuitem" @click="runMenu((target) => emit('delete', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
            {{ t('launch.sessions.delete') }}
          </button>
        </template>
        <template v-else>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => emit('new', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14" /></svg>
            {{ newInLabel(menu.target) }}
          </button>
          <button type="button" class="menu-item" role="menuitem" @click="runMenu((target) => toggleGroup(target.key))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6" /></svg>
            {{ isGroupClosed(menu.target.key) ? t('launch.sessions.menu.expand') : t('launch.sessions.menu.collapse') }}
          </button>
          <div class="menu-sep"></div>
          <button type="button" class="menu-item danger" role="menuitem" @click="runMenu((target) => emit('delete-group', target))">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
            {{ menu.target.isProject ? t('launch.sessions.menu.delete_project') : t('launch.sessions.menu.delete_group') }}
          </button>
        </template>
      </div>
    </Teleport>

    <div class="sidebar-foot">
      <button
        v-if="!collapsed"
        type="button"
        class="foot-new"
        :title="t('launch.sessions.add_project_hint')"
        @click="emit('add-project')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg>
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
        <svg :class="{ flipped: collapsed }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17-5-5 5-5" /><path d="m18 17-5-5 5-5" /></svg>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
  // Workflow file of a session that is open in this tab but not launched yet
  draft: { type: String, default: '' },
  // Project the draft belongs to (shown on the draft row)
  draftProject: { type: String, default: '' },
  // Workflow each project uses for its next session: { [projectName]: yamlFile }
  projectWorkflows: { type: Object, default: () => ({}) },
  collapsed: { type: Boolean, default: false }
})

const emit = defineEmits(['select', 'new', 'add-project', 'rename', 'delete', 'delete-group', 'toggle'])

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
  border-radius: 12px;
  border: 1px solid rgb(var(--ink) / 0.1);
  background: rgb(var(--ink) / 0.03);
  color: var(--text-2);
  font-size: 13px;
  overflow: hidden;
  transition: flex-basis 0.25s ease, width 0.25s ease;
}

.session-sidebar.collapsed {
  flex-basis: 44px;
  width: 44px;
}

.sidebar-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 14px 8px;
}

.sidebar-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--ink) / 0.55);
}

.sidebar-count {
  padding: 0 7px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 18px;
  background: rgb(var(--ink) / 0.08);
}

.sidebar-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 10px 8px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.1);
  background: rgb(var(--ink) / 0.04);
}

.sidebar-search svg { width: 14px; height: 14px; flex: none; opacity: 0.55; }

.sidebar-search input {
  flex: 1;
  min-width: 0;
  padding: 7px 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-1);
  font: inherit;
}

.session-sidebar *,
.session-sidebar *::before {
  box-sizing: border-box;
}

.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px 6px 8px;
}

.session-group + .session-group { margin-top: 6px; }

.group-head {
  display: flex;
  align-items: center;
}

.group-toggle {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgb(var(--ink) / 0.6);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  text-align: left;
}

.group-toggle:hover { color: var(--text-1); }

.group-chevron { width: 13px; height: 13px; flex: none; transition: transform 0.2s ease; }
.group-chevron.closed { transform: rotate(-90deg); }

.group-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.group-folder { width: 14px; height: 14px; flex: none; color: #f5b94a; }

.group-meta { margin-left: auto; flex: none; display: inline-flex; align-items: center; gap: 4px; }
.group-count { font-weight: 500; opacity: 0.7; }

.group-new { opacity: 0; }
.group-head:hover .group-new,
.group-new:focus-visible { opacity: 1; }

.session-item {
  position: relative;
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 7px 8px 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.session-item:hover { background: rgb(var(--ink) / 0.06); }

.session-item.active {
  background: rgb(var(--accent-sky-rgb) / 0.12);
  color: var(--text-1);
}

.session-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 3px;
  background: var(--accent-sky);
}

.session-item.draft { margin-bottom: 6px; }

.session-dot {
  width: 8px;
  height: 8px;
  flex: none;
  margin-top: 5px;
  border-radius: 50%;
  border: 1.5px solid rgb(var(--ink) / 0.45);
}

.status-running { border: none; background: #34d399; box-shadow: 0 0 6px #34d399; animation: session-pulse 1.4s ease-in-out infinite; }
.status-waiting_for_input { border: none; background: #fbbf24; }
.status-completed { border: none; background: rgb(var(--ink) / 0.35); }
.status-error { border: none; background: #f87171; }
.status-cancelled { border-color: #f87171; }
/* Stop pressed, still winding down */
.status-cancelling { border: none; background: #fbbf24; animation: session-pulse 1.4s ease-in-out infinite; }

@keyframes session-pulse { 50% { opacity: 0.45; } }

.sidebar-live {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 12px 8px;
}
.live-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  background: rgb(var(--ink) / 0.06);
  color: var(--text-1);
}
.live-chip .session-dot { margin: 0; }
.live-chip.waiting { background: rgb(251 191 36 / 0.14); }
.live-chip.running { background: rgb(52 211 153 / 0.12); }

.group-flow {
  flex: 0 1 auto;
  max-width: 84px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgb(var(--ink) / 0.06);
  color: var(--text-3, var(--text-2));
  font-size: 10.5px;
  font-weight: 500;
}
.group-live {
  flex: none;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  font-size: 10px;
  font-weight: 700;
  color: #0b1a12;
}
.group-live.running { background: #34d399; }
.group-live.waiting { background: #fbbf24; color: #2a1c00; }

.session-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-1);
  font-weight: 600;
}

.session-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: rgb(var(--ink) / 0.5);
}

.session-rename {
  width: 100%;
  padding: 1px 4px;
  border-radius: 4px;
  border: 1px solid rgb(var(--accent-sky-rgb) / 0.6);
  background: rgb(var(--ink) / 0.06);
  color: var(--text-1);
  font: inherit;
  font-weight: 600;
  outline: none;
}

.session-actions {
  display: none;
  gap: 2px;
  margin-top: 1px;
}

.session-item:hover .session-actions,
.session-item:focus-within .session-actions { display: inline-flex; }

.icon-btn {
  width: 24px;
  height: 24px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgb(var(--ink) / 0.6);
  cursor: pointer;
}

.icon-btn svg { width: 14px; height: 14px; }
.icon-btn:hover { background: rgb(var(--ink) / 0.1); color: var(--text-1); }
.icon-btn.danger:hover { color: #f87171; }

/* Teleported to <body>, so these rules are not tied to the sidebar box */
.session-menu {
  position: fixed;
  z-index: 10000;
  min-width: 190px;
  max-width: 260px;
  display: flex;
  flex-direction: column;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: var(--surface-3);
  box-shadow: 0 12px 32px rgb(var(--shade) / 0.45);
  font-size: 13px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-2);
  font: inherit;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.menu-item svg { width: 15px; height: 15px; flex: none; }
.menu-item:hover,
.menu-item:focus-visible { background: rgb(var(--ink) / 0.08); color: var(--text-1); outline: none; }
.menu-item.danger { color: #f87171; }
.menu-item.danger:hover { background: rgb(248 113 113 / 0.12); color: #ef4444; }

.menu-sep { height: 1px; margin: 4px 6px; background: rgb(var(--ink) / 0.1); }

.sidebar-empty {
  margin: 12px 8px;
  font-size: 12px;
  line-height: 1.5;
  color: rgb(var(--ink) / 0.5);
}

.sidebar-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid rgb(var(--ink) / 0.08);
}

.collapsed .sidebar-foot {
  flex-direction: column;
  margin-top: auto;
  border-top: none;
}

.foot-new {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(var(--ink) / 0.05);
  color: var(--text-1);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.foot-new svg { width: 14px; height: 14px; }
.foot-new:hover { background: rgb(var(--ink) / 0.1); }

.foot-toggle svg { transition: transform 0.25s ease; }
.foot-toggle svg.flipped { transform: rotate(180deg); }

@media (max-width: 900px) {
  .session-sidebar:not(.collapsed) { flex-basis: 210px; width: 210px; }
}

@media (prefers-reduced-motion: reduce) {
  .session-sidebar,
  .group-chevron,
  .foot-toggle svg { transition: none; }
  .status-running { animation: none; }
}
</style>
