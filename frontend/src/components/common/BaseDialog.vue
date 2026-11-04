<script setup>
/**
 * Accessible modal shell: role=dialog + aria-modal, Esc to close, focus trap,
 * initial focus, focus returned to the trigger, teleported to <body>.
 * Slots: header (replaces the title row), default (body), footer.
 *
 *   <BaseDialog v-model="open" :title="t('x.title')">...</BaseDialog>
 *
 * Initial focus goes to an element marked [data-autofocus] / [autofocus], else the
 * first field in the body, else the close button.
 */
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  // Id of an element inside the dialog that labels it (overrides the built-in title id)
  labelledby: { type: String, default: '' },
  closeOnBackdrop: { type: Boolean, default: true },
  // CSS width of the panel
  width: { type: String, default: '520px' }
})
const emit = defineEmits(['update:modelValue', 'close'])

const { t } = useI18n()
const uid = useId()
const titleId = computed(() => props.labelledby || `dialog-title-${uid}`)
const panelEl = ref(null)
const closeEl = ref(null)
let returnFocus = null

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

function close() {
  emit('update:modelValue', false)
  emit('close')
}

function focusables() {
  return [...(panelEl.value?.querySelectorAll(FOCUSABLE) ?? [])].filter(
    (el) => el.offsetParent !== null || el === document.activeElement
  )
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  if (!items.length) {
    event.preventDefault()
    panelEl.value?.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panelEl.value)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

// Close only when the press started AND ended on the backdrop (selection drags stay open)
let downOnBackdrop = false
function onBackdropDown(event) {
  downOnBackdrop = event.target === event.currentTarget
}
function onBackdropUp(event) {
  if (props.closeOnBackdrop && downOnBackdrop && event.target === event.currentTarget) close()
  downOnBackdrop = false
}

function restoreFocus() {
  if (returnFocus instanceof HTMLElement && document.contains(returnFocus)) returnFocus.focus()
  returnFocus = null
}

watch(
  () => props.modelValue,
  async (open, was) => {
    if (open && !was) {
      returnFocus = document.activeElement
      await nextTick()
      const target =
        panelEl.value?.querySelector('[data-autofocus], [autofocus]') ||
        panelEl.value?.querySelector('.base-dialog-body input, .base-dialog-body select, .base-dialog-body textarea') ||
        closeEl.value
      ;(target || panelEl.value)?.focus()
    } else if (!open && was) {
      restoreFocus()
    }
  },
  { immediate: true, flush: 'post' }
)

onBeforeUnmount(() => {
  if (props.modelValue) restoreFocus()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="base-dialog">
      <div v-if="modelValue" class="base-dialog-backdrop" @mousedown="onBackdropDown" @mouseup="onBackdropUp">
        <section
          ref="panelEl"
          class="base-dialog"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="title || labelledby ? titleId : undefined"
          tabindex="-1"
          :style="{ '--dialog-width': width }"
          @keydown="onKeydown"
        >
          <header class="base-dialog-header">
            <slot name="header">
              <h2 :id="titleId" class="base-dialog-title">{{ title }}</h2>
            </slot>
            <button
              ref="closeEl"
              type="button"
              class="base-dialog-close"
              :aria-label="t('common.close')"
              :title="t('common.close')"
              @click="close"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
            </button>
          </header>
          <div class="base-dialog-body"><slot /></div>
          <footer v-if="$slots.footer" class="base-dialog-footer"><slot name="footer" /></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.base-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: var(--backdrop-color);
}

.base-dialog {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  width: min(var(--dialog-width), 100%);
  max-height: calc(calc(100 * var(--dvh)) - 48px);
  border: 1px solid var(--line-4);
  border-radius: 14px;
  background: var(--surface-1);
  color: var(--text-1);
  box-shadow: 0 24px 64px -20px rgb(var(--shade) / 0.6);
}

.base-dialog:focus {
  outline: none;
}

.base-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 14px 12px 22px;
  border-bottom: 1px solid var(--line-1);
}

.base-dialog-title {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  line-height: 1.35;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}

.base-dialog-close {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin-left: auto;
  padding: 0;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.base-dialog-close:hover {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-strong);
}

.base-dialog-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 22px;
}

.base-dialog-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 22px 16px;
  border-top: 1px solid var(--line-1);
}

.base-dialog-enter-active,
.base-dialog-leave-active {
  transition: opacity 0.16s var(--ease-out);
}

.base-dialog-enter-active .base-dialog,
.base-dialog-leave-active .base-dialog {
  transition: transform 0.2s var(--ease-out);
}

.base-dialog-enter-from,
.base-dialog-leave-to {
  opacity: 0;
}

.base-dialog-enter-from .base-dialog,
.base-dialog-leave-to .base-dialog {
  transform: translateY(8px) scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .base-dialog-enter-active,
  .base-dialog-leave-active,
  .base-dialog-enter-active .base-dialog,
  .base-dialog-leave-active .base-dialog {
    transition: none;
  }
}
</style>
