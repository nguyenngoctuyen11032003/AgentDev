<template>
  <div class="control-section" role="region" :aria-label="$t('launch.panel.toggle')">
    <div v-if="showHead" class="sheet-head">
      <span v-if="showGrip" class="sheet-grip" aria-hidden="true"></span>
      <h2 class="sheet-title">{{ $t('launch.panel.toggle') }}</h2>
      <button type="button" class="chat-header-btn" :aria-label="$t('launch.panel.close')" :title="$t('launch.panel.close')" @click="emit('close')">
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
      </button>
    </div>

    <section class="panel-block">
      <label class="panel-heading" for="launch-workflow-select">{{ $t('launch.workflow_selection') }}</label>
      <div ref="picker" class="workflow-picker" :class="{ 'needs-workflow': !selectedFile && !loading, nudge: pickerNudge }">
        <BaseSkeleton v-if="loading && !workflowFiles.length" height="40px" radius="10px" />
        <BaseSelect
          v-else
          id="launch-workflow-select"
          :model-value="selectedFile"
          :disabled="loading || isWorkflowRunning"
          @update:model-value="emit('select-workflow', $event)"
        >
          <option value="" disabled>{{ loading ? $t('launch.loading') : $t('launch.select_yaml') }}</option>
          <option v-for="workflow in workflowFiles" :key="workflow.name" :value="workflow.name">{{ workflow.name.replace(/\.ya?ml$/i, '') }}</option>
        </BaseSelect>
      </div>
      <template v-if="selectedDescription">
        <p id="launch-workflow-desc" ref="descriptionRef" class="panel-note" :class="{ 'is-clamped': !isDescriptionOpen }">{{ selectedDescription }}</p>
        <button
          v-if="isDescriptionLong"
          type="button"
          class="panel-link"
          aria-controls="launch-workflow-desc"
          :aria-expanded="isDescriptionOpen"
          @click="isDescriptionOpen = !isDescriptionOpen"
        >{{ isDescriptionOpen ? $t('components.collapsible_message.show_less') : $t('components.collapsible_message.show_more') }}</button>
      </template>
      <p v-if="workflowHint" class="workflow-hint">{{ workflowHint }}</p>
    </section>

    <!-- Details of this run; its state itself is the chip in the chat header -->
    <section v-if="runFacts.length" class="panel-block">
      <h3 class="panel-heading">{{ $t('launch.panel.run') }}</h3>
      <dl class="status-facts">
        <div v-for="fact in runFacts" :key="fact.key" class="status-fact">
          <dt>{{ fact.label }}</dt>
          <dd :class="{ 'is-num': fact.numeric }">
            <LiveDuration v-if="fact.key === 'elapsed'" :started-at="startedAt" :ended-at="endedAt || 0" />
            <template v-else>{{ fact.value }}</template>
          </dd>
        </div>
      </dl>
    </section>

    <section v-if="selectedFile" class="panel-block">
      <div class="panel-heading-row">
        <h3 class="panel-heading">{{ $t('launch.panel.team') }}</h3>
        <button v-if="teamSize" type="button" class="panel-link" @click="emit('open-team')">{{ $t('launch.panel.team_all', { n: teamSize }) }}</button>
      </div>
      <ul v-if="teamMembers.length" class="team-list">
        <li v-for="member in teamMembers" :key="member.id" class="team-row">
          <span class="team-avatar" aria-hidden="true">
            <img v-if="member.sprite" :src="member.sprite" alt="" />
          </span>
          <span class="team-name" :title="member.id">{{ member.id }}</span>
          <StatusPill compact :tone="member.status" :label="$t(`launch.panel.step_${member.status}`)" />
        </li>
      </ul>
      <p v-else class="panel-note">{{ $t('launch.panel.team_empty') }}</p>
    </section>

    <section v-if="selectedFile" class="panel-block">
      <h3 class="panel-heading">{{ $t('launch.panel.activity') }}</h3>
      <ol v-if="recentEvents.length" class="activity-feed">
        <li v-for="event in recentEvents" :key="event.id" class="activity-feed-item">
          <span class="activity-feed-text">{{ event.text }}</span>
          <time class="activity-feed-time">{{ formatTime(event.at) }}</time>
        </li>
      </ol>
      <p v-else class="panel-note">{{ $t('launch.panel.activity_empty') }}</p>
    </section>

    <!-- Starting, continuing and stopping a run all live in the composer; only the log export stays here -->
    <div class="button-section">
      <button
        type="button"
        class="btn secondary sm"
        :disabled="!isRunFinished"
        @click="emit('download-logs')"
      >
        {{ $t('launch.download_logs') }}
      </button>
    </div>
  </div>
</template>

<script setup>
// The Launch view's control panel: workflow picker and description, run facts, the team of
// the run, recent activity and the log export. Lives in a column (chat view), a drawer
// (other views) or a bottom sheet (narrow); the parent decides where and when it shows.
import { ref, watch, nextTick, onUnmounted } from 'vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import BaseSkeleton from '@/components/ui/BaseSkeleton.vue'
import StatusPill from '@/components/launch/StatusPill.vue'
import LiveDuration from '@/components/common/LiveDuration.js'

