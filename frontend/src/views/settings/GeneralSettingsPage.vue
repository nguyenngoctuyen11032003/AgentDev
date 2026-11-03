<template>
  <div class="general-page">
    <header class="page-head">
      <p class="kicker">{{ $t('settings.nav_general') }}</p>
      <h1 class="title">{{ $t('settings.general_title') }}</h1>
      <p class="sub">{{ $t('settings.general_sub') }}</p>
    </header>
    <GeneralSettings :config="configStore" @change="apply" />
  </div>
</template>

<script setup>
import GeneralSettings from '@/components/settings/GeneralSettings.vue'
import { configStore } from '@/stores/configStore.js'
import { setLocale } from '@/i18n'

// On the page every change applies (and is saved) immediately: the store persists
// itself and re-applies the theme; only the language needs its chunk loaded.
function apply(key, value) {
  configStore[key] = value
  if (key === 'LANGUAGE') setLocale(value).catch((error) => console.error('Failed to switch language:', error))
}
</script>

<style scoped>
.general-page {
  box-sizing: border-box;
  max-width: 760px;
  font-family: 'Inter', system-ui, sans-serif;
}

.page-head {
  margin-bottom: 28px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
}

.title {
  margin: 0 0 10px;
  font-size: 32px;
  line-height: 1.15;
  font-weight: 750;
  letter-spacing: -0.03em;
  color: var(--text-strong);
}

.sub {
  margin: 0;
  max-width: 64ch;
  font-size: 15px;
  line-height: 1.65;
  color: var(--fg-muted);
}

@media (max-width: 600px) {
  .title { font-size: 27px; }
}
</style>
