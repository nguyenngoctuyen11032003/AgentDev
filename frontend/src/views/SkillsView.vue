<template>
  <div class="skills-view page">
    <header class="hero">
      <div class="hero-text">
        <p class="hero-kicker">{{ $t('skills.kicker') }}</p>
        <h1 class="hero-title">{{ $t('skills.title') }}</h1>
        <p class="hero-sub">{{ $t('skills.subtitle') }}</p>
      </div>
      <div class="hero-actions">
        <button type="button" class="btn" @click="openImport">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5" /><path d="M5 21h14" /></svg>
          {{ $t('skills.import_claude') }}
        </button>
        <button type="button" class="btn primary" @click="openEditor()">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          {{ $t('skills.add') }}
        </button>
      </div>
    </header>

    <nav v-if="!loading && !loadError && skills.length" class="cat-bar" :aria-label="$t('skills.categories_nav')">
      <button
        v-for="cat in categoryTabs"
        :key="cat.id"
        type="button"
        class="cat-chip"
        :class="{ active: category === cat.id }"
        :style="cat.hue == null ? null : { '--hue': cat.hue }"
        :aria-pressed="category === cat.id"
        @click="selectCategory(cat.id)"
      >
        <!-- eslint-disable-next-line vue/no-v-html -- static icon markup from skillCategories.js -->
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="cat.icon"></svg>
        <span class="cat-label">{{ $t(`skills.categories.${cat.id}`) }}</span>
        <span class="cat-count">{{ counts[cat.id] }}</span>
      </button>
    </nav>

    <div class="toolbar">
      <label class="search">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input
          v-model="query"
          type="search"
          :placeholder="$t('skills.search_placeholder')"
          :aria-label="$t('skills.search_placeholder')"
        />
      </label>
      <span class="count" aria-live="polite">
        <template v-if="query.trim() || category !== 'all'">{{ $t('skills.count_filtered', { shown: filtered.length, count: skills.length }) }}</template>
        <template v-else>{{ $t('skills.count', { count: skills.length }) }}</template>
      </span>
    </div>

    <div v-if="loading" class="skill-grid" aria-hidden="true">
      <div v-for="n in 6" :key="n" class="skeleton"></div>
    </div>

    <div v-else-if="loadError" class="empty-state" role="alert">
      <p class="empty-title">{{ $t('skills.load_error_title') }}</p>
      <p class="empty-desc">{{ loadError }}</p>
      <p class="empty-desc">{{ $t('skills.load_error_hint') }}</p>
      <div class="empty-actions">
        <button type="button" class="btn primary" @click="load">{{ $t('skills.retry') }}</button>
      </div>
    </div>

    <div v-else-if="!skills.length" class="empty-state">
      <span class="empty-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5V5a2 2 0 0 1 2-2h13v16H6.5A2.5 2.5 0 0 0 4 21.5" /><path d="M9 7h6M9 11h4" /></svg>
      </span>
      <p class="empty-title">{{ $t('skills.empty_title') }}</p>
      <p class="empty-desc">{{ $t('skills.empty_desc') }}</p>
      <div class="empty-actions">
        <button type="button" class="btn" @click="openImport">{{ $t('skills.import_claude') }}</button>
        <button type="button" class="btn primary" @click="openEditor()">{{ $t('skills.add') }}</button>
      </div>
    </div>

    <template v-else>
      <section
        v-for="section in sections"
        :key="section.id"
        class="cat-section"
        :aria-labelledby="section.header ? `skill-cat-${section.id}` : null"
      >
        <header v-if="section.header" class="cat-head">
          <span class="cat-tile" :class="{ neutral: section.meta.hue == null }" :style="section.meta.hue == null ? null : { '--hue': section.meta.hue }" aria-hidden="true">
            <!-- eslint-disable-next-line vue/no-v-html -- static icon markup from skillCategories.js -->
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="section.meta.icon"></svg>
          </span>
          <span class="cat-head-text">
            <h2 :id="`skill-cat-${section.id}`" class="cat-title">
              {{ $t(`skills.categories.${section.id}`) }}
              <span class="cat-title-count">{{ section.skills.length }}</span>
            </h2>
            <span class="cat-desc">{{ $t(`skills.category_desc.${section.id}`) }}</span>
          </span>
          <button
            v-if="section.skills.length > section.shown.length"
            type="button"
            class="btn ghost cat-more"
            @click="selectCategory(section.id)"
          >
            {{ $t('skills.show_all_in', { count: section.skills.length }) }}
          </button>
        </header>
        <ul class="skill-grid">
          <li v-for="skill in section.shown" :key="skill.name" class="skill-card" :class="{ invalid: !skill.valid }" @click="openDetail(skill)">
            <div class="skill-head">
              <span class="skill-mark" :style="{ '--hue': hueOf(skill.name) }" aria-hidden="true">{{ initialsOf(skill.name) }}</span>
              <button type="button" class="skill-name" :title="skill.name" @click.stop="openDetail(skill)">{{ skill.name }}</button>
              <span class="skill-actions" @click.stop>
                <button
                  type="button"
                  class="icon-btn"
                  :title="$t('skills.edit')"
                  :aria-label="`${$t('skills.edit')}: ${skill.name}`"
                  @click="openEditor(skill.name)"
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                </button>
                <button
                  type="button"
                  class="icon-btn danger"
                  :title="$t('skills.delete')"
                  :aria-label="`${$t('skills.delete')}: ${skill.name}`"
                  @click="remove(skill.name)"
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
                </button>
              </span>
            </div>
            <p class="skill-desc" :class="{ guided: skill.valid && skill.guide?.purpose }">{{ skill.valid ? skill.guide?.purpose || skill.description : skill.error }}</p>
            <p v-if="skill.valid && skill.guide?.when" class="skill-when"><span>{{ $t('skills.guide_when') }}</span> {{ skill.guide.when }}</p>
            <div v-if="!skill.valid || skill.extra_files || skill.guide?.paid" class="skill-foot">
              <span v-if="!skill.valid" class="badge danger">{{ $t('skills.invalid') }}</span>
              <span v-if="skill.guide?.paid" class="badge paid">{{ $t('skills.paid') }}</span>
              <span v-if="skill.extra_files" class="badge">{{ $t('skills.extra_files', { count: skill.extra_files }) }}</span>
            </div>
          </li>
        </ul>
      </section>
      <div v-if="!filtered.length" class="no-match">
        <p>{{ query.trim() ? $t('skills.no_match') : $t('skills.category_empty') }}</p>
        <button v-if="category !== 'all'" type="button" class="btn ghost" @click="selectCategory('all')">{{ $t('skills.show_all_categories') }}</button>
      </div>
    </template>

    <!-- Detail: what the skill is for, in the user's words -->
    <BaseDialog v-model="detail.open" :title="detail.skill?.name || ''" width="640px">
      <div v-if="detail.skill" class="detail">
        <div class="detail-tags">
          <span class="cat-pill" :style="detailMeta.hue == null ? null : { '--hue': detailMeta.hue }">
            <!-- eslint-disable-next-line vue/no-v-html -- static icon markup from skillCategories.js -->
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="detailMeta.icon"></svg>
            {{ $t(`skills.categories.${categoryOf(detail.skill)}`) }}
          </span>
          <span v-if="detail.skill.guide?.paid" class="badge paid">{{ $t('skills.paid') }}</span>
          <span v-if="detail.skill.extra_files" class="badge">{{ $t('skills.extra_files', { count: detail.skill.extra_files }) }}</span>
          <span v-if="!detail.skill.valid" class="badge danger">{{ $t('skills.invalid') }}</span>
        </div>

        <p v-if="!detail.skill.valid" class="error">{{ detail.skill.error }}</p>

        <dl v-if="hasGuideText(detail.skill.guide)" class="guide">
          <template v-for="key in GUIDE_KEYS" :key="key">
            <div v-if="detail.skill.guide[key]" class="guide-row" :class="key">
              <dt>{{ $t(`skills.guide_${key}`) }}</dt>
              <dd>{{ detail.skill.guide[key] }}</dd>
            </div>
          </template>
        </dl>
        <p v-else-if="detail.skill.valid" class="guide-missing">{{ $t('skills.guide_missing') }}</p>

        <div v-if="detail.skill.description" class="agent-desc">
          <span class="agent-desc-label">{{ $t('skills.agent_description') }}</span>
          <p>{{ detail.skill.description }}</p>
        </div>
      </div>
      <template #footer>
        <button type="button" class="btn ghost danger-text" @click="removeFromDetail">{{ $t('skills.delete') }}</button>
        <button type="button" class="btn primary" @click="editFromDetail">{{ $t('skills.edit') }}</button>
      </template>
    </BaseDialog>

    <!-- Add / edit -->
    <BaseDialog v-model="editor.open" :title="editorTitle" width="760px">
      <p class="dialog-hint">{{ $t('skills.editor_hint') }}</p>

      <div class="row">
        <label class="field">
          <span>{{ $t('skills.name_label') }}</span>
          <input v-model.trim="editor.name" type="text" placeholder="cto-management" />
        </label>
        <label class="field grow">
          <span>{{ $t('skills.description_label') }}</span>
          <input v-model.trim="editor.description" type="text" :placeholder="$t('skills.description_placeholder')" />
        </label>
        <label class="field">
          <span>{{ $t('skills.category_label') }}</span>
          <select v-model="editor.category" class="select">
            <option value="auto">
              {{ editor.guess ? $t('skills.category_auto_guess', { name: $t(`skills.categories.${editor.guess}`) }) : $t('skills.category_auto') }}
            </option>
            <option v-for="id in CATEGORY_IDS" :key="id" :value="id">{{ $t(`skills.categories.${id}`) }}</option>
          </select>
        </label>
      </div>

      <!-- div, not label: a label would forward clicks on its text to the upload button -->
      <div class="field">
        <span class="field-head">
          <span id="skill-content-label">{{ $t('skills.content_label') }}</span>
          <button type="button" class="link" @click="fileInput?.click()">{{ $t('skills.upload_md') }}</button>
          <input ref="fileInput" type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" hidden @change="loadFile" />
        </span>
        <textarea
          v-model="editor.content"
          rows="16"
          spellcheck="false"
          :placeholder="$t('skills.content_placeholder')"
          @dragover.prevent
          aria-labelledby="skill-content-label"
          @paste="onPaste"
          @drop.prevent="dropFile"
        ></textarea>
      </div>

      <fieldset class="guide-fields">
        <legend>{{ $t('skills.guide_title') }}</legend>
        <p class="dialog-hint">{{ $t('skills.guide_hint') }}</p>
        <label v-for="key in GUIDE_KEYS" :key="key" class="field">
          <span>{{ $t(`skills.guide_${key}`) }}</span>
          <input v-model="editor.guide[key]" type="text" maxlength="400" :placeholder="$t(`skills.guide_${key}_placeholder`)" />
        </label>
        <label class="check">
          <input v-model="editor.guide.paid" type="checkbox" />
          {{ $t('skills.guide_paid') }}
        </label>
      </fieldset>

      <p v-if="editor.loading" class="loading-note" role="status"><span class="spinner" aria-hidden="true"></span>{{ $t('skills.loading_editor') }}</p>
      <p v-if="editor.error" class="error" role="alert">{{ editor.error }}</p>

      <template #footer>
        <button type="button" class="btn ghost" @click="closeEditor">{{ $t('common.cancel') }}</button>
        <button type="button" class="btn primary" :disabled="editor.saving || editor.loading || !editor.content.trim()" @click="save">
          {{ editor.saving ? $t('skills.saving') : $t('skills.save') }}
        </button>
      </template>
    </BaseDialog>

    <!-- Import from ~/.claude/skills -->
    <BaseDialog v-model="importer.open" :title="$t('skills.import_title')" width="760px" :close-on-backdrop="!importer.saving">
      <div class="row">
        <label class="field grow">
          <span>{{ $t('skills.import_source') }}</span>
          <input v-model.trim="importer.source" type="text" @keydown.enter="loadSource" />
        </label>
        <button type="button" class="btn ghost align-end" :disabled="importer.loading" @click="loadSource">{{ $t('skills.import_reload') }}</button>
      </div>

      <p v-if="importer.loading" class="loading-note" role="status"><span class="spinner" aria-hidden="true"></span>{{ $t('skills.import_loading') }}</p>
      <p v-else-if="importer.error" class="error" role="alert">{{ importer.error }}</p>
      <p v-else-if="!importer.items.length" class="dialog-hint">{{ $t('skills.import_none') }}</p>

      <div v-if="importer.items.length > 8" class="import-filter">
        <input
          v-model="importer.query"
          type="search"
          class="input import-search"
          :placeholder="$t('skills.search_placeholder')"
          :aria-label="$t('skills.search_placeholder')"
        />
        <select v-model="importer.category" class="select import-cat" :aria-label="$t('skills.category_label')">
          <option value="all">{{ $t('skills.categories.all') }} ({{ importCounts.all }})</option>
          <template v-for="id in CATEGORY_IDS" :key="id">
            <option v-if="importCounts[id]" :value="id">{{ $t(`skills.categories.${id}`) }} ({{ importCounts[id] }})</option>
          </template>
        </select>
      </div>

      <div v-if="importer.items.length" class="import-bar">
        <label class="check">
          <input type="checkbox" :checked="allSelected" @change="toggleAll($event.target.checked)" />
          {{ $t('skills.select_all', { count: importable.length }) }}
        </label>
        <label class="check">
          <input v-model="importer.overwrite" type="checkbox" />
          {{ $t('skills.overwrite') }}
        </label>
      </div>

      <ul class="import-list">
        <li v-for="item in importVisible" :key="item.name">
          <label class="check" :class="{ disabled: !item.valid }">
            <input v-model="importer.selected" type="checkbox" :value="item.name" :disabled="!item.valid" />
            <span class="import-name">{{ item.name }}</span>
            <span class="badge">{{ $t(`skills.categories.${categoryOf(item)}`) }}</span>
            <span v-if="item.imported" class="badge">{{ $t('skills.already_imported') }}</span>
            <span v-if="!item.valid" class="badge danger">{{ $t('skills.invalid') }}</span>
          </label>
          <p class="import-desc">{{ item.valid ? item.description : item.error }}</p>
        </li>
      </ul>

      <template #footer>
        <button type="button" class="btn ghost" @click="importer.open = false">{{ $t('common.cancel') }}</button>
        <button
          type="button"
          class="btn primary"
          :disabled="importer.saving || !importer.selected.length"
          @click="runImport"
        >
          <span v-if="importer.saving" class="spinner" aria-hidden="true"></span>
          {{ $t('skills.import_n', { count: importer.selected.length }) }}
        </button>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  createSkill,
  deleteSkill,
  fetchSkill,
  fetchSkillImportSource,
  fetchSkills,
  importSkills,
  updateSkill
} from '@/api/client'
import BaseDialog from '@/components/common/BaseDialog.vue'
import { confirmDialog } from '@/utils/confirm'
import { toast } from '@/utils/toast'
import { createLatest } from '@/utils/latestOnly'
import {
  CATEGORY_IDS,
  SKILL_CATEGORIES,
  categoryMeta,
  categoryOf,
  countByCategory,
  filterSkills,
  groupByCategory
} from '@/utils/skillCategories'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const skills = ref([])
const loading = ref(true)
const query = ref('')
const fileInput = ref(null)

