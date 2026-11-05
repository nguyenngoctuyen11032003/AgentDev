<template>
  <section class="outputs" :aria-labelledby="titleId">
    <header class="out-head">
      <span class="out-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path v-for="(p, pi) in KIND_ICONS.folder" :key="pi" :d="p" /></svg>
      </span>
      <div class="out-text">
        <h4 :id="titleId" class="out-title">
          {{ tr('lab.outputs.title', 'Sản phẩm') }}
          <span v-if="hasFiles" class="out-count">{{ tr('lab.outputs.summary', '{n} file · {size}', { n: data.file_count, size: bytes(data.total_bytes) }) }}</span>
        </h4>
        <p v-if="hasFiles && summaryLine" class="out-summary">{{ summaryLine }}</p>
      </div>
      <div v-if="data?.available" class="out-actions">
        <button
          v-if="data.project?.can_preview"
          type="button"
          class="btn primary sm"
          :title="tr('lab.outputs.preview_hint', 'Chạy sản phẩm ngay tại đây để xem và dùng thử')"
          :aria-expanded="previewOpen"
          @click="openPreview(true)"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
          {{ tr('lab.outputs.preview', 'Chạy thử') }}
        </button>
        <button type="button" class="btn secondary sm" :title="trc('open_folder_hint', 'lab.outputs.open_folder_hint', 'Mở thư mục sản phẩm trên máy này')" :disabled="opening" @click="openOnMachine('', false)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(p, pi) in KIND_ICONS.folderOpen" :key="pi" :d="p" /></svg>
          {{ tr('lab.outputs.open_folder', 'Mở thư mục') }}
        </button>
        <span v-if="canDelete" class="del-wrap" :title="jobRunning ? tr('lab.outputs.delete_running', 'Kiểm định đang chạy: xoá được khi chạy xong.') : undefined">
          <button
            type="button"
            class="btn ghost sm icon-only icon-danger"
            :aria-label="tr('lab.outputs.delete', 'Xoá kết quả')"
            :title="jobRunning ? undefined : tr('lab.outputs.delete', 'Xoá kết quả')"
            :disabled="jobRunning || deleting"
            @click="deleteOutputs"
          >
            <span v-if="deleting" class="btn-spinner" aria-hidden="true"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
          </button>
        </span>
      </div>
    </header>

    <!-- loading / error / empty states -->
    <div v-if="loading && !data" class="out-skel" aria-hidden="true"><span v-for="n in 4" :key="n"></span></div>
    <p v-if="loading && !data" class="sr-only" role="status">{{ tr('lab.outputs.loading', 'Đang tải danh sách file…') }}</p>
    <div v-else-if="loadError" class="out-state bad" role="alert">
      <strong>{{ tr('lab.outputs.load_error', 'Không tải được danh sách file') }}</strong>
      <span>{{ loadError }}</span>
      <button type="button" class="btn secondary sm" @click="load">{{ tr('lab.outputs.retry', 'Thử lại') }}</button>
    </div>
    <div v-else-if="data && !data.available" class="out-state">
      <strong>{{ trc('gone_title', 'lab.outputs.gone_title', 'Kết quả đã bị xoá') }}</strong>
      <span>{{ trc('gone_hint', 'lab.outputs.gone_hint', 'Thư mục sản phẩm của lượt này không còn trên máy. Điểm và nhận xét vẫn ở bên dưới.') }}</span>
    </div>
    <div v-else-if="data && !data.files?.length" class="out-state">
      <strong>{{ trc('empty_title', 'lab.outputs.empty_title', 'Lượt này không tạo file nào') }}</strong>
      <span>{{ trc('empty_hint', 'lab.outputs.empty_hint', 'Nhóm chỉ trả lời bằng văn bản: xem phần Kết quả bên dưới.') }}</span>
    </div>

    <template v-else-if="hasFiles">
      <LabRunPreview
        v-if="previewOpen"
        :key="previewKey"
        :source="src"
        :autostart="previewAutostart"
        @close="previewOpen = false"
      />

      <div class="browser">
        <!-- file tree -->
        <nav class="tree" :aria-label="trc('tree_label', 'lab.outputs.tree_label', 'Cây thư mục sản phẩm')">
          <ul ref="treeEl" class="tree-list" @keydown="onTreeKey">
            <li v-for="{ node, depth } in rows" :key="node.path">
              <button
                type="button"
                :class="['tree-row', node.type, { on: node.path === selected }]"
                :style="{ '--depth': depth }"
                :aria-expanded="node.type === 'dir' ? expanded.has(node.path) : undefined"
                :aria-current="node.path === selected ? 'true' : undefined"
                :data-path="node.path"
                :title="node.path"
                @click="node.type === 'dir' ? toggleDir(node.path) : select(node.path)"
              >
                <svg v-if="node.type === 'dir'" class="tree-chev" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
                <span v-else class="tree-chev" aria-hidden="true"></span>
                <svg :class="['tree-icon', node.type === 'dir' ? 'dir' : node.file.kind]" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path v-for="(p, pi) in iconFor(node)" :key="pi" :d="p" />
                </svg>
                <span class="tree-name">{{ node.name }}</span>
                <span class="tree-size">{{ bytes(node.size) }}</span>
              </button>
            </li>
          </ul>
          <p v-if="data.truncated" class="tree-note">{{ tr('lab.outputs.truncated', 'Chỉ hiện {n} file đầu tiên.', { n: data.files.length }) }}</p>
        </nav>

        <!-- viewer -->
        <div class="viewer">
          <template v-if="current">
            <div class="v-bar">
              <div class="v-file">
                <span class="v-name">{{ currentName }}</span>
                <span class="v-path">{{ currentDir }}<template v-if="currentDir"> · </template>{{ bytes(current.size) }}</span>
              </div>
              <div class="v-tools">
                <div v-if="current.kind === 'markdown' && textState === 'ready'" class="seg" role="group" :aria-label="tr('lab.outputs.view_mode', 'Cách xem')">
                  <button type="button" :class="{ on: !showSource }" :aria-pressed="!showSource" @click="showSource = false">{{ tr('lab.outputs.view_rendered', 'Trình bày') }}</button>
                  <button type="button" :class="{ on: showSource }" :aria-pressed="showSource" @click="showSource = true">{{ tr('lab.outputs.view_source', 'Mã nguồn') }}</button>
                </div>
                <button
                  v-if="showsCode"
                  type="button"
                  :class="['btn ghost sm icon-only', { active: wrap }]"
                  :aria-pressed="wrap"
                  :title="tr('lab.outputs.wrap', 'Xuống dòng')"
                  :aria-label="tr('lab.outputs.wrap', 'Xuống dòng')"
                  @click="toggleWrap"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h13a3 3 0 0 1 0 6h-4M4 18h5" /><path d="m15 16-2 2 2 2" /></svg>
                </button>
                <button
                  v-if="textState === 'ready'"
                  type="button"
                  class="btn ghost sm icon-only"
                  :title="copied ? tr('lab.outputs.copied', 'Đã chép') : tr('lab.outputs.copy', 'Chép nội dung')"
                  :aria-label="copied ? tr('lab.outputs.copied', 'Đã chép') : tr('lab.outputs.copy', 'Chép nội dung')"
                  @click="copyText"
                >
                  <svg v-if="copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
                  <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a1 1 0 0 1 1-1h10" /></svg>
                </button>
                <a class="btn ghost sm icon-only" :href="newTabUrl" target="_blank" rel="noopener noreferrer" :title="tr('lab.outputs.new_tab', 'Mở trong tab mới')" :aria-label="tr('lab.outputs.new_tab', 'Mở trong tab mới')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
                </a>
                <a class="btn ghost sm icon-only" :href="fileUrl(current.path)" :download="currentName" :title="tr('lab.outputs.download', 'Tải xuống')" :aria-label="tr('lab.outputs.download', 'Tải xuống')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
                </a>
                <button type="button" class="btn ghost sm icon-only" :title="tr('lab.outputs.reveal', 'Hiện trong thư mục')" :aria-label="tr('lab.outputs.reveal', 'Hiện trong thư mục')" :disabled="opening" @click="openOnMachine(current.path, true)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /><path d="m11 11 2.5 2.5L11 16" /></svg>
                </button>
              </div>
            </div>

            <div :class="['v-body', current.kind, { wrap }]">
              <!-- text-like -->
              <template v-if="TEXT_KINDS.has(current.kind)">
                <div v-if="textState === 'loading'" class="out-skel pad" aria-hidden="true"><span v-for="n in 6" :key="n"></span></div>
                <div v-else-if="textState === 'large'" class="v-empty">
                  <span>{{ tr('lab.outputs.too_large', 'File quá lớn để xem trực tiếp ({size}).', { size: bytes(current.size) }) }}</span>
                  <a class="btn secondary sm" :href="fileUrl(current.path)" :download="currentName">{{ tr('lab.outputs.download', 'Tải xuống') }}</a>
                </div>
                <div v-else-if="textState === 'error'" class="v-empty bad" role="alert">
                  <strong>{{ tr('lab.outputs.file_error', 'Không mở được file') }}</strong>
                  <span>{{ textError }}</span>
                </div>
                <!-- markdown-it with html:false escapes raw HTML; links/images are checked by its validateLink -->
                <article
                  v-else-if="current.kind === 'markdown' && !showSource"
                  class="md-view markdown-body"
                  @click="onMarkdownClick"
                  v-html="renderedMarkdown"
                ></article>
                <pre v-else class="code"><code><span v-for="(line, li) in visibleLines" :key="li" class="ln">{{ line || ' ' }}</span></code></pre>
                <p v-if="showsCode && lineCount > MAX_LINES" class="v-more">{{ tr('lab.outputs.lines_truncated', 'Chỉ hiện {n} dòng đầu tiên. Tải xuống để xem đủ.', { n: MAX_LINES.toLocaleString(locale) }) }}</p>
              </template>

              <div v-else-if="current.kind === 'image'" class="media img">
                <img :src="fileUrl(current.path)" :alt="currentName" loading="lazy" />
              </div>
              <div v-else-if="current.kind === 'video'" class="media">
                <video :src="fileUrl(current.path)" controls preload="metadata"></video>
              </div>
              <div v-else-if="current.kind === 'audio'" class="media audio">
                <audio :src="fileUrl(current.path)" controls preload="metadata"></audio>
              </div>
              <template v-else-if="current.kind === 'html'">
                <iframe
                  class="frame"
                  :src="siteUrl(current.path)"
                  :title="currentName"
                  sandbox="allow-scripts allow-forms allow-popups"
                  referrerpolicy="no-referrer"
                ></iframe>
                <p class="v-note">{{ tr('lab.outputs.html_note', 'Trang chạy trong khung cách ly: không truy cập được AgentDev.') }}</p>
              </template>
              <!-- Browsers refuse to render a PDF inside a sandboxed frame; <object> shows it without running page scripts -->
              <object v-else-if="current.kind === 'pdf'" class="frame" :data="fileUrl(current.path)" type="application/pdf" :aria-label="currentName">
                <div class="v-empty">
                  <a class="btn secondary sm" :href="fileUrl(current.path)" target="_blank" rel="noopener noreferrer">{{ tr('lab.outputs.new_tab', 'Mở trong tab mới') }}</a>
                </div>
              </object>
              <div v-else class="v-empty">
                <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(p, pi) in KIND_ICONS.binary" :key="pi" :d="p" /></svg>
                <span>{{ tr('lab.outputs.binary_hint', 'Không xem trước được loại file này.') }}</span>
                <div class="v-empty-actions">
                  <a class="btn secondary sm" :href="fileUrl(current.path)" :download="currentName">{{ tr('lab.outputs.download', 'Tải xuống') }}</a>
                  <button type="button" class="btn secondary sm" :disabled="opening" @click="openOnMachine(current.path, false)">{{ tr('lab.outputs.open_file', 'Mở bằng ứng dụng trên máy') }}</button>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="v-empty">{{ tr('lab.outputs.select_file', 'Chọn một file bên trái để xem') }}</div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import LabRunPreview from './LabRunPreview.vue'
