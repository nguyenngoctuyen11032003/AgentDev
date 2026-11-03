<template>
  <BaseDialog :model-value="true" :title="$t('workflow_list.dept_title')" width="560px" @close="close">
    <div class="dept-body">
      <div class="dept-start">
        <!-- Describe the workflow in words and let the assistant build it -->
        <button type="button" class="dept-ai" @click="emit('ai')">
          <span class="dept-ai-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" /><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" /></svg>
          </span>
          <span class="dept-card-name">{{ $t('workflow_assistant.create_with_ai') }}</span>
          <span class="dept-card-desc">{{ $t('workflow_assistant.create_with_ai_desc') }}</span>
        </button>
        <button type="button" class="dept-blank" @click="emit('blank')">
          <span class="dept-card-name">{{ $t('workflow_list.dept_blank') }}</span>
          <span class="dept-card-desc">{{ $t('workflow_list.dept_blank_desc') }}</span>
        </button>
      </div>

        <div class="dept-section-label">{{ $t('workflow_list.dept_section') }}</div>
        <p v-if="loading" class="dept-empty">{{ $t('workflow_list.loading') }}</p>
        <p v-else-if="!templates.length" class="dept-empty">{{ $t('workflow_list.dept_none') }}</p>
        <div v-else class="dept-grid">
          <button
            v-for="tpl in templates"
            :key="tpl.file"
            type="button"
            :class="['dept-card', { selected: selected?.file === tpl.file }]"
            :aria-pressed="selected?.file === tpl.file"
            @click="select(tpl)"
          >
            <svg v-if="selected?.file === tpl.file" class="dept-card-check" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            <span class="dept-card-name">{{ $t(tpl.labelKey) }}</span>
            <span class="dept-card-desc">{{ $t(tpl.descKey) }}</span>
          </button>
        </div>

        <div v-if="selected" class="dept-name">
          <label for="dept-new-name" class="dept-label">{{ $t('workflow_list.dept_name') }}</label>
          <input
            id="dept-new-name"
            ref="nameInput"
            v-model="newName"
            type="text"
            class="dept-input"
            @keyup.enter="create"
          />
          <p v-if="nameError" class="dept-error">{{ nameError }}</p>
          <p v-else class="dept-hint">{{ $t('workflow_list.dept_name_hint') }}</p>
        </div>
    </div>
    <template #footer>
      <button type="button" class="dept-cancel" @click="close">{{ $t('common.cancel') }}</button>
      <button type="button" class="dept-submit" :disabled="!selected || !!nameError || busy || loading" @click="create">
        {{ $t('workflow_list.dept_create') }}
      </button>
    </template>
  </BaseDialog>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchVueGraph, postVuegraphs, postYamlCopy } from '@/api/client.js'
import { toast } from '@/utils/toast.js'
import BaseDialog from '@/components/common/BaseDialog.vue'

// "Mẫu phòng ban": ready-made team workflows (a lead + roster). Creating one copies the template
// YAML through the existing /api/workflows/{file}/copy endpoint, plus its saved canvas layout.
const DEPARTMENTS = [
  { file: 'software_company.yaml', slug: 'phong_phat_trien_phan_mem', labelKey: 'workflow_list.dept_software', descKey: 'workflow_list.dept_software_desc' },
  { file: 'marketing_agency.yaml', slug: 'phong_marketing', labelKey: 'workflow_list.dept_marketing', descKey: 'workflow_list.dept_marketing_desc' },
  { file: 'content_studio.yaml', slug: 'phong_noi_dung', labelKey: 'workflow_list.dept_content', descKey: 'workflow_list.dept_content_desc' },
  { file: 'video_studio.yaml', slug: 'phong_san_xuat_video', labelKey: 'workflow_list.dept_video', descKey: 'workflow_list.dept_video_desc' }
]

