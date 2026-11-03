<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Sidebar from '@/components/common/Sidebar.vue'
import ToastHost from '@/components/common/ToastHost.vue'
import ConfirmHost from '@/components/common/ConfirmHost.vue'

const route = useRoute()

// Hide the sidebar on LaunchView, BatchRunView and WorkflowWorkbench
const showSidebar = computed(() => route.path !== '/launch' && route.path !== '/batch-run')
const isHomeRoute = computed(() => route.path === '/')

// Keep <html lang> in sync with the UI language (accessibility, spell-check, hyphenation)
const { locale } = useI18n()
watch(locale, (value) => {
  document.documentElement.lang = value || 'vi'
}, { immediate: true })
</script>

<template>
  <div class="app-container" :class="{ 'home-route': isHomeRoute }">
    <Sidebar v-if="showSidebar" />
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <!--
          Short, enter-only fade (opacity on the compositor) so route switches feel
          settled without delaying the new page. Launch/Batch views render multiple
          root nodes and open in their own tab, so they are mounted directly.
        -->
        <Transition v-if="showSidebar" name="route-fade">
          <component :is="Component" />
        </Transition>
        <component :is="Component" v-else />
      </router-view>
    </main>
    <ToastHost />
    <ConfirmHost />
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-container.home-route {
  height: 100dvh;
  min-height: 100dvh;
  overflow: hidden;
}

.main-content {
  flex: 1;
  min-height: 0;
  background-color: var(--bg-base);
}

.home-route .main-content {
  overflow: hidden;
  background-color: var(--bg-base);
}

/* Route transition: enter-only, opacity only (no leave delay, no layout work) */
.route-fade-enter-active {
  transition: opacity 0.15s ease-out;
}

.route-fade-enter-from {
  opacity: 0;
}
</style>
