<template>
    <div class="sidebar" :class="{ 'is-hidden': isHidden }" @mouseenter="isHidden = false">
        <router-link to="/" class="sidebar-brand" aria-label="AgentDev">
            <img src="/media/logo.svg" alt="" class="sidebar-brand-logo" width="28" height="28" />
            <span class="sidebar-brand-name">AgentDev</span>
        </router-link>

        <nav class="sidebar-nav">
            <router-link to="/">{{ $t('nav.home') }}</router-link>
            <router-link to="/tutorial">{{ $t('nav.tutorial') }}</router-link>
            <router-link to="/workflows">{{ $t('nav.workflows') }}</router-link>
            <router-link to="/launch" target="_blank" rel="noopener">{{ $t('nav.launch') }}</router-link>
            <router-link to="/batch-run" target="_blank" rel="noopener">{{ $t('nav.laboratory') }}</router-link>
            <router-link to="/sprites">{{ $t('sprites.gallery.title') }}</router-link>
        </nav>
        <div class="sidebar-actions">
            <button class="settings-nav-btn" @click="showSettingsModal = true" :title="$t('settings.title')" :aria-label="$t('settings.title')">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
            </button>
        </div>
    </div>
    <div class="sidebar-hit-area" v-if="isHidden" @mouseenter="isHidden = false"></div>
    <SettingsModal
      :is-visible="showSettingsModal"
      @update:is-visible="showSettingsModal = $event"
    />
</template>

<script setup>
defineOptions({ name: 'AppSidebar' })
import { RouterLink, useRoute } from 'vue-router'
import { ref, onUnmounted, watch } from 'vue'
import SettingsModal from './SettingsModal.vue'

const showSettingsModal = ref(false)
const isHidden = ref(false)

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
    z-index: 100;
    border-bottom: 1px solid var(--line-5);
    justify-content: center;
    transition: margin-top 0.3s cubic-bezier(0.4, 0, 0.2, 1), transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    margin-top: 0;
    transform: translateY(0);
}

.sidebar.is-hidden {
    margin-top: -55px;
    transform: translateY(-100%);
}

.sidebar-hit-area {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 25px;
    z-index: 99;
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
    font-family: 'Inter', sans-serif;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo));
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
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
    color: var(--text-muted-4);
    font-weight: 500;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    transition: color 0.2s ease;
}

.sidebar-nav a:hover {
    color: var(--text-1);
}

.sidebar-nav a.router-link-active {
    background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
    );
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Light theme: the token gradient starts at #0f9d7a (~3.2:1 on the light bg),
   too faint for 14-16px text. Use a deeper gradient that clears 4.5:1 end to end. */
:root[data-theme="light"] .sidebar-brand-name,
:root[data-theme="light"] .sidebar-nav a.router-link-active {
    background: linear-gradient(90deg, #047857, #0369a1, #4338ca);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

:root[data-theme="light"] .sidebar {
    border-bottom-color: var(--line-4);
}

.settings-nav-btn {
  background: transparent;
  border: none;
  color: var(--text-muted-4);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
}

.settings-nav-btn:hover {
  color: var(--text-1);
}
</style>
