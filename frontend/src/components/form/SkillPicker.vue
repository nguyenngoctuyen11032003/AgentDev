<template>
  <div class="skill-picker">
    <div class="picker-head">
      <span class="picker-hint">{{ $t('skills.picker_hint') }}</span>
      <span class="picker-count" aria-live="polite">{{ $t('skills.picker_selected', { count: selected.length }) }}</span>
      <button type="button" class="picker-refresh" :disabled="loading" :title="$t('skills.picker_refresh')" :aria-label="$t('skills.picker_refresh')" @click="load">&#8635;</button>
      <a href="/settings/skills" target="_blank" rel="noopener" class="picker-link">{{ $t('skills.picker_manage') }}</a>
    </div>

    <div v-if="library.length > 6" class="picker-filter">
      <input
        v-model="query"
        type="search"
        class="picker-search"
        :placeholder="$t('skills.search_placeholder')"
        :aria-label="$t('skills.search_placeholder')"
        :disabled="disabled"
      />
      <select v-if="usedCategories.length > 1" v-model="category" class="picker-search picker-cat" :aria-label="$t('skills.category_label')" :disabled="disabled">
        <option value="all">{{ $t('skills.categories.all') }} ({{ counts.all }})</option>
        <option v-for="id in usedCategories" :key="id" :value="id">{{ $t(`skills.categories.${id}`) }} ({{ counts[id] }})</option>
      </select>
    </div>

    <div v-if="error" class="picker-error" role="alert">
      <p>{{ $t('skills.load_error_title') }}: {{ error }}</p>
      <p class="picker-error-hint">{{ $t('skills.load_error_hint') }}</p>
      <button type="button" class="picker-retry" @click="load">{{ $t('skills.retry') }}</button>
    </div>
    <p v-else-if="loading && !library.length" class="picker-empty" role="status">{{ $t('skills.picker_loading') }}</p>
    <p v-else-if="!library.length && !options.length" class="picker-empty">{{ $t('skills.picker_empty') }}</p>
    <p v-else-if="!visible.length" class="picker-empty">{{ $t('skills.picker_no_results') }}</p>

    <ul v-else class="picker-list" :aria-label="label" :aria-busy="loading">
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
            <span class="item-desc">{{ skill.missing ? $t('skills.missing') : skill.guide?.purpose || skill.description }}</span>
          </span>
        </label>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchSkills } from '@/api/client'
import { createLatest } from '@/utils/latestOnly'
import { CATEGORY_IDS, countByCategory, filterSkills } from '@/utils/skillCategories'
import { buildOptions, selectedNames, toggledValue } from './skillPickerLogic'

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
const latest = createLatest()

const selected = computed(() => selectedNames(props.modelValue, library.value))
const options = computed(() => buildOptions(props.modelValue, library.value))

const category = ref('all')
const counts = computed(() => countByCategory(options.value))
const usedCategories = computed(() => CATEGORY_IDS.filter((id) => counts.value[id] > 0))

const visible = computed(() => {
  const list = filterSkills(options.value, { query: query.value, category: category.value })
  // Ticked first, so the agent's current kit is visible at a glance.
  return [...list].sort((a, b) => Number(selected.value.includes(b.name)) - Number(selected.value.includes(a.name)))
})

function toggle(name, checked) {
  emit('update:modelValue', toggledValue(selected.value, name, checked))
}

async function load() {
  const ticket = latest.begin()
  loading.value = true
  error.value = ''
  try {
    const list = await fetchSkills()
    if (latest.isCurrent(ticket)) library.value = list
  } catch (e) {
    if (latest.isCurrent(ticket)) error.value = e.message
  } finally {
    if (latest.isCurrent(ticket)) loading.value = false
  }
}

// Skills added or removed in the "Manage" tab show up when the user comes back to this tab.
function onVisible() {
  if (document.visibilityState === 'visible' && !loading.value) load()
}

onMounted(() => {
  load()
  document.addEventListener('visibilitychange', onVisible)
})
onUnmounted(() => {
  latest.cancel()
  document.removeEventListener('visibilitychange', onVisible)
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
.picker-filter { display: flex; gap: 8px; flex-wrap: wrap; }
.picker-filter .picker-search { flex: 1; min-width: 160px; }
.picker-filter .picker-cat { flex: 0 1 auto; min-width: 150px; }
.picker-list { list-style: none; margin: 0; padding: 0; max-height: 260px; overflow: auto; border: 1px solid var(--line-4); border-radius: 10px; }
.picker-list li + li { border-top: 1px solid var(--line-4); }
.picker-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; cursor: pointer; }
.picker-item.checked { background: color-mix(in srgb, var(--accent-sky) 8%, transparent); }
.picker-item.missing .item-desc { color: var(--danger); }
.picker-item input { margin-top: 3px; }
.item-text { display: flex; flex-direction: column; min-width: 0; }
.item-name { font-family: ui-monospace, 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--text-1); }
.item-desc { font-size: 12px; color: var(--text-muted-4); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.picker-refresh, .picker-retry { border: 1px solid var(--line-4); background: var(--surface-2); color: var(--text-1); border-radius: 6px; cursor: pointer; padding: 2px 8px; font-size: 12px; }
.picker-error-hint { color: var(--text-muted-4); }
.picker-error p { margin: 0 0 4px; }
.picker-empty, .picker-error { margin: 0; font-size: 12.5px; color: var(--text-muted-4); }
.picker-error { color: var(--danger); }
</style>
