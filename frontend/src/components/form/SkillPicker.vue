<template>
  <div class="skill-picker">
    <div class="picker-head">
      <span class="picker-hint">{{ $t('skills.picker_hint') }}</span>
      <span class="picker-count">{{ $t('skills.picker_selected', { count: selected.length }) }}</span>
      <a href="/settings/skills" target="_blank" rel="noopener" class="picker-link">{{ $t('skills.picker_manage') }}</a>
    </div>

    <input
      v-if="library.length > 6"
      v-model="query"
      type="search"
      class="picker-search"
      :placeholder="$t('skills.search_placeholder')"
      :aria-label="$t('skills.search_placeholder')"
      :disabled="disabled"
    />

    <p v-if="error" class="picker-error" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !library.length" class="picker-empty">{{ $t('skills.picker_empty') }}</p>

    <ul v-else class="picker-list" :aria-label="label">
      <li v-for="skill in visible" :key="skill.name">
        <label class="picker-item" :class="{ checked: selected.includes(skill.name), missing: skill.missing }">
          <input
            type="checkbox"
            :checked="selected.includes(skill.name)"
            :disabled="disabled"
            @change="toggle(skill.name, $event.target.checked)"
          />
          <span class="item-text">
            <span class="item-name">{{ skill.name }}</span>
            <span class="item-desc">{{ skill.missing ? $t('skills.invalid') : skill.description }}</span>
          </span>
        </label>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchSkills } from '@/api/client'

const props = defineProps({
  // AgentSkillsConfig value: { enabled, allow: [{ name } | string] }
  modelValue: { type: Object, default: null },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const library = ref([])
const loading = ref(true)
const error = ref('')
const query = ref('')

const namesFrom = (value) =>
  (value?.allow || []).map((entry) => (typeof entry === 'string' ? entry : entry?.name)).filter(Boolean)

const selected = computed(() => {
  if (!props.modelValue?.enabled) return []
  const names = namesFrom(props.modelValue)
  // enabled with an empty allowlist means "every skill" in the runtime.
  return names.length ? names : library.value.filter((s) => !s.missing).map((s) => s.name)
})

// Ticked skills that were deleted from the library stay visible so the user can untick them.
const options = computed(() => {
  const known = new Set(library.value.map((s) => s.name))
  const missing = namesFrom(props.modelValue)
    .filter((n) => !known.has(n))
    .map((name) => ({ name, description: '', missing: true }))
  return [...library.value.filter((s) => s.valid), ...missing]
})

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = q ? options.value.filter((s) => `${s.name} ${s.description}`.toLowerCase().includes(q)) : options.value
  // Ticked first, so the agent's current kit is visible at a glance.
  return [...list].sort((a, b) => Number(selected.value.includes(b.name)) - Number(selected.value.includes(a.name)))
})

function toggle(name, checked) {
  const next = new Set(selected.value)
  if (checked) next.add(name)
  else next.delete(name)
  const names = [...next]
  emit('update:modelValue', names.length ? { enabled: true, allow: names.map((n) => ({ name: n })) } : null)
}

onMounted(async () => {
  try {
    library.value = await fetchSkills()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.skill-picker { display: flex; flex-direction: column; gap: 8px; }
.picker-head { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-muted-4); flex-wrap: wrap; }
.picker-hint { flex: 1; min-width: 0; }
.picker-count { font-weight: 600; color: var(--accent-sky); }
.picker-link { color: var(--accent-sky); text-decoration: none; }
.picker-link:hover { text-decoration: underline; }
.picker-search {
  padding: 7px 10px; border-radius: 8px; border: 1px solid var(--line-4);
  background: var(--surface-2); color: var(--text-1); font-size: 13px;
}
.picker-list { list-style: none; margin: 0; padding: 0; max-height: 260px; overflow: auto; border: 1px solid var(--line-4); border-radius: 10px; }
.picker-list li + li { border-top: 1px solid var(--line-4); }
.picker-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; cursor: pointer; }
.picker-item.checked { background: color-mix(in srgb, var(--accent-sky) 8%, transparent); }
.picker-item.missing .item-desc { color: var(--danger); }
.picker-item input { margin-top: 3px; }
.item-text { display: flex; flex-direction: column; min-width: 0; }
.item-name { font-family: ui-monospace, 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--text-1); }
.item-desc { font-size: 12px; color: var(--text-muted-4); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.picker-empty, .picker-error { margin: 0; font-size: 12.5px; color: var(--text-muted-4); }
.picker-error { color: var(--danger); }
</style>
