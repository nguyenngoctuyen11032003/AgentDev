<template>
    <div class="sidebar" :class="{ 'is-hidden': isHidden }" :inert="isHidden" @mouseenter="isHidden = false" @focusin="isHidden = false">
        <router-link to="/" class="sidebar-brand" aria-label="AgentDev">
            <img src="/media/logo.svg?v=2" alt="" class="sidebar-brand-logo" width="28" height="28" />
            <span class="sidebar-brand-name">AgentDev</span>
        </router-link>

        <nav ref="navRef" class="sidebar-nav">
            <router-link v-for="item in navItems" :key="item.to" :to="item.to" v-bind="item.attrs">{{ $t(item.label) }}</router-link>
        </nav>

        <!-- Phones: one button naming the current page, opening the full list -->
        <div ref="compactRef" class="nav-compact" @keydown.esc="closeMenu(true)" @focusout="onCompactFocusOut">
            <button
                ref="compactBtnRef"
                type="button"
                class="nav-compact-btn"
                aria-haspopup="true"
                :aria-expanded="menuOpen"
                aria-controls="nav-compact-list"
                @click="menuOpen = !menuOpen"
            >
                <span class="nav-compact-label">{{ activeLabel }}</span>
                <svg class="nav-compact-chevron" :class="{ open: menuOpen }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>
            </button>
            <nav v-show="menuOpen" id="nav-compact-list" class="nav-compact-list" :aria-label="activeLabel">
                <router-link v-for="item in navItems" :key="item.to" :to="item.to" v-bind="item.attrs" @click="closeMenu(false)">{{ $t(item.label) }}</router-link>
            </nav>
        </div>
        <div class="sidebar-actions">
            <!-- Settings page also holds Connections and Skills -->
            <router-link to="/settings" class="settings-nav-btn" :title="$t('settings.title')" :aria-label="$t('settings.title')">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <span class="settings-nav-text">{{ $t('settings.title') }}</span>
            </router-link>
        </div>
    </div>
    <div class="sidebar-hit-area" v-if="isHidden" @mouseenter="isHidden = false" @click="isHidden = false"></div>
</template>

