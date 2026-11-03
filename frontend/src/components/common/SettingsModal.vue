<template>
  <Transition name="modal-fade">
    <div v-if="isVisible" class="modal-overlay" @click.self="close">
      <div class="modal-content settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
        <div class="modal-header">
          <h3 id="settings-modal-title">{{ $t('settings.title') }}</h3>
          <button class="close-button" :aria-label="$t('common.close')" :title="$t('common.close')" @click="close">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <div class="modal-body">
          <GeneralSettings :config="localConfig" @change="(key, value) => (localConfig[key] = value)" />
          <a class="more-link" href="/settings" target="_blank" rel="noopener">
            {{ $t('settings.open_page') }}
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
          </a>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="close">{{ $t('common.cancel') }}</button>
          <button class="btn primary" @click="save">{{ $t('common.save') }}</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { configStore, applyTheme } from '@/stores/configStore.js'
import { setLocale } from '@/i18n'
import GeneralSettings from '@/components/settings/GeneralSettings.vue'

const props = defineProps({
  isVisible: {
    type: Boolean,
    required: true
  }
})

// Draft copy: nothing is saved until "Save"; the theme is previewed live and reverted on cancel.
const localConfig = reactive({
  AUTO_SHOW_ADVANCED: false,
  AUTO_EXPAND_MESSAGES: false,
  ENABLE_HELP_TOOLTIPS: true,
  LANGUAGE: 'vi',
  THEME: 'dark'
})

watch(() => props.isVisible, (newVal) => {
  if (newVal) Object.assign(localConfig, configStore)
})

watch(() => localConfig.THEME, (t) => {
  if (props.isVisible) applyTheme(t)
})

const emit = defineEmits(['update:isVisible', 'close'])

const close = () => {
  applyTheme(configStore.THEME)
  emit('update:isVisible', false)
  emit('close')
}

const save = () => {
  Object.assign(configStore, localConfig)
  setLocale(localConfig.LANGUAGE).catch((error) => console.error('Failed to switch language:', error))
  close()
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: var(--backdrop-color);
}

.modal-content.settings-modal {
  display: flex;
  flex-direction: column;
  width: 640px;
  max-width: 100%;
  max-height: calc(100vh - 32px);
  border-radius: 16px;
  background: var(--bg-base);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.1), 0 24px 60px rgb(var(--shade) / 0.5);
  color: var(--text-strong);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid rgb(var(--ink) / 0.09);
}

.modal-header h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.close-button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
}

.close-button:hover {
  color: var(--text-strong);
  background: rgb(var(--ink) / 0.07);
}

.modal-body {
  flex: 1;
  padding: 20px 22px;
  overflow-y: auto;
}

.more-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
}

.more-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 22px;
  border-top: 1px solid rgb(var(--ink) / 0.09);
}

.close-button:focus-visible,
.more-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Opacity + transform only, so the transition stays on the compositor */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
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
