<template>
  <div
    ref="rootRef"
    class="office-view dept-scope-dark"
    :class="{ pannable: zoom > 1, panning: panState.active }"
    @wheel="onWheel"
    @pointerdown="onPanStart"
  >
    <!-- Part of the panel not covered by the chat overlay; the scene is fitted into it -->
    <div ref="safeRef" class="office-safe-area" aria-hidden="true"></div>
    <div class="office-stage" :style="stageStyle">
      <img class="office-map" :src="OFFICE_IMAGE" alt="" draggable="false" />

      <!-- Department plaques -->
      <div
        v-for="room in plaques"
        :key="room.id"
        class="office-plaque"
        :style="{ ...pointStyle(room.x + 8, room.y < 200 ? 209 : 288), '--dept': room.color }"
      >
        <span class="plaque-dot"></span>
        <span class="plaque-name">{{ t(`launch.office.rooms.${room.id}`) }}</span>
        <span v-if="room.count" class="plaque-count">{{ room.count }}</span>
      </div>

      <!-- Server status lights (blink faster while the ops team is busy) -->
      <div class="office-racks" :class="{ busy: opsBusy }">
        <i
          v-for="led in rackLeds"
          :key="led.key"
          class="rack-led"
          :class="led.tone"
          :style="{ ...pointStyle(led.x, led.y), width: `${2 * scale}px`, height: `${scale}px`, animationDelay: `${led.delay}s` }"
        ></i>
      </div>

      <!-- Screen glow on desks in use -->
      <div
        v-for="g in deskGlows"
        :key="g.key"
        class="office-desk-glow"
        :class="g.tone"
        :style="glowStyle(g)"
      ></div>

      <!-- Characters -->
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="office-agent"
        :class="[
          `pose-${agent.pose}`,
          `state-${agent.state}`,
          { hovered: focusId === agent.id, 'desk-rest': agent.deskRest },
          isHeroSprite(agent.character) && [`hero-sprite`, `hero-${agent.facing}`, { 'is-moving': agent.pose === 'walk' }]
        ]"
        :style="agentStyle(agent)"
        :ref="(el) => bindEl(agent.id, 'root', el)"
        role="button"
        tabindex="0"
        :aria-pressed="pinnedId === agent.id"
        :aria-label="agent.label"
        @mouseenter="hoveredId = agent.id"
        @mouseleave="hoveredId = null"
        @focus="hoveredId = agent.id"
        @blur="hoveredId = null"
        @click="togglePin(agent.id)"
        @keydown.enter.prevent="togglePin(agent.id)"
        @keydown.space.prevent="togglePin(agent.id)"
      >
        <div class="office-agent-shadow"></div>
        <img class="office-agent-sprite" :src="spriteSrc(agent)" alt="" draggable="false" />
      </div>

      <!-- Tags, badges and bubbles (always above sprites) -->
      <div
        v-for="agent in agents"
        :key="`label-${agent.id}`"
        class="office-agent-overlay"
        :class="{ dim: focusId && focusId !== agent.id }"
        :style="overlayStyle(agent)"
        :ref="(el) => bindEl(agent.id, 'overlay', el)"
      >
        <Transition name="office-bubble">
          <div v-if="agent.bubble" :key="agent.bubble.key" class="office-bubble" :class="`bubble-${agent.bubble.type}`">
            <span v-if="agent.bubble.type === 'thinking'" class="bubble-dots"><i></i><i></i><i></i></span>
            <svg v-else-if="agent.bubble.type === 'tool'" class="bubble-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" /></svg>
            <svg v-else-if="['handoff', 'receive', 'delegate'].includes(agent.bubble.type)" class="bubble-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M9 14h6M9 17h4" /></svg>
            <svg v-else-if="agent.bubble.type === 'waiting'" class="bubble-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" /><path d="M12 17h.01" /></svg>
            <svg v-else-if="agent.bubble.type === 'done'" class="bubble-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
            <span v-if="agent.bubble.body" class="bubble-body">
              <b class="bubble-kicker">{{ agent.bubble.kicker }}</b>
              <span class="bubble-text">{{ agent.bubble.body }}</span>
            </span>
            <span v-else class="bubble-text">{{ agent.bubble.text }}</span>
          </div>
        </Transition>

        <div v-if="!agent.bubble && restBadge(agent)" class="office-rest-badge" :class="`rest-${restBadge(agent)}`">
          <template v-if="restBadge(agent) === 'sleep'"><b>z</b><b>z</b></template>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8h1a4 4 0 0 1 0 8h-1" /><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z" /><path d="M6 2v2M10 2v2M14 2v2" /></svg>
        </div>

        <div
          class="office-tag"
          :class="[`tag-${agent.state}`, { compact: compactTags && focusId !== agent.id && (agent.state === 'idle' || agent.state === 'done') }]"
          :style="{ '--dept': agent.color }"
        >
          <span class="tag-step">{{ agent.step }}</span>
          <span class="tag-name">{{ agent.label }}</span>
          <span class="tag-dot"></span>
        </div>
      </div>

      <!-- Info card -->
      <Transition name="office-card">
        <div v-if="focusAgent" ref="cardEl" class="office-card" :style="cardStyle(focusAgent)">
          <div class="card-head">
            <img class="card-avatar" :src="avatarSrc(focusAgent)" alt="" />
            <div class="card-title">
              <div class="card-name">{{ focusAgent.label }}</div>
              <div class="card-type">
                {{ t('launch.office.card.step', { n: focusAgent.step, total: agents.length }) }} · {{ focusAgent.typeLabel }}
              </div>
            </div>
            <span class="card-state" :class="`tag-${focusAgent.state}`">
              <span class="tag-dot"></span>{{ t(`launch.office.states.${focusAgent.state}`) }}
            </span>
          </div>
          <div class="card-row">
            <span class="card-key">{{ t('launch.office.card.department') }}</span>
            <span class="card-val"><span class="card-dept" :style="{ background: focusAgent.color }"></span>{{ t(`launch.office.rooms.${focusAgent.dept}`) }}</span>
          </div>
          <div v-if="focusAgent.model" class="card-row">
            <span class="card-key">{{ t('launch.office.card.model') }}</span>
            <span class="card-val">{{ focusAgent.model }}</span>
          </div>
          <div class="card-row">
            <span class="card-key">{{ t('launch.office.card.location') }}</span>
            <span class="card-val">{{ t(`launch.office.rooms.${locationRoom(focusAgent)}`) }}</span>
          </div>
          <div class="card-row">
            <span class="card-key">{{ t('launch.office.card.activity') }}</span>
            <span class="card-val">{{ activityText(focusAgent) }}</span>
          </div>
          <div v-if="focusAgent.role" class="card-block">
            <span class="card-key">{{ t('launch.office.card.role') }}</span>
            <p>{{ focusAgent.role }}</p>
          </div>
          <div v-if="focusAgent.lastOutput" class="card-block">
            <span class="card-key">{{ t('launch.office.card.last_output') }}</span>
            <p>{{ focusAgent.lastOutput }}</p>
          </div>
        </div>
      </Transition>
    </div>

    <!-- HUD: pull-down drawer from the top edge, collapsible to a small tab -->
    <div ref="hudRef" class="office-hud-dock" :class="{ collapsed: hudCollapsed }">
      <div class="office-hud-drawer" :aria-hidden="hudCollapsed">
        <div class="office-hud-clip">
          <div class="office-hud">
            <div class="hud-title">
              <span class="hud-live" :class="{ on: isRunning }"></span>
              {{ t('launch.office.title') }}
              <span v-if="workflowName" class="hud-workflow" :title="workflowName">{{ workflowName }}</span>
            </div>
            <span class="hud-staff">{{ t(isTeam ? 'launch.office.staff_count_team' : 'launch.office.staff_count', { n: agents.length }) }}</span>
            <div class="hud-stats">
              <span class="hud-chip tag-working"><span class="tag-dot"></span>{{ t('launch.office.states.working') }} {{ counts.working }}</span>
              <span v-if="counts.waiting" class="hud-chip tag-waiting"><span class="tag-dot"></span>{{ t('launch.office.states.waiting') }} {{ counts.waiting }}</span>
              <span class="hud-chip tag-done"><span class="tag-dot"></span>{{ t('launch.office.states.done') }} {{ counts.done }}</span>
              <span class="hud-chip tag-idle"><span class="tag-dot"></span>{{ t('launch.office.states.idle') }} {{ counts.idle }}</span>
            </div>
          </div>
        </div>
      </div>
      <button
        class="hud-toggle"
        type="button"
        :aria-expanded="!hudCollapsed"
        :title="hudCollapsed ? t('launch.office.hud_expand') : t('launch.office.hud_collapse')"
        @click="toggleHud"
      >
        <Transition name="hud-summary">
          <span v-if="hudCollapsed" class="hud-summary">
            <span class="hud-live" :class="{ on: isRunning }"></span>
            <span class="hud-summary-staff">{{ agents.length }}</span>
            <span class="hud-summary-sep"></span>
            <span class="hud-summary-item tag-working"><span class="tag-dot"></span>{{ counts.working }}</span>
            <span v-if="counts.waiting" class="hud-summary-item tag-waiting"><span class="tag-dot"></span>{{ counts.waiting }}</span>
          </span>
        </Transition>
        <svg class="hud-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6" /></svg>
      </button>
    </div>

    <!-- Roster: every workflow step is one staff member -->
    <div v-if="agents.length" class="office-roster" :class="{ open: rosterOpen }">
      <button class="roster-toggle" type="button" :aria-expanded="rosterOpen" @click="rosterOpen = !rosterOpen">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
        {{ t('launch.office.roster', { n: agents.length }) }}
        <svg class="roster-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6" /></svg>
      </button>
      <ul v-show="rosterOpen" class="roster-list">
        <li
          v-for="agent in agents"
          :key="`roster-${agent.id}`"
          class="roster-item"
          :class="{ active: focusId === agent.id }"
          role="button"
          tabindex="0"
          :aria-pressed="pinnedId === agent.id"
          @mouseenter="hoveredId = agent.id"
          @mouseleave="hoveredId = null"
          @click="togglePin(agent.id)"
          @keydown.enter.prevent="togglePin(agent.id)"
          @keydown.space.prevent="togglePin(agent.id)"
        >
          <span class="roster-step">{{ agent.step }}</span>
          <img class="roster-avatar" :src="avatarSrc(agent)" alt="" />
          <span class="roster-name">{{ agent.label }}</span>
          <span class="roster-dept" :style="{ '--dept': agent.color }">{{ t(`launch.office.dept_short.${agent.dept}`) }}</span>
          <span class="roster-state" :class="`tag-${agent.state}`"><span class="tag-dot"></span></span>
        </li>
      </ul>
    </div>

    <!-- Zoom: the scene fits the panel by default; zoom in to read a room, drag to pan -->
    <div class="office-zoom" role="group" :aria-label="t('launch.office.zoom_group')">
      <button type="button" class="zoom-btn" :title="t('launch.office.zoom_out')" :aria-label="t('launch.office.zoom_out')" :disabled="zoom <= 1" @click="zoomBy(1 / 1.25)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14" /></svg>
      </button>
      <button type="button" class="zoom-btn zoom-fit" :title="t('launch.office.zoom_fit')" :aria-label="t('launch.office.zoom_fit')" :disabled="zoom === 1" @click="fitView">
        <span class="zoom-level">{{ Math.round(zoom * 100) }}%</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4" /></svg>
      </button>
      <button type="button" class="zoom-btn" :title="t('launch.office.zoom_in')" :aria-label="t('launch.office.zoom_in')" :disabled="zoom >= ZOOM_MAX" @click="zoomBy(1.25)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5v14" /></svg>
      </button>
    </div>

    <div v-if="!agents.length" class="office-empty">
      <div class="office-empty-card">{{ t('launch.office.empty') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, markRaw, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { buildSpritePath, spriteFetcher } from '@/utils/spriteFetcher.js'
import { isHeroSprite } from '@/utils/spriteCharacters.js'
import { OfficePathfinder } from '@/utils/officePathfinder.js'
import {
  OFFICE_WIDTH,
  OFFICE_HEIGHT,
  OFFICE_IMAGE,
  ENTRANCE,
  ROOMS,
  REST_SPOTS,
  SERVER_RACKS,
  DEPARTMENT_COLOR,
  classifyNode,
  assignSeats,
  orderSteps,
} from '@/utils/officeLayout.js'
import { computeTeamLinks } from '@/utils/teamLinks.js'
import { stepStatus } from '@/utils/runTracker.js'

const props = defineProps({
  // Workflow graph from the YAML (`graph`: nodes, edges, start)
  graph: { type: Object, default: () => ({}) },
  // node id -> sprite path chosen by the Launch view (keeps characters consistent with chat/graph)
  spriteMap: { type: Map, default: () => new Map() },
  // ids of nodes currently executing
  activeNodes: { type: Array, default: () => [] },
  // raw workflow status string of the Launch view
  status: { type: String, default: '' },
  workflowName: { type: String, default: '' },
  // false while the view is hidden: no animation frames, characters snap into place
  visible: { type: Boolean, default: true },
  // Run record of the session (runTracker state): who worked, waits or is done, in every
  // turn, replays included. The events above only animate; the status comes from here.
  tracker: { type: Object, default: null },
})

const { t, te } = useI18n()
// A team (a lead delegating to members) is not a pipeline of steps: say "people", not "steps"
const isTeam = computed(() => computeTeamLinks(props.graph?.nodes, props.graph?.edges).length > 0)

// One sprite art pixel = one map unit (sprites are 30x38 art px).
const SPRITE_H = 38
const SPRITE_W = 30
const WALK_SPEED = 78 // map units per second at full stride
const ACCEL = 4 // fraction of full speed gained per second
const STEP_LENGTH = 7 // map units per walking frame
const SIT_DROP = 7 // how far the body sinks into the chair
const WALK_FRAMES = [2, 1, 3, 1]
const BUBBLE_MS = { say: 5200, done: 3000, handoff: 2200, receive: 2200 }

const pathfinder = new OfficePathfinder()
const rootRef = ref(null)
const scale = ref(1)
const offset = reactive({ x: 0, y: 0 })
const agents = ref([])
const hoveredId = ref(null)
const pinnedId = ref(null)
const rosterOpen = ref(false)

// HUD drawer state is a per-viewer preference.
const HUD_KEY = 'agentdev.office.hudCollapsed'
const readHudPref = () => {
  try { return localStorage.getItem(HUD_KEY) === '1' } catch { return false }
}
const hudCollapsed = ref(readHudPref())
const toggleHud = () => {
  hudCollapsed.value = !hudCollapsed.value
  try { localStorage.setItem(HUD_KEY, hudCollapsed.value ? '1' : '0') } catch { /* storage unavailable */ }
  // the free area under the HUD changes once the drawer has finished sliding
  setTimeout(() => measure(), 360)
}
const waitingIds = ref(new Set())
const hasRun = new Set()
const reservations = new Map() // rest spot id -> agent id
let bubbleSeq = 0

const isRunning = computed(() => props.status === 'Running...' || props.status === 'Waiting for input...')
const focusId = computed(() => hoveredId.value || pinnedId.value)
const focusAgent = computed(() => agents.value.find((a) => a.id === focusId.value) || null)
// Crowded offices show only the step number for people who are not busy (full name on hover).
const compactTags = computed(() => agents.value.length > 12)
const opsBusy = computed(() => agents.value.some((a) => a.dept === 'ops' && a.state === 'working'))

const counts = computed(() => {
  const c = { working: 0, waiting: 0, done: 0, idle: 0 }
  for (const a of agents.value) c[a.state] += 1
  return c
})

const plaques = computed(() =>
  ROOMS.filter((r) => r.id !== 'corridor').map((r) => ({
    ...r,
    color: DEPARTMENT_COLOR[r.id] || r.color,
    count: agents.value.filter((a) => a.seat?.dept === r.id).length,
  }))
)

const rackLeds = SERVER_RACKS.flatMap(([x, y, , h], r) => {
  const leds = []
  for (let j = y + 4, k = 0; j < y + h - 3; j += 5, k++) {
    leds.push({ key: `${r}-${k}-a`, x: x + 3, y: j + 1, tone: (r + k) % 3 ? 'led-green' : 'led-amber', delay: ((r * 7 + k * 3) % 10) / 10 })
    leds.push({ key: `${r}-${k}-b`, x: x + 5, y: j + 1, tone: 'led-blue', delay: ((r * 5 + k * 7) % 10) / 10 })
  }
  return leds
})

const reducedMotionQuery =
  typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
const prefersReducedMotion = () => !!reducedMotionQuery?.matches

const hashOf = (text) => {
  let h = 2166136261
  for (const ch of String(text)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619)
  return (h >>> 0) / 4294967296
}

// ---------------------------------------------------------------- layout / scaling
const stageStyle = computed(() => ({
  width: `${OFFICE_WIDTH * scale.value}px`,
  height: `${OFFICE_HEIGHT * scale.value}px`,
  transform: `translate(${offset.x}px, ${offset.y}px)`,
}))

let resizeObserver = null
const safeRef = ref(null)
const hudRef = ref(null)
const ZOOM_MAX = 3
// zoom is a multiplier over the "fit" scale: 1 = the whole office fits the free area
const zoom = ref(1)
let fitScale = 1
// Free area (px, relative to the root): right of the chat overlay, below the HUD, above the roster
const area = { x: 0, y: 0, w: 1, h: 1 }

const clampOffset = () => {
  const w = OFFICE_WIDTH * scale.value
  const h = OFFICE_HEIGHT * scale.value
  offset.x = Math.round(w <= area.w ? area.x + (area.w - w) / 2 : Math.min(area.x, Math.max(area.x + area.w - w, offset.x)))
  offset.y = Math.round(h <= area.h ? area.y + (area.h - h) / 2 : Math.min(area.y, Math.max(area.y + area.h - h, offset.y)))
}

const measure = () => {
  const el = rootRef.value
  if (!el) return
  const root = el.getBoundingClientRect()
  if (!root.width || !root.height) return
  const safe = safeRef.value?.getBoundingClientRect()
  const left = safe ? Math.max(0, safe.left - root.left) : 0
  const hud = hudRef.value?.getBoundingClientRect()
  const top = hud ? Math.max(12, hud.bottom - root.top + 8) : 12
  const bottom = 60 // roster toggle + zoom controls
  area.x = left + 12
  area.y = top
  area.w = Math.max(1, root.width - left - 24)
  area.h = Math.max(1, root.height - top - bottom)
  fitScale = Math.min(area.w / OFFICE_WIDTH, area.h / OFFICE_HEIGHT)
  scale.value = fitScale * zoom.value
  clampOffset()
}

// Zoom around a point of the root (defaults to the centre of the free area)
const zoomTo = (next, cx = area.x + area.w / 2, cy = area.y + area.h / 2) => {
  const z = Math.min(ZOOM_MAX, Math.max(1, next))
  const prev = scale.value
  zoom.value = z
  scale.value = fitScale * z
  const r = scale.value / prev
  offset.x = cx - (cx - offset.x) * r
  offset.y = cy - (cy - offset.y) * r
  clampOffset()
}
const zoomBy = (factor) => zoomTo(zoom.value * factor)
const fitView = () => zoomTo(1)

// Ctrl/⌘ + wheel zooms (plain wheel keeps scrolling the page)
const onWheel = (e) => {
  if (!e.ctrlKey && !e.metaKey) return
  e.preventDefault()
  const root = rootRef.value.getBoundingClientRect()
  zoomTo(zoom.value * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX - root.left, e.clientY - root.top)
}

// Drag to pan while zoomed in (not when starting on a control or a person)
const panState = reactive({ active: false, x: 0, y: 0, ox: 0, oy: 0 })
const onPanMove = (e) => {
  offset.x = panState.ox + e.clientX - panState.x
  offset.y = panState.oy + e.clientY - panState.y
  clampOffset()
}
const onPanEnd = () => {
  panState.active = false
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
  window.removeEventListener('pointercancel', onPanEnd)
}
const onPanStart = (e) => {
  if (zoom.value <= 1 || e.button !== 0) return
  if (e.target.closest?.('button, [role="button"], .office-roster, .office-hud-dock, .office-zoom')) return
  Object.assign(panState, { active: true, x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y })
  window.addEventListener('pointermove', onPanMove)
  window.addEventListener('pointerup', onPanEnd)
  window.addEventListener('pointercancel', onPanEnd)
}

const pointStyle = (x, y) => ({ left: `${x * scale.value}px`, top: `${y * scale.value}px` })

// ---------------------------------------------------------------- agents
const characterFor = (id) => {
  const path = props.spriteMap.get(id) || ''
  const match = path.match(/\/sprites\/(\d+)-/)
  if (match) return Number(match[1])
  const bound = spriteFetcher.getCharacter(id)
  if (bound) return bound
  return Math.floor(hashOf(id) * 12) + 1
}

const roleSnippet = (role) => {
  if (!role) return ''
  const text = String(role).replace(/\s+/g, ' ').trim()
  return text.length > 160 ? `${text.slice(0, 157)}…` : text
}

const typeLabel = (type) => {
  const key = `launch.office.types.${type || 'agent'}`
  return te(key) ? t(key) : type
}

const createAgent = (node, spawn) => {
  const h = hashOf(node.id)
  return reactive({
    id: node.id,
    label: node.id,
    type: node.type,
    typeLabel: typeLabel(node.type),
    model: node.config?.name && !String(node.config.name).startsWith('${') ? node.config.name : '',
    role: roleSnippet(node.config?.role || node.description),
    dept: classifyNode(node),
    color: DEPARTMENT_COLOR.eng,
    step: 0,
    isHuman: node.type === 'human',
    character: characterFor(node.id),
    seat: null,
    lane: { x: (h - 0.5) * 6, y: (hashOf(`${node.id}#`) - 0.5) * 6 },
    // Per-frame motion state. markRaw keeps it out of Vue's reactivity: the rAF
    // loop writes these values straight to the DOM (see paint()), so walking
    // never re-renders the office. Discrete fields below stay reactive.
    m: markRaw({
      x: ENTRANCE.x + (h - 0.5) * 30,
      y: ENTRANCE.y,
      path: [],
      speed: 0,
      sitT: spawn ? 0 : 1,
      frame: 1,
      stride: 0,
    }),
    destKey: '',
    dest: null,
    pose: spawn ? 'walk' : 'sit',
    facing: 'U',
    state: 'idle',
    deskRest: false,
    activity: null,
    bubble: null,
    handoff: null,
    breakSpot: null,
    breakUntil: 0,
    // First coffee break is staggered so the office never empties out at once.
    nextBreakAt: performance.now() + 6000 + h * 40000,
    lastOutput: '',
    task: '', // short brief of the work this person is on (set when a lead delegates to them)
    question: '', // what they are asking the user while waiting
  })
}

const syncAgents = () => {
  const steps = orderSteps(props.graph)
  const existing = new Map(agents.value.map((a) => [a.id, a]))
  const spawn = props.visible && !prefersReducedMotion()
  const list = steps.map((node) => existing.get(node.id) || createAgent(node, spawn))
  const seats = assignSeats(list.map((a) => ({ id: a.id, dept: a.dept })))
  list.forEach((agent, i) => {
    agent.step = i + 1
    agent.seat = seats.get(agent.id)
    agent.color = DEPARTMENT_COLOR[agent.dept] || DEPARTMENT_COLOR.eng
    agent.character = characterFor(agent.id)
  })
  for (const [spot, id] of reservations) if (!list.some((a) => a.id === id)) reservations.delete(spot)
  if (pinnedId.value && !list.some((a) => a.id === pinnedId.value)) pinnedId.value = null
  agents.value = list
  const now = performance.now()
  for (const agent of list) {
    spriteFetcher.preloadCharacter(agent.character)
    if (!existing.has(agent.id) && !spawn) placeAt(agent, resolveDestination(agent, now))
  }
}

// ---------------------------------------------------------------- state
// id -> 'working' | 'waiting' | 'done' from the run record: the current turn first, then
// anyone who worked in an earlier turn of the session counts as done
const trackerStates = computed(() => {
  const tracker = props.tracker
  const states = {}
  if (!tracker) return states
  for (const turn of tracker.turns || []) {
    for (const [id, node] of Object.entries(turn.nodes || {})) if (node?.runs?.length) states[id] = 'done'
  }
  for (const [id, node] of Object.entries(tracker.nodes || {})) {
    const status = stepStatus(node)
    if (status === 'working' || status === 'waiting') states[id] = status
    else if (status !== 'todo') states[id] = 'done'
  }
  return states
})

const computeState = (agent) => {
  const tracked = trackerStates.value[agent.id]
  if (waitingIds.value.has(agent.id) || tracked === 'waiting') return 'waiting'
  // Nobody works once the run is over, even if the Launch view still lists them as active
  if ((isRunning.value && props.activeNodes.includes(agent.id)) || tracked === 'working') return 'working'
  if (hasRun.has(agent.id) || tracked === 'done') return 'done'
  return 'idle'
}

const refreshStates = () => {
  const now = performance.now()
  for (const agent of agents.value) {
    const next = computeState(agent)
    if (next === agent.state) continue
    const prev = agent.state
    agent.state = next
    if (next === 'working' || next === 'waiting') {
      hasRun.add(agent.id)
      agent.handoff = null
      endBreak(agent)
      restoreActivityBubble(agent)
    } else {
      agent.activity = null
      if (prev === 'working' || prev === 'waiting') {
        if (!agent.bubble || THOUGHT_TYPES.includes(agent.bubble.type)) {
          setBubble(agent, 'done', t('launch.office.bubble.done'))
        }
        // Finished a task: take a short break soon.
        agent.nextBreakAt = now + 2500 + Math.random() * 3000
      }
    }
  }
}

const setBubble = (agent, type, text, ttl = BUBBLE_MS[type] ?? 3000, parts = null) => {
  bubbleSeq += 1
  agent.bubble = {
    type,
    text,
    kicker: parts?.kicker || '',
    body: parts?.body || '',
    key: bubbleSeq,
    until: ttl ? performance.now() + ttl : 0,
  }
}

// Text of the persistent "thought" bubble: what this person is doing right now, with details.
// Returns { type, text, kicker, body }: `text` is the one-line form (info card), `kicker` + `body`
// are the two lines of the thought bubble (small caption, then the detail).
const thoughtOf = (agent) => {
  const make = (type, kicker, body) => ({ type, kicker, body, text: body ? `${kicker}: ${body}` : kicker })
  if (agent.state === 'waiting') {
    return agent.question
      ? make('waiting', t('launch.office.bubble.k_decide'), agent.question)
      : make('waiting', t('launch.office.bubble.waiting'), '')
  }
  const act = agent.activity
  if (act?.kind === 'delegate') return make('delegate', t('launch.office.bubble.k_delegate', { name: act.label }), act.detail)
  if (act?.kind === 'ask') return make('waiting', t('launch.office.bubble.k_ask'), act.detail)
  if (act?.kind === 'tool') return make('tool', t('launch.office.bubble.tool', { name: act.label }), '')
  if (agent.task) return make('thinking', t('launch.office.bubble.k_working'), agent.task)
  return make('thinking', t(act ? 'launch.office.bubble.thinking' : 'launch.office.bubble.working'), '')
}
const THOUGHT_TYPES = ['thinking', 'tool', 'waiting', 'delegate']

const restoreActivityBubble = (agent) => {
  if (agent.state === 'waiting' || agent.state === 'working') {
    const thought = thoughtOf(agent)
    setBubble(agent, thought.type, thought.text, 0, thought)
  } else if (agent.bubble && THOUGHT_TYPES.includes(agent.bubble.type)) {
    agent.bubble = null
  }
}

const findAgent = (id) => agents.value.find((a) => a.id === id)

// ---------------------------------------------------------------- breaks & destinations
const endBreak = (agent) => {
  if (agent.breakSpot && reservations.get(agent.breakSpot.id) === agent.id) reservations.delete(agent.breakSpot.id)
  agent.breakSpot = null
  agent.breakUntil = 0
}

const startBreak = (agent, now) => {
  const free = REST_SPOTS.filter((s) => !reservations.has(s.id))
  if (!free.length) return false
  // Prefer spots close to the agent's own room so short breaks stay short.
  const scored = free
    .map((s) => ({ s, d: Math.hypot(s.x - agent.seat.x, s.y - agent.seat.y) + Math.random() * 220 }))
    .sort((a, b) => a.d - b.d)
  const spot = scored[0].s
  reservations.set(spot.id, agent.id)
  agent.breakSpot = spot
  agent.breakUntil = now + 14000 + Math.random() * 22000
  return true
}

// Point next to a colleague's seat where a visitor stands to hand over work.
const visitPoint = (target, visitor) => {
  const seat = target.seat
  const offsets = seat.facing === 'L' || seat.facing === 'R'
    ? [[0, -30], [0, 30], [seat.facing === 'R' ? -26 : 26, 0]]
    : [[30, seat.facing === 'D' ? -4 : 4], [-30, seat.facing === 'D' ? -4 : 4], [0, seat.facing === 'D' ? -26 : 26]]
  for (const [dx, dy] of offsets) {
    const x = seat.x + dx, y = seat.y + dy
    const busy = agents.value.some((a) => a !== visitor && a !== target && Math.hypot(a.m.x - x, a.m.y - y) < 12)
    if (pathfinder.isFreePoint(x, y) && !busy) {
      return { x, y, facing: dx > 0 ? 'L' : dx < 0 ? 'R' : dy > 0 ? 'U' : 'D' }
    }
  }
  return { x: seat.x + 30, y: seat.y, facing: 'L' }
}

// Facing used while relaxing at the desk: turned away from the screen.
const relaxedFacing = (agent) => {
  const f = agent.seat.facing
  if (f === 'L' || f === 'R') return 'D'
  return hashOf(agent.id) > 0.5 ? 'L' : 'R'
}

const resolveDestination = (agent, now) => {
  const seat = agent.seat
  const atDesk = (facing) => ({
    key: `desk:${seat.id}`,
    x: seat.x,
    y: seat.y,
    facing,
    pose: seat.kind === 'stand' ? 'stand' : 'sit',
    seat,
  })

  if ((agent.state === 'working' || agent.state === 'waiting') && !agent.handoff?.force) return atDesk(seat.facing)

  if (agent.handoff) {
    const target = findAgent(agent.handoff.targetId)
    if (target?.seat) {
      const p = agent.handoff.point || (agent.handoff.point = visitPoint(target, agent))
      return { key: `visit:${target.id}`, x: p.x, y: p.y, facing: p.facing, pose: 'stand', visit: true }
    }
    agent.handoff = null
  }

  if (agent.isHuman) return atDesk(seat.facing)

  // Coffee breaks: idle and finished agents get up now and then, then come back.
  if (agent.breakSpot && now > agent.breakUntil && agent.pose !== 'walk') {
    endBreak(agent)
    agent.nextBreakAt = now + 25000 + Math.random() * 45000
  } else if (!agent.breakSpot && now > agent.nextBreakAt && agent.pose !== 'walk') {
    if (!startBreak(agent, now)) agent.nextBreakAt = now + 8000 + Math.random() * 8000
  }

  if (agent.breakSpot) {
    const s = agent.breakSpot
    return { key: `rest:${s.id}`, x: s.x, y: s.y, facing: s.facing, pose: s.kind === 'stand' ? 'stand' : 'sit', seat: s, rest: true }
  }
  return { ...atDesk(relaxedFacing(agent)), deskRest: true }
}

const placeAt = (agent, dest) => {
  agent.destKey = dest.key
  agent.dest = dest
  agent.m.path = []
  agent.m.x = dest.x
  agent.m.y = dest.y
  agent.facing = dest.facing
  agent.pose = dest.pose
  agent.m.sitT = dest.pose === 'sit' ? 1 : 0
  agent.m.speed = 0
  agent.m.frame = 1
  agent.deskRest = !!dest.deskRest
}

// ---------------------------------------------------------------- simulation
const facingFor = (dx, dy, current) => {
  if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) return current
  if (Math.abs(dx) > Math.abs(dy) * 1.2) return dx > 0 ? 'R' : 'L'
  if (Math.abs(dy) > Math.abs(dx) * 1.2) return dy > 0 ? 'D' : 'U'
  return current // diagonal: keep the current facing to avoid flicker
}

const remainingLength = (agent) => {
  let len = 0, px = agent.m.x, py = agent.m.y
  for (const p of agent.m.path) { len += Math.hypot(p.x - px, p.y - py); px = p.x; py = p.y }
  return len
}

// Give every walker its own lane so people sharing a corridor do not overlap.
const laneShift = (agent, path) =>
  path.map((p, i) => {
    if (i === path.length - 1) return p
    const q = { x: p.x + agent.lane.x, y: p.y + agent.lane.y }
    return pathfinder.isFreePoint(q.x, q.y) ? q : p
  })

const onArrive = (agent, now) => {
  const dest = agent.dest
  agent.pose = dest.pose
  agent.facing = dest.facing
  agent.m.frame = 1
  agent.m.speed = 0
  agent.deskRest = !!dest.deskRest
  if (dest.visit && agent.handoff && !agent.handoff.deliveredAt) {
    agent.handoff.deliveredAt = now
    const target = findAgent(agent.handoff.targetId)
    setBubble(agent, 'handoff', t('launch.office.bubble.handoff', { name: target?.label || agent.handoff.targetId }))
    if (target) setBubble(target, 'receive', t('launch.office.bubble.receive', { name: agent.label }))
  }
}

const step = (agent, dt, now, animate) => {
  if (agent.bubble?.until && now > agent.bubble.until) {
    agent.bubble = null
    restoreActivityBubble(agent)
  }
  if (agent.handoff?.deliveredAt && now - agent.handoff.deliveredAt > BUBBLE_MS.handoff) agent.handoff = null

  const dest = resolveDestination(agent, now)
  if (dest.key !== agent.destKey) {
    agent.destKey = dest.key
    agent.dest = dest
    if (!animate) {
      placeAt(agent, dest)
      if (dest.visit) onArrive(agent, now)
      return
    }
    agent.m.path = laneShift(agent, pathfinder.findPath({ x: agent.m.x, y: agent.m.y }, dest))
    agent.pose = 'walk'
  } else if (agent.pose === 'walk') {
    // Same seat, new intent (e.g. work started while walking back): arrive with the right facing.
    // resolveDestination() returns a fresh object every frame; only store real changes so
    // walking does not trigger a re-render per frame.
    const cur = agent.dest
    if (!cur || cur.facing !== dest.facing || cur.pose !== dest.pose || !!cur.deskRest !== !!dest.deskRest) {
      agent.dest = dest
    }
  } else if (dest.facing !== agent.facing || !!dest.deskRest !== agent.deskRest) {
    // Only turning on the chair: towards the screen to work, away from it to relax.
    agent.dest = dest
    agent.facing = dest.facing
    agent.deskRest = !!dest.deskRest
  }

  // Smoothly stand up / sit down.
  const wantSit = agent.pose === 'sit' ? 1 : 0
  if (agent.m.sitT !== wantSit) {
    agent.m.sitT = animate ? Math.max(0, Math.min(1, agent.m.sitT + (wantSit ? 1 : -1) * dt * 6)) : wantSit
  }

  if (agent.pose !== 'walk') return
  if (!animate) {
    placeAt(agent, agent.dest)
    onArrive(agent, now)
    return
  }
  // Stand up before walking off.
  if (agent.m.sitT > 0.05) return

  // Ease in at the start and ease out on the last stretch.
  const remaining = remainingLength(agent)
  agent.m.speed = Math.min(1, agent.m.speed + ACCEL * dt)
  const easeOut = Math.min(1, 0.35 + remaining / 18)
  let budget = WALK_SPEED * agent.m.speed * easeOut * dt
  while (budget > 0 && agent.m.path.length) {
    const target = agent.m.path[0]
    const dx = target.x - agent.m.x, dy = target.y - agent.m.y
    const dist = Math.hypot(dx, dy)
    if (dist <= budget) {
      agent.m.x = target.x
      agent.m.y = target.y
      budget -= dist
      agent.m.stride += dist
      agent.m.path.shift()
    } else {
      agent.m.x += (dx / dist) * budget
      agent.m.y += (dy / dist) * budget
      agent.m.stride += budget
      budget = 0
    }
    agent.facing = facingFor(dx, dy, agent.facing)
  }
  agent.m.frame = WALK_FRAMES[Math.floor(agent.m.stride / STEP_LENGTH) % WALK_FRAMES.length]
  if (!agent.m.path.length) onArrive(agent, now)
}

// The loop runs every frame only while someone walks or sits down / stands up.
// When everyone is settled it drops to a slow timer that just checks break and
// bubble timers; any event (state change, handoff, ...) wakes it immediately.
const IDLE_TICK_MS = 200
let rafId = 0
let idleTimer = 0
let lastTick = 0

const isMoving = (agent) => agent.pose === 'walk' || agent.m.sitT !== (agent.pose === 'sit' ? 1 : 0)

const tick = (time) => {
  rafId = 0
  const dt = Math.min(0.05, (time - (lastTick || time)) / 1000)
  lastTick = time
  const animate = props.visible && !prefersReducedMotion()
  let moving = false
  for (const agent of agents.value) {
    step(agent, dt, time, animate)
    paint(agent)
    if (isMoving(agent)) moving = true
  }
  if (!props.visible) return
  if (moving) {
    rafId = requestAnimationFrame(tick)
  } else {
    idleTimer = setTimeout(() => {
      idleTimer = 0
      lastTick = 0
      rafId = requestAnimationFrame(tick)
    }, IDLE_TICK_MS)
  }
}

const startLoop = () => {
  if (!props.visible || typeof requestAnimationFrame === 'undefined') return
  if (idleTimer) {
    clearTimeout(idleTimer)
    idleTimer = 0
  }
  if (rafId) return
  lastTick = 0
  rafId = requestAnimationFrame(tick)
}

const stopLoop = () => {
  if (rafId) cancelAnimationFrame(rafId)
  if (idleTimer) clearTimeout(idleTimer)
  rafId = 0
  idleTimer = 0
}

// While hidden, keep the logical state current so the office is right when shown
// again. While visible, wake the loop so a new destination is acted on at once.
const settleHidden = () => {
  if (props.visible) {
    startLoop()
    return
  }
  const now = performance.now()
  for (const agent of agents.value) step(agent, 0, now, false)
}

// ---------------------------------------------------------------- direct DOM painting
// agent id -> { root, img, overlay } elements, filled by template function refs.
const agentEls = new Map()
const cardEl = ref(null)

const bindEl = (id, part, el) => {
  let entry = agentEls.get(id)
  if (!entry) {
    if (!el) return
    entry = {}
    agentEls.set(id, entry)
  }
  entry[part] = el || null
  if (part === 'root') entry.img = el ? el.querySelector('.office-agent-sprite') : null
  if (!entry.root && !entry.overlay) agentEls.delete(id)
}

const setStyle = (el, prop, value) => {
  if (el && el.style.getPropertyValue(prop) !== value) el.style.setProperty(prop, value)
}

// Write the values that change every frame straight to the elements. Vue renders
// the same values (agentStyle / overlayStyle / spriteSrc) whenever it re-renders
// for other reasons, so the two never disagree.
const paint = (agent) => {
  const els = agentEls.get(agent.id)
  if (!els) return
  const style = agentStyle(agent)
  if (els.root) {
    setStyle(els.root, 'transform', style.transform)
    setStyle(els.root, 'z-index', String(style.zIndex))
    setStyle(els.root, '--sit', String(style['--sit']))
    if (style['--hero-sprite']) setStyle(els.root, '--hero-sprite', style['--hero-sprite'])
  }
  const src = spriteSrc(agent)
  if (els.img && els.img.getAttribute('src') !== src) els.img.setAttribute('src', src)
  if (els.overlay) setStyle(els.overlay, 'transform', overlayStyle(agent).transform)
  if (cardEl.value && focusId.value === agent.id) {
    const card = cardStyle(agent)
    setStyle(cardEl.value, 'left', card.left)
    setStyle(cardEl.value, 'top', card.top)
    setStyle(cardEl.value, 'transform', card.transform)
  }
}

// ---------------------------------------------------------------- rendering helpers
const spriteSrc = (agent) => buildSpritePath(agent.character, agent.facing, agent.pose === 'walk' ? agent.m.frame : 1)
const avatarSrc = (agent) => buildSpritePath(agent.character, 'D', 1)

const footY = (agent) => agent.m.y + 1 + SIT_DROP * agent.m.sitT

const agentStyle = (agent) => {
  const k = scale.value
  const fy = footY(agent)
  return {
    width: `${SPRITE_W * k}px`,
    height: `${SPRITE_H * k}px`,
    transform: `translate3d(${(agent.m.x - SPRITE_W / 2) * k}px, ${(fy - SPRITE_H) * k}px, 0)`,
    zIndex: Math.round(fy * 2) + 10,
    '--sit': agent.m.sitT,
    // Afterimage source for the hero character's motion trail
    ...(isHeroSprite(agent.character) ? { '--hero-sprite': `url("${spriteSrc(agent)}")` } : {}),
  }
}

const overlayStyle = (agent) => {
  const k = scale.value
  // Sprite art has ~5 px of empty space above the head.
  const headY = footY(agent) - SPRITE_H + 3
  return { transform: `translate3d(${agent.m.x * k}px, ${headY * k}px, 0)` }
}

const cardStyle = (agent) => {
  const k = scale.value
  const right = agent.m.x > OFFICE_WIDTH * 0.6
  const below = agent.m.y < OFFICE_HEIGHT * 0.45
  return {
    left: `${(agent.m.x + (right ? -20 : 20)) * k}px`,
    top: `${(agent.m.y + (below ? -6 : -30)) * k}px`,
    transform: `translate(${right ? '-100%' : '0'}, ${below ? '0' : '-100%'})`,
  }
}

// Monitor glow positions relative to the seat facing direction.
const deskGlows = computed(() =>
  agents.value
    .filter((a) => (a.state === 'working' || a.state === 'waiting') && a.pose === 'sit' && a.destKey.startsWith('desk:'))
    .map((a) => {
      const s = a.seat
      const off = { D: [0, 20], U: [0, -26], L: [-22, 0], R: [22, 0] }[s.facing]
      return { key: a.id, x: s.x + off[0], y: s.y + off[1], tone: a.state === 'waiting' ? 'glow-amber' : 'glow-sky' }
    })
)

const glowStyle = (g) => {
  const k = scale.value
  return { left: `${(g.x - 26) * k}px`, top: `${(g.y - 14) * k}px`, width: `${52 * k}px`, height: `${28 * k}px` }
}

const restBadge = (agent) => {
  if (agent.pose !== 'sit' || agent.state === 'working' || agent.state === 'waiting' || agent.isHuman) return null
  if (agent.deskRest) return 'coffee'
  const kind = agent.dest?.seat?.kind
  if (kind === 'coffee') return 'coffee'
  if (kind === 'sofa') return 'sleep'
  return null
}

const locationRoom = (agent) => {
  if (agent.pose === 'walk') return 'corridor_moving'
  if (agent.dest?.visit) return findAgent(agent.handoff?.targetId)?.seat?.dept || 'corridor'
  return agent.dest?.seat?.dept || agent.seat?.dept || 'corridor'
}

const activityText = (agent) => {
  if (agent.state === 'waiting' || (agent.state === 'working' && ['delegate', 'ask'].includes(agent.activity?.kind))) {
    return thoughtOf(agent).text
  }
  if (agent.state === 'working') {
    if (agent.task && !agent.activity) return t('launch.office.bubble.working_on', { task: agent.task })
    if (agent.activity?.kind === 'tool') return t('launch.office.bubble.tool', { name: agent.activity.label })
    if (agent.activity?.kind === 'model') return t('launch.office.activity.model', { name: agent.activity.label })
    return t('launch.office.bubble.working')
  }
  if (agent.handoff) return t('launch.office.bubble.handoff', { name: findAgent(agent.handoff.targetId)?.label || '' })
  if (agent.pose === 'walk') return t('launch.office.activity.walking')
  if (agent.isHuman) return t('launch.office.activity.standby')
  if (agent.breakSpot) return t('launch.office.activity.break')
  return t(agent.state === 'done' ? 'launch.office.activity.finished' : 'launch.office.activity.no_task')
}

const togglePin = (id) => {
  pinnedId.value = pinnedId.value === id ? null : id
}

const plainSnippet = (output, max = 90) => {
  let text = output
  if (text && typeof text === 'object') {
    try { text = JSON.stringify(text) } catch { text = String(text) }
  }
  text = String(text || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_>`~|-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

// ---------------------------------------------------------------- public API (called by LaunchView)
// `args` are the tool arguments: team tools carry the information shown in the thought bubble
// (delegate_task: who gets which task; ask_user: the question for the user).
const activity = (nodeId, kind, label, running, args = null) => {
  const agent = findAgent(nodeId)
  if (!agent) return
  let entry = { kind, label }
  if (kind === 'tool' && args && typeof args === 'object') {
    if (label === 'delegate_task' && args.member) {
      entry = { kind: 'delegate', label: findAgent(String(args.member))?.label || String(args.member), detail: plainSnippet(args.task, 110) }
      const member = findAgent(String(args.member))
      if (running && member) member.task = plainSnippet(args.task, 120)
    } else if (label === 'ask_user' && args.question) {
      entry = { kind: 'ask', label, detail: plainSnippet(args.question, 140) }
    }
  }
  if (running) agent.activity = entry
  else if (agent.activity && (agent.activity.kind === kind || agent.activity.kind === entry.kind)) agent.activity = null
  if (agent.state === 'working') restoreActivityBubble(agent)
}

const nodeEnd = (nodeId, output) => {
  const agent = findAgent(nodeId)
  if (!agent) return
  hasRun.add(nodeId)
  agent.task = ''
  agent.question = ''
  if (waitingIds.value.has(nodeId)) {
    const next = new Set(waitingIds.value)
    next.delete(nodeId)
    waitingIds.value = next
  }
  const snippet = plainSnippet(output)
  if (snippet) {
    agent.lastOutput = plainSnippet(output, 220)
    setBubble(agent, 'say', snippet)
  }
  refreshStates()
}

// `visit: true` is used for team delegation (lead -> member, member -> lead report): the person
// walks over to the other desk even while still "working", then returns to their own desk.
const handoff = (sourceId, targetId, { visit = false } = {}) => {
  const source = findAgent(sourceId)
  const target = findAgent(targetId)
  if (!source || !target || source === target) return
  const canWalk = !source.isHuman && !!target.seat && !!source.seat
  if (visit && canWalk) {
    endBreak(source)
    source.handoff = { targetId, point: null, deliveredAt: 0, force: true }
    settleHidden()
    return
  }
  if (source.state === 'working' || source.state === 'waiting' || source.isHuman) {
    // Busy (or the human at reception): announce the handoff without walking over.
    setBubble(source, 'handoff', t('launch.office.bubble.handoff', { name: target.label }))
    setBubble(target, 'receive', t('launch.office.bubble.receive', { name: source.label }))
    return
  }
  endBreak(source)
  source.handoff = { targetId, point: null, deliveredAt: 0 }
  settleHidden()
}

// The request a (lead) agent has just received from the user, shown in its thought bubble.
const brief = (nodeId, text) => {
  const agent = findAgent(nodeId)
  const task = plainSnippet(text, 120)
  if (!agent || !task || agent.task) return
  agent.task = task
  if (agent.state === 'working') restoreActivityBubble(agent)
}

const waitingInput = (nodeId, question = '') => {
  if (!nodeId || !findAgent(nodeId)) return
  findAgent(nodeId).question = plainSnippet(question, 160)
  const next = new Set(waitingIds.value)
  next.add(nodeId)
  waitingIds.value = next
  refreshStates()
}

const reset = () => {
  hasRun.clear()
  waitingIds.value = new Set()
  for (const agent of agents.value) {
    agent.activity = null
    agent.bubble = null
    agent.handoff = null
    agent.lastOutput = ''
    agent.task = ''
    agent.question = ''
  }
  refreshStates()
}

defineExpose({ activity, nodeEnd, handoff, waitingInput, brief, reset })

// ---------------------------------------------------------------- watchers / lifecycle
watch(() => props.graph, () => { syncAgents(); refreshStates(); settleHidden() }, { immediate: true })
watch(() => props.spriteMap, () => { for (const a of agents.value) a.character = characterFor(a.id) }, { deep: true })
watch(() => [...props.activeNodes], () => { refreshStates(); settleHidden() })
watch(trackerStates, () => { refreshStates(); settleHidden() })
watch(() => props.status, (status) => {
  if (status !== 'Waiting for input...' && waitingIds.value.size) waitingIds.value = new Set()
  refreshStates()
  settleHidden()
})
watch(() => props.visible, (visible) => {
  if (visible) {
    requestAnimationFrame(() => { measure(); startLoop() })
  } else {
    stopLoop()
    settleHidden()
  }
})

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(measure)
    resizeObserver.observe(rootRef.value)
    if (safeRef.value) resizeObserver.observe(safeRef.value)
  }
  if (props.visible) startLoop()
  else settleHidden()
})

onBeforeUnmount(() => {
  stopLoop()
  onPanEnd()
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.office-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #1c1f26;
  user-select: none;
  font-family: inherit;
}

.office-view.pannable { cursor: grab; }
.office-view.panning { cursor: grabbing; }

.office-safe-area {
  position: absolute;
  top: 0;
  bottom: 0;
  left: var(--office-inset-left, 0px);
  right: 0;
  visibility: hidden;
  pointer-events: none;
}

.office-stage {
  position: absolute;
  top: 0;
  left: 0;
}

/* ---------- zoom controls ---------- */
.office-zoom {
  position: absolute;
  right: 12px;
  bottom: 12px;
  z-index: var(--z-backdrop);
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border-radius: 12px;
  color: #eef1f6;
  background: rgba(17, 20, 27, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
}

.zoom-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 36px;
  height: 36px;
  padding: 0 8px;
  border: 0;
  border-radius: 9px;
  color: inherit;
  background: transparent;
  font: inherit;
  font-size: 12px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), opacity 0.15s var(--ease-out);
}

.zoom-btn svg { width: 15px; height: 15px; flex: none; }
.zoom-btn:hover:not(:disabled) { background: rgba(255, 255, 255, 0.1); }
.zoom-btn:disabled { opacity: 0.45; cursor: default; }
.zoom-btn:focus-visible { outline: 2px solid #7cc7ff; outline-offset: -2px; }
.zoom-level { min-width: 3.2em; text-align: right; }

/* The map and sprites come at 4x/8x resolution: let the browser downsample smoothly
   instead of dropping pixels, which keeps the pixel art crisp at any window size. */
.office-map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  image-rendering: auto;
  pointer-events: none;
}

/* ---------- department plaques ---------- */
.office-plaque {
  position: absolute;
  z-index: 3;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 7px 2px 6px;
  border-radius: 6px;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: #f4f6fa;
  background: rgba(17, 20, 27, 0.94);
  border: 1px solid color-mix(in srgb, var(--dept) 70%, transparent);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  white-space: nowrap;
  pointer-events: none;
}

.plaque-dot {
  width: 6px;
  height: 6px;
  border-radius: 2px;
  background: var(--dept);
}

.plaque-count {
  min-width: 16px;
  padding: 0 4px;
  border-radius: 999px;
  text-align: center;
  font-size: var(--fs-xs);
  /* dept hue darkened under white text: >= 4.5:1 for every department */
  color: #ffffff;
  background: color-mix(in srgb, var(--dept) 55%, #11141b);
}

/* ---------- server LEDs ---------- */
.office-racks {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}

.rack-led {
  position: absolute;
  border-radius: 1px;
  animation: office-led 1.8s steps(2, end) infinite;
}

.office-racks.busy .rack-led {
  animation-duration: 0.45s;
}

.led-green { background: #3ee08f; box-shadow: 0 0 4px #3ee08f; }
.led-amber { background: #f5b84a; box-shadow: 0 0 4px #f5b84a; }
.led-blue { background: #5aa2ff; box-shadow: 0 0 4px #5aa2ff; }

@keyframes office-led {
  0% { opacity: 1; }
  100% { opacity: 0.25; }
}

/* ---------- desk glow ---------- */
.office-desk-glow {
  position: absolute;
  z-index: 4;
  border-radius: 50%;
  pointer-events: none;
  animation: office-glow 2.4s ease-in-out infinite;
}

.glow-sky { background: radial-gradient(closest-side, rgba(126, 205, 255, 0.55), rgba(126, 205, 255, 0)); }
.glow-amber { background: radial-gradient(closest-side, rgba(255, 196, 84, 0.6), rgba(255, 196, 84, 0)); }

@keyframes office-glow {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}

/* ---------- characters ---------- */
.office-agent {
  position: absolute;
  top: 0;
  left: 0;
  will-change: transform;
  cursor: pointer;
}

.office-agent-sprite {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: bottom center;
  image-rendering: auto;
  pointer-events: none;
  transform-origin: 50% 100%;
  /* Hide the legs behind the chair while seated. */
  clip-path: inset(0 0 calc(var(--sit, 0) * 20%) 0);
  transition: filter 0.2s ease;
}

.office-agent-shadow {
  position: absolute;
  left: 20%;
  right: 20%;
  bottom: -3%;
  height: 12%;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(0, 0, 0, 0.45), rgba(0, 0, 0, 0));
  opacity: calc(1 - var(--sit, 0));
  pointer-events: none;
}

.pose-sit.state-working .office-agent-sprite {
  animation: office-typing 0.42s steps(2, end) infinite;
}

.pose-sit.state-idle .office-agent-sprite,
.pose-sit.state-done .office-agent-sprite,
.pose-stand .office-agent-sprite {
  animation: office-breathe 3.4s ease-in-out infinite;
}

.office-agent.hovered .office-agent-sprite {
  filter: drop-shadow(0 0 1.5px #fff) drop-shadow(0 0 4px rgba(126, 205, 255, 0.95));
}

@keyframes office-typing {
  0% { transform: translateY(0); }
  100% { transform: translateY(-1.6%); }
}

@keyframes office-breathe {
  0%, 100% { transform: scaleY(1); }
  50% { transform: scaleY(1.018); }
}

/* ---------- overlay: tag + bubble ---------- */
.office-agent-overlay {
  position: absolute;
  top: 0;
  left: 0;
  z-index: var(--z-sticky);
  width: 0;
  height: 0;
  pointer-events: none;
  will-change: transform;
  transition: opacity 0.2s ease;
}

.office-agent-overlay.dim {
  opacity: 0.35;
}

.office-tag {
  position: absolute;
  left: 0;
  bottom: 0;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 116px;
  padding: 1px 6px 1px 2px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 600;
  line-height: 14px;
  color: #f4f6fa;
  background: rgba(17, 20, 27, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.28);
  white-space: nowrap;
}

.tag-step {
  flex: none;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 800;
  line-height: 14px;
  text-align: center;
  color: #ffffff;
  background: color-mix(in srgb, var(--dept) 55%, #11141b);
}

.tag-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.office-tag.compact {
  gap: 3px;
  padding-right: 4px;
}

.office-tag.compact .tag-name {
  display: none;
}

.tag-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.tag-working .tag-dot { background: #4ade80; box-shadow: 0 0 6px #4ade80; animation: office-pulse 1.4s ease-in-out infinite; }
.tag-waiting .tag-dot { background: #fbbf24; box-shadow: 0 0 6px #fbbf24; animation: office-pulse 1s ease-in-out infinite; }
/* Not colour alone: each state has its own shape (round, diamond, square, ring) */
.tag-waiting .tag-dot { border-radius: 1px; transform: rotate(45deg); }
.tag-done .tag-dot { background: #60a5fa; border-radius: 2px; }
.tag-idle .tag-dot { background: transparent; border: 1.5px solid #9ca3af; }

@keyframes office-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.office-bubble {
  position: absolute;
  left: 0;
  bottom: 20px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 200px;
  padding: 4px 9px;
  border-radius: 10px;
  font-size: var(--fs-xs);
  font-weight: 500;
  line-height: 1.3;
  color: #1c1f27;
  background: #ffffff;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28);
  white-space: nowrap;
}

.office-bubble::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -4px;
  width: 8px;
  height: 8px;
  background: inherit;
  transform: translateX(-50%) rotate(45deg);
  border-radius: 1px;
}

.bubble-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.bubble-say {
  white-space: normal;
  width: max-content;
  max-width: 210px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bubble-thinking { color: #0f5132; background: #e9fbef; }
.bubble-tool { color: #1e3a8a; background: #e8f0ff; }
.bubble-waiting { color: #7a4b00; background: #fff4d6; }
.bubble-handoff, .bubble-receive, .bubble-delegate { color: #4c1d95; background: #f1ebff; }

/* Thought bubbles: what the person is thinking / doing / asking, with details (multi-line cloud) */
.bubble-thinking,
.bubble-delegate,
.bubble-waiting {
  white-space: normal;
  width: max-content;
  max-width: 220px;
  padding: 6px 11px;
  border-radius: 14px;
  align-items: flex-start;
  line-height: 1.35;
}

.bubble-thinking .bubble-text,
.bubble-delegate .bubble-text,
.bubble-waiting .bubble-text {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: clip;
}

/* Two lines: a small caption (what kind of thought) and the detail under it */
.bubble-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.bubble-kicker {
  font-size: var(--fs-xs);
  font-weight: 700;
  opacity: 0.72;
}

.bubble-body .bubble-text {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: #1c1f27;
}

.bubble-thinking,
.bubble-delegate,
.bubble-waiting {
  border: 1px solid rgba(15, 23, 42, 0.08);
}

/* Cloud tail: two shrinking circles instead of the speech-bubble corner */
.bubble-thinking::after,
.bubble-delegate::after,
.bubble-waiting::after {
  bottom: -9px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  transform: translateX(-50%);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.18);
}

.bubble-thinking::before,
.bubble-delegate::before,
.bubble-waiting::before {
  content: '';
  position: absolute;
  left: calc(50% + 6px);
  bottom: -14px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: inherit;
}

/* The user must act: make it stand out */
.bubble-waiting {
  box-shadow: 0 0 0 2px #f5b301, 0 6px 16px rgba(0, 0, 0, 0.3);
  animation: office-need-you 1.6s ease-in-out infinite;
}

@keyframes office-need-you {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(-3px); }
}
.bubble-done { color: #0b4a6f; background: #e3f4ff; }

.bubble-icon { flex: none; width: 12px; height: 12px; }

.bubble-dots { display: inline-flex; gap: 2px; }

.bubble-dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: office-dot 1.2s ease-in-out infinite;
}

.bubble-dots i:nth-child(2) { animation-delay: 0.15s; }
.bubble-dots i:nth-child(3) { animation-delay: 0.3s; }

@keyframes office-dot {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-3px); opacity: 1; }
}

.office-rest-badge {
  position: absolute;
  left: 9px;
  bottom: 17px;
  display: flex;
  gap: 1px;
  color: #e5e7eb;
  font-size: var(--fs-xs);
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}

.office-rest-badge svg {
  width: 13px;
  height: 13px;
  color: #fde68a;
  filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.6));
  animation: office-float 2.6s ease-in-out infinite;
}

.rest-sleep b { animation: office-zzz 2.4s ease-in-out infinite; }
.rest-sleep b:nth-child(2) { font-size: 8px; animation-delay: 0.6s; }

@keyframes office-zzz {
  0% { opacity: 0; transform: translate(0, 2px); }
  40% { opacity: 1; }
  100% { opacity: 0; transform: translate(3px, -6px); }
}

@keyframes office-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

.office-bubble-enter-active,
.office-bubble-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.office-bubble-enter-from,
.office-bubble-leave-to {
  opacity: 0;
  transform: translate(-50%, 4px) scale(0.92);
}

/* ---------- info card ---------- */
.office-card {
  position: absolute;
  z-index: var(--z-dropdown);
  width: 260px;
  padding: 12px;
  border-radius: 12px;
  color: #e8ebf2;
  background: rgba(20, 23, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.45);
  font-size: 12px;
  pointer-events: none;
}

.card-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }

.card-avatar {
  width: 34px;
  height: 43px;
  object-fit: contain;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
}

.card-title { flex: 1; min-width: 0; }

.card-name { font-weight: 700; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.card-type { color: #9aa3b2; font-size: var(--fs-xs); }

.card-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  font-size: var(--fs-xs);
  white-space: nowrap;
}

.card-row { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; }

.card-key { color: #9aa3b2; flex: none; }

.card-val {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-dept { width: 8px; height: 8px; border-radius: 2px; flex: none; }

.card-block { margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.08); }

.card-block p {
  margin: 3px 0 0;
  color: #cfd5df;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.office-card-enter-active,
.office-card-leave-active { transition: opacity 0.15s ease; }

.office-card-enter-from,
.office-card-leave-to { opacity: 0; }

/* ---------- HUD drawer ---------- */
.office-hud-dock {
  --hud-bg: rgba(17, 20, 27, 0.96); /* opaque enough to need no backdrop blur over the animated stage */
  --hud-border: rgba(255, 255, 255, 0.1);
  position: absolute;
  top: 0;
  /* centred in the space not covered by the chat panel (--office-inset-left is set by LaunchView) */
  left: calc(var(--office-inset-left, 0px) + (100% - var(--office-inset-left, 0px)) / 2);
  transform: translateX(-50%);
  z-index: var(--z-backdrop);
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: calc(100% - var(--office-inset-left, 0px) - 24px);
  pointer-events: none;
}

/* Animates height between auto and 0 (grid row trick), so the drawer slides up smoothly. */
.office-hud-drawer {
  display: grid;
  grid-template-rows: 1fr;
  max-width: 100%;
  transition: grid-template-rows 0.32s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.22s ease;
}

.office-hud-clip {
  min-height: 0;
  overflow: hidden;
}

.office-hud-dock.collapsed .office-hud-drawer {
  grid-template-rows: 0fr;
  opacity: 0;
}

.office-hud {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 6px 12px;
  border-radius: 12px;
  color: #eef1f6;
  background: var(--hud-bg);
  border: 1px solid var(--hud-border);
  font-size: 12px;
  flex-wrap: wrap;
  justify-content: center;
  transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
}

.office-hud-dock.collapsed .office-hud {
  transform: translateY(-110%);
}

/* Pull tab under the HUD; once collapsed it hangs from the top edge with a summary. */
.hud-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 20px;
  min-width: 44px;
  margin-top: -1px;
  padding: 0 12px;
  border: 1px solid var(--hud-border);
  border-top: none;
  border-radius: 0 0 10px 10px;
  color: rgba(238, 241, 246, 0.75);
  background: var(--hud-bg);
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 700;
  cursor: pointer;
  pointer-events: auto;
  transition: background-color 0.2s ease, color 0.2s ease, height 0.25s ease;
}

.hud-toggle:hover {
  color: #ffffff;
  background: rgba(32, 36, 46, 0.95);
}

.hud-toggle:focus-visible {
  outline: 2px solid #7cc7ff;
  outline-offset: 2px;
}

.office-hud-dock.collapsed .hud-toggle {
  height: 26px;
  margin-top: 0;
}

.hud-chevron {
  width: 13px;
  height: 13px;
  flex: none;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.office-hud-dock.collapsed .hud-chevron {
  transform: rotate(180deg);
}

.hud-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #eef1f6;
  white-space: nowrap;
}

.hud-summary-staff {
  padding: 0 6px;
  border-radius: 999px;
  line-height: 15px;
  color: #11141b;
  background: #e8ebf2;
}

.hud-summary-sep {
  width: 1px;
  height: 11px;
  background: rgba(255, 255, 255, 0.18);
}

.hud-summary-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.hud-summary-enter-active,
.hud-summary-leave-active {
  transition: opacity 0.2s ease, max-width 0.3s ease;
  overflow: hidden;
}

.hud-summary-enter-from,
.hud-summary-leave-to {
  opacity: 0;
  max-width: 0;
}

.hud-summary-enter-to,
.hud-summary-leave-from {
  max-width: 160px;
}

.hud-title { display: flex; align-items: center; gap: 7px; font-weight: 700; white-space: nowrap; }

.hud-workflow { font-weight: 500; color: #9aa3b2; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }

.hud-staff {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 700;
  color: #11141b;
  background: #e8ebf2;
  white-space: nowrap;
}

.hud-live { width: 8px; height: 8px; border-radius: 50%; background: #6b7280; }

.hud-live.on { background: #ef4444; box-shadow: 0 0 8px #ef4444; animation: office-pulse 1.2s ease-in-out infinite; }

.hud-stats { display: flex; gap: 6px; flex-wrap: wrap; }

.hud-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  white-space: nowrap;
}

/* ---------- roster ---------- */
.office-roster {
  position: absolute;
  left: calc(var(--office-inset-left, 0px) + 12px);
  bottom: 12px;
  z-index: var(--z-backdrop);
  width: 250px;
  max-width: calc(100% - var(--office-inset-left, 0px) - 24px);
  max-height: calc(100% - 70px);
  display: flex;
  flex-direction: column-reverse;
  border-radius: 12px;
  color: #eef1f6;
  background: rgba(17, 20, 27, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
  font-size: 12px;
  overflow: hidden;
}

.office-roster:not(.open) { width: auto; }

.roster-toggle {
  min-height: 40px;
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 8px 11px;
  border: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.roster-toggle svg { width: 15px; height: 15px; flex: none; }

.roster-chevron { margin-left: auto; transition: transform 0.2s ease; }

.office-roster.open .roster-chevron { transform: rotate(180deg); }

.roster-list {
  margin: 0;
  padding: 4px;
  list-style: none;
  overflow-y: auto;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.roster-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 6px;
  border-radius: 8px;
  cursor: pointer;
}

.roster-item:hover,
.roster-item.active { background: rgba(255, 255, 255, 0.08); }

.roster-step { width: 16px; flex: none; text-align: right; color: #9aa3b2; font-size: var(--fs-xs); font-weight: 700; }

.roster-avatar { width: 18px; height: 23px; flex: none; object-fit: contain; }

.roster-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.roster-dept {
  flex: none;
  padding: 0 6px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 700;
  line-height: 15px;
  color: color-mix(in srgb, var(--dept) 55%, #ffffff);
  background: color-mix(in srgb, var(--dept) 22%, transparent);
}

.roster-state { flex: none; display: inline-flex; }

.office-empty {
  position: absolute;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(14, 16, 21, 0.45);
}

.office-empty-card {
  padding: 14px 22px;
  border-radius: 12px;
  color: #eef1f6;
  background: rgba(18, 21, 28, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 14px;
}

.hud-toggle::before { content: ''; position: absolute; inset: -6px; }

.roster-toggle:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; border-radius: 8px; }
.office-agent:focus-visible,
.roster-item:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 8px; }

@media (pointer: coarse) {
  .hud-toggle { height: 44px; }
  .roster-item { min-height: 44px; }
}

@media (max-width: 640px) {
  .office-roster { max-width: calc(100vw - 24px); }
  .office-hud { max-width: calc(100vw - 24px); }
}

@media (prefers-reduced-motion: reduce) {
  .office-hud-drawer,
  .office-hud,
  .hud-chevron {
    transition: none !important;
  }

  .office-agent-sprite,
  .office-desk-glow,
  .rack-led,
  .tag-dot,
  .bubble-dots i,
  .office-rest-badge svg,
  .rest-sleep b {
    animation: none !important;
  }
}
</style>
