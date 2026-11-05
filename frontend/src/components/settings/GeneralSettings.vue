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
        <div class="lang-select">
          <BaseSelect
            id="gs-language"
            :model-value="config.LANGUAGE"
            :options="languages"
            @update:model-value="emit('change', 'LANGUAGE', $event)"
          />
        </div>
      </div>
    </section>

    <!-- Behaviour -->
    <section class="group" aria-labelledby="gs-behaviour">
      <h3 id="gs-behaviour" class="group-title">{{ $t('settings.section_behaviour') }}</h3>
      <div v-for="item in toggles" :key="item.key" class="row">
        <div class="row-text">
          <span class="row-label">{{ $t(item.label) }}</span>
          <span class="row-desc">{{ $t(item.desc) }}</span>
        </div>
        <BaseSwitch
          :model-value="!!config[item.key]"
          :aria-label="$t(item.label)"
          @update:model-value="emit('change', item.key, $event)"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import BaseSelect from '@/components/ui/BaseSelect.vue'
import BaseSwitch from '@/components/ui/BaseSwitch.vue'

// Presentational: the parent owns the values (live store on the Settings page,
// a draft copy in the Settings modal) and applies each `change(key, value)`.
defineProps({
  config: { type: Object, required: true }
})
const emit = defineEmits(['change'])

const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
const ICON_MONITOR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>'

const languages = [
  { value: 'vi', label: 'Tiếng Việt' },
  { value: 'en', label: 'English' },
  { value: 'zh', label: '简体中文' }
]

const themeOptions = [
  { value: 'dark', label: 'settings.theme_dark', icon: ICON_MOON },
  { value: 'light', label: 'settings.theme_light', icon: ICON_SUN },
  { value: 'system', label: 'settings.theme_system', icon: ICON_MONITOR }
]

const toggles = [
  { key: 'ENABLE_HELP_TOOLTIPS', label: 'settings.enable_help_tooltips', desc: 'settings.enable_help_tooltips_desc' },
  { key: 'AUTO_SHOW_ADVANCED', label: 'settings.auto_show_advanced', desc: 'settings.auto_show_advanced_desc' }
]
</script>

<style scoped>
.general-settings {
  --line: var(--border);
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.group {
  border-radius: 14px;
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}

.group-title {
  margin: 0;
  padding: 16px 20px 4px;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg-muted);
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
  color: var(--fg);
}

.row-desc {
  font-size: 13px;
  line-height: 1.55;
  color: var(--fg-muted);
}

.lang-select { flex: none; min-width: 180px; }

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
  color: var(--fg);
  font: inherit;
  cursor: pointer;
  transition: box-shadow 0.15s var(--ease-out);
}

.theme-card:hover {
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

.theme-card.active {
  box-shadow: inset 0 0 0 2px var(--accent);
}

/* Previews depict each theme, so they keep fixed colours on purpose */
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

.tp-bar { height: 8px; width: 46%; border-radius: 4px; background: var(--accent); opacity: 0.85; }
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

.theme-icon { display: inline-flex; width: 15px; height: 15px; color: var(--fg-muted); }
.theme-icon :deep(svg) { width: 15px; height: 15px; }
.theme-card.active .theme-icon { color: var(--fg); }

.theme-card:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

@media (max-width: 600px) {
  .row { flex-direction: column; align-items: stretch; gap: 12px; }
  .row .switch-row { align-self: flex-start; }
  .lang-select { min-width: 0; }
  .theme-grid { gap: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .theme-card { transition: none; }
}
</style>
