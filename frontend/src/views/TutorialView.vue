<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import markdownItAnchor from 'markdown-it-anchor'
import { useI18n } from 'vue-i18n'
import mediaSizes from '@/utils/tutorialMediaSizes.json'

// ---------------------------------------------------------------------------
// Module-level: one parser for the app lifetime (built once, not per visit)
// and a cache of rendered HTML so revisits / language switches are instant.
// ---------------------------------------------------------------------------
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
})
md.use(markdownItAnchor, {
  permalink: markdownItAnchor.permalink.ariaHidden({
    placement: 'before',
    symbol: '#',
    space: true,
    class: 'header-anchor'
  }),
  slugify: s =>
    s
      .trim()
      .toLowerCase()
      // Strip Vietnamese/Latin diacritics so headings get readable ASCII anchors
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\u0111/g, 'd')
      .replace(/[^a-z0-9\u4e00-\u9fa5\s-]/g, '')
      .replace(/\s+/g, '-')
})

// Images load up front (only a handful) but decode off the main thread, so nothing
// pops in and shifts the text while the reader is scrolling.
// Each image also gets its real size (scripts/tutorial-media-sizes.mjs), so the browser reserves
// the box before the file arrives: no layout shift while a large image is still downloading.
const defaultImageRenderer = md.renderer.rules.image
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('decoding', 'async')
  const file = (token.attrGet('src') || '').split('/').pop().split('?')[0]
  const size = mediaSizes[file]
  if (size && !token.attrGet('width')) {
    token.attrSet('width', String(size[0]))
    token.attrSet('height', String(size[1]))
  }
  return defaultImageRenderer(tokens, idx, options, env, self)
}

const TUTORIAL_FILES = { vi: '/tutorial-vi.md', en: '/tutorial-en.md', zh: '/tutorial-zh.md' }

/** file -> rendered HTML */
const renderedCache = new Map()
/** file -> in-flight promise (concurrent requests share one fetch) */
const pendingLoads = new Map()