// ---- categories: the selected one lives in ?cat= so a link or reload keeps it ----
const PREVIEW_PER_CATEGORY = 4
const readCategory = (value) => (CATEGORY_IDS.includes(value) ? value : 'all')
const category = ref(readCategory(route.query.cat))
watch(() => route.query.cat, (value) => { category.value = readCategory(value) })

function selectCategory(id) {
  category.value = id
  const next = { ...route.query }
  if (id === 'all') delete next.cat
  else next.cat = id
  router.replace({ query: next }).catch(() => {})
}

const counts = computed(() => countByCategory(skills.value))
// "All" first, then only the categories that have skills (the chosen one stays visible even when empty).
const categoryTabs = computed(() => [
  { id: 'all', hue: null, icon: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>' },
  ...SKILL_CATEGORIES.filter((c) => counts.value[c.id] > 0 || c.id === category.value)
])

// "All" without a search: one section per category with a short preview; a search or one category: every match.
const sections = computed(() => {
  if (category.value !== 'all') {
    return filtered.value.length
      ? [{ id: category.value, header: false, meta: categoryMeta(category.value), skills: filtered.value, shown: filtered.value }]
      : []
  }
  const limit = query.value.trim() ? Infinity : PREVIEW_PER_CATEGORY
  return groupByCategory(filtered.value).map((g) => ({
    ...g,
    header: true,
    meta: categoryMeta(g.id),
    shown: g.skills.slice(0, limit)
  }))
})

// Stable colour + initials per skill so cards are easy to tell apart at a glance
const hueOf = (name) => {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}
const initialsOf = (name) => {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase()
}

const filtered = computed(() => filterSkills(skills.value, { query: query.value, category: category.value }))

const loadError = ref('')
const listLatest = createLatest()
async function load() {
  const ticket = listLatest.begin()
  loading.value = true
  loadError.value = ''
  try {
    const list = await fetchSkills()
    if (listLatest.isCurrent(ticket)) skills.value = list // an older response never overwrites a newer one
  } catch (error) {
    if (listLatest.isCurrent(ticket)) loadError.value = error.message
  } finally {
    if (listLatest.isCurrent(ticket)) loading.value = false
  }
}

// ---- detail ----
// Human-facing guide fields, in display order (labels: skills.guide_<key>)
const GUIDE_KEYS = ['purpose', 'when', 'benefit', 'requires']
const emptyGuide = () => ({ purpose: '', when: '', benefit: '', requires: '', paid: false })
const hasGuideText = (guide) => !!guide && GUIDE_KEYS.some((k) => guide[k])

const detail = reactive({ open: false, skill: null })
const detailMeta = computed(() => categoryMeta(categoryOf(detail.skill)))

function openDetail(skill) {
  Object.assign(detail, { open: true, skill })
}

function editFromDetail() {
  const name = detail.skill?.name
  detail.open = false
  if (name) openEditor(name)
}

async function removeFromDetail() {
  const name = detail.skill?.name
  if (!name) return
  if (await remove(name)) detail.open = false
}

// ---- add / edit ----
// category: 'auto' or a category id; guess: the auto category the library computed (shown in the "Auto" option)
const editor = reactive({ open: false, original: null, name: '', description: '', category: 'auto', guess: '', guide: emptyGuide(), content: '', error: '', saving: false, loading: false })
const editorLatest = createLatest()
// Form values as last loaded; when the content has frontmatter, unchanged form fields are not sent so
// edits made directly in the frontmatter are not overridden.
const baseline = { name: '', description: '', category: 'auto', guide: JSON.stringify(emptyGuide()) }
const editorTitle = computed(() => (editor.original ? t('skills.edit_title', { name: editor.original }) : t('skills.add_title')))

// Pull name/description out of pasted frontmatter so the form shows what will be saved.
function readFrontmatter(text) {
  const clean = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(clean)
  if (!match) return {}
  const out = {}
  for (const line of match[1].split(/\r?\n/)) {
    const m = /^(name|description):\s*(.*)$/.exec(line)
    if (m) out[m[1]] = m[2].trim().replace(/^["']|["']$/g, '')
  }
  return out
}

async function openEditor(name = null) {
  const ticket = editorLatest.begin()
  // A new skill added while one category is open goes into that category.
  const preset = !name && category.value !== 'all' ? category.value : 'auto'
  Object.assign(editor, { open: true, original: name, name: name || '', description: '', category: preset, guess: '', guide: emptyGuide(), content: '', error: '', saving: false, loading: !!name })
  Object.assign(baseline, { name: editor.name, description: '', category: 'auto', guide: JSON.stringify(emptyGuide()) })
  if (!name) return
  try {
    const skill = await fetchSkill(name)
    if (!editorLatest.isCurrent(ticket)) return // another skill was opened (or the editor closed) meanwhile
    editor.content = skill.content
    editor.description = skill.description
    baseline.description = skill.description
    const manual = skill.category_source === 'manual'
    editor.category = baseline.category = manual ? skill.category : 'auto'
    editor.guess = manual ? '' : skill.category || ''
    editor.guide = { ...emptyGuide(), ...(skill.guide || {}) }
    baseline.guide = JSON.stringify(editor.guide)
  } catch (error) {
    if (editorLatest.isCurrent(ticket)) editor.error = error.message
  } finally {
    if (editorLatest.isCurrent(ticket)) editor.loading = false
  }
}

function closeEditor() {
  editorLatest.cancel()
  editor.loading = false
  editor.open = false
}

function applyText(text, filename = '') {
  editor.content = text
  const meta = readFrontmatter(text)
  if (meta.name && !editor.original) editor.name = meta.name
  if (meta.description) editor.description = meta.description
  Object.assign(baseline, { name: editor.name, description: editor.description })
  if (!editor.name && filename) {
    const base = filename.replace(/\.(md|markdown|txt)$/i, '')
    // "SKILL.md" says nothing about the skill; keep the name empty so the user types one.
    if (base.toLowerCase() !== 'skill') editor.name = base.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  }
}

async function readTextFile(file) {
  if (!file) return
  editor.error = ''
  if (file.size > 256 * 1024) {
    editor.error = t('skills.file_too_large')
    return
  }
  applyText(await file.text(), file.name)
}

async function loadFile(event) {
  await readTextFile(event.target.files?.[0])
  event.target.value = ''
}

// Optional BOM, then the opening '---' line of YAML frontmatter
const FRONTMATTER_START = new RegExp(`^${String.fromCharCode(0xfeff)}?---\\r?\\n`)

// Pasted SKILL.md text fills the name / description fields from its frontmatter, like an upload does.
function onPaste() {
  nextTick(() => {
    if (FRONTMATTER_START.test(editor.content)) applyText(editor.content)
  })
}

function dropFile(event) {
  readTextFile(event.dataTransfer?.files?.[0])
}

async function save() {
  editor.error = ''
  editor.saving = true
  const hasFrontmatter = FRONTMATTER_START.test(editor.content)
  const field = (key) => (hasFrontmatter && editor[key] === baseline[key] ? null : editor[key] || null)
  // Category is sent only when changed, so a category written by hand in the frontmatter is kept.
  const payload = {
    content: editor.content,
    name: field('name'),
    description: field('description'),
    category: editor.category !== baseline.category ? editor.category : null,
    // Sent only when edited; all-empty means "remove the guide"
    guide: JSON.stringify(editor.guide) !== baseline.guide ? { ...editor.guide } : null
  }
  try {
    if (editor.original) {
      await updateSkill(editor.original, payload)
    } else {
      try {
        await createSkill(payload)
      } catch (error) {
        if (error.status !== 409) throw error
        const ok = await confirmDialog({
          title: t('skills.exists_title'),
          message: t('skills.exists_message', { name: editor.name || readFrontmatter(editor.content).name || '' }),
          confirmText: t('skills.overwrite_confirm')
        })
        if (!ok) return
        await createSkill({ ...payload, overwrite: true })
      }
    }
    toast.success(t('skills.saved'))
    editor.open = false
    await load()
  } catch (error) {
    editor.error = error.detail || error.message
  } finally {
    editor.saving = false
  }
}

async function remove(name) {
  const ok = await confirmDialog({
    title: t('skills.delete_title'),
    message: t('skills.delete_message', { name }),
    confirmText: t('skills.delete'),
    tone: 'danger'
  })
  if (!ok) return false
  try {
    await deleteSkill(name)
    toast.success(t('skills.deleted', { name }))
    await load()
    return true
  } catch (error) {
    toast.error(error.message)
    return false
  }
}

// ---- import ----
const importer = reactive({ open: false, source: '', items: [], selected: [], overwrite: false, loading: false, saving: false, error: '', query: '', category: 'all' })
const importCounts = computed(() => countByCategory(importer.items))
const importVisible = computed(() => filterSkills(importer.items, { query: importer.query, category: importer.category }))
// "Select all" acts on what the filter shows; ticks on hidden items are kept.
const importable = computed(() => importVisible.value.filter((i) => i.valid))
const allSelected = computed(() => importable.value.length > 0 && importable.value.every((i) => importer.selected.includes(i.name)))

function toggleAll(checked) {
  const shown = new Set(importable.value.map((i) => i.name))
  const others = importer.selected.filter((n) => !shown.has(n))
  importer.selected = checked ? [...others, ...shown] : others
}

let importLoadSeq = 0
async function loadSource() {
  const seq = ++importLoadSeq
  importer.loading = true
  importer.error = ''
  try {
    const data = await fetchSkillImportSource(importer.source)
    if (seq !== importLoadSeq) return // a newer reload superseded this one
    importer.source = data.source
    importer.items = data.skills
    if (!data.exists) importer.error = t('skills.import_missing', { path: data.source })
    // Preselect what is new; already-imported ones stay unticked unless the user wants to refresh them.
    importer.selected = data.skills.filter((i) => i.valid && !i.imported).map((i) => i.name)
  } catch (error) {
    if (seq === importLoadSeq) importer.error = error.message
  } finally {
    if (seq === importLoadSeq) importer.loading = false
  }
}

function openImport() {
  Object.assign(importer, { open: true, items: [], selected: [], overwrite: false, error: '', query: '', category: 'all' })
  loadSource()
}

async function runImport() {
  importer.saving = true
  try {
    const result = await importSkills({
      names: importer.selected,
      source: importer.source || null,
      overwrite: importer.overwrite
    })
    const items = [
      ...result.skipped.map((n) => t('skills.skipped_item', { name: n })),
      ...result.failed.map((f) => `${f.name}: ${f.error}`)
    ]
    toast[result.failed.length ? 'warning' : 'success'](t('skills.imported', { count: result.imported.length }), { items })
    importer.open = false
    await load()
  } catch (error) {
    importer.error = error.message
  } finally {
    importer.saving = false
  }
}

onMounted(load)
</script>

<style scoped>
.skills-view {
  padding-bottom: 72px;
  color: var(--fg);
  font-family: 'Inter', system-ui, sans-serif;
  --line: rgb(var(--ink) / 0.09);
  --muted: var(--fg-muted);
}

/* ---- header (shared look with the Connections page) ---- */
.hero { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 28px; }
.hero-kicker { margin: 0 0 8px; font-size: 12.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }
.hero-title { margin: 0 0 10px; font-size: 32px; line-height: 1.15; font-weight: 750; letter-spacing: -0.03em; color: var(--text-strong); }
.hero-sub { margin: 0; max-width: 64ch; font-size: 15px; line-height: 1.65; color: var(--muted); }
.hero-actions { display: flex; gap: 10px; flex-wrap: wrap; }

/* ---- buttons: global .btn (ui.css); only local helpers here ---- */
.btn.align-end { align-self: flex-end; }
.icon-btn:focus-visible, .search:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.link { background: none; border: none; border-radius: var(--radius-sm); color: var(--accent); cursor: pointer; font-size: 12.5px; font-weight: 600; min-height: 40px; padding: 0 4px; margin-left: auto; }

/* ---- category bar: one chip per non-empty category, tinted by the category hue ---- */
.cat-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 18px; }
.cat-chip {
  --hue: 210;
  display: inline-flex; align-items: center; gap: 7px; min-height: 36px; padding: 0 8px 0 11px;
  border: 0; border-radius: 999px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line);
  color: var(--muted); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap;
  transition: color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}
.cat-chip svg { flex: none; color: hsl(var(--hue) 65% 68%); }
:root[data-theme='light'] .cat-chip svg { color: hsl(var(--hue) 60% 38%); }
.cat-chip:hover { color: var(--fg); box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.2); }
.cat-chip.active {
  color: var(--text-strong);
  background: hsl(var(--hue) 55% 50% / 0.14);
  box-shadow: inset 0 0 0 1.5px hsl(var(--hue) 60% 58% / 0.7);
}
.cat-chip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.cat-count {
  min-width: 22px; padding: 1px 6px; border-radius: 999px; text-align: center;
  background: rgb(var(--ink) / 0.07); color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums;
}
.cat-chip.active .cat-count { background: hsl(var(--hue) 55% 50% / 0.22); color: var(--text-strong); }

