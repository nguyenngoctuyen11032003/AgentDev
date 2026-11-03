<template>
  <aside
    class="assistant-panel"
    :style="{ width: `${width}px` }"
    role="complementary"
    :aria-label="$t('workflow_assistant.title')"
    @keydown.esc.stop="close"
  >
    <div
      class="resize-handle"
      role="separator"
      aria-orientation="vertical"
      tabindex="0"
      :aria-label="$t('workflow_assistant.resize')"
      :aria-valuemin="MIN_WIDTH"
      :aria-valuemax="MAX_WIDTH"
      :aria-valuenow="width"
      @pointerdown="startResize"
      @keydown.left.prevent="setWidth(width + 20)"
      @keydown.right.prevent="setWidth(width - 20)"
    ></div>

    <header class="panel-head">
      <div class="panel-heading">
        <h2 class="panel-title">{{ $t('workflow_assistant.title') }}</h2>
        <span class="panel-context" :title="contextLabel">{{ contextLabel }}</span>
      </div>
      <button
        type="button"
        class="icon-btn"
        :title="$t('workflow_assistant.new_conversation')"
        :aria-label="$t('workflow_assistant.new_conversation')"
        :disabled="!thread.messages.length && thread.status === 'idle'"
        @click="startNewConversation"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
      </button>
      <button
        type="button"
        class="icon-btn"
        :title="$t('workflow_assistant.close')"
        :aria-label="$t('workflow_assistant.close')"
        @click="close"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
      </button>
    </header>

    <div ref="scrollRef" class="panel-body">
      <!-- Empty thread -->
      <div v-if="!thread.messages.length && thread.status === 'idle'" class="empty">
        <p class="empty-title">
          {{ isCreate ? $t('workflow_assistant.empty_create_title') : $t('workflow_assistant.empty_workflow_title', { name: context.workflow }) }}
        </p>
        <p class="empty-hint">
          {{ isCreate ? $t('workflow_assistant.empty_create_hint') : $t('workflow_assistant.empty_workflow_hint') }}
        </p>
        <div v-if="isCreate" class="starters" role="group" :aria-label="$t('workflow_assistant.starters_label')">
          <button
            v-for="key in STARTER_KEYS"
            :key="key"
            type="button"
            class="chip"
            @click="useStarter($t(key))"
          >{{ $t(key) }}</button>
        </div>
      </div>

      <ol class="messages">
        <li v-for="(m, index) in thread.messages" :key="m.id" :class="['msg', m.role, m.kind]">
          <!-- User -->
          <div v-if="m.role === 'user'" class="bubble">{{ m.content }}</div>

          <!-- Assistant -->
          <template v-else-if="m.role === 'assistant'">
            <!-- eslint-disable-next-line vue/no-v-html -- markdown-it with html: false escapes raw HTML -->
            <div v-if="m.content" class="reply markdown-body" v-html="render(m.content)"></div>
            <div v-if="m.validationErrors?.length" class="notice error" :role="alertRole(index)">
              <div class="notice-title">{{ $t('workflow_assistant.validation_failed') }}</div>
              <ul class="notice-list">
                <li v-for="(err, i) in m.validationErrors" :key="i"><code>{{ err }}</code></li>
              </ul>
            </div>
            <ProposalCard
              v-if="m.proposal"
              :proposal="m.proposal"
              :superseded="!!m.superseded"
              :applied="!!m.applied"
              :active="m.proposal === thread.pendingProposal"
              :busy="thread.status !== 'idle'"
              :applying="thread.status === 'applying'"
              @apply="emit('apply')"
              @discard="discardProposal"
            />
            <div
              v-if="m.quickReplies?.length && index === thread.messages.length - 1 && thread.status === 'idle'"
              class="quick-replies"
              role="group"
              :aria-label="$t('workflow_assistant.quick_replies_label')"
            >
              <button v-for="q in m.quickReplies" :key="q" type="button" class="chip" @click="send(q)">
                {{ q }}
              </button>
            </div>
          </template>

          <!-- Local notices -->
          <div v-else-if="m.kind === 'quota'" class="notice warn" :role="alertRole(index)">
            <div class="notice-title">{{ $t('workflow_assistant.quota_exhausted', { vendor: vendorLabel(m.vendor) }) }}</div>
            <div v-if="index === thread.messages.length - 1" class="notice-actions">
              <button
                v-for="p in otherProviders(m.vendor)"
                :key="p.vendor"
                type="button"
                class="btn-small"
                :disabled="thread.status !== 'idle'"
                @click="switchAndRetry(p.vendor, m.retryText)"
              >{{ $t('workflow_assistant.switch_to', { vendor: p.label }) }}</button>
            </div>
          </div>
          <div v-else-if="m.kind === 'conflict'" class="notice warn" :role="alertRole(index)">
            <div class="notice-title">{{ $t('workflow_assistant.conflict_notice', { file: m.filename }) }}</div>
            <div class="notice-actions">
              <button type="button" class="btn-small" :disabled="thread.status !== 'idle'" @click="send($t('workflow_assistant.redo_prompt'))">
                {{ $t('workflow_assistant.redo') }}
              </button>
            </div>
          </div>
          <div v-else class="notice error" :role="alertRole(index)">
            <div class="notice-title">{{ errorTitle(m) }}</div>
            <details v-if="m.detail" class="notice-detail">
              <summary>{{ $t('workflow_assistant.error_detail') }}</summary>
              <code>{{ m.detail }}</code>
            </details>
          </div>
        </li>
      </ol>

      <div v-if="thread.status === 'sending'" class="waiting">
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="waiting-text">{{ $t('workflow_assistant.thinking') }} <span class="elapsed">{{ elapsed }}s</span></span>
        <button type="button" class="btn-small" @click="stopWaiting">{{ $t('workflow_assistant.stop') }}</button>
      </div>
    </div>

    <!-- Screen readers hear status changes only, not every message re-read -->
    <div class="sr-only" role="status" aria-live="polite">{{ announcement }}</div>

    <form class="composer" @submit.prevent="submit">
      <textarea
        ref="inputRef"
        v-model="draft"
        class="composer-input"
        rows="1"
        :placeholder="isCreate ? $t('workflow_assistant.placeholder_create') : $t('workflow_assistant.placeholder_workflow')"
        :aria-label="$t('workflow_assistant.input_label')"
        @input="autosize"
        @keydown.enter="onEnter"
      ></textarea>
      <div class="composer-bar">
        <template v-if="hasProvider">
          <label class="sr-only" for="assistant-vendor">{{ $t('workflow_assistant.model_label') }}</label>
          <select id="assistant-vendor" v-model="vendor" class="vendor-select" :disabled="thread.status === 'sending'">
            <option v-for="p in providers" :key="p.vendor" :value="p.vendor" :disabled="!p.available">
              {{ p.available ? p.label : $t('workflow_assistant.not_signed_in_option', { vendor: p.label }) }}
            </option>
          </select>
        </template>
        <span v-else-if="providersLoaded" class="no-provider">
          {{ $t('workflow_assistant.no_provider') }}
          <RouterLink to="/connections">{{ $t('workflow_assistant.open_connections') }}</RouterLink>
        </span>
        <span class="composer-hint">{{ $t('workflow_assistant.enter_hint') }}</span>
        <button
          type="submit"
          class="send-btn"
          :disabled="!canSend"
          :title="$t('workflow_assistant.send')"
          :aria-label="$t('workflow_assistant.send')"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
        </button>
      </div>
    </form>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import MarkdownIt from 'markdown-it'