const props = defineProps({
  // Workflow file names that exist (e.g. "software_company.yaml")
  existingFiles: { type: Array, default: () => [] },
  // True while the workflow list is still loading: templates and taken names are not known yet.
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['close', 'blank', 'ai', 'created'])
const { t } = useI18n()

const existing = computed(() => new Set(props.existingFiles.map((name) => String(name).toLowerCase())))
const templates = computed(() => DEPARTMENTS.filter((tpl) => existing.value.has(tpl.file)))

const selected = ref(null)
const newName = ref('')
const busy = ref(false)
const nameInput = ref(null)

const stripExt = (name) => String(name || '').trim().replace(/\.ya?ml$/i, '')

const freeName = (slug) => {
  let candidate = slug
  let n = 2
  while (existing.value.has(`${candidate}.yaml`)) candidate = `${slug}_${n++}`
  return candidate
}

const nameError = computed(() => {
  const name = stripExt(newName.value)
  if (!name) return t('workflow_list.dept_name_required')
  if (!/^[a-zA-Z0-9._-]+$/.test(name) || name.includes('..')) return t('workflow_list.dept_name_invalid')
  if (existing.value.has(`${name.toLowerCase()}.yaml`)) return t('workflow_list.dept_name_taken')
  return ''
})

const select = async (tpl) => {
  selected.value = tpl
  newName.value = freeName(tpl.slug)
  await nextTick()
  nameInput.value?.focus?.()
  nameInput.value?.select?.()
}

const close = () => {
  if (!busy.value) emit('close')
}

const create = async () => {
  if (!selected.value || nameError.value || busy.value || props.loading) return
  const name = stripExt(newName.value)
  busy.value = true
  try {
    const result = await postYamlCopy(selected.value.file, name)
    if (!result?.success) {
      toast.error(result?.message || t('workflow_list.dept_failed'))
      return
    }
    // Keep the template's arranged org chart if it has one; otherwise the editor lays it out.
    try {
      const layout = await fetchVueGraph(stripExt(selected.value.file))
      if (layout?.success && layout.content) {
        await postVuegraphs({ filename: name, content: layout.content })
      }
    } catch (error) {
      console.warn('Could not copy the template layout:', error)
    }
    toast.success(t('workflow_list.dept_done', { name }))
    emit('created', result.filename || `${name}.yaml`)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.dept-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dept-section-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(var(--ink) / 0.55);
  margin-top: 4px;
}

.dept-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.dept-start {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

/* The AI card is the most prominent way in */
.dept-ai {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgb(var(--accent-sky-rgb) / 0.55);
  background: rgb(var(--accent-sky-rgb) / 0.1);
  color: var(--text-1);
  cursor: pointer;
  font: inherit;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.dept-ai:hover {
  background: rgb(var(--accent-sky-rgb) / 0.16);
  border-color: var(--accent-sky);
}

.dept-ai-icon {
  display: inline-flex;
  color: var(--accent-sky);
  margin-bottom: 2px;
}

.dept-ai:focus-visible,
.dept-blank:focus-visible,
.dept-card:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

.dept-blank,
.dept-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgb(var(--ink) / 0.1);
  background: rgb(var(--ink) / 0.04);
  color: var(--text-1);
  cursor: pointer;
  font: inherit;
  transition: border-color 0.15s var(--ease-out), background-color 0.15s var(--ease-out);
}

.dept-blank:hover,
.dept-card:hover {
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
}

.dept-card.selected {
  border-color: var(--accent-indigo);
  background: rgb(var(--ink) / 0.08);
  box-shadow: inset 0 0 0 1px var(--accent-indigo);
}

.dept-card-check {
  position: absolute;
  top: 10px;
  right: 10px;
  color: var(--accent-indigo);
}

.dept-card.selected .dept-card-name {
  padding-right: 22px;
}

.dept-blank:focus-visible,
.dept-card:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.dept-card-name {
  font-size: 14px;
  font-weight: 600;
}

.dept-card-desc {
  font-size: 12px;
  line-height: 1.4;
  color: rgb(var(--ink) / 0.65);
}

.dept-empty {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--ink) / 0.6);
}

.dept-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.dept-input {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.15);
  background: rgb(var(--ink) / 0.05);
  color: var(--text-1);
  font: inherit;
  font-size: 14px;
  outline: none;
}

.dept-input:focus {
  border-color: var(--focus-ring);
  box-shadow: 0 0 0 1px var(--focus-ring);
}

.dept-hint,
.dept-error {
  margin: 6px 0 0;
  font-size: 12px;
}

.dept-hint {
  color: rgb(var(--ink) / 0.6);
}

.dept-error {
  color: var(--danger);
}

.dept-cancel,
.dept-submit {
  padding: 8px 16px;
  border-radius: 10px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgb(var(--ink) / 0.12);
  min-height: 36px;
  transition: filter 0.15s var(--ease-out), background-color 0.15s var(--ease-out);
}

.dept-cancel:hover {
  background: rgb(var(--ink) / 0.06);
}

.dept-submit:hover:not(:disabled) {
  filter: brightness(1.08);
}

.dept-cancel {
  background: transparent;
  color: var(--text-1);
}

.dept-submit {
  background: var(--accent-indigo);
  color: var(--bg-base);
  border-color: transparent;
}

.dept-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
