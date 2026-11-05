<template>
  <aside
    class="assistant-panel"
    :style="{ width: `${width}px` }"
    role="complementary"
    :aria-label="$t('workflow_assistant.title')"
    @keydown.esc="onEscape"
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
        ref="historyBtnRef"
        type="button"
        class="icon-btn"
        :class="{ on: historyOpen }"
        :title="$t('workflow_assistant.history')"
        :aria-label="$t('workflow_assistant.history')"
        :aria-expanded="historyOpen"
        aria-controls="assistant-history"
        @click="toggleHistory"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l3 2" /></svg>
      </button>
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

    <!-- Saved conversations of this workflow (or of "new workflow") -->
    <div v-if="historyOpen" id="assistant-history" class="history" role="region" :aria-label="$t('workflow_assistant.history')">
      <div class="history-head">
        <span class="history-title">{{ $t('workflow_assistant.history_for', { name: contextLabel }) }}</span>
        <button type="button" class="btn-small" @click="startNewConversation">{{ $t('workflow_assistant.new_conversation') }}</button>
      </div>
      <p v-if="sessionsLoading && !currentSessions.length" class="history-empty">{{ $t('workflow_assistant.history_loading') }}</p>
      <p v-else-if="!currentSessions.length" class="history-empty">{{ $t('workflow_assistant.history_empty') }}</p>
      <ul v-else class="history-list">
        <li v-for="s in currentSessions" :key="s.id" :class="['history-item', { current: s.id === thread.id }]">
          <button type="button" class="history-open" :aria-current="s.id === thread.id ? 'true' : undefined" @click="pickSession(s.id)">
            <span class="history-name">{{ s.title || $t('workflow_assistant.untitled') }}</span>
            <span class="history-sub">
              {{ relativeTime(s.updated_at) }} · {{ $t('workflow_assistant.message_count', { n: s.message_count || 0 }) }}
              <span v-if="threadBusy(s.id)" class="history-busy">· {{ $t('workflow_assistant.thinking') }}</span>
            </span>
          </button>
          <button
            type="button"
            class="icon-btn history-delete"
            :class="{ confirm: confirmDelete === s.id }"
            :title="confirmDelete === s.id ? $t('workflow_assistant.delete_confirm') : $t('workflow_assistant.delete_session')"
            :aria-label="confirmDelete === s.id ? $t('workflow_assistant.delete_confirm') : $t('workflow_assistant.delete_session')"
            @click="removeSession(s.id)"
          >
            <svg v-if="confirmDelete !== s.id" aria-hidden="true" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></svg>
            <span v-else class="confirm-text">{{ $t('workflow_assistant.delete_confirm_short') }}</span>
          </button>
        </li>
      </ul>
    </div>

    <div ref="scrollRef" class="panel-body">
      <!-- Empty thread -->
      <div v-if="!thread.messages.length && thread.status === 'idle'" class="empty">
        <p class="empty-title">
          {{ isCreate ? $t('workflow_assistant.empty_create_title') : $t('workflow_assistant.empty_workflow_title', { name: context.workflow }) }}
        </p>
        <p class="empty-hint">
          {{ isCreate ? $t('workflow_assistant.empty_create_hint') : $t('workflow_assistant.empty_workflow_hint') }}
        </p>
        <div class="starters" role="group" :aria-label="$t('workflow_assistant.starters_label')">
          <button
            v-for="key in starterKeys"
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
          <div v-if="m.role === 'user'" class="bubble"><span class="sr-only">{{ `${$t('workflow_assistant.sender_you')} ` }}</span>{{ m.content }}</div>

          <!-- Assistant -->
          <template v-else-if="m.role === 'assistant'">
            <span class="sr-only">{{ $t('workflow_assistant.sender_assistant') }}</span>
            <!-- eslint-disable-next-line vue/no-v-html -- markdown-it with html: false escapes raw HTML -->
            <div v-if="m.content" class="reply markdown-body" v-html="render(m.content)"></div>
            <p v-else-if="!m.proposal && !m.validationErrors?.length" class="reply reply-empty">
              {{ $t('workflow_assistant.empty_reply') }}
            </p>
            <div v-if="m.validationErrors?.length" class="notice error" :role="alertRole(index)">
              <div class="notice-title">{{ $t('workflow_assistant.validation_failed') }}</div>
              <ul class="notice-list">
                <li v-for="(err, i) in m.validationErrors" :key="i"><code>{{ err }}</code></li>
              </ul>
            </div>
            <ProposalCard
              v-if="m.proposal"
              :proposal="m.proposal"
              :number="m.proposalNumber || 0"
              :superseded="!!m.superseded"
              :conflicted="!!m.conflicted"
              :applied="!!m.applied"
              :can-undo="!!m.applied && m.id === undoMessageId"
              :active="m.proposal === thread.pendingProposal"
              :earlier-turn="m.proposal === thread.pendingProposal && answeredSince(index)"
              :busy="thread.status !== 'idle'"
              :applying="thread.status === 'applying'"
              @apply="emit('apply')"
              @discard="discardProposal"
              @undo="emit('undo', workflowKey(m.proposal.filename))"
            />
            <div v-if="metaLine(m)" class="reply-meta" :title="metaTitle(m)">
              <span>{{ metaLine(m) }}</span>
              <button v-if="m.content" type="button" class="meta-btn" :title="$t('workflow_assistant.copy')" @click="copyReply(m)">
                {{ copiedId === m.id ? $t('workflow_assistant.copied') : $t('workflow_assistant.copy') }}
              </button>
            </div>
            <div
              v-if="showQuickReplies(m, index)"
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
            <!-- Only the newest notice: an older one would resend the redo out of context. -->
            <div v-if="index === thread.messages.length - 1" class="notice-actions">
              <button type="button" class="btn-small" :disabled="thread.status !== 'idle'" @click="send($t('workflow_assistant.redo_prompt'))">
                {{ $t('workflow_assistant.redo') }}
              </button>
            </div>
          </div>
          <!-- Stopped by the user: neutral, not an error (and not an alert for screen readers). -->
          <div v-else-if="m.kind === 'stopped'" class="notice stopped">
            <span class="notice-title">{{ $t('workflow_assistant.stopped') }}</span>
            <button
              v-if="index === thread.messages.length - 1 && m.retryText"
              type="button"
              class="btn-small"
              :disabled="!canRetry"
              @click="retryStopped(m)"
            >{{ $t('workflow_assistant.retry') }}</button>
          </div>
          <div v-else class="notice error" :role="alertRole(index)">
            <div class="notice-title">{{ errorTitle(m) }}</div>
            <!-- Newest notice only: retry the same message, or move to a model that can answer it. -->
            <div v-if="index === thread.messages.length - 1 && errorActions(m, index)" class="notice-actions">
              <button
                v-if="errorActions(m, index).retry"
                type="button"
                class="btn-small"
                :disabled="!canRetry"
                @click="retryError(index)"
              >{{ $t('workflow_assistant.retry') }}</button>
              <template v-if="errorActions(m, index).switchVendor">
                <button
                  v-for="p in otherProviders(vendor)"
                  :key="p.vendor"
                  type="button"
                  class="btn-small"
                  :disabled="thread.status !== 'idle'"
                  @click="switchAndRetryError(p.vendor, index)"
                >{{ $t('workflow_assistant.switch_to', { vendor: p.label }) }}</button>
              </template>
              <RouterLink v-if="errorActions(m, index).connections" to="/connections" class="btn-small">
                {{ $t('workflow_assistant.open_connections') }}
              </RouterLink>
            </div>
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
          <label class="sr-only" for="assistant-model">{{ $t('workflow_assistant.model_name_label') }}</label>
          <select
            id="assistant-model"
            v-model="model"
            class="vendor-select model-select"
            :title="$t('workflow_assistant.model_hint')"
            :disabled="thread.status === 'sending' || !vendor"
          >
            <option value="">{{ defaultModelLabel }}</option>
            <option v-for="opt in modelOptions" :key="opt.id" :value="opt.id">{{ opt.name && opt.name !== opt.id ? `${opt.name} (${opt.id})` : opt.id }}</option>
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
import { workflowKey } from '@/utils/workflowSync.js'

