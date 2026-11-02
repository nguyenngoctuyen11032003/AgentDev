<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import markdownItAnchor from 'markdown-it-anchor'
import { useI18n } from 'vue-i18n'

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

// Defer off-screen images so the long tutorial paints quickly.
const defaultImageRenderer = md.renderer.rules.image
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('loading', 'lazy')
  token.attrSet('decoding', 'async')
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
      // For HTML image tags: src="media/file.gif" -> src="/media/file.gif"
      text = text.replace(/src="media\//g, 'src="/media/')
      // Raw <img> tags in the markdown are deferred as well
      text = text.replace(/<img\s(?![^>]*\bloading=)/g, '<img loading="lazy" decoding="async" ')

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

// Guards against a slow earlier request overwriting a newer language choice
let loadToken = 0

const loadTutorial = async () => {
  const token = ++loadToken
  try {
    const html = await fetchRendered(getTutorialFile())
    if (token !== loadToken) return
    renderedContent.value = html
    addCopyButtons()
    scrollToHash()
  } catch (error) {
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
  <div class="tutorial-view">
    <div ref="markdownBody" class="markdown-body" v-html="renderedContent"></div>
  </div>
</template>

<style scoped>
.tutorial-view {
  padding: 40px;
  width: 100%;
  max-width: 100%;
  margin: 0 auto;
  height: calc(100vh - 55px); /* Adjust the height of the .sidebar */
  background: linear-gradient(135deg, var(--surface-2) 0%, var(--surface-1) 100%);
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  /* Glowing border and card shadow */
  border-radius: 18px;
  box-shadow: 0 4px 32px 0 rgb(var(--cyan-rgb-2) / 0.08), 0 0 0 2px rgb(var(--cyan-rgb) / 0.2);
  border: 1.5px solid rgb(var(--cyan-rgb) / 0.2);
  transition: box-shadow 0.3s, height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  scroll-behavior: smooth;
}

:global(body.nav-hidden .tutorial-view) {
  height: 100vh;
}

:deep(.markdown-body) {
  max-width: 980px;
  margin: 0 auto;
  color: var(--text-2);
  font-family: 'JetBrains Mono', 'Fira Mono', 'Consolas', 'Menlo', 'Monaco', 'monospace', -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.7;
  letter-spacing: 0.01em;
  background: rgb(var(--panel-30) / 0.85);
  border-radius: 14px;
  box-shadow: 0 2px 16px 0 rgb(var(--cyan-rgb-2) / 0.04);
  padding: 32px 36px 32px 36px;
  border: 1px solid rgb(var(--cyan-rgb) / 0.13);
  /* No backdrop-filter here: it sits over a static gradient (no visible effect)
     but would force the compositor to re-blur the whole article on every scroll. */
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4),
:deep(.markdown-body h5),
:deep(.markdown-body h6) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--cyan);
  text-shadow: 0 0 8px rgb(var(--cyan-rgb) / 0.27);
  letter-spacing: 0.02em;
  scroll-margin-top: 20px; /* Offset for hash scroll target */
  transition: background 0.3s ease;
}

/* Highlight targeted heading */
:deep(.markdown-body h1:target),
:deep(.markdown-body h2:target),
:deep(.markdown-body h3:target),
:deep(.markdown-body h4:target),
:deep(.markdown-body h5:target),
:deep(.markdown-body h6:target) {
  background: rgb(var(--cyan-rgb) / 0.15);
  padding: 8px 12px;
  margin-left: -12px;
  margin-right: -12px;
  border-radius: 6px;
  box-shadow: 0 0 16px rgb(var(--cyan-rgb) / 0.3);
}

:deep(.markdown-body h1) { font-size: 2.2em; border-bottom: 1px solid rgb(var(--cyan-rgb) / 0.2); padding-bottom: 0.3em; }
:deep(.markdown-body h2) { font-size: 1.6em; border-bottom: 1px solid rgb(var(--cyan-rgb) / 0.13); padding-bottom: 0.3em; }
:deep(.markdown-body h3) { font-size: 1.3em; }

:deep(.markdown-body p) {
  margin-top: 0;
  margin-bottom: 16px;
  color: var(--accent-sky-3);
  font-size: 1.08em;
}

:deep(.markdown-body a) {
  color: var(--cyan);
  text-decoration: none;
  border-bottom: 1px dashed rgb(var(--cyan-rgb) / 0.6);
  transition: color 0.2s, border-bottom 0.2s;
}
:deep(.markdown-body a:hover) {
  color: var(--text-strong);
  border-bottom: 1px solid var(--cyan);
  text-shadow: 0 0 6px rgb(var(--cyan-rgb) / 0.6);
}

:deep(.markdown-body img) {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  background-color: transparent;
  border-radius: 10px;
  border: 1.5px solid rgb(var(--cyan-rgb) / 0.2);
  box-shadow: 0 2px 16px 0 rgb(var(--cyan-rgb) / 0.13);
  margin: 16px 0;
  transition: box-shadow 0.2s;
}
:deep(.markdown-body img:hover) {
  box-shadow: 0 0 24px 2px rgb(var(--cyan-rgb) / 0.53);
}

:deep(.markdown-body video) {
  max-width: 100%;
  border-radius: 10px;
  border: 1.5px solid rgb(var(--cyan-rgb) / 0.2);
  margin-bottom: 16px;
  box-shadow: 0 2px 16px 0 rgb(var(--cyan-rgb) / 0.13);
}

:deep(.markdown-body code) {
  padding: 0.2em 0.5em;
  margin: 0;
  font-size: 90%;
  background: linear-gradient(90deg, var(--surface-2) 60%, rgb(var(--cyan-rgb) / 0.13) 100%);
  border-radius: 6px;
  color: var(--cyan);
  font-family: 'JetBrains Mono', 'Fira Mono', 'Consolas', 'Menlo', 'Monaco', 'monospace';
  border: 1px solid rgb(var(--cyan-rgb) / 0.2);
  box-shadow: 0 0 8px rgb(var(--cyan-rgb) / 0.13);
}

:deep(.markdown-body pre) {
  padding: 18px 20px;
  overflow: auto;
  font-size: 95%;
  line-height: 1.55;
  background: linear-gradient(90deg, var(--bg-deep-2) 80%, rgb(var(--cyan-rgb) / 0.07) 100%);
  border-radius: 10px;
  margin-bottom: 18px;
  border: 1.5px solid rgb(var(--cyan-rgb) / 0.2);
  box-shadow: 0 0 16px rgb(var(--cyan-rgb) / 0.07);
  position: relative;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

:deep(.markdown-body pre code) {
  display: inline;
  padding: 0;
  margin: 0;
  overflow: visible;
  line-height: inherit;
  word-wrap: normal;
  background: transparent;
  border: 0;
  color: var(--cyan);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

:deep(.markdown-body pre.has-copy-button) {
  padding-top: 44px;
}

:deep(.markdown-body .copy-code-btn) {
  position: absolute;
  top: 10px;
  right: 10px;
  background: linear-gradient(90deg, var(--surface-2) 60%, rgb(var(--cyan-rgb) / 0.13) 100%);
  color: var(--cyan);
  border: 1px solid rgb(var(--cyan-rgb) / 0.27);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.85em;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border 0.2s, box-shadow 0.2s;
  box-shadow: 0 2px 8px rgb(var(--cyan-rgb) / 0.07);
}

:deep(.markdown-body .copy-code-btn:hover) {
  background: linear-gradient(90deg, var(--cyan) 0%, var(--cyan-deep) 100%);
  color: #fff;
  border: 1px solid var(--cyan);
  box-shadow: 0 0 12px rgb(var(--cyan-rgb) / 0.27);
}

:deep(.markdown-body blockquote) {
  padding: 0 1em;
  color: var(--accent-mint-3);
  border-left: 0.25em solid rgb(var(--cyan-rgb) / 0.6);
  margin: 0 0 16px 0;
  background: rgb(var(--cyan-rgb) / 0.04);
  border-radius: 6px;
}

:deep(.markdown-body hr) {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background: linear-gradient(90deg, rgb(var(--cyan-rgb) / 0.2) 0%, var(--surface-2) 100%);
  border: 0;
  border-radius: 2px;
}

:deep(.markdown-body table) {
  border-spacing: 0;
  border-collapse: collapse;
  margin-top: 0;
  margin-bottom: 16px;
  width: 100%;
  overflow: auto;
  background: rgb(var(--cyan-rgb) / 0.02);
  border-radius: 8px;
}

:deep(.markdown-body table th),
:deep(.markdown-body table td) {
  padding: 8px 15px;
  border: 1px solid rgb(var(--cyan-rgb) / 0.13);
}

:deep(.markdown-body table th) {
  font-weight: 700;
  background: rgb(var(--cyan-rgb) / 0.08);
  color: var(--cyan);
}

:deep(.markdown-body table tr) {
  background: rgb(var(--panel-30) / 0.7);
  border-top: 1px solid rgb(var(--cyan-rgb) / 0.07);
}

:deep(.markdown-body table tr:nth-child(2n)) {
  background: rgb(var(--cyan-rgb) / 0.03);
}

/* Custom Scrollbar */
.tutorial-view::-webkit-scrollbar {
  width: 10px;
  background: var(--surface-2);
}
.tutorial-view::-webkit-scrollbar-thumb {
  background: linear-gradient(135deg, var(--cyan) 0%, var(--surface-2) 100%);
  border-radius: 8px;
}

:deep(.markdown-body::-webkit-scrollbar) {
  height: 8px;
  background: var(--surface-2);
}
:deep(.markdown-body::-webkit-scrollbar-thumb) {
  background: linear-gradient(90deg, var(--cyan) 0%, var(--surface-2) 100%);
  border-radius: 8px;
}

/* ---------- Light theme: dark body copy, cyan kept for headings/links/code ---------- */
:root[data-theme="light"] .tutorial-view :deep(.markdown-body),
:root[data-theme="light"] .tutorial-view :deep(.markdown-body p),
:root[data-theme="light"] .tutorial-view :deep(.markdown-body li),
:root[data-theme="light"] .tutorial-view :deep(.markdown-body td),
:root[data-theme="light"] .tutorial-view :deep(.markdown-body blockquote) {
  color: var(--text-2);
}
:root[data-theme="light"] .tutorial-view :deep(.markdown-body strong) {
  color: var(--text-strong);
}

</style>