/* ---- category sections (the "All" view) ---- */
.cat-section + .cat-section { margin-top: 30px; }
.cat-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.cat-tile {
  display: grid; flex: none; place-items: center; width: 36px; height: 36px; border-radius: 10px;
  color: hsl(var(--hue) 65% 72%); background: hsl(var(--hue) 50% 50% / 0.15);
}
:root[data-theme='light'] .cat-tile { color: hsl(var(--hue) 60% 34%); background: hsl(var(--hue) 60% 50% / 0.12); }
.cat-tile.neutral { color: var(--muted); background: rgb(var(--ink) / 0.07); }
.cat-head-text { display: flex; flex: 1; flex-direction: column; gap: 2px; min-width: 0; }
.cat-title { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 16px; font-weight: 700; letter-spacing: -0.01em; color: var(--text-strong); }
.cat-title-count { font-size: 13px; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; }
.cat-desc { font-size: 13px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-more { flex: none; }

/* ---- toolbar ---- */
.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.search {
  display: flex; flex: 1; align-items: center; gap: 10px; min-width: 0; height: 42px; padding: 0 14px;
  border-radius: 11px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); color: var(--muted);
}
.search input { flex: 1; min-width: 0; height: 100%; border: 0; outline: 0; background: transparent; color: var(--fg); font: inherit; font-size: 14.5px; }
.count { font-size: 13px; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }

