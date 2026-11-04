<template>
  <div class="settings-view">
    <div class="settings-layout">
      <aside class="settings-nav" :aria-label="$t('settings.title')">
        <p class="nav-title">{{ $t('settings.title') }}</p>
        <nav>
          <router-link v-for="item in sections" :key="item.to" :to="item.to" class="nav-item">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="item.icon"></svg>
            <span class="nav-text">
              <span class="nav-label">{{ $t(item.label) }}</span>
              <span class="nav-desc">{{ $t(item.desc) }}</span>
            </span>
          </router-link>
        </nav>
      </aside>

      <main class="settings-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'SettingsView' })

const sections = [
  {
    to: '/settings/general',
    label: 'settings.nav_general',
    desc: 'settings.nav_general_desc',
    icon: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>'
  },
  {
    to: '/settings/connections',
    label: 'settings.nav_connections',
    desc: 'settings.nav_connections_desc',
    icon: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
  },
  {
    to: '/settings/skills',
    label: 'settings.nav_skills',
    desc: 'settings.nav_skills_desc',
    icon: '<path d="M4 19.5V5a2 2 0 0 1 2-2h13v16H6.5A2.5 2.5 0 0 0 4 21.5"/><path d="M9 7h6M9 11h4"/>'
  }
]
</script>

<style scoped>
.settings-view {
  box-sizing: border-box;
  width: 100%;
  min-height: calc(calc(100 * var(--vh)) - 55px);
  background: var(--bg);
  font-family: 'Inter', system-ui, sans-serif;
  color: var(--fg);
}

.settings-layout {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 48px;
  box-sizing: border-box;
  max-width: 1240px;
  margin: 0 auto;
  padding: 48px 32px 80px;
}

/* ---- side navigation ---- */
.settings-nav {
  position: sticky;
  top: 24px;
  align-self: start;
}

.nav-title {
  margin: 0 0 14px 12px;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg-muted);
}

.settings-nav nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  color: var(--fg-muted);
  text-decoration: none;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-item svg {
  flex: none;
  margin-top: 1px;
}

.nav-item:hover {
  color: var(--fg);
  background: rgb(var(--ink) / 0.05);
}

.nav-item.router-link-active {
  color: var(--text-strong);
  background: rgb(var(--ink) / 0.07);
  box-shadow: inset 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.4);
}

.nav-item.router-link-active svg {
  color: var(--accent);
}

.nav-item:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.nav-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.nav-label {
  font-size: 14px;
  font-weight: 600;
}

.nav-desc {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--fg-muted);
}

/* ---- content: the embedded pages drop their own page frame ---- */
.settings-content {
  min-width: 0;
}

.settings-content :deep(.connections-view),
.settings-content :deep(.skills-view) {
  max-width: none;
  margin: 0;
  padding: 0;
}

@media (max-width: 900px) {
  .settings-layout {
    grid-template-columns: 1fr;
    gap: 24px;
    padding: 28px 16px 64px;
  }

  .settings-nav {
    position: static;
  }

  .nav-title {
    display: none;
  }

  .settings-nav nav {
    flex-direction: row;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .nav-item {
    flex: none;
    align-items: center;
    padding: 8px 14px;
    box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.09);
  }

  .nav-item.router-link-active {
    box-shadow: inset 0 0 0 1px var(--accent);
  }

  .nav-desc {
    display: none;
  }
}
</style>
