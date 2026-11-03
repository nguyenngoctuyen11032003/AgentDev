<script setup>
import { toasts, dismissToast, runToastAction } from '@/utils/toast'

const ICONS = { success: '✓', info: 'i', warning: '!', error: '✕' }
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="`toast--${item.type}`"
        :role="item.type === 'error' ? 'alert' : 'status'"
      >
        <span class="toast-icon" aria-hidden="true">{{ ICONS[item.type] }}</span>
        <div class="toast-body">
          <p class="toast-title">{{ item.title }}</p>
          <p v-if="item.detail" class="toast-detail">{{ item.detail }}</p>
          <ul v-if="item.items?.length" class="toast-items">
            <li v-for="(line, i) in item.items" :key="`${i}-${line}`">{{ line }}</li>
          </ul>
          <button
            v-if="item.action"
            type="button"
            class="toast-action"
            @click="runToastAction(item.id)"
          >
            {{ item.action.label }}
          </button>
        </div>
        <button
          type="button"
          class="toast-close"
          :aria-label="$t('common.close')"
          :title="$t('common.close')"
          @click="dismissToast(item.id)"
        >
          ×
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(380px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  --toast-accent: var(--accent-sky);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 12px 12px 14px;
  background: var(--surface-1);
  border: 1px solid var(--line-2);
  border-left: 3px solid var(--toast-accent);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(var(--shade) / 0.45);
  color: var(--text-1);
  pointer-events: auto;
}

.toast--success { --toast-accent: var(--accent-mint); }
.toast--warning { --toast-accent: var(--warn-soft-1); }
.toast--error { --toast-accent: var(--danger); }

.toast-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: 50%;
  border: 1.5px solid var(--toast-accent);
  color: var(--toast-accent);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.toast-body {
  flex: 1;
  min-width: 0;
}

.toast-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-strong);
  overflow-wrap: anywhere;
}

.toast-detail {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted-6);
  overflow-wrap: anywhere;
}

.toast-items {
  margin: 6px 0 0;
  padding: 0 0 0 16px;
  max-height: 96px;
  overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted-6);
  overflow-wrap: anywhere;
}

.toast-action {
  margin-top: 8px;
  padding: 4px 10px;
  border: 1px solid var(--toast-accent);
  border-radius: 6px;
  background: none;
  color: var(--text-strong);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.toast-action:hover {
  background: rgb(var(--ink) / 0.08);
}

.toast-action:focus-visible {
  outline: 2px solid var(--toast-accent);
  outline-offset: 2px;
}

.toast-close {
  flex: none;
  width: 24px;
  height: 24px;
  margin: -2px -2px 0 0;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--text-muted-3);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.toast-close:hover {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-strong);
}

.toast-close:focus-visible {
  outline: 2px solid var(--toast-accent);
  outline-offset: 1px;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    transition: opacity 0.12s linear;
  }

  .toast-enter-from,
  .toast-leave-to {
    transform: none;
  }
}
</style>