const emit = defineEmits(['close', 'apply', 'undo'])
const { t, te } = useI18n()

const {
  context,
  providers,
  vendor,
  currentThread: thread,
  currentSessions,
  sessionsLoading,
  loadSessions,
  openSession,
  deleteSession,
  model,
  models,
  threads,
  undoMessageId,
  refreshProviders,
  send,
  stop,
  newConversation,
  discardProposal,
  draftSeed
} = useWorkflowAssistant()

const CREATE_STARTER_KEYS = [
  'workflow_assistant.starter_team',
  'workflow_assistant.starter_pipeline',
  'workflow_assistant.starter_review'
]
const WORKFLOW_STARTER_KEYS = [
  'workflow_assistant.starter_explain',
  'workflow_assistant.starter_add_step',
  'workflow_assistant.starter_remove_step'
]
const VENDOR_FALLBACK_LABELS = { anthropic: 'Claude', openai: 'Codex', gemini: 'Gemini' }

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
const starterKeys = computed(() => (isCreate.value ? CREATE_STARTER_KEYS : WORKFLOW_STARTER_KEYS))
const contextLabel = computed(() =>
  isCreate.value
    ? t('workflow_assistant.context_create')
    : t('workflow_assistant.context_workflow', { name: context.value.workflow })
)
const providersLoaded = ref(false)
const hasProvider = computed(() => providers.value.some((p) => p.available))
const draft = ref('')
const canSend = computed(() => !!draft.value.trim() && !!vendor.value && thread.value.status === 'idle')