<script setup>
defineOptions({ name: 'AppSidebar' })
import { RouterLink, useRoute } from 'vue-router'
import { ref, computed, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const isHidden = ref(false)
const { t } = useI18n()

const navItems = [
    { to: '/', label: 'nav.home', attrs: {} },
    { to: '/tutorial', label: 'nav.tutorial', attrs: {} },
    { to: '/workflows', label: 'nav.workflows', attrs: {} },
    { to: '/launch', label: 'nav.launch', attrs: { target: '_blank', rel: 'noopener' } },
    { to: '/lab', label: 'nav.laboratory', attrs: {} },
]

// Compact (phone) menu: the button always names the page the user is on.
const menuOpen = ref(false)
const compactRef = ref(null)
const compactBtnRef = ref(null)
const closeMenu = (refocus) => {
    if (!menuOpen.value) return
    menuOpen.value = false
    if (refocus) compactBtnRef.value?.focus()
}
const onCompactFocusOut = (e) => {
    if (!compactRef.value?.contains(e.relatedTarget)) menuOpen.value = false
}
const onDocPointer = (e) => {
    if (menuOpen.value && !compactRef.value?.contains(e.target)) menuOpen.value = false
}
document.addEventListener('pointerdown', onDocPointer)

// An inert (hidden) bar cannot take focus, so Tab itself brings it back for keyboard users.
const revealOnTab = (e) => { if (e.key === 'Tab' && isHidden.value) isHidden.value = false }
document.addEventListener('keydown', revealOnTab)

watch(isHidden, (val) => {
    if (val) {
        document.body.classList.add('nav-hidden')
    } else {
        document.body.classList.remove('nav-hidden')
    }
})

// Active highlighting relies on the router-link-active class only: the /workflows
// link resolves to the "/workflows/:name?" record, so it stays active for every
// workflow without a path watcher.
const route = useRoute()

const activeLabel = computed(() => {
    const p = route.path
    if (p.startsWith('/settings')) return t('settings.title')
    const hit = navItems.find((item) => item.to !== '/' && (p === item.to || p.startsWith(`${item.to}/`)))
    return t(hit ? hit.label : 'nav.home')
})
watch(() => route.fullPath, () => { menuOpen.value = false })

// Narrow screens scroll the nav row sideways: keep the current page's link in view.
const navRef = ref(null)
watch(() => route.path, async () => {
    await nextTick()
    const nav = navRef.value
    const active = nav?.querySelector('.router-link-active')
    if (!nav || !active || nav.scrollWidth <= nav.clientWidth) return
    const left = active.getBoundingClientRect().left - nav.getBoundingClientRect().left + nav.scrollLeft
    const target = left - (nav.clientWidth - active.offsetWidth) / 2
    nav.scrollTo({ left: Math.max(0, target), behavior: 'auto' })
}, { immediate: true })

let lastScrollY = 0
let scrollRaf = 0
let pendingScrollTarget = null

const applyScroll = () => {
    scrollRaf = 0
    const target = pendingScrollTarget
    pendingScrollTarget = null
    const currentScrollY = (target && target.scrollTop) || window.scrollY || 0;
    // Minimize small scroll jitters
    if (Math.abs(currentScrollY - lastScrollY) < 5) return;

    // Scrolling down -> hide (if past slight threshold). Scrolling up -> show
    if (currentScrollY > lastScrollY && currentScrollY > 10) {
        isHidden.value = true;
    } else if (currentScrollY < lastScrollY) {
        isHidden.value = false;
    }
    lastScrollY = currentScrollY <= 0 ? 0 : currentScrollY;
}

// Passive + rAF-throttled: at most one state update per frame and it never blocks scrolling
const handleScroll = (e) => {
    if (e.target instanceof Element && e.target.closest('[data-local-scroll]')) {
        return;
    }
    pendingScrollTarget = e.target instanceof Element ? e.target : null
    if (!scrollRaf) scrollRaf = requestAnimationFrame(applyScroll)
}

const toggleScrollListener = (shouldListen) => {
    if (shouldListen) {
        window.addEventListener('scroll', handleScroll, { capture: true, passive: true });
    } else {
        window.removeEventListener('scroll', handleScroll, { capture: true });
        if (scrollRaf) {
            cancelAnimationFrame(scrollRaf)
            scrollRaf = 0
        }
        isHidden.value = false; // Reset state when leaving
    }
}

watch(() => route.path, () => {
    toggleScrollListener(!!route.meta.hideNavOnScroll);
}, { immediate: true }) // immediate: true runs this once on mount

onUnmounted(() => {
    document.removeEventListener('keydown', revealOnTab)
    document.removeEventListener('pointerdown', onDocPointer)
    toggleScrollListener(false);
    document.body.classList.remove('nav-hidden');
})
</script>

<style scoped>
.sidebar {
    width: 100%;
    background-color: var(--bg-base);
    padding: 0 24px 0 0;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    height: 55px;
    position: sticky;
    top: 0;
    z-index: var(--z-sticky);
    border-bottom: 1px solid var(--line-5);
    justify-content: center;
    transition: transform 0.3s var(--ease-out);
    transform: translateY(0);
}

.sidebar.is-hidden {
    transform: translateY(-100%);
}

@media (prefers-reduced-motion: reduce) {
    .sidebar { transition: none; }
}

.sidebar-hit-area {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 40px;
    z-index: calc(var(--z-sticky) - 1);
}

.sidebar-actions {
    position: absolute;
    right: 24px;
    top: 50%;
    transform: translateY(-50%);
}

.sidebar-brand {
    position: absolute;
    left: 20px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    gap: 10px;
    text-decoration: none;
    user-select: none;
}

.sidebar-brand-logo {
    width: 28px;
    height: 28px;
    display: block;
    border-radius: 7px;
    box-shadow: 0 0 0 1px rgb(var(--ink) / 0.06);
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.sidebar-brand:hover .sidebar-brand-logo {
    transform: translateY(-1px) scale(1.04);
    box-shadow: 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.35), 0 4px 14px rgb(var(--accent-sky-rgb) / 0.18);
}

.sidebar-brand-name {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-strong);
}