import { toast } from '@/utils/toast.js'
import { confirmDialog } from '@/utils/confirm.js'
import {
  KIND_ICONS, MAX_TEXT_BYTES, TEXT_KINDS, ancestorsOf, buildTree, countKinds, flattenTree, formatBytes, pickDefaultFile
} from '@/utils/labOutputs.js'
import { labOutputSource } from '@/utils/outputSources.js'

const props = defineProps({
  // A Lab run (jobId + run) or any product folder through an adapter (`source`, see utils/outputSources.js)
  jobId: { type: String, default: '' },
  run: { type: Number, default: -1 },
  source: { type: Object, default: null },
  // The evaluation is still running: its folders cannot be deleted yet.
  jobRunning: { type: Boolean, default: false }
})
const emit = defineEmits(['deleted'])

const { t, te, locale } = useI18n()
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
const bytes = (n) => formatBytes(n, locale.value)
const src = computed(() => props.source || labOutputSource(props.jobId, props.run))
// Wording that depends on where the files come from (a Lab run, a chat session): the source may override it
const trc = (name, key, fallback, params) => {
  const own = src.value.copy?.[name]
  return own ? tr(own[0], own[1], params) : tr(key, fallback, params)
}
const canDelete = computed(() => typeof src.value.deleteOutputs === 'function')
const titleId = `lab-outputs-${useId()}`