// ---------------------------------------------------------------- models
const currentProvider = computed(() => providers.value.find((p) => p.vendor === vendor.value))
const defaultModelLabel = computed(() => {
  const name = currentProvider.value?.model
  return name ? t('workflow_assistant.model_default_named', { model: name }) : t('workflow_assistant.model_default')
})
// The remembered model stays listed even before the account's list has loaded.
const modelOptions = computed(() => {
  const list = models.value.slice()
  if (model.value && !list.some((m) => m.id === model.value)) list.unshift({ id: model.value, name: model.value })
  return list
})

// "Claude · claude-sonnet-4-5 · 12.3k tokens · 8s" under a reply: what answered and what it cost.
const formatTokens = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n))
const metaLine = (m) => {
  const parts = []
  if (m.vendor) parts.push(vendorLabel(m.vendor))
  if (m.model) parts.push(m.model)
  const u = m.usage || {}
  const tokens = (u.input_tokens || 0) + (u.output_tokens || 0)
  if (tokens) parts.push(t('workflow_assistant.meta_tokens', { n: formatTokens(tokens) }))
  if (u.duration_ms) parts.push(`${Math.max(1, Math.round(u.duration_ms / 1000))}s`)
  return parts.join(' · ')
}
const metaTitle = (m) => {
  const u = m.usage || {}
  if (u.input_tokens == null && u.output_tokens == null) return undefined
  return t('workflow_assistant.meta_detail', {
    input: u.input_tokens ?? '?',
    output: u.output_tokens ?? '?',
    cached: u.cache_read_tokens ?? 0,
    calls: u.calls ?? 1
  })
}
const copiedId = ref(null)
let copiedTimer = null
const copyReply = async (m) => {
  try {
    await navigator.clipboard.writeText(m.content)
    copiedId.value = m.id
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copiedId.value = null), 1500)
  } catch {
    // clipboard blocked (http on a LAN address): nothing to do
  }
}

