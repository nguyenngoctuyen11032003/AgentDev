<template>
  <Teleport to="body">
    <Transition name="confirm">
      <div v-if="request" class="confirm-backdrop" @mousedown.self="answer(false)">
        <section
          class="confirm"
          :class="`is-${request.tone}`"
          role="alertdialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="request.message ? descId : undefined"
          @keydown.esc.stop.prevent="answer(false)"
          @keydown.tab="trapFocus"
        >
          <span class="confirm-icon" aria-hidden="true">
            <svg v-if="request.tone === 'danger'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" /><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01" /></svg>
          </span>

          <div class="confirm-text">
            <h2 :id="titleId">{{ request.title }}</h2>
            <p v-if="request.message" :id="descId">{{ request.message }}</p>
          </div>

          <footer class="confirm-foot">
            <button ref="cancelEl" type="button" class="btn secondary" @click="answer(false)">
              {{ request.cancelText || t('confirm.cancel') }}
            </button>
            <button ref="okEl" type="button" class="btn" :class="request.tone === 'danger' ? 'danger' : 'primary'" @click="answer(true)">
              {{ request.confirmText || t('confirm.ok') }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { pendingConfirm } from '@/utils/confirm'

const { t } = useI18n()
const request = pendingConfirm
const titleId = 'confirm-host-title'
const descId = 'confirm-host-desc'
const cancelEl = ref(null)
const okEl = ref(null)
let returnFocus = null

function answer(value) {
  request.value?.resolve(value)
}

// Keep Tab cycling between the two buttons while the dialog is open.
function trapFocus(event) {
  const first = cancelEl.value
  const last = okEl.value
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(request, async (current, previous) => {
  if (current && !previous) returnFocus = document.activeElement
  if (current) {
    await nextTick()
    // Destructive actions start on Cancel so Enter never deletes by accident.
    ;(current.tone === 'danger' ? cancelEl.value : okEl.value)?.focus()
  } else if (returnFocus instanceof HTMLElement && document.contains(returnFocus)) {
    returnFocus.focus()
    returnFocus = null
  }
})
</script>

<style scoped>
.confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: var(--backdrop-color);
}

.confirm {
  --tone: var(--accent);
  box-sizing: border-box;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 16px;
  width: min(440px, 100%);
  padding: 22px 22px 18px;
  border-radius: 14px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--fg);
  box-shadow: 0 24px 64px -20px rgb(0 0 0 / 0.7);
}

.confirm.is-danger {
  --tone: var(--danger);
}

.confirm-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--tone) 28%, transparent);
}

.confirm-text {
  min-width: 0;
  padding-top: 2px;
}

.confirm-text h2 {
  margin: 0;
  font-size: 16.5px;
  font-weight: 650;
  line-height: 1.35;
  letter-spacing: -0.01em;
}

.confirm-text p {
  margin: 6px 0 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--fg-muted);
  overflow-wrap: anywhere;
}

.confirm-foot {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

/* buttons: global .btn (ui.css) */
.confirm-foot .btn {
  min-width: 84px;
}

.confirm-enter-active,
.confirm-leave-active {
  transition: opacity 0.16s ease;
}

.confirm-enter-active .confirm,
.confirm-leave-active .confirm {
  transition: transform 0.2s var(--ease-out);
}

.confirm-enter-from,
.confirm-leave-to {
  opacity: 0;
}

.confirm-enter-from .confirm,
.confirm-leave-to .confirm {
  transform: translateY(8px) scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .confirm-enter-active,
  .confirm-leave-active,
  .confirm-enter-active .confirm,
  .confirm-leave-active .confirm {
    transition: none;
  }
}

@media (max-width: 420px) {
  .confirm { grid-template-columns: 1fr; padding: 20px 18px 16px; }
  .confirm-foot .btn { flex: 1; }
}
</style>