const fetchRendered = (file) => {
  if (renderedCache.has(file)) return Promise.resolve(renderedCache.get(file))
  if (pendingLoads.has(file)) return pendingLoads.get(file)

  const load = fetch(file)
    .then(async (response) => {
      if (!response.ok) {
        const error = new Error(`HTTP ${response.status}`)
        error.notOk = true
        throw error
      }
      let text = await response.text()
      // Fix media paths to point to /media/ (absolute path from public root)
      // For markdown images: ![alt](media/file.png) -> ![alt](/media/file.png)
      text = text.replace(/\]\(media\//g, '](/media/')
      // For HTML image tags: src="media/file.webp" -> src="/media/file.webp"
      text = text.replace(/src="media\//g, 'src="/media/')
      // Raw <img> tags in the markdown decode asynchronously as well
      text = text.replace(/<img\s(?![^>]*\bdecoding=)/g, '<img decoding="async" ')

      const html = md.render(text)
      renderedCache.set(file, html)
      return html
    })
    .finally(() => pendingLoads.delete(file))

  pendingLoads.set(file, load)
  return load
}

const route = useRoute()
const { locale, t } = useI18n()

const renderedContent = ref('')
const status = ref('loading') // loading | ready | error
const markdownBody = ref(null)
const getTutorialFile = () => TUTORIAL_FILES[locale.value] || TUTORIAL_FILES.en

const scrollToHash = () => {
  // Wait for DOM to update, then scroll to hash if present
  nextTick(() => {
    if (route.hash) {
      // Remove the '#' from the hash
      const targetId = route.hash.slice(1)
      const targetElement = document.getElementById(targetId)
      
      if (targetElement) {
        setTimeout(() => {
          targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 100)
      }
    }
  })
}

const addCopyButtons = () => {
  nextTick(() => {
    const container = markdownBody.value
    if (!container) return
    const blocks = container.querySelectorAll('pre')
    blocks.forEach((block) => {
      if (block.querySelector('.copy-code-btn')) return
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'copy-code-btn'
      button.textContent = t('tutorial.copy')
      button.addEventListener('click', async () => {
        const code = block.querySelector('code')
        const text = code ? code.innerText : block.innerText
        try {
          await navigator.clipboard.writeText(text)
          button.textContent = t('tutorial.copied')
          setTimeout(() => {
            button.textContent = t('tutorial.copy')
          }, 1200)
        } catch (error) {
          console.error(t('tutorial.failed_to_copy'), error)
        }
      })
      block.classList.add('has-copy-button')
      block.appendChild(button)
    })
  })
}

// ---------------------------------------------------------------------------
// Table of contents (sticky side panel) + scroll spy
// ---------------------------------------------------------------------------
const scroller = ref(null)
const toc = ref([]) // { id, text, level }
const activeId = ref('')
let headingEls = []
let spyFrame = 0
// While a TOC click scrolls the page, keep the clicked item highlighted instead of
// flickering through every heading the smooth scroll passes.
let lockUntil = 0

// The active section is the last heading that has reached the top band of the viewport.
// Stable in both directions, unlike "first heading currently intersecting".
const updateActive = () => {
  spyFrame = 0
  const root = scroller.value
  if (!root || !headingEls.length || Date.now() < lockUntil) return
  const limit = root.getBoundingClientRect().top + 96
  let current = headingEls[0]
  for (const el of headingEls) {
    if (el.getBoundingClientRect().top <= limit) current = el
    else break
  }
  if (root.scrollTop + root.clientHeight >= root.scrollHeight - 2) current = headingEls[headingEls.length - 1]
  if (current && activeId.value !== current.id) activeId.value = current.id
}

const onScroll = () => {
  if (!spyFrame) spyFrame = requestAnimationFrame(updateActive)
}

const headingText = (el) =>
  Array.from(el.childNodes)
    .filter((node) => !(node.nodeType === 1 && node.classList.contains('header-anchor')))
    .map((node) => node.textContent)
    .join('')
    .trim()

const buildToc = () => {
  nextTick(() => {
    const container = markdownBody.value
    if (!container) return
    const headings = Array.from(container.querySelectorAll('h1[id], h2[id]'))
    let inReference = false
    toc.value = headings.slice(1).map((el) => {
      if (el.tagName === 'H1') inReference = true
      return { id: el.id, text: headingText(el), level: el.tagName === 'H1' ? 0 : inReference ? 1 : 0, group: el.tagName === 'H1' }
    })
    // The markdown has its own link list under the title; the side panel replaces it on wide screens.
    const firstList = container.querySelector(':scope > ul')
    if (firstList && Array.from(firstList.querySelectorAll('a')).every((a) => a.getAttribute('href')?.startsWith('#'))) {
      firstList.classList.add('inline-toc')
    }
    headingEls = headings.slice(1)
    updateActive()
  })
}

const goTo = (id) => {
  const el = document.getElementById(id)
  if (!el) return
  activeId.value = id
  const smooth = !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  lockUntil = smooth ? Date.now() + 900 : 0
  el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
  history.replaceState(history.state, '', `#${id}`)
}

const releaseLock = () => {
  lockUntil = 0
  updateActive()
}

onMounted(() => {
  scroller.value?.addEventListener('scroll', onScroll, { passive: true })
  scroller.value?.addEventListener('scrollend', releaseLock, { passive: true })
})

onBeforeUnmount(() => {
  scroller.value?.removeEventListener('scroll', onScroll)
  scroller.value?.removeEventListener('scrollend', releaseLock)
  if (spyFrame) cancelAnimationFrame(spyFrame)
})

// Guards against a slow earlier request overwriting a newer language choice
let loadToken = 0

const loadTutorial = async () => {
  const token = ++loadToken
  status.value = 'loading'
  try {
    const html = await fetchRendered(getTutorialFile())
    if (token !== loadToken) return
    renderedContent.value = html
    status.value = 'ready'
    addCopyButtons()
    buildToc()
    scrollToHash()
  } catch (error) {
    if (token !== loadToken) return
    status.value = 'error'
    renderedContent.value = ''
    toc.value = []
    if (error && error.notOk) {
      console.error(t('tutorial.failed_to_fetch'))
    } else {
      console.error(t('tutorial.failed_to_load'), error)
    }
  }
}

watch(locale, () => {
  loadTutorial()
})

onMounted(() => {
  loadTutorial()
})
</script>

<template>
  <div ref="scroller" class="tutorial-view scroll-y">
    <div class="tutorial-layout">
      <nav v-if="toc.length" class="toc" :aria-label="$t('tutorial.toc')">
        <p class="toc-title">{{ $t('tutorial.toc') }}</p>
        <ul>
          <li v-for="item in toc" :key="item.id" :class="[`lvl-${item.level}`, { group: item.group }]">
            <a
              :href="`#${item.id}`"
              :class="{ active: activeId === item.id }"
              :aria-current="activeId === item.id ? 'location' : undefined"
              @click.prevent="goTo(item.id)"
            >{{ item.text }}</a>
          </li>
        </ul>
      </nav>
      <div v-if="status === 'loading'" class="doc-skeleton" role="status" :aria-label="$t('tutorial.loading')">
        <span class="skeleton sk sk-title"></span>
        <span class="skeleton sk sk-line"></span>
        <span class="skeleton sk sk-line"></span>
        <span class="skeleton sk sk-line sk-short"></span>
        <span class="skeleton sk sk-block"></span>
        <span class="skeleton sk sk-line"></span>
        <span class="skeleton sk sk-line sk-short"></span>
      </div>
      <div v-else-if="status === 'error'" class="doc-error" role="alert">
        <p class="doc-error-title">{{ $t('tutorial.error_title') }}</p>
        <p class="doc-error-desc">{{ $t('tutorial.error_desc') }}</p>
        <button type="button" class="btn primary doc-retry" @click="loadTutorial">{{ $t('tutorial.retry') }}</button>
      </div>
      <article v-show="status === 'ready'" ref="markdownBody" class="markdown-body" v-html="renderedContent"></article>
    </div>
  </div>
</template>

<style scoped>
.tutorial-view {
  --doc-text: var(--text-2);
  --doc-muted: var(--fg-muted);
  --doc-strong: var(--text-strong);
  --doc-line: rgb(var(--ink) / 0.1);
  --doc-soft: rgb(var(--ink) / 0.04);
  --doc-accent: var(--accent);
  --doc-accent-rgb: var(--accent-sky-rgb);

  box-sizing: border-box;
  width: 100%;
  height: calc(calc(100 * var(--dvh)) - var(--nav-height, 55px)); /* below the top bar */
  overflow-x: hidden;
  overscroll-behavior: contain;
  background: var(--bg);
  font-family: 'Inter', system-ui, sans-serif;
}

:global(body.nav-hidden .tutorial-view) {
  height: calc(100 * var(--dvh));
}

.tutorial-layout {
  display: grid;
  grid-template-columns: 248px minmax(0, 780px);
  justify-content: center;
  gap: 56px;
  box-sizing: border-box;
  max-width: 1180px;
  margin: 0 auto;
  padding: 48px 32px 120px;
}

/* ---------------------------------------------------------------- TOC */
.toc {
  position: sticky;
  top: 32px;
  align-self: start;
  max-height: calc(calc(100 * var(--dvh)) - 140px);
  overflow-y: auto;
  padding-right: 8px;
}

.toc-title {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 650;
  color: var(--doc-muted);
}

.toc ul {
  margin: 0;
  padding: 0;
  list-style: none;
  border-left: 1px solid var(--doc-line);
}

.toc li.group {
  margin-top: 14px;
}

.toc a {
  display: block;
  margin-left: -1px;
  padding: 9px 0 9px 14px;
  border-left: 2px solid transparent;
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.45;
  color: var(--doc-muted);
  text-decoration: none;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.toc li.group > a {
  font-weight: 650;
  color: var(--doc-text);
}

.toc li.lvl-1 a {
  padding-left: 26px;
  font-size: 13px;
}

.toc a:hover {
  color: var(--doc-strong);
}

.toc a.active {
  color: var(--doc-accent);
  border-left-color: var(--doc-accent);
}

.toc a:focus-visible {
  outline: 2px solid var(--doc-accent);
  outline-offset: 2px;
  border-radius: 4px;
}

/* ---------------------------------------------------------------- article */
.markdown-body {
  min-width: 0;
  color: var(--doc-text);
  font-size: 16px;
  line-height: 1.75;
}

.markdown-body :deep(> :first-child) {
  margin-top: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  position: relative;
  color: var(--doc-strong);
  font-weight: 750;
  line-height: 1.25;
  letter-spacing: -0.02em;
  scroll-margin-top: 24px;
}

.markdown-body :deep(h1) {
  margin: 64px 0 20px;
  font-size: 34px;
  letter-spacing: -0.03em;
}

.markdown-body :deep(h1:first-child) {
  font-size: 40px;
}

.markdown-body :deep(h2) {
  margin: 52px 0 16px;
  padding-top: 28px;
  border-top: 1px solid var(--doc-line);
  font-size: 25px;
}

/* The markdown already separates sections with "---": no second rule on the heading */
.markdown-body :deep(hr + h1),
.markdown-body :deep(hr + h2),
.markdown-body :deep(h1 + h2) {
  margin-top: 24px;
  padding-top: 0;
  border-top: 0;
}

.markdown-body :deep(h3) {
  margin: 36px 0 12px;
  font-size: 19px;
}

.markdown-body :deep(h4) {
  margin: 28px 0 10px;
  font-size: 16px;
}

/* Permalink "#" shows on hover, outside the text column */
.markdown-body :deep(.header-anchor) {
  position: absolute;
  left: -1em;
  padding-right: 0.25em;
  color: var(--doc-muted);
  font-weight: 500;
  text-decoration: none;
  border: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.markdown-body :deep(h1:hover .header-anchor),
.markdown-body :deep(h2:hover .header-anchor),
.markdown-body :deep(h3:hover .header-anchor),
.markdown-body :deep(.header-anchor:focus-visible) {
  opacity: 1;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 18px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.4em;
}

.markdown-body :deep(li + li) {
  margin-top: 6px;
}

.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) {
  margin: 6px 0 0;
}

.markdown-body :deep(li::marker) {
  color: var(--doc-muted);
}

.markdown-body :deep(strong) {
  color: var(--doc-strong);
  font-weight: 650;
}

.markdown-body :deep(a) {
  color: var(--doc-accent);
  font-weight: 500;
  text-decoration: underline;
  text-decoration-color: rgb(var(--doc-accent-rgb) / 0.4);
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  transition: text-decoration-color 0.15s ease;
}

.markdown-body :deep(a:hover) {
  text-decoration-color: currentColor;
}

/* Inline code */
.markdown-body :deep(code) {
  padding: 0.15em 0.4em;
  border-radius: 6px;
  font-family: ui-monospace, 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  font-size: 0.87em;
  color: var(--doc-strong);
  background: rgb(var(--ink) / 0.07);
  box-shadow: inset 0 0 0 1px var(--doc-line);
}

/* Code blocks */
.markdown-body :deep(pre) {
  position: relative;
  margin: 0 0 22px;
  padding: 18px 20px;
  overflow: auto;
  border-radius: 12px;
  background: var(--bg-deep-2);
  box-shadow: inset 0 0 0 1px var(--doc-line);
  font-size: 13.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.markdown-body :deep(pre code) {
  padding: 0;
  font-size: inherit;
  color: var(--text-soft-3);
  background: transparent;
  box-shadow: none;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.markdown-body :deep(pre.has-copy-button) {
  padding-top: 44px;
}

.markdown-body :deep(.copy-code-btn) {
  position: absolute;
  top: 6px;
  right: 8px;
  min-height: 36px;
  padding: 4px 12px;
  border-radius: 7px;
  border: 0;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--doc-muted);
  background: rgb(var(--ink) / 0.06);
  box-shadow: inset 0 0 0 1px var(--doc-line);
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.markdown-body :deep(.copy-code-btn:hover) {
  color: var(--doc-strong);
  background: rgb(var(--ink) / 0.12);
}

/* Callouts */
.markdown-body :deep(blockquote) {
  margin: 0 0 22px;
  padding: 14px 18px;
  border: 1px solid rgb(var(--doc-accent-rgb) / 0.35);
  border-radius: 10px;
  color: var(--doc-text);
  background: rgb(var(--doc-accent-rgb) / 0.07);
}

.markdown-body :deep(blockquote > :last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(hr) {
  height: 1px;
  margin: 48px 0 40px;
  border: 0;
  background: var(--doc-line);
}

/* Tables */
.markdown-body :deep(table) {
  display: block;
  width: 100%;
  margin: 0 0 22px;
  overflow-x: auto;
  border-collapse: separate;
  border-spacing: 0;
  border-radius: 12px;
  box-shadow: inset 0 0 0 1px var(--doc-line);
  font-size: 14.5px;
  line-height: 1.6;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 10px 14px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--doc-line);
}

.markdown-body :deep(th) {
  font-size: 13px;
  font-weight: 650;
  color: var(--doc-muted);
  background: var(--doc-soft);
}

.markdown-body :deep(tr:last-child td) {
  border-bottom: 0;
}

.markdown-body :deep(td:first-child) {
  color: var(--doc-strong);
}

/* Media */
.markdown-body :deep(img),
.markdown-body :deep(video) {
  display: block;
  width: auto;
  max-width: 100%;
  height: auto;
  margin: 8px 0 22px;
  box-sizing: border-box;
  border-radius: 12px;
  /* Hairline only: a large blurred shadow under animated images repaints every frame while scrolling */
  border: 1px solid var(--doc-line);
  background: var(--doc-soft);
  /* Own layer: animated webp frames do not invalidate the text around them */
  contain: paint;
  transform: translateZ(0);
}

/* Loading + error */
.doc-skeleton {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.sk {
  height: 14px;
  border-radius: 8px;
}

.sk-title { width: 55%; height: 36px; margin-bottom: 14px; }
.sk-short { width: 70%; }
.sk-block { height: 120px; margin: 10px 0; border-radius: 12px; }

.doc-error {
  align-self: start;
  padding: 28px;
  border: 1px solid var(--doc-line);
  border-radius: 14px;
  background: var(--doc-soft);
}

.doc-error-title {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 650;
  color: var(--doc-strong);
}

.doc-error-desc {
  margin: 0 0 16px;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--doc-muted);
}

/* ---------------------------------------------------------------- responsive */
@media (min-width: 1025px) {
  .markdown-body :deep(.inline-toc),
  .markdown-body :deep(.inline-toc + hr) {
    display: none;
  }
}

@media (max-width: 1024px) {
  .tutorial-layout {
    grid-template-columns: minmax(0, 780px);
    padding: 36px 24px 96px;
  }

  .toc {
    display: none;
  }
}

@media (max-width: 600px) {
  .tutorial-layout { padding: 28px 16px 72px; }
  .markdown-body { font-size: 15.5px; }
  .markdown-body :deep(h1:first-child) { font-size: 30px; }
  .markdown-body :deep(h1) { font-size: 26px; }
  .markdown-body :deep(h2) { font-size: 21px; }
  .markdown-body :deep(.header-anchor) { display: none; }
}

</style>