// ---------------------------------------------------------------- history
const historyOpen = ref(false)
const historyBtnRef = ref(null)
const confirmDelete = ref(null)
const toggleHistory = () => {
  historyOpen.value = !historyOpen.value
  confirmDelete.value = null
  if (historyOpen.value) loadSessions()
}
const threadBusy = (id) => threads.get(id)?.status === 'sending'
const pickSession = async (id) => {
  const result = await openSession(id)
  if (result.ok) {
    historyOpen.value = false
    draft.value = ''
    focusInput()
  }
}
const removeSession = async (id) => {
  if (confirmDelete.value !== id) {
    confirmDelete.value = id
    return
  }
  confirmDelete.value = null
  await deleteSession(id)
}
const relativeTime = (seconds) => {
  if (!seconds) return ''
  const diff = Math.max(0, Date.now() / 1000 - seconds)
  if (diff < 60) return t('workflow_assistant.time_now')
  if (diff < 3600) return t('workflow_assistant.time_minutes', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('workflow_assistant.time_hours', { n: Math.floor(diff / 3600) })
  if (diff < 86400 * 7) return t('workflow_assistant.time_days', { n: Math.floor(diff / 86400) })
  return new Date(seconds * 1000).toLocaleDateString()
}

const vendorLabel = (code) =>
  providers.value.find((p) => p.vendor === code)?.label || VENDOR_FALLBACK_LABELS[code] || code
const otherProviders = (code) => providers.value.filter((p) => p.available && p.vendor !== code)

// Only the newest notice is an alert; older ones would otherwise be announced again on re-render.
const alertRole = (index) => (index === thread.value.messages.length - 1 ? 'alert' : undefined)

// Quick replies belong to the newest assistant turn only, and only while they still fit: not while
// a request runs, not next to a proposal card (Apply / Discard are the answers there), and not
// after a proposal was applied (a chip like "Applied, thanks" would only send a chat message).
const showQuickReplies = (m, index) =>
  !!m.quickReplies?.length &&
  !m.proposal &&
  index === thread.value.messages.length - 1 &&
  thread.value.status === 'idle' &&
  !thread.value.appliedSinceUserMessage

// The assistant has replied again after this message (a turn without a new card can still have
// changed what was agreed, so the pending card may not include it).
const answeredSince = (index) => thread.value.messages.slice(index + 1).some((m) => m.role === 'assistant')

const canRetry = computed(() => !!vendor.value && thread.value.status === 'idle')

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
    if (current !== before || !last || last === previous) return
    // Stop is the user's own action: a plain status, never an error.
    if (last.kind === 'stopped') {
      announcement.value = t('workflow_assistant.stopped')
      return
    }
    if (last.role !== 'assistant') return
    const status = last.proposal ? t('workflow_assistant.announce_proposal') : t('workflow_assistant.announce_reply')
    const emptyReply = !last.content && !last.proposal && !last.validationErrors?.length
    const text = emptyReply ? t('workflow_assistant.empty_reply') : replySnippet(last.content)
    announcement.value = text ? `${status} ${text}` : status
  }
)

// The start of a reply as plain text, for the live region (markdown rendered, then tags dropped;
// DOMParser documents load nothing).
const ANNOUNCE_LIMIT = 200
function replySnippet(content) {
  if (!content) return ''
  let text = ''
  try {
    text = new DOMParser().parseFromString(render(content), 'text/html').body.textContent || ''
  } catch {
    text = String(content)
  }
  text = text.replace(/\s+/g, ' ').trim()
  return text.length > ANNOUNCE_LIMIT ? `${text.slice(0, ANNOUNCE_LIMIT - 1).trimEnd()}…` : text
}

const errorTitle = (m) => {
  const key = `workflow_assistant.errors.${m.code}`
  return m.code && te(key) ? t(key) : m.message || t('workflow_assistant.errors.request_failed')
}