const MAX_LINES = 5000
const WRAP_KEY = 'agentdev.lab.outputs.wrap'

const data = ref(null)
const loading = ref(false)
const loadError = ref('')
const selected = ref('')
const expanded = ref(new Set())
const treeEl = ref(null)
const opening = ref(false)
const deleting = ref(false)
let alive = true

const hasFiles = computed(() => !!data.value?.available && (data.value.files?.length || 0) > 0)
const fileMap = computed(() => new Map((data.value?.files || []).map((f) => [f.path, f])))
const tree = computed(() => buildTree(data.value?.files || []))
const rows = computed(() => flattenTree(tree.value, expanded.value))
const current = computed(() => fileMap.value.get(selected.value) || null)
const currentName = computed(() => (current.value ? current.value.path.split('/').pop() : ''))
const currentDir = computed(() => (current.value ? current.value.path.split('/').slice(0, -1).join('/') : ''))
const summaryLine = computed(() => {
  const parts = []
  // "none" projects say there is nothing to run: not worth a line of its own
  if (data.value?.project?.summary && data.value.project.type !== 'none') parts.push(data.value.project.summary)
  for (const { kind, n } of countKinds(data.value?.files).slice(0, 4)) {
    parts.push(`${n} ${tr(`lab.outputs.kinds.${kind}`, kind)}`)
  }
  return parts.join(' · ')
})

