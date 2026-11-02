<template>
  <Transition name="modal-fade">
    <div v-if="isVisible" class="modal-overlay" @click.self="close">
      <div class="modal-content settings-modal">
        <div class="modal-header">
          <h3>{{ $t('settings.title') }}</h3>
          <button class="close-button" :aria-label="$t('common.close')" :title="$t('common.close')" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div class="settings-item">
            <span class="setting-label" id="settings-theme-label">{{ $t('settings.theme') }}</span>
            <div class="theme-switch" role="radiogroup" aria-labelledby="settings-theme-label">
              <button
                v-for="opt in themeOptions"
                :key="opt.value"
                type="button"
                class="theme-option"
                :class="{ active: localConfig.THEME === opt.value }"
                role="radio"
                :aria-checked="localConfig.THEME === opt.value"
                @click="localConfig.THEME = opt.value"
              >
                <span class="theme-option-icon" v-html="opt.icon"></span>
                <span class="theme-option-text">{{ $t(opt.label) }}</span>
              </button>
            </div>
            <p class="setting-desc no-indent">{{ $t('settings.theme_desc') }}</p>
          </div>
          <div class="settings-item">
            <label class="checkbox-label">
              <input type="checkbox" v-model="localConfig.AUTO_SHOW_ADVANCED">
              {{ $t('settings.auto_show_advanced') }}
            </label>
            <p class="setting-desc">{{ $t('settings.auto_show_advanced_desc') }}</p>
          </div>
          <div class="settings-item">
            <label class="checkbox-label">
              <input type="checkbox" v-model="localConfig.AUTO_EXPAND_MESSAGES">
              {{ $t('settings.auto_expand_messages') }}
            </label>
            <p class="setting-desc">{{ $t('settings.auto_expand_messages_desc') }}</p>
          </div>
          <div class="settings-item">
            <label class="checkbox-label">
              <input type="checkbox" v-model="localConfig.ENABLE_HELP_TOOLTIPS">
              {{ $t('settings.enable_help_tooltips') }}
            </label>
            <p class="setting-desc">{{ $t('settings.enable_help_tooltips_desc') }}</p>
          </div>
          <div class="settings-item">
            <label class="setting-label" for="settings-language-select">{{ $t('settings.language') }}</label>
            <select id="settings-language-select" v-model="localConfig.LANGUAGE" class="language-select">
              <option value="vi">Tiếng Việt</option>
              <option value="en">English</option>
              <option value="zh">简体中文</option>
            </select>
            <p class="setting-desc">{{ $t('settings.language_desc') }}</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="cancel-button" @click="close">{{ $t('common.cancel') }}</button>
          <button class="confirm-button" @click="save">{{ $t('common.save') }}</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { configStore, applyTheme } from '@/stores/configStore.js'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()

const props = defineProps({
  isVisible: {
    type: Boolean,
    required: true
  }
})

const localConfig = reactive({
  AUTO_SHOW_ADVANCED: false,
  AUTO_EXPAND_MESSAGES: false,
  ENABLE_HELP_TOOLTIPS: true,
  LANGUAGE: 'vi',
  THEME: 'dark'
})

const ICON_MOON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
const ICON_SUN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
const ICON_MONITOR = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>'

const themeOptions = [
  { value: 'dark', label: 'settings.theme_dark', icon: ICON_MOON },
  { value: 'light', label: 'settings.theme_light', icon: ICON_SUN },
  { value: 'system', label: 'settings.theme_system', icon: ICON_MONITOR }
]

watch(() => props.isVisible, (newVal) => {
  if (newVal) {
    // Sync local state with global store when modal opens
    Object.assign(localConfig, configStore)
  }
})

// Live preview of the theme while the modal is open; reverted on cancel.
watch(() => localConfig.THEME, (t) => {
  if (props.isVisible) applyTheme(t)
})

const emit = defineEmits(['update:isVisible', 'close'])

const close = () => {
  // Undo any un-saved theme preview
  applyTheme(configStore.THEME)
  emit('update:isVisible', false)
  emit('close')
}

const save = () => {
  // Commit local changes to global store
  Object.assign(configStore, localConfig)
  locale.value = localConfig.LANGUAGE
  close()
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgb(var(--shade) / 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(2px);
}

.modal-content.settings-modal {
  width: 500px !important;
  max-width: 90vw;
  background: var(--surface-1);
  border-radius: 8px;
  border: 1px solid var(--line-1);
  color: var(--text-strong);
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 20px rgb(var(--shade) / 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line-1);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
}

.close-button {
  background: none;
  border: none;
  color: var(--text-muted-3);
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-button:hover {
  color: var(--text-strong);
}

.modal-body {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
}

.settings-item {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid rgb(var(--ink) / 0.08);
}

.settings-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.setting-label {
  display: block;
  color: var(--text-2);
  font-size: 15px;
  margin-bottom: 8px;
}

.language-select {
  width: 100%;
  padding: 8px;
  background: var(--surface-4);
  border: 1px solid var(--line-3);
  color: var(--text-strong);
  border-radius: 4px;
  margin-bottom: 6px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-2);
  font-size: 15px;
  cursor: pointer;
  user-select: none;
  margin-bottom: 6px;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #4facfe;
  cursor: pointer;
}

.setting-desc {
  margin-left: 26px;
  color: var(--text-muted-8);
  font-size: 13px;
  line-height: 1.4;
  margin-top: 0;
}

.setting-desc.no-indent {
  margin-left: 0;
  margin-top: 8px;
}

/* Theme segmented control */
.theme-switch {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: rgb(var(--ink) / 0.06);
  border: 1px solid rgb(var(--ink) / 0.08);
}

.theme-option {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 9px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted-6);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.theme-option:hover {
  color: var(--text-1);
  background: rgb(var(--ink) / 0.05);
}

.theme-option.active {
  color: var(--text-strong);
  background: var(--surface-4);
  box-shadow: 0 1px 2px rgb(var(--shade) / 0.25), 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.35);
}

.theme-option.active .theme-option-icon {
  color: var(--accent-sky);
}

.theme-option:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 1px;
}

.theme-option-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.theme-option-icon :deep(svg) {
  width: 16px;
  height: 16px;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--line-1);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.confirm-button {
  background: #4facfe;
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.confirm-button:hover {
  background: #3a9cfa;
}

.cancel-button {
  background: transparent;
  color: var(--text-soft-1);
  border: 1px solid var(--line-3);
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.cancel-button:hover {
  background: rgb(var(--ink) / 0.05);
  color: var(--text-strong);
  border-color: var(--neutral-1);
}

/* Transitions: overlay fades, panel settles with a subtle scale (opacity +
   transform only, so both run on the compositor). The full-screen backdrop
   blur is suspended while animating so it is not re-blurred every frame. */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
  backdrop-filter: none;
}

.modal-fade-enter-active .modal-content,
.modal-fade-leave-active .modal-content {
  transition: transform 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal-content,
.modal-fade-leave-to .modal-content {
  transform: scale(0.98);
}
</style>