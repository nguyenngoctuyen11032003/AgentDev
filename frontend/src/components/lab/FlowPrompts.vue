<template>
  <div class="flow">
    <div class="fl-head">
      <p class="fl-hint">
        {{ tr('lab.outputs.flow.hint', 'Dán từng prompt vào Google Flow để làm clip bằng Veo trong gói Google AI của bạn (không tốn thêm tiền API). Mỗi cảnh một clip, cắt clip cho đúng số giây ghi bên cạnh rồi ghép theo thứ tự.') }}
      </p>
      <div class="fl-actions">
        <a class="btn secondary sm" :href="FLOW_URL" target="_blank" rel="noopener noreferrer">{{ tr('lab.outputs.flow.open_flow', 'Mở Google Flow') }}</a>
        <button type="button" class="btn secondary sm" :disabled="state !== 'ready' || !shots.length" @click="copy('all', allText)">
          {{ copiedKey === 'all' ? tr('lab.outputs.copied', 'Đã chép') : tr('lab.outputs.flow.copy_all', 'Chép tất cả') }}
        </button>
        <button type="button" class="btn secondary sm" :disabled="state !== 'ready' || !shots.length" @click="download">{{ tr('lab.outputs.flow.download', 'Tải .txt') }}</button>
      </div>
    </div>

    <div v-if="state === 'loading'" class="fl-skel" aria-hidden="true"><span v-for="n in 4" :key="n"></span></div>
    <p v-if="state === 'loading'" class="sr-only" role="status">{{ tr('lab.outputs.flow.loading', 'Đang tách prompt từng cảnh…') }}</p>

    <div v-else-if="state === 'error'" class="fl-empty bad" role="alert">
      <strong>{{ tr('lab.outputs.flow.error_title', 'Không tách được prompt') }}</strong>
      <span>{{ error }}</span>
      <span>{{ tr('lab.outputs.flow.error_hint', 'Kiểm tra máy chủ AgentDev còn chạy rồi thử lại.') }}</span>
      <button type="button" class="btn secondary sm" @click="load">{{ tr('lab.outputs.flow.retry', 'Thử lại') }}</button>
    </div>

    <div v-else-if="state === 'ready' && !shots.length" class="fl-empty">
      <strong>{{ tr('lab.outputs.flow.empty_title', 'Chưa thấy cảnh nào') }}</strong>
      <span>{{ tr('lab.outputs.flow.empty_hint', 'Gói sản xuất cần các dòng dạng "**1.** IMG: … VID: …". Hãy nhờ nhóm làm lại gói sản xuất cho tập này.') }}</span>
    </div>

    <template v-else-if="state === 'ready'">
      <p v-if="missingTags.length" class="fl-warn" role="note">
        {{ tr('lab.outputs.flow.missing_tags', 'Chưa có mô tả ngoại hình cho {tags}: nhân vật có thể trông khác nhau giữa các cảnh. Thêm dòng "Appearance:" vào {file}.', { tags: missingTags.join(', '), file: BIBLE_FILE }) }}
      </p>
      <ol class="fl-list">
        <li v-for="shot in shots" :key="shot.number" class="fl-shot">
          <div class="fl-shot-head">
            <strong>{{ shotLabel(shot) }}</strong>
            <span class="fl-sec">{{ tr('lab.outputs.flow.seconds', '{n} giây', { n: fmtSeconds(shot.seconds) }) }}</span>
            <span class="fl-spacer"></span>
            <button type="button" class="btn ghost sm" :title="tr('lab.outputs.flow.copy_image_hint', 'Prompt ảnh khung đầu (dùng cho Frames to Video)')" @click="copy(`img${shot.number}`, shot.image_prompt)">
              {{ copiedKey === `img${shot.number}` ? tr('lab.outputs.copied', 'Đã chép') : tr('lab.outputs.flow.copy_image', 'Chép prompt ảnh') }}
            </button>
            <button type="button" class="btn secondary sm" @click="copy(`vid${shot.number}`, shot.prompt)">
              {{ copiedKey === `vid${shot.number}` ? tr('lab.outputs.copied', 'Đã chép') : tr('lab.outputs.flow.copy_video', 'Chép prompt video') }}
            </button>
          </div>
          <p class="fl-prompt">{{ shot.prompt }}</p>
        </li>
      </ol>
    </template>
  </div>