import ProposalCard from './ProposalCard.vue'
import { useWorkflowAssistant } from '@/composables/useWorkflowAssistant.js'

const emit = defineEmits(['close', 'apply'])
const { t, te } = useI18n()

const {
  context,
  providers,
  vendor,
  currentThread: thread,
  refreshProviders,
  send,
  stop,
  newConversation,
  discardProposal
} = useWorkflowAssistant()

const STARTER_KEYS = [
  'workflow_assistant.starter_team',
  'workflow_assistant.starter_pipeline',
  'workflow_assistant.starter_review'
]
const VENDOR_FALLBACK_LABELS = { anthropic: 'Claude', openai: 'Codex' }

// ---------------------------------------------------------------- width (drag the left edge)
const MIN_WIDTH = 340
const MAX_WIDTH = 720
const WIDTH_KEY = 'agentdev:assistant-width'
const clampWidth = (value) => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(Number(value) || 420)))
const readWidth = () => {
  try {
    return clampWidth(localStorage.getItem(WIDTH_KEY) || 420)
  } catch {
    return 420
  }
}
const width = ref(readWidth())
const setWidth = (value) => {
  width.value = clampWidth(value)
  try {
    localStorage.setItem(WIDTH_KEY, String(width.value))
  } catch {
    // storage unavailable: the width lasts for this page only
  }
}
let resizeStart = null
const onResizeMove = (event) => {
  if (!resizeStart) return
  width.value = clampWidth(resizeStart.width + (resizeStart.x - event.clientX))
}
const stopResize = () => {
  if (!resizeStart) return
  resizeStart = null
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', stopResize)
  document.body.style.userSelect = ''
  setWidth(width.value)
}
const startResize = (event) => {
  resizeStart = { x: event.clientX, width: width.value }
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', stopResize)
}

