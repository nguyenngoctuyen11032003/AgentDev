<script setup>
import { toasts, dismissToast, runToastAction, pauseToast, resumeToast } from '@/utils/toast'

// Resume only once focus has left the toast (moving between its buttons is not leaving).
const onFocusOut = (event, id) => {
  const el = event.currentTarget
  if (!el.contains(event.relatedTarget) && !el.matches(':hover')) resumeToast(id)
}
const onMouseLeave = (event, id) => {
  if (!event.currentTarget.contains(document.activeElement)) resumeToast(id)
}

const ICONS = { success: '✓', info: 'i', warning: '!', error: '✕' }
</script>

<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="`toast--${item.type}`"
        :role="item.type === 'error' ? 'alert' : 'status'"
        @mouseenter="pauseToast(item.id)"
        @mouseleave="onMouseLeave($event, item.id)"
        @focusin="pauseToast(item.id)"
        @focusout="onFocusOut($event, item.id)"
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
  top: 67px; /* below the 55px sticky header */
  right: 16px;
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(380px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  --toast-accent: var(--accent);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--surface);
  border: 1px solid color-mix(in srgb, var(--toast-accent) 45%, var(--line-2));
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(var(--shade) / 0.45);
  color: var(--fg);
  pointer-events: auto;
}

.toast--success { --toast-accent: var(--accent-mint); }
.toast--warning { --toast-accent: var(--warn); }
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
  font-size: var(--fs-xs);
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
  font-size: var(--fs-xs);
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
  width: 32px;
  height: 32px;
  margin: -6px -6px 0 0;
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
  transition: opacity 0.18s var(--ease-out), transform 0.18s var(--ease-out);
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
