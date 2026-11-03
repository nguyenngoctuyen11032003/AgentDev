<template>
  <div class="dept-overlay" @click.self="close">
    <div class="dept-modal" role="dialog" aria-modal="true" :aria-label="$t('workflow_list.dept_title')">
      <div class="dept-header">
        <h3 class="dept-title">{{ $t('workflow_list.dept_title') }}</h3>
        <button type="button" class="dept-close" :aria-label="$t('common.cancel')" @click="close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <div class="dept-body">
        <button type="button" class="dept-blank" @click="emit('blank')">
          <span class="dept-card-name">{{ $t('workflow_list.dept_blank') }}</span>
          <span class="dept-card-desc">{{ $t('workflow_list.dept_blank_desc') }}</span>
        </button>

        <div class="dept-section-label">{{ $t('workflow_list.dept_section') }}</div>
        <p v-if="!templates.length" class="dept-empty">{{ $t('workflow_list.dept_none') }}</p>
        <div v-else class="dept-grid">
          <button
            v-for="tpl in templates"
            :key="tpl.file"
            type="button"
            :class="['dept-card', { selected: selected?.file === tpl.file }]"
            @click="select(tpl)"
          >
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

      <div class="dept-footer">
        <button type="button" class="dept-cancel" @click="close">{{ $t('common.cancel') }}</button>
        <button type="button" class="dept-submit" :disabled="!selected || !!nameError || busy" @click="create">
          {{ $t('workflow_list.dept_create') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchVueGraph, postVuegraphs, postYamlCopy } from '@/api/client.js'
import { toast } from '@/utils/toast.js'

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
  existingFiles: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'blank', 'created'])
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
  if (!selected.value || nameError.value || busy.value) return
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
.dept-overlay {
  position: fixed;
  inset: 0;
  background-color: rgb(var(--shade) / 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
}

.dept-modal {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  background-color: rgb(var(--panel-33) / 0.98);
  border-radius: 16px;
  border: 1px solid rgb(var(--ink) / 0.08);
  box-shadow: 0 20px 40px rgb(var(--shade) / 0.6);
  overflow: hidden;
  color: var(--text-1);
  font-family: 'Inter', sans-serif;
}

.dept-header {
  display: flex;
  align-items: center;
  padding: 14px 20px 10px;
  border-bottom: 1px solid rgb(var(--ink) / 0.06);
}

.dept-title {
  margin: 0;
  flex: 1;
  font-size: 15px;
  font-weight: 600;
}

.dept-close {
  background: transparent;
  border: none;
  cursor: pointer;
  color: rgb(var(--ink) / 0.6);
  display: flex;
}

.dept-close:hover {
  color: var(--text-1);
}

.dept-body {
  padding: 16px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dept-section-label {
  font-size: 12px;
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

.dept-blank,
.dept-card {
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
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.dept-blank:hover,
.dept-card:hover {
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
}

.dept-card.selected {
  border-color: var(--accent-indigo);
  background: rgb(var(--ink) / 0.08);
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
  border-color: var(--accent-indigo);
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
  color: var(--danger, #e5484d);
}

.dept-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px 16px;
  border-top: 1px solid rgb(var(--ink) / 0.06);
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