// ---------------------------------------------------------------- state
const isCreate = computed(() => context.value.mode !== 'workflow')
const contextLabel = computed(() =>
  isCreate.value
    ? t('workflow_assistant.context_create')
    : t('workflow_assistant.context_workflow', { name: context.value.workflow })
)
const providersLoaded = ref(false)
const hasProvider = computed(() => providers.value.some((p) => p.available))
const draft = ref('')
const canSend = computed(() => !!draft.value.trim() && !!vendor.value && thread.value.status === 'idle')

const vendorLabel = (code) =>
  providers.value.find((p) => p.vendor === code)?.label || VENDOR_FALLBACK_LABELS[code] || code
const otherProviders = (code) => providers.value.filter((p) => p.available && p.vendor !== code)

// Only the newest notice is an alert; older ones would otherwise be announced again on re-render.
const alertRole = (index) => (index === thread.value.messages.length - 1 ? 'alert' : undefined)

// Short status line for screen readers (the message list itself is not a live region).
const announcement = ref('')
watch(
  () => thread.value.status,
  (status) => {
    if (status === 'sending') announcement.value = t('workflow_assistant.thinking')
  }
)
watch(
  () => [thread.value, thread.value.messages.at(-1)],
  ([current, last], [before, previous]) => {
    // Switching to another thread is not a new reply.
    if (current !== before || !last || last === previous || last.role !== 'assistant') return
    announcement.value = last.proposal
      ? t('workflow_assistant.announce_proposal')
      : t('workflow_assistant.announce_reply')
  }
)

const errorTitle = (m) => {
  const key = `workflow_assistant.errors.${m.code}`
  return m.code && te(key) ? t(key) : m.message || t('workflow_assistant.errors.request_failed')
}

// AI replies are markdown; html: false escapes any raw HTML in them.
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, i, options, env, self) => self.renderToken(tokens, i, options))
// No remote images in replies (they would load from any URL the model writes): show the alt text.
md.renderer.rules.image = (tokens, i) => md.utils.escapeHtml(tokens[i].content || '')
md.renderer.rules.link_open = (tokens, i, options, env, self) => {
  tokens[i].attrSet('target', '_blank')
  tokens[i].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, i, options, env, self)
}
const renderCache = new Map()
const render = (text) => {
  let html = renderCache.get(text)
  if (html === undefined) {
    html = md.render(text)
    if (renderCache.size > 200) renderCache.clear()
    renderCache.set(text, html)
  }
  return html
}

// ---------------------------------------------------------------- composer
const inputRef = ref(null)
const scrollRef = ref(null)

const autosize = () => {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

const focusInput = () => nextTick(() => inputRef.value?.focus())

// canSend mirrors send()'s own guards (text, vendor, idle), so the text is never lost.
const submit = () => {
  if (!canSend.value) return
  const text = draft.value
  draft.value = ''
  nextTick(autosize)
  send(text)
}

const onEnter = (event) => {
  // Shift+Enter adds a line; Enter while an IME (e.g. Vietnamese Telex) is composing is not a send.
  if (event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  submit()
}

const useStarter = (text) => {
  draft.value = text
  focusInput()
  nextTick(autosize)
}

const switchAndRetry = (code, retryText) => {
  vendor.value = code
  send(retryText)
}

// The Stop button disappears with the waiting row: keep the keyboard focus in the panel.
const stopWaiting = () => {
  stop()
  focusInput()
}

const startNewConversation = () => {
  newConversation()
  draft.value = ''
  focusInput()
}

const close = () => {
  if (thread.value.status === 'sending') stop()
  emit('close')
}

// ---------------------------------------------------------------- waiting timer, scrolling
const elapsed = ref(0)
let tick = null
watch(
  () => thread.value.status,
  (status) => {
    clearInterval(tick)
    tick = null
    if (status === 'sending') {
      elapsed.value = 0
      tick = setInterval(() => (elapsed.value += 1), 1000)
    }
  },
  { immediate: true }
)

const scrollToEnd = () =>
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
watch(() => [thread.value, thread.value.messages.length, thread.value.status], scrollToEnd)

onMounted(async () => {
  focusInput()
  scrollToEnd()
  await refreshProviders()
  providersLoaded.value = true
})

onBeforeUnmount(() => {
  clearInterval(tick)
  stopResize()
})
</script>

<style scoped>
.assistant-panel {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  border-left: 1px solid rgb(var(--ink) / 0.1);
  background: var(--bg-deep);
  color: var(--text-1);
  font-family: 'Inter', sans-serif;
  z-index: 6;
}

.resize-handle {
  position: absolute;
  left: -3px;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 2;
}

.resize-handle:hover,
.resize-handle:focus-visible {
  background: rgb(var(--accent-sky-rgb) / 0.35);
  outline: none;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 40px;
  padding: 0 8px 0 14px;
  border-bottom: 1px solid rgb(var(--ink) / 0.1);
  flex-shrink: 0;
}

.panel-heading {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.panel-context {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-muted-1);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--ink) / 0.65);
  cursor: pointer;
}