const fileUrl = (path) => src.value.fileUrl(path)
const siteUrl = (path) => src.value.siteUrl(path)
const newTabUrl = computed(() => (current.value?.kind === 'html' ? siteUrl(current.value.path) : fileUrl(current.value?.path || '')))
const iconFor = (node) =>
  node.type === 'dir' ? (expanded.value.has(node.path) ? KIND_ICONS.folderOpen : KIND_ICONS.folder) : KIND_ICONS[node.file.kind] || KIND_ICONS.binary

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const key = src.value.key
    const result = await src.value.files()
    if (!alive || key !== src.value.key) return
    data.value = result
    const files = result.files || []
    const first = pickDefaultFile(files)
    // Small products open fully; large ones only along the path to the first file.
    const open = new Set()
    if (files.length <= 60) {
      for (const f of files) for (const dir of ancestorsOf(f.path)) open.add(dir)
    } else if (first) {
      for (const dir of ancestorsOf(first.path)) open.add(dir)
    }
    expanded.value = open
    if (first && !fileMap.value.has(selected.value)) select(first.path)
    if (result.available && result.project?.can_preview) checkRunningPreview()
  } catch (err) {
    if (alive) loadError.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

// ------------------------------------------------------------------ tree
function toggleDir(path) {
  const next = new Set(expanded.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  expanded.value = next
}
function select(path) {
  selected.value = path
}
function focusRow(index) {
  const buttons = treeEl.value?.querySelectorAll('.tree-row')
  buttons?.[Math.max(0, Math.min(index, buttons.length - 1))]?.focus()
}
// Arrow keys walk the tree like a file explorer: up/down move, right opens a folder, left closes it or goes to its parent.
function onTreeKey(event) {
  const target = event.target.closest?.('.tree-row')
  if (!target) return
  const index = rows.value.findIndex((r) => r.node.path === target.dataset.path)
  if (index < 0) return
  const { node } = rows.value[index]
  const key = event.key
  if (key === 'ArrowDown') focusRow(index + 1)
  else if (key === 'ArrowUp') focusRow(index - 1)
  else if (key === 'Home') focusRow(0)
  else if (key === 'End') focusRow(rows.value.length - 1)
  else if (key === 'ArrowRight' && node.type === 'dir') {
    if (!expanded.value.has(node.path)) toggleDir(node.path)
    else focusRow(index + 1)
  } else if (key === 'ArrowLeft') {
    if (node.type === 'dir' && expanded.value.has(node.path)) toggleDir(node.path)
    else {
      const parent = ancestorsOf(node.path).pop()
      const parentIndex = rows.value.findIndex((r) => r.node.path === parent)
      if (parentIndex >= 0) focusRow(parentIndex)
    }
  } else return
  event.preventDefault()
}

// ------------------------------------------------------------------ viewer
const textState = ref('idle') // idle | loading | ready | large | error
const text = ref('')
const textError = ref('')
const showSource = ref(false)
const copied = ref(false)
const wrap = ref(readWrap())
const textCache = new Map()
let controller = null

function readWrap() {
  try {
    return localStorage.getItem(WRAP_KEY) !== '0'
  } catch {
    return true
  }
}
function toggleWrap() {
  wrap.value = !wrap.value
  try {
    localStorage.setItem(WRAP_KEY, wrap.value ? '1' : '0')
  } catch {
    // not remembered
  }
}

const showsCode = computed(() => textState.value === 'ready' && (current.value?.kind !== 'markdown' || showSource.value))
const lines = computed(() => text.value.replace(/\r\n?/g, '\n').split('\n'))
const lineCount = computed(() => lines.value.length)
const visibleLines = computed(() => (lineCount.value > MAX_LINES ? lines.value.slice(0, MAX_LINES) : lines.value))

watch(current, async (file) => {
  controller?.abort()
  controller = null
  showSource.value = false
  copied.value = false
  text.value = ''
  textError.value = ''
  if (!file || !TEXT_KINDS.has(file.kind)) {
    textState.value = 'idle'
    return
  }
  if (file.size > MAX_TEXT_BYTES) {
    textState.value = 'large'
    return
  }
  if (textCache.has(file.path)) {
    text.value = textCache.get(file.path)
    textState.value = 'ready'
    return
  }
  textState.value = 'loading'
  const ctrl = new AbortController()
  controller = ctrl
  try {
    const body = await src.value.fileText(file.path, { signal: ctrl.signal })
    if (ctrl.signal.aborted || !alive) return
    if (textCache.size > 30) textCache.clear()
    textCache.set(file.path, body)
    text.value = body
    textState.value = 'ready'
  } catch (err) {
    if (ctrl.signal.aborted || !alive) return
    if (err?.status === 413) textState.value = 'large'
    else {
      textError.value = err?.message || String(err)
      textState.value = 'error'
    }
  }
})

// Markdown: raw HTML stays escaped (html:false). Relative images load from the run's own files,
// relative links to other product files open them here, outside links open in a new tab.
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
const isExternal = (href) => /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')
function resolveRelative(href) {
  const clean = decodeURIComponent(String(href).split(/[?#]/)[0])
  if (!clean || clean.startsWith('/')) return ''
  const parts = currentDir.value ? currentDir.value.split('/') : []
  for (const part of clean.split('/')) {
    if (part === '..') parts.pop()
    else if (part && part !== '.') parts.push(part)
  }
  return parts.join('/')
}
const defaultImage = md.renderer.rules.image
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const src = token.attrGet('src') || ''
  if (src && !isExternal(src)) {
    const path = resolveRelative(src)
    if (path && fileMap.value.has(path)) token.attrSet('src', fileUrl(path))
  }
  token.attrSet('loading', 'lazy')
  return defaultImage(tokens, idx, options, env, self)
}
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const href = token.attrGet('href') || ''
  if (isExternal(href)) {
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
  }
  return self.renderToken(tokens, idx, options)
}
const renderedMarkdown = computed(() => (current.value?.kind === 'markdown' && textState.value === 'ready' ? md.render(text.value) : ''))
function onMarkdownClick(event) {
  const anchor = event.target.closest?.('a[href]')
  if (!anchor) return
  const href = anchor.getAttribute('href') || ''
  if (isExternal(href) || href.startsWith('#')) return
  const path = resolveRelative(href)
  if (!fileMap.value.has(path)) return
  event.preventDefault()
  expanded.value = new Set([...expanded.value, ...ancestorsOf(path)])
  select(path)
}

async function copyText() {
  try {
    await navigator.clipboard.writeText(text.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // clipboard unavailable: the text stays selectable
  }
}

// ------------------------------------------------------------------ actions
async function openOnMachine(path, reveal) {
  if (opening.value) return
  opening.value = true
  try {
    await src.value.open(path, reveal)
  } catch (err) {
    toast.error(tr('lab.outputs.open_error', 'Không mở được trên máy'), { detail: err?.detail || err?.message || String(err) })
  } finally {
    opening.value = false
  }
}

async function deleteOutputs() {
  if (props.jobRunning || deleting.value || !canDelete.value) return
  const ok = await confirmDialog({
    title: tr('lab.outputs.delete_confirm_title', 'Xoá kết quả của lượt này?'),
    message: tr('lab.outputs.delete_confirm_message', 'Toàn bộ file mà lượt này tạo ra ({size}) sẽ bị xoá khỏi máy.', { size: bytes(data.value?.total_bytes) }),
    confirmText: tr('lab.outputs.delete_confirm', 'Xoá kết quả'),
    tone: 'danger'
  })
  if (!ok || !alive) return
  deleting.value = true
  try {
    const result = await src.value.deleteOutputs()
    toast.success(tr('lab.outputs.deleted_toast', 'Đã xoá kết quả, giải phóng {size}', { size: bytes(result?.freed_bytes) }))
    previewOpen.value = false
    selected.value = ''
    textCache.clear()
    emit('deleted', result)
    await load()
  } catch (err) {
    toast.error(tr('lab.outputs.delete_failed', 'Không xoá được kết quả'), { detail: err?.detail || err?.message || String(err) })
  } finally {
    deleting.value = false
  }
}

// ------------------------------------------------------------------ preview
const previewOpen = ref(false)
const previewAutostart = ref(false)
const previewKey = ref(0)
function openPreview(autostart) {
  previewAutostart.value = autostart
  previewKey.value += 1
  previewOpen.value = true
}
// A preview started earlier (another visit, before a collapse) is still running: show it again.
async function checkRunningPreview() {
  if (previewOpen.value) return
  try {
    const status = await src.value.preview.status()
    if (alive && ['installing', 'starting', 'running'].includes(status?.status)) openPreview(false)
  } catch {
    // no preview: nothing to show
  }
}

onMounted(load)
// The owner reloads the list when the folder may have changed (a chat turn finished)
// (files may have been rewritten: cached texts are dropped; the new listing re-fetches the open file)
function reload() {
  textCache.clear()
  return load()
}
// openPreview(true): start the app now ("Chạy thử" pressed outside this component)
defineExpose({ reload, openPreview })
onBeforeUnmount(() => {
  alive = false
  controller?.abort()
})
watch(() => src.value.key, () => {
  data.value = null
  selected.value = ''
  textCache.clear()
  previewOpen.value = false
  nextTick(load)
})
</script>

<style scoped>
.outputs { container-type: inline-size; margin: 12px 0 0; padding: 14px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.out-head { display: flex; flex-wrap: wrap; gap: 10px 12px; align-items: center; }
.out-icon { display: grid; flex: none; place-items: center; width: 32px; height: 32px; border-radius: 9px; --c: var(--accent-mint-rgb); color: rgb(var(--c)); background: rgb(var(--c) / 0.12); box-shadow: inset 0 0 0 1px rgb(var(--c) / 0.22); }
.out-text { flex: 1 1 220px; min-width: 0; }
.out-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin: 0; font-size: 14px; font-weight: 700; color: var(--fg); }
.out-count { font-size: 12.5px; font-weight: 600; color: var(--fg-muted); }
.out-summary { margin: 2px 0 0; font-size: 12.5px; line-height: 1.5; color: var(--fg-muted); overflow-wrap: anywhere; }
.out-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.del-wrap { display: inline-flex; }
.btn.icon-danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.btn.active { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }

.out-state { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; margin-top: 12px; padding: 14px 16px; border-radius: 10px; font-size: 13px; line-height: 1.5; color: var(--fg-muted); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
.out-state strong { font-size: 14px; color: var(--fg); }
.out-state.bad { background: color-mix(in srgb, var(--danger) 7%, var(--surface)); }
.out-state.bad strong { color: var(--danger); }
.out-state .btn { margin-top: 6px; }
.out-skel { display: flex; flex-direction: column; gap: 9px; margin-top: 12px; }
.out-skel.pad { margin: 0; padding: 16px; }
.out-skel span { height: 13px; border-radius: 6px; background: linear-gradient(90deg, var(--tint), var(--tint-2), var(--tint)); background-size: 200% 100%; animation: out-shimmer 1.4s ease-in-out infinite; }
.out-skel span:nth-child(2n) { width: 70%; }
@keyframes out-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }

/* ---------------------------------------------------------------- browser */
.browser { display: grid; grid-template-columns: minmax(200px, 30%) minmax(0, 1fr); height: min(68vh, 560px); margin-top: 12px; border-radius: 10px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); overflow: hidden; }
.tree { min-width: 0; overflow: auto; border-right: 1px solid var(--line); padding: 6px; overscroll-behavior: contain; }
.tree-list { list-style: none; margin: 0; padding: 0; }
.tree-row {
  display: flex; align-items: center; gap: 5px; width: 100%; min-height: 30px; padding: 4px 8px 4px calc(6px + var(--depth) * 14px);
  border: 0; border-radius: 7px; background: transparent; color: var(--fg); font: inherit; font-size: 12.5px; text-align: left; cursor: pointer;
  transition: background-color 0.12s ease;
}
.tree-row:hover { background: var(--tint-2); }
.tree-row:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.tree-row.on { background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--fg); font-weight: 600; }
.tree-row.dir { font-weight: 600; }
.tree-chev { flex: none; width: 12px; color: var(--fg-muted); transition: transform 0.15s ease; }
.tree-row[aria-expanded='true'] .tree-chev { transform: rotate(90deg); }
.tree-icon { flex: none; color: var(--fg-muted); }
.tree-icon.dir { color: rgb(var(--accent-sky-rgb)); }
.tree-icon.markdown, .tree-icon.text, .tree-icon.pdf { color: rgb(var(--accent-indigo-rgb)); }
.tree-icon.image, .tree-icon.video, .tree-icon.audio { color: rgb(var(--accent-mint-rgb)); }
.tree-icon.html { color: var(--accent); }
.tree-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-size { flex: none; font-size: 11px; font-weight: 500; color: var(--fg-muted); opacity: 0; transition: opacity 0.12s ease; }
.tree-row:hover .tree-size, .tree-row:focus-visible .tree-size, .tree-row.on .tree-size { opacity: 1; }
.tree-note { margin: 8px 6px 4px; font-size: 12px; color: var(--warn); }

.viewer { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.v-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 6px 6px 6px 14px; border-bottom: 1px solid var(--line); }
.v-file { display: flex; flex-direction: column; flex: 1 1 160px; min-width: 0; }
.v-name { font-size: 13px; font-weight: 650; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.v-path { font-size: 11.5px; color: var(--fg-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.v-tools { display: flex; align-items: center; gap: 2px; }
.seg { display: inline-flex; margin-right: 4px; padding: 2px; border-radius: 8px; background: var(--tint-2); }
.seg button { min-height: 28px; padding: 0 10px; border: 0; border-radius: 6px; background: transparent; color: var(--fg-muted); font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
.seg button:hover { color: var(--fg); }
.seg button.on { background: var(--surface); color: var(--fg); box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }
.seg button:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.v-body { position: relative; flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.v-body.html, .v-body.pdf { display: flex; flex-direction: column; overflow: hidden; }
.md-view { max-width: 78ch; padding: 18px 22px 28px; font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; }
.md-view :deep(img) { max-width: 100%; height: auto; border-radius: 8px; }
.code { margin: 0; padding: 12px 0; min-width: max-content; font-size: 12.5px; line-height: 1.6; color: var(--fg); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; counter-reset: ln; tab-size: 4; }
.wrap .code { min-width: 0; }
.ln { display: block; padding: 0 16px 0 0; white-space: pre; }
.wrap .ln { white-space: pre-wrap; overflow-wrap: anywhere; padding-left: 4.2em; text-indent: -4.2em; }
.ln::before { counter-increment: ln; content: counter(ln); display: inline-block; width: 3.4em; margin-right: 0.8em; padding-right: 0.6em; text-align: right; color: var(--fg-subtle, var(--fg-muted)); opacity: 0.7; user-select: none; text-indent: 0; }
.code ::selection, .md-view ::selection { background: color-mix(in srgb, var(--accent) 28%, transparent); }
.v-more { margin: 0; padding: 4px 16px 12px; font-size: 12px; color: var(--fg-muted); }
.media { display: grid; place-items: center; min-height: 100%; padding: 16px; box-sizing: border-box; }
.media.img { background-color: var(--tint); background-image: conic-gradient(var(--tint-2) 25%, transparent 0 50%, var(--tint-2) 0 75%, transparent 0); background-size: 18px 18px; }
.media img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; box-shadow: 0 1px 3px rgb(0 0 0 / 0.15); }
.media video { max-width: 100%; max-height: 100%; border-radius: 8px; background: #000; }
.media.audio audio { width: min(100%, 480px); }
.frame { flex: 1; width: 100%; min-height: 0; border: 0; background: #fff; }
.v-note { margin: 0; padding: 6px 14px; border-top: 1px solid var(--line); font-size: 11.5px; color: var(--fg-muted); }
.v-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-height: 100%; padding: 24px; box-sizing: border-box; text-align: center; font-size: 13px; line-height: 1.5; color: var(--fg-muted); }
.v-empty.bad strong { color: var(--danger); }
.v-empty-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

/* Narrow run body: tree on top, viewer below */
@container (max-width: 620px) {
  .browser { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); height: auto; }
  .tree { max-height: 220px; border-right: 0; border-bottom: 1px solid var(--line); }
  .viewer { height: min(64vh, 480px); }
  .tree-size { opacity: 1; }
  .out-actions { width: 100%; }
}
@media (max-width: 720px) {
  .tree-row { min-height: 40px; }
  .seg button { min-height: 36px; }
}
@media (prefers-reduced-motion: reduce) {
  .out-skel span { animation: none; }
  .tree-chev, .tree-row, .tree-size { transition: none; }
}
</style>
