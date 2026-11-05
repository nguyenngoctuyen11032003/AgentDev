<template>
  <BaseDialog :model-value="isVisible" :title="$t('settings.title')" width="640px" @close="close">
    <GeneralSettings :config="localConfig" @change="(key, value) => (localConfig[key] = value)" />
    <a class="more-link" href="/settings" target="_blank" rel="noopener">
      {{ $t('settings.open_page') }}
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
    </a>
    <template #footer>
      <button class="btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
      <button class="btn primary" type="button" @click="save">{{ $t('common.save') }}</button>
    </template>
  </BaseDialog>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { configStore, applyTheme } from '@/stores/configStore.js'
import { setLocale } from '@/i18n'
import BaseDialog from '@/components/common/BaseDialog.vue'
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

.more-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