.icon-btn,
.send-btn {
  box-sizing: border-box;
  padding: 0;
}

.icon-btn svg,
.send-btn svg {
  flex-shrink: 0;
  width: 17px;
  height: 17px;
}

.icon-btn:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-1);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.icon-btn:focus-visible,
.chip:focus-visible,
.btn-small:focus-visible,
.send-btn:focus-visible,
.vendor-select:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 14px 8px;
}

.empty {
  padding: 18px 4px 8px;
  text-align: center;
}

.empty-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
}

.empty-hint {
  margin: 0 auto;
  max-width: 36ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted-1);
}

.starters {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-top: 16px;
}

.chip {
  max-width: 100%;
  padding: 7px 12px;
  border-radius: 12px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(var(--ink) / 0.04);
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.chip:hover {
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.24);
}

.messages {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.msg.user {
  display: flex;
  justify-content: flex-end;
}

.bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 14px 14px 4px 14px;
  background: rgb(var(--ink) / 0.08);
  font-size: 13.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.reply {
  font-size: 13.5px;
  line-height: 1.6;
  word-break: break-word;
}

.quick-replies {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.quick-replies .chip {
  border-radius: 999px;
  border-color: rgb(var(--accent-sky-rgb) / 0.4);
}

.notice {
  padding: 9px 11px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
  border: 1px solid rgb(var(--ink) / 0.1);
}

.notice.warn {
  background: color-mix(in srgb, var(--warn-soft-1) 10%, transparent);
  border-color: color-mix(in srgb, var(--warn-soft-1) 40%, transparent);
}

.notice.error {
  background: color-mix(in srgb, var(--danger) 9%, transparent);
  border-color: color-mix(in srgb, var(--danger) 35%, transparent);
}

.notice-title {
  font-weight: 600;
}

.reply + .notice,
.reply + .proposal-card {
  margin-top: 10px;
}

.notice-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
}

.notice-list code,
.notice-detail code {
  word-break: break-word;
  white-space: pre-wrap;
}

.notice-detail {
  margin-top: 4px;
  font-size: 12px;
}

.notice-detail summary {
  cursor: pointer;
  color: var(--text-muted-1);
}

.notice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.btn-small {
  padding: 5px 11px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.16);
  background: rgb(var(--ink) / 0.05);
  color: var(--text-1);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.btn-small:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.1);
}

.btn-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.waiting {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--text-muted-1);
}

.waiting-text {
  flex: 1;
}

.elapsed {
  font-variant-numeric: tabular-nums;
  opacity: 0.8;
}

.dots {
  display: inline-flex;
  gap: 3px;
}

.dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-sky);
  animation: blink 1.2s infinite ease-in-out;
}

.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}

.composer {
  flex-shrink: 0;
  margin: 8px 12px 12px;
  border-radius: 12px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(var(--ink) / 0.04);
}

.composer:focus-within {
  border-color: rgb(var(--accent-sky-rgb) / 0.6);
}

.composer-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  max-height: 200px;
  padding: 10px 12px 4px;
  border: 0;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 13.5px;
  line-height: 1.5;
  resize: none;
  outline: none;
}

.composer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 6px 8px;
}

.vendor-select {
  padding: 4px 6px;
  border-radius: 7px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: var(--bg-deep);
  color: var(--text-1);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.no-provider {
  font-size: 12px;
  color: var(--warn-soft-1);
}

.no-provider a {
  color: var(--accent-sky);
}

.composer-hint {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
  font-size: 11px;
  color: var(--text-muted-1);
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: var(--accent-sky);
  color: #05141f;
  cursor: pointer;
}

:root[data-theme="light"] .send-btn {
  color: #fff;
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Narrow screens: the panel covers the whole workbench */
@media (max-width: 899px) {
  .assistant-panel {
    position: absolute;
    inset: 0;
    width: 100% !important;
    border-left: 0;
    z-index: 20;
  }

  .resize-handle {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .dots i {
    animation: none;
    opacity: 0.7;
  }

  .chip {
    transition: none;
  }
}
</style>
