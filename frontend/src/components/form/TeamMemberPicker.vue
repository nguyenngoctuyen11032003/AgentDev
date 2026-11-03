<template>
  <div class="member-picker">
    <div class="picker-head">
      <span class="picker-hint">{{ $t('dynamic_form_field.team_members_hint') }}</span>
      <span class="picker-count">{{ $t('dynamic_form_field.team_members_selected', { count: selected.length }) }}</span>
      <button
        v-if="options.length"
        type="button"
        class="picker-all"
        :disabled="disabled"
        @click="toggleAll"
      >
        {{ allTicked ? $t('dynamic_form_field.team_members_none') : $t('dynamic_form_field.team_members_all') }}
      </button>
    </div>

    <p v-if="!rows.length" class="picker-empty">{{ $t('dynamic_form_field.team_members_empty') }}</p>
    <ul v-else class="picker-list" :aria-label="label">
      <li v-for="row in rows" :key="row.id">
        <label class="picker-item" :class="{ checked: selected.includes(row.id), missing: row.missing }">
          <input
            type="checkbox"
            :checked="selected.includes(row.id)"
            :disabled="disabled"
            @change="toggle(row.id, $event.target.checked)"
          />
          <span class="item-text">
            <span class="item-name">{{ row.id }}</span>
            <span class="item-desc">
              {{ row.missing ? $t('dynamic_form_field.team_members_missing') : (row.description || $t('dynamic_form_field.team_members_no_desc')) }}
            </span>
          </span>
        </label>
      </li>
    </ul>

    <form class="picker-add" @submit.prevent="addTyped">
      <input
        v-model="typed"
        type="text"
        class="picker-input"
        :placeholder="$t('dynamic_form_field.team_members_add_placeholder')"
        :aria-label="$t('dynamic_form_field.team_members_add_placeholder')"
        :disabled="disabled"
      />
      <button type="submit" class="picker-add-button" :disabled="disabled || !typed.trim()">
        {{ $t('dynamic_form_field.team_members_add') }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  // AgentTeamConfig.members: list of node IDs
  modelValue: { type: Array, default: () => [] },
  // Agent nodes of the workflow (lead excluded): [{ id, description }]
  options: { type: Array, default: () => [] },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const typed = ref('')

const selected = computed(() => (Array.isArray(props.modelValue) ? props.modelValue.filter(Boolean) : []))

// Graph agents first (in graph order), then listed IDs that have no node yet so they can be unticked.
const rows = computed(() => {
  const known = new Set(props.options.map((o) => o.id))
  const missing = selected.value.filter((id) => !known.has(id)).map((id) => ({ id, description: '', missing: true }))
  return [...props.options, ...missing]
})

const allTicked = computed(() => props.options.length > 0 && props.options.every((o) => selected.value.includes(o.id)))

// Keep the graph order so the lead's roster reads like the org chart.
const ordered = (ids) => {
  const set = new Set(ids)
  return rows.value.map((r) => r.id).filter((id) => set.has(id)).concat(ids.filter((id) => !rows.value.some((r) => r.id === id)))
}

function toggle(id, checked) {
  const next = new Set(selected.value)
  if (checked) next.add(id)
  else next.delete(id)
  emit('update:modelValue', ordered([...next]))
}

function toggleAll() {
  const missing = rows.value.filter((r) => r.missing && selected.value.includes(r.id)).map((r) => r.id)
  emit('update:modelValue', allTicked.value ? missing : ordered([...props.options.map((o) => o.id), ...missing]))
}

function addTyped() {
  const id = typed.value.trim()
  if (!id) return
  if (!selected.value.includes(id)) emit('update:modelValue', [...selected.value, id])
  typed.value = ''
}
</script>

<style scoped>
.member-picker { display: flex; flex-direction: column; gap: 8px; }
.picker-head { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-muted-4); flex-wrap: wrap; }
.picker-hint { flex: 1; min-width: 0; line-height: 1.4; }
.picker-count { font-weight: 600; color: var(--accent-sky); }
.picker-all {
  border: 0; background: none; padding: 0; font: inherit; color: var(--accent-sky); cursor: pointer;
}
.picker-all:hover:not(:disabled) { text-decoration: underline; }
.picker-list { list-style: none; margin: 0; padding: 0; max-height: 280px; overflow: auto; border: 1px solid var(--line-4); border-radius: 10px; }
.picker-list li + li { border-top: 1px solid var(--line-4); }
.picker-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; cursor: pointer; }
.picker-item.checked { background: color-mix(in srgb, var(--accent-sky) 8%, transparent); }
.picker-item.missing .item-desc { color: var(--danger); }
.picker-item input { margin-top: 3px; }
.item-text { display: flex; flex-direction: column; min-width: 0; }
.item-name { font-size: 13px; font-weight: 600; color: var(--text-1); }
.item-desc { font-size: 12px; color: var(--text-muted-4); line-height: 1.4; }
.picker-empty { margin: 0; font-size: 12.5px; color: var(--text-muted-4); }
.picker-add { display: flex; gap: 8px; }
.picker-input {
  flex: 1; min-width: 0; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--line-4);
  background: var(--surface-2); color: var(--text-1); font-size: 13px;
}
.picker-add-button {
  padding: 7px 12px; border-radius: 8px; border: 1px solid var(--line-4);
  background: var(--surface-2); color: var(--text-1); font-size: 13px; cursor: pointer;
}
.picker-add-button:disabled { opacity: 0.5; cursor: default; }
</style>