</template>

<script setup>
// "Prompt cho Flow" view of a production package (goi_san_xuat.md): the exact per-shot prompts AgentDev would
// send to Veo, to paste into Google Flow where the user's Google AI plan includes Veo (the API does not).
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchFlowPrompts } from '@/api/client.js'
import { BIBLE_FILE, FLOW_URL, biblePathFor, flowPromptsText } from '@/utils/flowPrompts.js'
import { labErrorText } from '@/utils/labOutputs.js'

const props = defineProps({
  source: { type: Object, required: true }, // a product source (utils/outputSources.js)
  packagePath: { type: String, required: true },
  packageText: { type: String, required: true },
  hasFile: { type: Function, required: true } // (path) -> whether the product has that file
})

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')

const state = ref('idle') // idle | loading | ready | error
const error = ref('')
const shots = ref([])
const missingTags = ref([])
const copiedKey = ref('')
let controller = null
let copiedTimer = null

const fmtSeconds = (n) => Number(n).toLocaleString(locale.value, { maximumFractionDigits: 1 })
const shotLabel = (shot) => tr('lab.outputs.flow.shot', 'Cảnh {n}', { n: shot.number })
const allText = computed(() =>
  flowPromptsText(shots.value, (shot) => `${shotLabel(shot)} · ${tr('lab.outputs.flow.seconds', '{n} giây', { n: fmtSeconds(shot.seconds) })}`))

async function load() {
  controller?.abort()
  const ctrl = new AbortController()
  controller = ctrl
  state.value = 'loading'
  error.value = ''
  try {
    const biblePath = biblePathFor(props.packagePath, props.hasFile)
    // A missing or unreadable bible only leaves the tags as written (reported as missing_tags)
    const bibleText = biblePath ? await props.source.fileText(biblePath, { signal: ctrl.signal }).catch(() => '') : ''
    const result = await fetchFlowPrompts({ packageText: props.packageText, bibleText }, { signal: ctrl.signal })
    if (ctrl.signal.aborted) return
    shots.value = result.shots || []
    missingTags.value = result.missing_tags || []
    state.value = 'ready'
  } catch (err) {
    if (ctrl.signal.aborted) return
    error.value = labErrorText(err, { t, te })
    state.value = 'error'
  }
}

async function copy(key, value) {
  try {
    await navigator.clipboard.writeText(value)
    copiedKey.value = key
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copiedKey.value = '' }, 2000)
  } catch {
    // clipboard unavailable: the prompts stay selectable
  }
}

function download() {
  const url = URL.createObjectURL(new Blob([allText.value], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'prompt_flow.txt'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

watch(() => [props.packagePath, props.packageText], load, { immediate: true })
onBeforeUnmount(() => {
  controller?.abort()
  clearTimeout(copiedTimer)
})
</script>

<style scoped>
.flow { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px 24px; max-width: 92ch; }
.fl-head { display: flex; flex-direction: column; gap: 10px; }
.fl-hint { margin: 0; font-size: 13px; line-height: 1.55; color: var(--fg-muted); }
.fl-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.fl-warn { margin: 0; padding: 8px 12px; border-radius: 8px; font-size: 12.5px; line-height: 1.5; color: var(--fg); background: color-mix(in srgb, var(--warn) 14%, transparent); }
.fl-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.fl-shot { padding: 10px 12px; border-radius: 10px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.fl-shot-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.fl-shot-head strong { font-size: 13.5px; }
.fl-sec { font-size: 12px; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.fl-spacer { flex: 1; }
.fl-prompt { margin: 8px 0 0; font-size: 13px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; user-select: text; }
.fl-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px; text-align: center; font-size: 13px; line-height: 1.5; color: var(--fg-muted); }
.fl-empty strong { color: var(--fg); }
.fl-empty.bad strong { color: var(--danger); }
.fl-skel { display: flex; flex-direction: column; gap: 9px; }
.fl-skel span { height: 52px; border-radius: 10px; background: linear-gradient(90deg, var(--tint), var(--tint-2), var(--tint)); background-size: 200% 100%; animation: fl-shimmer 1.4s ease-in-out infinite; }
@keyframes fl-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (prefers-reduced-motion: reduce) {
  .fl-skel span { animation: none; }
}
</style>