const props = defineProps({
  // Header with a close button (drawer and sheet); the grip only on the sheet
  showHead: { type: Boolean, default: false },
  showGrip: { type: Boolean, default: false },
  // The panel is on screen (re-measures the description)
  visible: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  workflowFiles: { type: Array, default: () => [] },
  selectedFile: { type: String, default: '' },
  isWorkflowRunning: { type: Boolean, default: false },
  pickerNudge: { type: Boolean, default: false },
  selectedDescription: { type: String, default: '' },
  workflowHint: { type: String, default: '' },
  runFacts: { type: Array, default: () => [] },
  startedAt: { type: Number, default: 0 },
  endedAt: { type: Number, default: 0 },
  teamSize: { type: Number, default: 0 },
  teamMembers: { type: Array, default: () => [] },
  recentEvents: { type: Array, default: () => [] },
  isRunFinished: { type: Boolean, default: false },
  formatTime: { type: Function, required: true }
})
const emit = defineEmits(['close', 'select-workflow', 'open-team', 'download-logs'])

// The workflow picker's box: the parent focuses its <select> (see focusWorkflowPicker)
const picker = ref(null)
defineExpose({ picker })

// A long workflow description folds to three lines
const isDescriptionOpen = ref(false)
const isDescriptionLong = ref(false)
const descriptionRef = ref(null)
// The toggle shows only when three lines really cut the text (measured, so the panel's
// width - column, drawer or sheet - decides)
const measureDescription = () => {
  const el = descriptionRef.value
  if (!el || isDescriptionOpen.value) return
  isDescriptionLong.value = el.scrollHeight > el.clientHeight + 1
}
let descriptionObserver = null
watch(descriptionRef, (el, previous) => {
  if (previous) descriptionObserver?.unobserve(previous)
  if (!el || typeof ResizeObserver === 'undefined') return
  if (!descriptionObserver) descriptionObserver = new ResizeObserver(() => measureDescription())
  descriptionObserver.observe(el)
})
watch(() => props.selectedFile, () => { isDescriptionOpen.value = false })
watch([() => props.selectedDescription, () => props.visible], () => nextTick(measureDescription))
onUnmounted(() => descriptionObserver?.disconnect())
</script>

<style scoped>
/* Moved from LaunchView (rules whose element lives in this panel), in their original order.
   The panel root (.control-section) is styled by LaunchView. */
.workflow-hint {
  margin: -2px 0 2px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(var(--ink) / 0.5);
}

.chat-header-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--ink) / 0.65);
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.chat-header-btn:hover {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-1);
}

.chat-header-btn:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.chat-header-btn { position: relative; color: var(--fg-muted); }

.chat-header-btn:hover { background: var(--surface-raised); color: var(--fg); }

.panel-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-4) 0;
}

.panel-block + .panel-block { border-top: 1px solid var(--border); }

.control-section > .button-section { padding-top: var(--space-4); border-top: 1px solid var(--border); }

.panel-heading-row { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }

.panel-link {
  align-self: flex-start;
  min-height: 28px;
  padding: 2px 6px;
  margin-left: -6px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.panel-heading-row .panel-link { margin: 0 -6px 0 0; }

.panel-link:hover { background: var(--surface-raised); text-decoration: underline; text-underline-offset: 3px; }

.panel-link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.panel-note.is-clamped {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
}

.team-list { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; }

.team-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
  min-width: 0;
}

.team-avatar {
  flex: none;
  display: grid;
  place-items: end center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  border: 1px solid var(--border);
  overflow: hidden;
}

.team-avatar img { width: 22px; height: 22px; object-fit: contain; object-position: 50% 100%; image-rendering: pixelated; }

.team-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 550;
  color: var(--fg);
}

.activity-feed { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }

.activity-feed-item { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; font-size: 13px; line-height: 1.4; }

.activity-feed-text {
  flex: 1;
  min-width: 0;
  color: var(--fg);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.activity-feed-time { flex: none; font-size: 12px; color: var(--fg-muted); font-variant-numeric: tabular-nums; }

.panel-heading {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  color: var(--fg);
}

.panel-note,
.workflow-hint { margin: 0; font-size: 12px; line-height: 1.5; color: var(--fg-muted); }

.workflow-picker { border-radius: var(--radius-md); }

.workflow-picker.needs-workflow :deep(.select) {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}

.workflow-picker.nudge { animation: nudge 0.9s var(--ease-out) 2; }

.status-facts { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; }

.status-fact { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); }

.status-fact dt { flex: none; font-size: 12px; color: var(--fg-muted); }

.status-fact dd { margin: 0; min-width: 0; font-size: 13px; color: var(--fg); text-align: right; overflow-wrap: anywhere; }

.status-fact dd.is-num { font-variant-numeric: tabular-nums; }

.button-section { display: flex; flex-direction: column; gap: var(--space-2); }

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  position: relative;
  margin-right: calc(var(--space-2) * -1);
  padding-top: var(--space-1);
}

.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--fg); }

@media (max-width: 899.98px) {
  .chat-header-btn { width: 40px; height: 40px; }
  .sheet-head { padding-top: var(--space-2); }
  .sheet-grip {
    position: absolute;
    top: -4px;
    left: 50%;
    width: 36px;
    height: 4px;
    margin-left: -18px;
    border-radius: 2px;
    background: var(--border-strong);
  }
}

@keyframes nudge {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 0%, transparent); }
  50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 35%, transparent); }
}
</style>
