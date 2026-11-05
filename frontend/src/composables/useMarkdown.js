import { toRaw } from 'vue'
import MarkdownIt from 'markdown-it'
import { toast } from '@/utils/toast.js'

/**
 * Chat markdown rendering for the Launch view: markdown-it with copy buttons on code
 * blocks, scrolling tables and new-tab links, memoized per source text and per chat row.
 * Everything is created per call (per component instance), as it was inline.
 *
 * @param {{ t: Function, locale: import('vue').Ref<string> }} i18n
 */
export function useMarkdown({ t, locale: i18nLocale }) {
  const md = new MarkdownIt({
    html: false,
    linkify: true,
    typographer: true
  })
  // Code blocks get their own copy button (like Claude / ChatGPT) and wide tables scroll
  // sideways instead of squeezing a column per letter. The button label is localized at
  // render time, so the markdown cache is keyed by locale too.
  const CODE_COPY_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
  let codeCopyLabel = 'Copy'
  const withCopyButton = (rule) => (tokens, idx, options, env, self) => {
    const html = rule(tokens, idx, options, env, self)
    const lang = (tokens[idx].info || '').trim().split(/\s+/)[0]
    const label = md.utils.escapeHtml(codeCopyLabel)
    const langTag = lang ? `<span class="md-code-lang">${md.utils.escapeHtml(lang)}</span>` : ''
    return `<div class="md-code">${langTag}<button type="button" class="md-code-copy" data-code-copy title="${label}" aria-label="${label}">${CODE_COPY_ICON}<span>${label}</span></button>${html}</div>`
  }
  md.renderer.rules.fence = withCopyButton(md.renderer.rules.fence)
  md.renderer.rules.code_block = withCopyButton(md.renderer.rules.code_block)
  md.renderer.rules.table_open = () => '<div class="md-table"><table>\n'
  md.renderer.rules.table_close = () => '</table></div>\n'
  // Links in a message open in a new tab and never get a handle back on this page
  const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener noreferrer')
    return defaultLinkOpen(tokens, idx, options, env, self)
  }

  // Memoize markdown output by source text so re-renders never re-parse the same message
  const MARKDOWN_CACHE_LIMIT = 300
  const markdownCache = new Map()
  // Above this size a message is shown as preformatted text: running markdown-it
  // (linkify + typographer) over hundreds of KB blocks the WebSocket handler and
  // freezes the page for a noticeable moment.
  const MARKDOWN_MAX_CHARS = 120_000
  const preformatted = (text, lang = '') =>
    `<pre><code${lang ? ` class="language-${lang}"` : ''}>${md.utils.escapeHtml(text)}</code></pre>`

  // A chat row's markdown, kept on the row until its `rev`, text or language changes (the plain
  // renderMarkdown cache hashes the whole text on every render of every row)
  const rowHtmlCache = new WeakMap()
  const renderRowMarkdown = (message, text) => {
    const raw = toRaw(message)
    const source = text || ''
    const cached = rowHtmlCache.get(raw)
    if (cached && cached.rev === raw.rev && cached.locale === i18nLocale.value && cached.source === source) return cached.html
    const html = renderMarkdown(source)
    rowHtmlCache.set(raw, { rev: raw.rev, locale: i18nLocale.value, source, html })
    return html
  }

  const renderMarkdown = (text) => {
    const source = text || ''
    codeCopyLabel = t('launch.copy_code')
    const cacheKey = `${i18nLocale.value}\u0000${source}`
    const cached = markdownCache.get(cacheKey)
    if (cached !== undefined) return cached
    const html = source.length > MARKDOWN_MAX_CHARS ? preformatted(source) : md.render(source)
    if (markdownCache.size >= MARKDOWN_CACHE_LIMIT) {
      markdownCache.delete(markdownCache.keys().next().value)
    }
    markdownCache.set(cacheKey, html)
    return html
  }

  // One delegated listener for every code block's copy button in the chat
  const copiedTimers = new WeakMap()
  const handleChatClick = async (event) => {
    const button = event.target.closest?.('[data-code-copy]')
    if (!button) return
    event.stopPropagation()
    const code = button.parentElement?.querySelector('pre')?.innerText ?? ''
    try {
      await navigator.clipboard.writeText(code.replace(/\n$/, ''))
    } catch (error) {
      console.warn('Copy failed:', error)
      toast.error(t('launch.copy_failed'))
      return
    }
    const label = button.querySelector('span')
    if (label) label.textContent = t('launch.copied')
    button.classList.add('copied')
    clearTimeout(copiedTimers.get(button))
    copiedTimers.set(button, setTimeout(() => {
      button.classList.remove('copied')
      if (label) label.textContent = t('launch.copy_code')
    }, 1600))
  }

  return { md, preformatted, renderMarkdown, renderRowMarkdown, handleChatClick }
}
