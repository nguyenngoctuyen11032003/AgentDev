<template>
  <article
    :class="['proposal-card', { superseded: superseded || conflicted, applied, inactive: !active && !applied, collapsed }]"
    :aria-label="$t('workflow_assistant.proposal.aria', { file: proposal.filename })"
  >
    <header class="proposal-head">
      <span :class="['proposal-kind', proposal.kind]">
        {{ proposal.kind === 'create' ? $t('workflow_assistant.proposal.kind_create') : $t('workflow_assistant.proposal.kind_edit') }}
      </span>
      <span v-if="number" class="proposal-version">{{ $t('workflow_assistant.proposal.version', { n: number }) }}</span>
      <code class="proposal-file" :title="proposal.filename">{{ proposal.filename }}</code>
      <span v-if="applied" class="proposal-state ok">{{ $t('workflow_assistant.proposal.applied') }}</span>
      <span v-else-if="conflicted" class="proposal-state">{{ $t('workflow_assistant.proposal.conflicted') }}</span>
      <span v-else-if="superseded" class="proposal-state old">{{ $t('workflow_assistant.proposal.superseded') }}</span>
      <span v-else-if="!active" class="proposal-state">{{ $t('workflow_assistant.proposal.discarded') }}</span>
      <span v-else class="proposal-state latest">{{ $t('workflow_assistant.proposal.latest') }}</span>
    </header>

    <!-- Replaced, discarded or out of date: one line is enough, the full card stays above/below. -->
    <p v-if="collapsed" class="proposal-summary">{{ summaryLine }}</p>

    <template v-else>
      <!-- What changes, computed by the backend from the two YAML files (not from the AI's words) -->
      <div class="proposal-changes">
        <p v-if="!groups.length" class="proposal-empty">{{ $t('workflow_assistant.proposal.no_changes') }}</p>
        <div v-for="group in groups" :key="group.key" :class="['change-group', group.tone]">
          <div class="change-title">{{ group.title }} <span class="change-count">{{ group.items.length }}</span></div>
          <ul class="change-list">
            <li v-for="item in group.items" :key="item.key">
              <code>{{ item.label }}</code>
              <span v-if="item.fields?.length" class="change-fields">
                <code v-for="field in item.fields" :key="field" class="field">{{ field }}</code>
              </span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Tools that run commands on this machine, reach the network or run code: high severity. -->
      <ul v-if="dangers.length" class="proposal-dangers" :aria-label="$t('workflow_assistant.proposal.dangers')">
        <li v-for="item in dangers" :key="item.key" class="danger-chip">
          <svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3Z" /><path d="M12 10v4M12 18h.01" /></svg>
          <span>{{ item.text }}</span>
        </li>
      </ul>

      <!-- Changes the user never asked for, and checks that did not fully pass. Never block Apply. -->
      <ul v-if="warnings.length" class="proposal-warnings" :aria-label="$t('workflow_assistant.proposal.warnings')">
        <li v-for="item in warnings" :key="item.key" class="warning-chip">
          <svg aria-hidden="true" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3Z" /><path d="M12 10v4M12 18h.01" /></svg>
          <span class="warning-body">
            <span v-if="item.title" class="warning-title">{{ item.title }}: </span>{{ item.text }}
            <details v-if="item.detail" class="warning-more">
              <summary>{{ $t('workflow_assistant.error_detail') }}</summary>
              <code class="warning-detail">{{ item.detail }}</code>
            </details>
          </span>
        </li>
      </ul>

      <WorkflowGraphPreview v-if="graph" :graph="graph" :diff="proposal.kind === 'edit' ? proposal.diff_summary : null" />

      <details class="proposal-yaml">
        <summary>{{ $t('workflow_assistant.proposal.show_yaml') }}</summary>
        <div class="yaml-actions">
          <button type="button" class="btn-ghost btn-compact" @click="copyYaml">
            {{ $t('workflow_assistant.proposal.copy_yaml') }}
          </button>
          <button type="button" class="btn-ghost btn-compact" @click="downloadYaml">
            {{ $t('workflow_assistant.proposal.download_yaml') }}
          </button>
        </div>
        <pre><code>{{ proposal.yaml }}</code></pre>
      </details>
    </template>

    <footer v-if="active" class="proposal-actions">
      <button type="button" class="btn-ghost" :disabled="busy" @click="emit('discard')">
        {{ $t('workflow_assistant.proposal.discard') }}
      </button>
      <button
        type="button"
        :class="['btn-primary', { danger: confirming }]"
        :disabled="busy"
        @click="onApply"
      >
        {{ applyLabel }}
      </button>
    </footer>
    <!-- An older version: Apply stays visible but disabled, so it is clear this one cannot be saved. -->
    <footer v-else-if="superseded && !applied && !conflicted" class="proposal-actions">
      <button type="button" class="btn-ghost btn-compact" disabled :title="$t('workflow_assistant.proposal.superseded')">
        {{ $t('workflow_assistant.proposal.apply') }}
      </button>
    </footer>
    <footer v-else-if="applied && canUndo" class="proposal-actions">
      <button type="button" class="btn-ghost" @click="emit('undo')">
        {{ $t('workflow_assistant.undo') }}
      </button>
    </footer>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import yaml from 'js-yaml'
import WorkflowGraphPreview from './WorkflowGraphPreview.vue'
import { toast } from '@/utils/toast.js'

const props = defineProps({
  proposal: { type: Object, required: true },
  // "Version N" of the thread (1-based); 0 hides the label.
  number: { type: Number, default: 0 },
  // A newer proposal replaced this one.
  superseded: { type: Boolean, default: false },
  // The file changed after this proposal was made, so it was not saved (and is no longer pending).
  conflicted: { type: Boolean, default: false },
  // Apply / a reply is in progress: the buttons are disabled.
  busy: { type: Boolean, default: false },
  // This proposal is being written right now (label "Applying…").
  applying: { type: Boolean, default: false },
  // This is the thread's pending proposal: Apply / Discard are offered.
  active: { type: Boolean, default: false },
  applied: { type: Boolean, default: false },
  // This applied proposal is the one Undo would revert: the card offers Undo too.
  canUndo: { type: Boolean, default: false }
})
const emit = defineEmits(['apply', 'discard', 'undo'])
const { t, te } = useI18n()

const collapsed = computed(() => !props.applied && !props.active)

const graph = computed(() => {
  try {
    const doc = yaml.load(props.proposal.yaml)
    return doc && typeof doc.graph === 'object' ? doc.graph : null
  } catch {
    return null
  }
})

// ---------------------------------------------------------------- copy / download the YAML
// navigator.clipboard needs a secure context (https, localhost); over http on a LAN address fall
// back to a hidden textarea + execCommand('copy').
function copyWithTextarea(text) {
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '0'
  area.style.left = '0'
  area.style.opacity = '0'
  document.body.appendChild(area)
  const active = document.activeElement
  area.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(area)
  active?.focus?.()
  return ok
}

async function copyYaml() {
  const text = props.proposal.yaml ?? ''
  let ok = false
  try {
    if (typeof navigator.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(text)
      ok = true
    }
  } catch {
    ok = false
  }
  if (!ok) ok = copyWithTextarea(text)
  if (ok) toast.success(t('workflow_assistant.proposal.copied'))
  else toast.error(t('workflow_assistant.proposal.copy_failed'))
}

function downloadYaml() {
  const name = String(props.proposal.filename || 'workflow.yaml')
  const filename = /\.ya?ml$/i.test(name) ? name : `${name}.yaml`
  const url = URL.createObjectURL(new Blob([props.proposal.yaml ?? ''], { type: 'application/x-yaml' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // Revoke later: some browsers start the download only after the click handler returns.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const edgeLabel = (e) => `${e?.from} → ${e?.to}`

const groups = computed(() => {
  const d = props.proposal.diff_summary || {}
  const list = [
    {
      key: 'nodes_added',
      tone: 'add',
      title: t('workflow_assistant.proposal.nodes_added'),
      items: (d.nodes_added || []).map((id) => ({ key: id, label: id }))
    },
    {
      key: 'nodes_removed',
      tone: 'remove',
      title: t('workflow_assistant.proposal.nodes_removed'),
      items: (d.nodes_removed || []).map((id) => ({ key: id, label: id }))
    },
    {
      key: 'nodes_changed',
      tone: 'change',
      title: t('workflow_assistant.proposal.nodes_changed'),
      items: (d.nodes_changed || []).map((n) => ({ key: n.id, label: n.id, fields: n.fields }))
    },
    {
      key: 'edges_added',
      tone: 'add',
      title: t('workflow_assistant.proposal.edges_added'),
      items: (d.edges_added || []).map((e, i) => ({ key: `${i}:${edgeLabel(e)}`, label: edgeLabel(e) }))
    },
    {
      key: 'edges_removed',
      tone: 'remove',
      title: t('workflow_assistant.proposal.edges_removed'),
      items: (d.edges_removed || []).map((e, i) => ({ key: `${i}:${edgeLabel(e)}`, label: edgeLabel(e) }))
    },
    {
      key: 'edges_changed',
      tone: 'change',
      title: t('workflow_assistant.proposal.edges_changed'),
      items: (d.edges_changed || []).map((e, i) => ({ key: `${i}:${edgeLabel(e)}`, label: edgeLabel(e), fields: e.fields }))
    },
    {
      key: 'graph_fields_changed',
      tone: 'change',
      title: t('workflow_assistant.proposal.graph_changed'),
      items: (d.graph_fields_changed || []).map((f) => ({ key: f, label: f }))
    }
  ]
  // A new workflow has no previous settings to compare with.
  return list.filter((g) => g.items.length && !(props.proposal.kind === 'create' && g.key === 'graph_fields_changed'))
})

const summaryLine = computed(() =>
  groups.value.length
    ? groups.value.map((g) => `${g.title}: ${g.items.length}`).join(' · ')
    : t('workflow_assistant.proposal.no_changes')
)

// `proposal.checks` is the static check summary ({status, checks: [...]}).
const checkList = computed(() => {
  const checks = props.proposal.checks
  const list = Array.isArray(checks) ? checks : checks?.checks
  return Array.isArray(list) ? list : []
})

// dangerous_tools (backend): one chip per tool that runs a local command, calls out to the
// network or can run code. Absent → nothing shown.
const DANGER_KINDS = ['mcp_local', 'mcp_remote', 'code_execution']
const dangers = computed(() => {
  const check = checkList.value.find((c) => c?.id === 'dangerous_tools')
  const items = Array.isArray(check?.items) ? check.items : []
  return items
    .filter((item) => item && typeof item === 'object')
    .map((item, i) => {
      const kind = DANGER_KINDS.includes(item.kind) ? item.kind : 'other'
      const params = { node: String(item.node ?? '?'), detail: String(item.detail ?? '') }
      return { key: `d:${i}:${params.node}:${kind}`, text: t(`workflow_assistant.proposal.danger.${kind}`, params) }
    })
})

const checkTitle = (id) => (te(`lab.checks.${id}.title`) ? t(`lab.checks.${id}.title`) : '')
const checkText = (id) =>
  te(`workflow_assistant.checks.${id}`) ? t(`workflow_assistant.checks.${id}`) : t('workflow_assistant.checks.other')

const warnings = computed(() => {
  const items = (props.proposal.warnings || []).map((id) => ({
    key: `w:${id}`,
    text: t('workflow_assistant.proposal.also_changes', { id })
  }))
  // WARN checks, plus an `accounts` FAIL (no connection bound on this machine yet): shown, not
  // blocking. The headline is a short localised sentence; the backend's raw text (English, YAML
  // paths) only sits behind "Details".
  for (const check of checkList.value) {
    if (!check || check.id === 'dangerous_tools') continue
    if (check.status === 'warn' || (check.status === 'fail' && check.id === 'accounts')) {
      items.push({
        key: `c:${check.id}`,
        title: checkTitle(check.id),
        text: checkText(check.id),
        detail: check.detail || ''
      })
    }
  }
  return items
})

// With dangerous tools, Apply takes a second, deliberate click ("I understand the risk").
const confirming = ref(false)
watch(
  () => props.proposal,
  () => {
    confirming.value = false
  }
)
const applyLabel = computed(() => {
  if (props.applying) return t('workflow_assistant.proposal.applying')
  return confirming.value ? t('workflow_assistant.proposal.confirm_danger') : t('workflow_assistant.proposal.apply')
})
const onApply = (event) => {
  if (dangers.value.length) {
    // The second click of a double click is not a confirmation.
    if (event?.detail > 1) return
    if (!confirming.value) {
      confirming.value = true
      return
    }
  }
  emit('apply')
}
</script>

<style scoped>
.proposal-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: rgb(var(--ink) / 0.03);
}

.proposal-card.superseded,
.proposal-card.inactive {
  opacity: 0.75;
}

.proposal-card.collapsed {
  gap: 6px;
  padding: 8px 12px;
}

.proposal-summary {
  margin: 0;
  font-size: 12px;
  color: var(--text-soft-1);
}

.proposal-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.proposal-kind {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: rgb(var(--accent-sky-rgb) / 0.14);
  color: var(--accent-sky);
}

.proposal-file {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
}

.proposal-state {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted-1);
}

.proposal-state.ok {
  color: var(--accent-green-1);
  font-weight: 600;
}

.proposal-state.latest {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgb(var(--accent-sky-rgb) / 0.14);
  color: var(--accent-sky);
  font-weight: 600;
}

.proposal-state.old {
  color: var(--warn-soft-1);
  font-weight: 600;
}

.proposal-version {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-soft-1);
}

.yaml-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.btn-ghost.btn-compact {
  padding: 4px 10px;
  font-size: 12px;
}

.proposal-changes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.proposal-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted-1);
}

