<template>
  <div class="collapsible-message">
    <div v-if="rawContent" class="copy-button-wrapper" :class="{ 'is-copied': copyStatus === 'copied' }">
      <button 
        class="copy-btn" 
        @click="copyToClipboard" 
        :title="copyStatus === 'copied' ? $t('components.collapsible_message.copied') : $t('components.collapsible_message.copy_original')"
        :aria-label="copyStatus === 'copied' ? $t('components.collapsible_message.copied') : $t('components.collapsible_message.copy_original')"
      >
        <svg v-if="copyStatus === 'idle'" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <span v-if="copyStatus === 'copied'" class="copy-label">{{ $t('components.collapsible_message.copied') }}</span>
      </button>
    </div>
    <div 
      ref="contentRef"
      class="content-wrapper"
      :class="{ 'is-collapsed': isCollapsed && shouldShowToggle }"
      :style="contentStyle"
    >
      <div 
        class="message-text markdown-body" 
        v-html="htmlContent"
      ></div>
    </div>
    
    <div 
      v-if="shouldShowToggle" 
      class="toggle-wrapper"
      :class="{ 'is-collapsed': isCollapsed }"
    >
      <button 
        class="toggle-btn" 
        @click="toggle"
      >
        {{ isCollapsed ? $t('components.collapsible_message.show_more') : $t('components.collapsible_message.show_less') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { toast } from '@/utils/toast.js'

const { t } = useI18n()

const props = defineProps({
  htmlContent: {
    type: String,
    required: true
  },
  rawContent: {
    type: String,
    default: ''
  },
  maxHeight: {
    type: Number,
    default: 200
  },
  defaultExpanded: {
    type: Boolean,
    default: false
  }
})

const contentRef = ref(null)
const isCollapsed = ref(!props.defaultExpanded)
const contentHeight = ref(0)
const copyStatus = ref('idle') // idle, copied

const shouldShowToggle = computed(() => {
  return contentHeight.value > props.maxHeight
})

const contentStyle = computed(() => {
  if (isCollapsed.value && shouldShowToggle.value) {
    return { maxHeight: `${props.maxHeight}px` }
  }
  return {}
})

// Coalesce height checks into one layout read per frame (images loading, content updates)
let heightRafId = null
const checkHeight = async () => {
  await nextTick()
  if (heightRafId !== null) return
  heightRafId = requestAnimationFrame(() => {
    heightRafId = null
    if (contentRef.value) {
      contentHeight.value = contentRef.value.scrollHeight
    }
  })
}

const toggle = () => {
  isCollapsed.value = !isCollapsed.value
}

let copyResetTimeout = null
const copyToClipboard = async () => {
  if (!props.rawContent) return

  try {
    await navigator.clipboard.writeText(props.rawContent)
    copyStatus.value = 'copied'
    if (copyResetTimeout) clearTimeout(copyResetTimeout)
    copyResetTimeout = setTimeout(() => {
      copyStatus.value = 'idle'
      copyResetTimeout = null
    }, 2000)
  } catch (err) {
    console.error('Failed to copy text: ', err)
    toast.error(t('components.collapsible_message.copy_failed'))
  }
}

// Measure via ResizeObserver: it reports the initial size and every later change
// (content updates, images or code blocks finishing loading). The size comes from
// the observer entry, so no layout is read: when many messages mount at once
// (e.g. replay after reconnect) this avoids a forced layout per message.
let resizeObserver = null

onMounted(() => {
  const target = contentRef.value?.firstElementChild
  if (typeof ResizeObserver === 'undefined' || !target) {
    checkHeight()
    return
  }
  resizeObserver = new ResizeObserver(([entry]) => {
    const height = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height
    if (height !== contentHeight.value) contentHeight.value = height
  })
  resizeObserver.observe(target)
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (heightRafId !== null) {
    cancelAnimationFrame(heightRafId)
    heightRafId = null
  }
  if (copyResetTimeout) {
    clearTimeout(copyResetTimeout)
    copyResetTimeout = null
  }
})

// Without ResizeObserver, re-measure when the content changes.
watch(() => props.htmlContent, () => {
  if (!resizeObserver) checkHeight()
})
</script>

<style scoped>
.collapsible-message {
  position: relative;
  width: 100%;
  padding: 10px 0;
}

.copy-button-wrapper {
  position: absolute;
  top: 8px;
  right: 0;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.collapsible-message:hover .copy-button-wrapper,
.copy-button-wrapper.is-copied {
  opacity: 1;
}

.copy-label {
  margin-left: 4px;
  font-size: 12px;
  line-height: 16px;
}

.copy-btn {
  background: rgb(var(--panel-40b) / 0.8);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 4px;
  padding: 4px;
  cursor: pointer;
  color: var(--text-muted-7);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s, color 0.2s;
}

.copy-btn:hover {
  background: rgb(var(--panel-60b) / 0.9);
  color: var(--text-strong);
}


.content-wrapper {
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.content-wrapper.is-collapsed {
  mask-image: linear-gradient(to bottom, black calc(100% - 60px), transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black calc(100% - 60px), transparent 100%);
}

.message-text {
  word-wrap: break-word;
}

.toggle-wrapper {
  display: flex;
  justify-content: center;
  padding-top: 8px;
  position: relative;
}

.toggle-btn {
  background: none;
  border: none;
  color: var(--accent-blue-1); /* Adjust color to match theme */
  cursor: pointer;
  font-size: 0.9em;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
  z-index: 1; /* Ensure button is clickcable above gradient */
}

.toggle-btn:hover {
  background-color: color-mix(in srgb, var(--accent-blue-1) 10%, transparent);
  text-decoration: underline;
}

/* Markdown Styles */
.markdown-body {
  color: var(--fg);
  font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif,Apple Color Emoji,Segoe UI Emoji;
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
}

.markdown-body :deep(blockquote), 
.markdown-body :deep(dl), 
.markdown-body :deep(li), 
.markdown-body :deep(ol), 
.markdown-body :deep(p), 
.markdown-body :deep(pre), 
.markdown-body :deep(table), 
.markdown-body :deep(ul) {
    margin-bottom: 0px; 
    margin-top: 0;
}

.markdown-body :deep(p) {
    margin-bottom: 8px;
}

.markdown-body :deep(p:last-child) {
    margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
    margin-top: 16px;
    margin-bottom: 8px;
    font-weight: 600;
    line-height: 1.25;
}

.markdown-body :deep(pre) {
    background-color: rgb(var(--shade) / 0.3);
    border-radius: 6px;
    padding: 12px;
    overflow: auto;
    margin-bottom: 8px;
}

.markdown-body :deep(code) {
    padding: 0.2em 0.4em;
    margin: 0;
    font-size: 85%;
    background-color: rgb(var(--ink) / 0.1);
    border-radius: 4px;
    font-family: ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace;
}

.markdown-body :deep(pre code) {
    padding: 0;
    margin: 0;
    font-size: 100%;
    word-break: normal;
    white-space: pre;
    background: transparent;
    border: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
    padding-left: 2em;
    margin-bottom: 8px;
}

.markdown-body :deep(a) {
    color: var(--accent-blue-1);
    text-decoration: none;
}

.markdown-body :deep(a:hover) {
    text-decoration: underline;
}

.markdown-body :deep(img) {
    max-width: 100%;
    box-sizing: border-box;
    background-color: transparent;
}

/* Light theme: crisper edges for the copy button and code blocks */
:root[data-theme="light"] .copy-btn {
  background: var(--surface);
  border-color: var(--line-4);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.15);
}
:root[data-theme="light"] .copy-btn:hover {
  background: var(--surface-4);
}
:root[data-theme="light"] .toggle-btn:hover {
  background-color: rgb(37 99 235 / 0.08);
}
:root[data-theme="light"] .markdown-body :deep(pre) {
  background-color: var(--surface-4);
  border: 1px solid var(--line-3);
}
:root[data-theme="light"] .markdown-body :deep(code) {
  background-color: rgb(var(--ink) / 0.07);
}
:root[data-theme="light"] .markdown-body :deep(pre code) {
  background: transparent;
}

@media (prefers-reduced-motion: reduce) {
  .copy-button-wrapper,
  .copy-btn,
  .content-wrapper,
  .toggle-btn {
    transition-duration: 0.01ms;
  }
}
</style>
