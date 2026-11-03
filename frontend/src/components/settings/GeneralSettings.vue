<template>
  <div class="general-settings">
    <!-- Appearance -->
    <section class="group" aria-labelledby="gs-appearance">
      <h3 id="gs-appearance" class="group-title">{{ $t('settings.section_appearance') }}</h3>
      <div class="row stacked">
        <div class="row-text">
          <span id="gs-theme-label" class="row-label">{{ $t('settings.theme') }}</span>
          <span class="row-desc">{{ $t('settings.theme_desc') }}</span>
        </div>
        <div class="theme-grid" role="radiogroup" aria-labelledby="gs-theme-label">
          <button
            v-for="opt in themeOptions"
            :key="opt.value"
            type="button"
            role="radio"
            class="theme-card"
            :class="[`is-${opt.value}`, { active: config.THEME === opt.value }]"
            :aria-checked="config.THEME === opt.value"
            @click="emit('change', 'THEME', opt.value)"
          >
            <span class="theme-preview" aria-hidden="true">
              <span class="tp-bar"></span>
              <span class="tp-line"></span>
              <span class="tp-line short"></span>
            </span>
            <span class="theme-name">
              <span class="theme-icon" aria-hidden="true" v-html="opt.icon"></span>
              {{ $t(opt.label) }}
            </span>
          </button>
        </div>
      </div>

      <div class="row">
        <div class="row-text">
          <label class="row-label" for="gs-language">{{ $t('settings.language') }}</label>
          <span class="row-desc">{{ $t('settings.language_desc') }}</span>
        </div>
        <span class="select-wrap">
          <select id="gs-language" :value="config.LANGUAGE" @change="emit('change', 'LANGUAGE', $event.target.value)">
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
            <option value="zh">简体中文</option>
          </select>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </span>
      </div>
    </section>

    <!-- Behaviour -->
    <section class="group" aria-labelledby="gs-behaviour">
      <h3 id="gs-behaviour" class="group-title">{{ $t('settings.section_behaviour') }}</h3>
      <div v-for="item in toggles" :key="item.key" class="row">
        <div class="row-text">
          <span :id="`gs-${item.key}`" class="row-label">{{ $t(item.label) }}</span>
          <span class="row-desc">{{ $t(item.desc) }}</span>
        </div>
        <button
          type="button"
          role="switch"
          class="switch"
          :aria-checked="!!config[item.key]"
          :aria-labelledby="`gs-${item.key}`"
          @click="emit('change', item.key, !config[item.key])"
        >
          <span class="switch-thumb" aria-hidden="true"></span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
// Presentational: the parent owns the values (live store on the Settings page,
// a draft copy in the Settings modal) and applies each `change(key, value)`.
defineProps({
  config: { type: Object, required: true }
})
const emit = defineEmits(['change'])

const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
const ICON_MONITOR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>'

const themeOptions = [
  { value: 'dark', label: 'settings.theme_dark', icon: ICON_MOON },
  { value: 'light', label: 'settings.theme_light', icon: ICON_SUN },
  { value: 'system', label: 'settings.theme_system', icon: ICON_MONITOR }
]

const toggles = [
  { key: 'ENABLE_HELP_TOOLTIPS', label: 'settings.enable_help_tooltips', desc: 'settings.enable_help_tooltips_desc' },
  { key: 'AUTO_SHOW_ADVANCED', label: 'settings.auto_show_advanced', desc: 'settings.auto_show_advanced_desc' },
  { key: 'AUTO_EXPAND_MESSAGES', label: 'settings.auto_expand_messages', desc: 'settings.auto_expand_messages_desc' }
]
</script>

<style scoped>
.general-settings {
  --line: rgb(var(--ink) / 0.09);
  --muted: var(--text-muted-4);
  display: flex;
  flex-direction: column;
  gap: 28px;
  font-family: 'Inter', system-ui, sans-serif;
}

.group {
  border-radius: 14px;
  background: var(--surface-1);
  box-shadow: inset 0 0 0 1px var(--line);
}

.group-title {
  margin: 0;
  padding: 16px 20px 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 20px;
}

.row + .row {
  border-top: 1px solid var(--line);
}

.row.stacked {
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
}

.row-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.row-label {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-1);
}

.row-desc {
  font-size: 13px;
  line-height: 1.55;
  color: var(--muted);
}

/* ---- theme cards ---- */
.theme-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.theme-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--line);
  color: var(--text-1);
  font: inherit;
  cursor: pointer;
  transition: box-shadow 0.15s ease;
}

.theme-card:hover {
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.2);
}

.theme-card.active {
  box-shadow: inset 0 0 0 2px var(--accent-sky);
}

.theme-preview {
  --tp-bg: #17191d;
  --tp-fg: #2b2f36;
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 64px;
  padding: 10px;
  box-sizing: border-box;
  border-radius: 8px;
  background: var(--tp-bg);
}

.theme-card.is-light .theme-preview { --tp-bg: #f3f5f9; --tp-fg: #d9dfe8; }
.theme-card.is-system .theme-preview {
  background: linear-gradient(110deg, #17191d 0 50%, #f3f5f9 50% 100%);
  --tp-fg: rgb(128 140 160 / 0.6);
}

.tp-bar { height: 8px; width: 46%; border-radius: 4px; background: var(--accent-sky); opacity: 0.85; }
.tp-line { height: 6px; width: 86%; border-radius: 3px; background: var(--tp-fg); }
.tp-line.short { width: 60%; }

.theme-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 2px;
  font-size: 13.5px;
  font-weight: 600;
}

.theme-icon { display: inline-flex; width: 15px; height: 15px; color: var(--muted); }
.theme-icon :deep(svg) { width: 15px; height: 15px; }
.theme-card.active .theme-icon { color: var(--accent-sky); }

/* ---- select ---- */
.select-wrap {
  position: relative;
  flex: none;
  color: var(--muted);
}

.select-wrap select {
  min-width: 180px;
  height: 40px;
  padding: 0 38px 0 12px;
  border: 0;
  border-radius: 10px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--surface-3);
  box-shadow: inset 0 0 0 1px var(--line);
  color: var(--text-1);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.select-wrap svg {
  position: absolute;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  pointer-events: none;
}

/* ---- switch ---- */
.switch {
  position: relative;
  flex: none;
  width: 44px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgb(var(--ink) / 0.18);
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.switch[aria-checked='true'] {
  background: var(--accent-sky);
}

.switch-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.3);
  transition: transform 0.18s ease;
}

.switch[aria-checked='true'] .switch-thumb {
  transform: translateX(18px);
}

.theme-card:focus-visible,
.switch:focus-visible,
.select-wrap select:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

@media (max-width: 600px) {
  .row { flex-direction: column; align-items: stretch; gap: 12px; }
  .row .switch { align-self: flex-start; }
  .select-wrap select { width: 100%; }
  .theme-grid { gap: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .switch, .switch-thumb, .theme-card { transition: none; }
}
</style>