// What an error notice offers, by code. A retry resends the user message the error answered; it is
// offered only when that message is right above the notice (so the resend replaces it, not duplicates it).
const RETRY_CODES = new Set(['timeout', 'busy', 'provider_error', 'internal', 'network'])
const SWITCH_CODES = new Set(['model_unavailable', 'not_signed_in', 'timeout', 'provider_error'])
const CONNECTIONS_CODES = new Set(['model_unavailable', 'not_signed_in'])
const failedUserText = (index) => {
  const previous = thread.value.messages[index - 1]
  return previous?.role === 'user' ? previous.content : ''
}
const errorActions = (m, index) => {
  const code = m.code || 'network'
  const hasText = !!failedUserText(index)
  const actions = {
    retry: hasText && RETRY_CODES.has(code),
    switchVendor: hasText && SWITCH_CODES.has(code) && otherProviders(vendor.value).length > 0,
    connections: CONNECTIONS_CODES.has(code)
  }
  return actions.retry || actions.switchVendor || actions.connections ? actions : null
}
// Drops the notice and the failed user message; send() adds the message again.
const resendFailed = (index) => {
  const text = failedUserText(index)
  if (!text || thread.value.status !== 'idle') return
  thread.value.messages.splice(index - 1, 2)
  send(text)
  focusInput()
}
const retryError = (index) => resendFailed(index)
const switchAndRetryError = (code, index) => {
  vendor.value = code
  resendFailed(index)
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

// Text from another page (Lab "fix this"): placed in the composer to edit, never sent automatically.
watch(
  draftSeed,
  (text) => {
    if (!text) return
    draft.value = text
    draftSeed.value = ''
    focusInput()
    nextTick(autosize)
  },
  { immediate: true }
)

const useStarter = (text) => {
  draft.value = text
  focusInput()
  nextTick(autosize)
}

const switchAndRetry = (code, retryText) => {
  vendor.value = code
  send(retryText)
}

// Resends the stopped message with the model it was sent to, when that one is still signed in.
const retryStopped = (m) => {
  if (providers.value.some((p) => p.available && p.vendor === m.vendor)) vendor.value = m.vendor
  send(m.retryText)
  focusInput()
}

// The Stop button disappears with the waiting row: keep the keyboard focus in the panel.
const stopWaiting = () => {
  stop()
  focusInput()
}

const startNewConversation = () => {
  newConversation()
  historyOpen.value = false
  draft.value = ''
  focusInput()
}

const close = () => {
  if (thread.value.status === 'sending') stop()
  emit('close')
}

// Esc closes the panel, but not while an IME (e.g. Vietnamese Telex) is composing: there Esc only
// dismisses the candidate list.
const onEscape = (event) => {
  if (event.isComposing || event.keyCode === 229) return
  event.stopPropagation()
  // Esc first closes the history list, then the panel.
  if (historyOpen.value) {
    historyOpen.value = false
    nextTick(() => historyBtnRef.value?.focus())
    return
  }
  close()
}

// ---------------------------------------------------------------- waiting timer, scrolling
const elapsed = ref(0)
let tick = null
// Counted from when the request left, so switching sessions and back keeps the true time.
const updateElapsed = () => {
  const since = thread.value.sendingSince
  elapsed.value = since ? Math.max(0, Math.floor((Date.now() - since) / 1000)) : 0
}
watch(
  () => [thread.value, thread.value.status],
  () => {
    clearInterval(tick)
    tick = null
    if (thread.value.status === 'sending') {
      updateElapsed()
      tick = setInterval(updateElapsed, 1000)
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
  clearTimeout(copiedTimer)
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
  font-family: inherit;
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

.icon-btn.on {
  background: rgb(var(--accent-sky-rgb) / 0.16);
  color: var(--text-1);
}

.history {
  flex-shrink: 0;
  max-height: 55%;
  overflow-y: auto;
  padding: 10px 10px 8px;
  border-bottom: 1px solid rgb(var(--ink) / 0.1);
  background: rgb(var(--ink) / 0.025);
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 4px 8px;
}

.history-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted-1);
}

.history-empty {
  margin: 4px;
  font-size: 12.5px;
  color: var(--text-muted-1);
}

.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 8px;
}

.history-item:hover,
.history-item.current {
  background: rgb(var(--ink) / 0.06);
}

.history-item.current {
  box-shadow: inset 2px 0 0 var(--accent-sky);
}

.history-open {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 8px;
  border: 0;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.history-open:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: -2px;
  border-radius: 8px;
}

.history-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.history-sub {
  font-size: 11.5px;
  color: var(--text-muted-1);
}

.history-busy {
  color: var(--accent-sky);
}

.history-delete {
  flex-shrink: 0;
  opacity: 0;
}

.history-item:hover .history-delete,
.history-delete:focus-visible,
.history-delete.confirm {
  opacity: 1;
}

.history-delete.confirm {
  width: auto;
  padding: 0 8px;
  color: var(--danger);
}

.confirm-text {
  font-size: 11.5px;
  font-weight: 600;
}

.reply-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted-1);
}

.meta-btn {
  padding: 1px 6px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted-1);
  font: inherit;
  cursor: pointer;
  opacity: 0;
}

.msg:hover .meta-btn,
.meta-btn:focus-visible {
  opacity: 1;
}

.meta-btn:hover {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-1);
}

.model-select {
  min-width: 0;
  max-width: 150px;
  text-overflow: ellipsis;
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

.notice.stopped {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 8px 6px 11px;
  background: rgb(var(--ink) / 0.03);
  color: var(--text-muted-1);
}

.notice.stopped .notice-title {
  font-weight: 500;
}

.reply-empty {
  margin: 0;
  color: var(--text-muted-1);
  font-style: italic;
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
  text-decoration: none;
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
  color: var(--on-accent);
  cursor: pointer;
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