@media (max-width: 720px) {
    .sidebar-brand-name {
        display: none;
    }
}

.sidebar-nav {
    display: flex;
    flex-direction: row;
    gap: 24px;
    align-items: center;
    margin-left: auto;
    margin-right: auto;
}

.sidebar-nav a {
    text-decoration: none;
    color: var(--fg-muted);
    font-weight: 500;
    font-size: 14px;
    padding: 6px 0;
    border-bottom: 2px solid transparent;
    transition: color 0.2s ease, border-color 0.2s ease;
}

.sidebar-nav a:hover {
    color: var(--fg);
}

.sidebar-brand:focus-visible,
.sidebar-nav a:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 4px;
    border-radius: 4px;
}

/* Small screens: one scrollable row between the logo and the settings button, never wrapping */
@media (max-width: 900px) {
    .sidebar-nav {
        gap: 18px;
        margin: 0 52px 0 64px;
        padding: 0 12px;
        overflow-x: auto;
        scrollbar-width: none;
        -webkit-mask-image: linear-gradient(90deg, transparent, #000 12px, #000 calc(100% - 12px), transparent);
        mask-image: linear-gradient(90deg, transparent, #000 12px, #000 calc(100% - 12px), transparent);
    }

    .sidebar-nav::-webkit-scrollbar {
        display: none;
    }

    .sidebar-nav a {
        flex: none;
        white-space: nowrap;
    }
}

/* Phones: the scrolling row clips labels, so swap it for "current page + menu" */
.nav-compact {
    display: none;
}

@media (max-width: 480px) {
    .sidebar-nav {
        display: none;
    }

    .nav-compact {
        display: block;
        position: relative;
        margin: 0 auto;
    }
}

.nav-compact-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 34px;
    max-width: calc(100vw - 150px);
    padding: 0 12px;
    border: 1px solid var(--line-3);
    border-radius: 9px;
    background: transparent;
    color: var(--text-strong);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
}

.nav-compact-btn:hover {
    background: rgb(var(--ink) / 0.06);
}

.nav-compact-btn:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
}

.nav-compact-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.nav-compact-chevron {
    flex: none;
    color: var(--fg-muted);
    transition: transform 0.2s var(--ease-out);
}

.nav-compact-chevron.open {
    transform: rotate(180deg);
}

.nav-compact-list {
    position: absolute;
    top: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--z-dropdown);
    display: flex;
    flex-direction: column;
    min-width: 200px;
    padding: 4px;
    background: var(--surface-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: 0 8px 24px rgb(var(--shade) / 0.22);
}

.nav-compact-list a {
    display: block;
    padding: 10px 12px;
    border-radius: 6px;
    color: var(--fg-muted);
    font-size: 14px;
    font-weight: 500;
    text-decoration: none;
}

.nav-compact-list a:hover {
    background: rgb(var(--ink) / 0.06);
    color: var(--fg);
}

.nav-compact-list a.router-link-active {
    color: var(--text-strong);
    background: rgb(var(--ink) / 0.08);
    box-shadow: inset 2px 0 0 var(--accent);
}

.nav-compact-list a:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
    .nav-compact-chevron { transition: none; }
}

/* Active page: solid text plus a 2px accent underline (aria-current is set by the router) */
.sidebar-nav a.router-link-active {
    color: var(--text-strong);
    border-bottom-color: var(--accent);
}

:root[data-theme="light"] .sidebar {
    border-bottom-color: var(--line-4);
}

.settings-nav-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 12px;
  border-radius: 9px;
  color: var(--fg-muted);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.2s ease, background-color 0.2s ease;
}

.settings-nav-btn:hover {
  color: var(--fg);
  background: rgb(var(--ink) / 0.06);
}

.settings-nav-btn.router-link-active {
  color: var(--text-strong);
  background: rgb(var(--ink) / 0.08);
}

.settings-nav-btn.router-link-active svg {
  color: var(--accent);
}

.settings-nav-btn:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

@media (max-width: 900px) {
  .settings-nav-text {
    display: none;
  }

  .settings-nav-btn {
    padding: 0 8px;
  }
}
</style>
