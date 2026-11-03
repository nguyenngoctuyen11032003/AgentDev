<template>
  <article
    :class="['proposal-card', { superseded, applied, inactive: !active && !applied }]"
    :aria-label="$t('workflow_assistant.proposal.aria', { file: proposal.filename })"
  >
    <header class="proposal-head">
      <span :class="['proposal-kind', proposal.kind]">
        {{ proposal.kind === 'create' ? $t('workflow_assistant.proposal.kind_create') : $t('workflow_assistant.proposal.kind_edit') }}
      </span>
      <code class="proposal-file" :title="proposal.filename">{{ proposal.filename }}</code>
      <span v-if="applied" class="proposal-state ok">{{ $t('workflow_assistant.proposal.applied') }}</span>
      <span v-else-if="superseded" class="proposal-state">{{ $t('workflow_assistant.proposal.superseded') }}</span>
      <span v-else-if="!active" class="proposal-state">{{ $t('workflow_assistant.proposal.discarded') }}</span>
    </header>

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

    <!-- Changes the user never asked for, and checks that did not fully pass. Never block Apply. -->
    <ul v-if="warnings.length" class="proposal-warnings" :aria-label="$t('workflow_assistant.proposal.warnings')">
      <li v-for="item in warnings" :key="item.key" class="warning-chip">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3Z" /><path d="M12 10v4M12 18h.01" /></svg>
        <span>{{ item.text }}<code v-if="item.detail" class="warning-detail">{{ item.detail }}</code></span>
      </li>
    </ul>

    <WorkflowGraphPreview v-if="graph" :graph="graph" :diff="proposal.kind === 'edit' ? proposal.diff_summary : null" />

    <details class="proposal-yaml">
      <summary>{{ $t('workflow_assistant.proposal.show_yaml') }}</summary>
      <pre><code>{{ proposal.yaml }}</code></pre>
    </details>

    <footer v-if="active" class="proposal-actions">
      <button type="button" class="btn-ghost" :disabled="busy" @click="emit('discard')">
        {{ $t('workflow_assistant.proposal.discard') }}
      </button>
      <button type="button" class="btn-primary" :disabled="busy" @click="emit('apply')">
        {{ applying ? $t('workflow_assistant.proposal.applying') : $t('workflow_assistant.proposal.apply') }}
      </button>
    </footer>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import yaml from 'js-yaml'
import WorkflowGraphPreview from './WorkflowGraphPreview.vue'

const props = defineProps({
  proposal: { type: Object, required: true },
  // A newer proposal replaced this one.
  superseded: { type: Boolean, default: false },
  // Apply / a reply is in progress: the buttons are disabled.
  busy: { type: Boolean, default: false },
  // This proposal is being written right now (label "Applying…").
  applying: { type: Boolean, default: false },
  // This is the thread's pending proposal: Apply / Discard are offered.
  active: { type: Boolean, default: false },
  applied: { type: Boolean, default: false }
})
const emit = defineEmits(['apply', 'discard'])
const { t, te } = useI18n()

const graph = computed(() => {
  try {
    const doc = yaml.load(props.proposal.yaml)
    return doc && typeof doc.graph === 'object' ? doc.graph : null
  } catch {
    return null
  }
})

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

const checkTitle = (id) => (te(`lab.checks.${id}.title`) ? t(`lab.checks.${id}.title`) : id)

const warnings = computed(() => {
  const items = (props.proposal.warnings || []).map((id) => ({
    key: `w:${id}`,
    text: t('workflow_assistant.proposal.also_changes', { id })
  }))
  // WARN checks, plus an `accounts` FAIL (no connection bound on this machine yet): shown, not blocking.
  for (const check of props.proposal.checks?.checks || []) {
    if (check.status === 'warn' || (check.status === 'fail' && check.id === 'accounts')) {
      items.push({ key: `c:${check.id}`, text: checkTitle(check.id), detail: check.detail || '' })
    }
  }
  return items
})
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
  opacity: 0.6;
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
