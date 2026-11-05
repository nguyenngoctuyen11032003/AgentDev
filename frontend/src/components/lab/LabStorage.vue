<template>
  <div class="storage">
    <svg class="st-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></svg>
    <p class="st-line" aria-live="polite">
      <template v-if="info && info.run_dirs">
        {{ tr('lab.storage.line', 'Kết quả thử nghiệm: {size} · {n} lượt', { size: bytes(info.total_bytes), n: info.run_dirs.toLocaleString(locale) }) }}
        <span v-if="oldest" class="st-sub"> · {{ tr('lab.storage.oldest', 'cũ nhất từ {date}', { date: oldest }) }}</span>
      </template>
      <template v-else-if="info">{{ tr('lab.storage.empty', 'Chưa có kết quả thử nghiệm nào trên máy') }}</template>
      <span v-else class="st-sub">…</span>
    </p>
    <button v-if="info && info.run_dirs" type="button" class="btn ghost sm" @click="open = true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 21h18M6 21l1.5-6h9L18 21M9 15V4a3 3 0 0 1 6 0v11" /></svg>
      {{ tr('lab.storage.cleanup', 'Dọn kết quả cũ') }}
    </button>

    <BaseDialog v-model="open" :title="tr('lab.storage.dialog_title', 'Dọn kết quả thử nghiệm cũ')" width="480px">
      <p class="dl-intro">{{ tr('lab.storage.dialog_intro', 'File mà các lượt thử nghiệm tạo ra được lưu trong thư mục storage/warehouse. Thư mục cũ hơn 14 ngày được tự xoá sau mỗi lần kiểm định.') }}</p>
      <fieldset class="dl-options">
        <legend>{{ tr('lab.storage.option_label', 'Xoá những gì') }}</legend>
        <label v-for="days in [7, 30, 90]" :key="days" class="dl-option">
          <input v-model="choice" type="radio" name="lab-cleanup" :value="String(days)" />
          <span>{{ tr('lab.storage.older', 'Cũ hơn {n} ngày', { n: days }) }}</span>
        </label>
        <label class="dl-option">
          <input v-model="choice" type="radio" name="lab-cleanup" value="orphans" />
          <span>
            {{ tr('lab.storage.orphans', 'Chỉ thư mục không còn thuộc lượt kiểm định nào') }}
            <small>{{ tr('lab.storage.orphans_count', '{n} thư mục', { n: info?.orphan_dirs ?? 0 }) }}</small>
          </span>
        </label>
      </fieldset>
      <p class="dl-note">{{ tr('lab.storage.note', 'Không đụng tới kiểm định đang chạy hoặc bản đang chạy thử. Không thể hoàn tác.') }}</p>
      <template #footer>
        <button type="button" class="btn secondary" @click="open = false">{{ tr('lab.storage.cancel', 'Huỷ') }}</button>
        <button type="button" class="btn danger" :disabled="cleaning" @click="cleanup">
          <span v-if="cleaning" class="btn-spinner" aria-hidden="true"></span>
          {{ tr('lab.storage.confirm', 'Dọn') }}
        </button>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseDialog from '@/components/common/BaseDialog.vue'
import { toast } from '@/utils/toast.js'
import { formatBytes } from '@/utils/labOutputs.js'
import { labStorage, labStorageCleanup } from '@/api/client'

// Bump to re-read the totals (e.g. after one run's output was deleted).
const props = defineProps({ refreshKey: { type: Number, default: 0 } })

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
const bytes = (n) => formatBytes(n, locale.value)

const info = ref(null)
const open = ref(false)
const choice = ref('30')
const cleaning = ref(false)

const oldest = computed(() => {
  const value = info.value?.oldest
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(locale.value, { day: 'numeric', month: 'numeric', year: 'numeric' })
})

async function load() {
  try {
    info.value = await labStorage()
  } catch {
    // Older server without this endpoint, or offline: the line simply stays hidden.
    info.value = null
  }
}

async function cleanup() {
  if (cleaning.value) return
  cleaning.value = true
  const orphansOnly = choice.value === 'orphans'
  try {
    const result = await labStorageCleanup({ olderThanDays: orphansOnly ? 0 : Number(choice.value), orphansOnly })
    open.value = false
    if (result?.deleted) {
      toast.success(tr('lab.storage.done', 'Đã xoá {n} thư mục, giải phóng {size}', { n: result.deleted, size: bytes(result.freed_bytes) }))
    } else {
      toast.info(tr('lab.storage.nothing', 'Không có thư mục nào phù hợp để xoá'))
    }
    await load()
  } catch (err) {
    toast.error(tr('lab.storage.failed', 'Không dọn được kết quả'), { detail: err?.detail || err?.message || String(err) })
  } finally {
    cleaning.value = false
  }
}

onMounted(load)
watch(() => props.refreshKey, load)
</script>

<style scoped>
.storage { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 20px; padding: 6px 6px 6px 14px; border-radius: 12px; font-size: 13px; color: var(--fg-muted); box-shadow: inset 0 0 0 1px var(--line); }
.st-icon { flex: none; }
.st-line { flex: 1 1 240px; min-width: 0; margin: 0; padding: 6px 0; line-height: 1.5; }
.st-sub { color: var(--fg-muted); opacity: 0.85; }
.dl-intro { margin: 0 0 16px; font-size: 13.5px; line-height: 1.6; color: var(--fg-muted); }
.dl-options { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; border: 0; }
.dl-options legend { margin-bottom: 8px; padding: 0; font-size: 13px; font-weight: 600; color: var(--fg); }
.dl-option { display: flex; gap: 10px; align-items: flex-start; padding: 9px 10px; border-radius: 8px; font-size: 13.5px; line-height: 1.45; color: var(--fg); cursor: pointer; }
.dl-option:hover { background: var(--surface-raised); }
.dl-option input { flex: none; margin: 2px 0 0; accent-color: var(--accent); }
.dl-option small { display: block; font-size: 12px; color: var(--fg-muted); }
.dl-option:has(input:focus-visible) { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.dl-note { margin: 14px 0 0; font-size: 12.5px; line-height: 1.5; color: var(--warn); }
</style>