.change-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(var(--ink) / 0.6);
}

.change-group.add .change-title { color: var(--accent-green-1); }
.change-group.remove .change-title { color: var(--danger); }
.change-group.change .change-title { color: var(--warn-soft-1); }

.change-count {
  padding: 0 6px;
  border-radius: 999px;
  background: rgb(var(--ink) / 0.08);
  color: var(--text-1);
  font-weight: 600;
}

.change-list {
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
}

.change-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}

.change-list code {
  color: var(--text-1);
  word-break: break-word;
}

.change-group.remove .change-list > li > code {
  text-decoration: line-through;
}

.change-fields {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}

.change-fields .field {
  padding: 0 5px;
  border-radius: 4px;
  background: rgb(var(--ink) / 0.07);
  font-size: 11px;
  color: var(--text-soft-1);
}

.proposal-warnings {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.warning-chip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.08);
  background: color-mix(in srgb, var(--warn-soft-1) 12%, transparent);
  color: var(--warn-soft-1);
  font-size: 12px;
  line-height: 1.4;
}

.warning-chip svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.warning-title {
  font-weight: 600;
}

.warning-more summary {
  cursor: pointer;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-soft-1);
}

.warning-more summary:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
  border-radius: 4px;
}

.proposal-dangers {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.danger-chip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--danger) 55%, transparent);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
  color: var(--text-1);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-word;
}

.danger-chip svg {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--danger);
}

.warning-detail {
  display: block;
  margin-top: 2px;
  color: var(--text-soft-1);
  font-size: 11px;
  word-break: break-word;
}

.proposal-yaml summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft-1);
}

.proposal-yaml summary:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
  border-radius: 4px;
}

.proposal-yaml pre {
  margin: 8px 0 0;
  max-height: 280px;
  overflow: auto;
  padding: 10px;
  border-radius: 8px;
  background: rgb(var(--ink) / 0.05);
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-1);
}

.proposal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-ghost,
.btn-primary {
  padding: 7px 14px;
  border-radius: 9px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgb(var(--ink) / 0.14);
}

.btn-ghost {
  background: transparent;
  color: var(--text-1);
}

.btn-ghost:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.06);
}

.btn-primary {
  background: var(--accent-sky);
  border-color: transparent;
  color: #05141f;
}

:root[data-theme="light"] .btn-primary {
  color: #fff;
}

.btn-primary.danger {
  background: var(--danger);
  color: #05141f;
}

:root[data-theme="light"] .btn-primary.danger {
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
}

.btn-ghost:disabled,
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost:focus-visible,
.btn-primary:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}
</style>