/* ---- grid ---- */
.skill-grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.skill-card {
  display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 18px;
  border-radius: 14px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line);
  cursor: pointer; transition: box-shadow 0.15s ease;
}
.skill-card:hover { box-shadow: inset 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.4); }
.skill-card.invalid { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 55%, transparent); }
.skill-head { display: flex; align-items: center; gap: 12px; min-width: 0; }
.skill-mark {
  display: grid; flex: none; place-items: center; width: 36px; height: 36px; border-radius: 10px;
  font-size: 12.5px; font-weight: 750; letter-spacing: 0.02em;
  color: hsl(var(--hue) 70% 78%); background: hsl(var(--hue) 45% 50% / 0.16);
}
:root[data-theme='light'] .skill-mark { color: hsl(var(--hue) 60% 32%); background: hsl(var(--hue) 60% 50% / 0.12); }
.skill-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, 'JetBrains Mono', monospace; font-size: 14px; font-weight: 600; color: var(--text-strong); }
.skill-actions { display: flex; flex: none; gap: 4px; }
.icon-btn {
  position: relative; display: grid; place-items: center; width: 36px; height: 36px; padding: 0; border: 0; border-radius: 10px;
  color: var(--muted); background: transparent; cursor: pointer; transition: color 0.15s ease, background-color 0.15s ease;
}
.icon-btn::after { content: ''; position: absolute; inset: -4px; } /* 44px hit area */
.icon-btn:hover { color: var(--fg); background: rgb(var(--ink) / 0.07); }
.icon-btn.danger:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.skill-desc { margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.skill-foot { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.skill-desc.guided { color: var(--fg); -webkit-line-clamp: 2; line-clamp: 2; }
.skill-when {
  margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--muted);
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.skill-when span { font-weight: 650; color: var(--accent); }
button.skill-name { padding: 0; border: 0; background: none; text-align: left; cursor: pointer; border-radius: 4px; }
button.skill-name:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.badge.paid { background: color-mix(in srgb, var(--warning, #d97706) 16%, transparent); color: var(--warning, #b45309); }

/* ---- detail dialog ---- */
.detail { display: flex; flex-direction: column; gap: 16px; }
.detail-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.cat-pill {
  --hue: 210;
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border-radius: 999px;
  font-size: 12.5px; font-weight: 650; color: hsl(var(--hue) 65% 72%); background: hsl(var(--hue) 50% 50% / 0.15);
}
:root[data-theme='light'] .cat-pill { color: hsl(var(--hue) 60% 32%); background: hsl(var(--hue) 60% 50% / 0.12); }
.guide { display: flex; flex-direction: column; gap: 10px; margin: 0; }
.guide-row {
  display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 12px; padding: 12px 14px;
  border-radius: 12px; background: rgb(var(--ink) / 0.04); box-shadow: inset 3px 0 0 var(--row-accent, var(--accent));
}
.guide-row.when { --row-accent: hsl(160 55% 45%); }
.guide-row.benefit { --row-accent: hsl(45 85% 50%); }
.guide-row.requires { --row-accent: hsl(285 45% 60%); }
.guide-row dt { font-size: 12.5px; font-weight: 700; color: var(--text-strong); }
.guide-row dd { margin: 0; font-size: 14px; line-height: 1.6; color: var(--fg); }
.guide-missing { margin: 0; padding: 12px 14px; border-radius: 12px; border: 1px dashed var(--border-strong); font-size: 13.5px; color: var(--muted); }
.agent-desc { padding-top: 12px; border-top: 1px solid var(--line); }
.agent-desc-label { font-size: 12px; font-weight: 650; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
.agent-desc p { margin: 6px 0 0; font-size: 13px; line-height: 1.6; color: var(--muted); }
.danger-text { color: var(--danger); margin-right: auto; }

/* ---- editor: guide fields ---- */
.guide-fields { display: flex; flex-direction: column; gap: 10px; margin: 16px 0 0; padding: 14px 16px 12px; border: 1px solid var(--border-strong); border-radius: 12px; }
.guide-fields legend { padding: 0 6px; font-size: 13px; font-weight: 650; color: var(--text-strong); }
.guide-fields .dialog-hint { margin: 0; }
.no-match { display: flex; flex-direction: column; align-items: center; gap: 12px; margin: 0; padding: 32px 4px; text-align: center; color: var(--muted); font-size: 14px; }
.no-match p { margin: 0; }

.badge { font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: rgb(var(--ink) / 0.06); color: var(--muted); }
.badge.danger { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }

/* ---- empty + loading ---- */
.skeleton { height: 128px; border-radius: 14px; }
.empty-icon { display: grid; place-items: center; width: 56px; height: 56px; border-radius: 16px; color: var(--accent); background: rgb(var(--accent-sky-rgb) / 0.12); }
.empty-title { font-weight: 650; }
.empty-desc { max-width: 46ch; line-height: 1.6; }
.empty-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }

.dialog-hint { margin: 0 0 14px; font-size: 13px; color: var(--fg-muted); line-height: 1.5; }
.row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--fg-muted); }
.field.grow { flex: 1; min-width: 220px; }
.field-head { display: flex; align-items: center; gap: 8px; }
.field input, .field input:focus-visible, .field textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 0; border-color: var(--accent); }
.field textarea {
  min-height: 40px; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--surface-2);
  color: var(--fg); font-size: 13.5px;
}
.field textarea { font-family: ui-monospace, 'JetBrains Mono', monospace; font-size: 12.5px; line-height: 1.5; resize: vertical; }
.error { color: var(--danger); font-size: 13px; margin: 10px 0 0; }

.import-filter { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.import-search { flex: 1; min-width: 200px; }
.import-cat { width: auto; min-width: 180px; }
.import-bar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 8px 0; border-bottom: 1px solid var(--border-strong); }
.import-list { list-style: none; margin: 0; padding: 0; max-height: calc(46 * var(--vh)); overflow: auto; }
.import-list li { padding: 8px 2px; border-bottom: 1px solid var(--border-strong); }
.check { display: flex; align-items: center; gap: 8px; min-height: 40px; font-size: 13.5px; cursor: pointer; }
.loading-note { display: flex; align-items: center; gap: 8px; margin: 10px 0; font-size: 13px; color: var(--muted); }
.spinner { flex: none; width: 14px; height: 14px; border-radius: 50%; border: 2px solid color-mix(in srgb, currentColor 30%, transparent); border-top-color: currentColor; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.check.disabled { opacity: 0.6; cursor: not-allowed; }
.import-name { font-family: ui-monospace, 'JetBrains Mono', monospace; }
.import-desc { margin: 3px 0 0 24px; font-size: 12.5px; color: var(--fg-muted); line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

@media (max-width: 860px) {
  .skill-grid { grid-template-columns: 1fr; }
}

@media (max-width: 520px) {
  .guide-row { grid-template-columns: 1fr; gap: 4px; }
}

@media (max-width: 720px) {
  .skills-view { padding-bottom: 56px; }
  .hero-title { font-size: 27px; }
}

@media (max-width: 600px) {
  .toolbar { flex-wrap: wrap; }
  .search { flex-basis: 100%; }
  /* one swipeable row instead of four wrapped rows of chips */
  .cat-bar { flex-wrap: nowrap; overflow-x: auto; margin-inline: -16px; padding: 2px 16px 6px; scrollbar-width: none; }
  .cat-bar::-webkit-scrollbar { display: none; }
  .cat-desc { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
}
</style>
