<template>
  <div class="output-loc" role="status">
    <svg class="output-loc-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
    <span class="output-loc-text">
      {{ $t('launch.output.session') }}
      <code v-if="path" class="output-loc-path" :title="path">{{ path }}</code>
      <span v-else class="output-loc-later">{{ $t('launch.output.session_later') }}</span>
    </span>
    <button v-if="path" type="button" class="output-loc-btn" :disabled="busy" @click="reveal">{{ $t('launch.output.open') }}</button>
    <button type="button" class="output-loc-btn is-primary" @click="$emit('choose')">{{ $t('launch.output.choose') }}</button>
  </div>
</template>

<script setup>
// Tells the user where results (source code, videos, files) will be saved before they ask for anything:
// the session's own folder when no project is open, with a way to pick a real one.
import { ref, watch } from 'vue'
import { fetchOutputLocation, openOutputLocation } from '@/api/client.js'
import { toast } from '@/utils/toast.js'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  sessionId: { type: String, default: '' }
})
defineEmits(['choose'])

const { t } = useI18n()
const path = ref('')
const busy = ref(false)

let token = 0
watch(
  () => props.sessionId,
  async () => {
    const id = ++token
    path.value = ''
    if (!props.sessionId) return
    try {
      const location = await fetchOutputLocation(props.sessionId)
      if (id !== token) return
      path.value = location.path
    } catch {
      // The line still explains the default; only the path is missing
    }
  },
  { immediate: true }
)

const reveal = async () => {
  busy.value = true
  try {
    await openOutputLocation(props.sessionId)
  } catch (err) {
    toast.error(t('launch.output.open_failed'), { detail: err?.message || '' })
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.output-loc {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin: 0;
  padding: 6px var(--space-4, 16px);
  font-size: 12.5px;
  line-height: 1.4;
  color: var(--fg-muted);
}
.output-loc-icon { flex: none; color: var(--warn, #e8b44a); }
.output-loc-text { flex: 1 1 240px; min-width: 0; }
.output-loc-path {
  display: inline-block;
  max-width: 100%;
  vertical-align: bottom;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
  font: 12px ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--fg);
}
.output-loc-btn {
  flex: none;
  padding: 3px 10px;
  border: 1px solid var(--border-strong, var(--border));
  border-radius: 999px;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
@media (pointer: coarse), (max-width: 899.98px) {
  .output-loc-btn { min-height: 44px; }
}
.output-loc-btn:hover:not(:disabled) { border-color: var(--accent); }
.output-loc-btn.is-primary { border-color: color-mix(in srgb, var(--accent) 50%, transparent); color: var(--accent); }
.output-loc-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.output-loc-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
