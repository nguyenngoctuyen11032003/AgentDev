<template>
  <div ref="rootRef" class="mode-picker" @keydown.esc.stop="close(true)">
    <button
      ref="triggerRef"
      type="button"
      class="mode-trigger"
      :class="`is-${current.key}`"
      aria-haspopup="menu"
      :aria-expanded="open"
      :title="$t('launch.mode.trigger_title', { mode: current.label })"
      @click="toggle"
    >
      <span class="mode-icon" aria-hidden="true" v-html="current.icon"></span>
      <span class="mode-trigger-label">{{ current.label }}</span>
    </button>
    <Teleport to="body">
    <Transition name="mode-menu">
      <div
        v-if="open"
        ref="menuRef"
        class="mode-menu"
        :style="menuStyle"
        role="menu"
        :aria-label="$t('launch.mode.title')"
        @keydown="onMenuKey"
      >
        <div class="mode-menu-head">
          <span class="mode-menu-title">{{ $t('launch.mode.title') }}</span>
          <span class="mode-menu-keys" aria-hidden="true"><kbd>⇧</kbd> + <kbd>Tab</kbd> {{ $t('launch.mode.to_switch') }}</span>
        </div>
        <button
          v-for="(mode, index) in modes"
          :key="mode.key"
          :ref="(el) => (itemRefs[index] = el)"
          type="button"
          class="mode-item"
          :class="[`is-${mode.key}`, { 'is-selected': mode.key === modelValue }]"
          role="menuitemradio"
          :aria-checked="mode.key === modelValue"
          @click="pick(mode.key)"
        >
          <span class="mode-item-icon" aria-hidden="true" v-html="mode.icon"></span>
          <span class="mode-item-text">
            <span class="mode-item-label">{{ mode.label }}</span>
            <span class="mode-item-desc">{{ mode.desc }}</span>
          </span>
          <svg v-if="mode.key === modelValue" class="mode-item-check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>
        </button>
        <p v-if="runActive" class="mode-menu-note">{{ $t('launch.mode.next_turn') }}</p>
      </div>
    </Transition>
    </Teleport>
  </div>
</template>

<script setup>
// How much a chat turn asks before acting. The page owns the value (it is sent with each turn) and the
// Shift+Tab shortcut in the message box; this is the button and its menu.
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: String, default: 'manual' },
  // A turn is running: a change applies from the next message
  runActive: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const ICONS = {
  manual: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 11V6a2 2 0 0 0-4 0v5"/><path d="M14 10V4a2 2 0 0 0-4 0v6"/><path d="M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>',
  plan: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6"/><path d="M9 16h4"/></svg>',
  auto: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
  bypass: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></svg>'
}
const MODE_KEYS = ['manual', 'plan', 'auto', 'bypass']
const modes = computed(() => MODE_KEYS.map((key) => ({
  key,
  icon: ICONS[key],
  label: t(`launch.mode.${key}.label`),
  desc: t(`launch.mode.${key}.desc`)
})))
const current = computed(() => modes.value.find((m) => m.key === props.modelValue) || modes.value[0])

const open = ref(false)
const rootRef = ref(null)
const triggerRef = ref(null)
const menuRef = ref(null)
const itemRefs = []

const focusItem = (index) => {
  const n = itemRefs.length
  itemRefs[((index % n) + n) % n]?.focus()
}
// The menu is teleported to <body> and placed against the viewport, so a narrow chat panel (or any
// overflow:hidden ancestor) can no longer clip it. It stays inside the window and scrolls if tall.
const MENU_WIDTH = 340
const GAP = 8
const menuStyle = ref({})
const placeMenu = () => {
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const width = Math.min(MENU_WIDTH, vw - GAP * 2)
  const left = Math.min(Math.max(GAP, rect.right - width), vw - width - GAP)
  const above = rect.top - GAP * 2
  const below = vh - rect.bottom - GAP * 2
  const openUp = above >= Math.min(420, below) || above >= below
  menuStyle.value = openUp
    ? { left: `${left}px`, width: `${width}px`, bottom: `${vh - rect.top + GAP}px`, maxHeight: `${Math.max(160, above)}px` }
    : { left: `${left}px`, width: `${width}px`, top: `${rect.bottom + GAP}px`, maxHeight: `${Math.max(160, below)}px` }
}
const toggle = async () => {
  open.value = !open.value
  if (open.value) {
    placeMenu()
    await nextTick()
    focusItem(Math.max(0, MODE_KEYS.indexOf(props.modelValue)))
  }
}
const close = (refocus = false) => {
  if (!open.value) return
  open.value = false
  if (refocus) triggerRef.value?.focus()
}
const pick = (key) => {
  emit('update:modelValue', key)
  close(true)
}
const onMenuKey = (event) => {
  const index = itemRefs.indexOf(document.activeElement)
  if (event.key === 'ArrowDown') { event.preventDefault(); focusItem(index + 1) }
  else if (event.key === 'ArrowUp') { event.preventDefault(); focusItem(index - 1) }
  else if (event.key === 'Home') { event.preventDefault(); focusItem(0) }
  else if (event.key === 'End') { event.preventDefault(); focusItem(itemRefs.length - 1) }
  else if (event.key === 'Escape') { event.stopPropagation(); close(true) }
  else if (event.key === 'Tab') close(false)
}
const onOutside = (event) => {
  if (rootRef.value?.contains(event.target) || menuRef.value?.contains(event.target)) return
  close(false)
}
watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('pointerdown', onOutside, true)
    window.addEventListener('resize', placeMenu)
    window.addEventListener('scroll', placeMenu, true)
  } else {
    document.removeEventListener('pointerdown', onOutside, true)
    window.removeEventListener('resize', placeMenu)
    window.removeEventListener('scroll', placeMenu, true)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onOutside, true)
  window.removeEventListener('resize', placeMenu)
  window.removeEventListener('scroll', placeMenu, true)
})
</script>

<style scoped>
.mode-picker { position: relative; }

.mode-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  max-width: 220px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: rgb(var(--ink) / 0.72);
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}
.mode-trigger:hover,
.mode-trigger[aria-expanded="true"] { background: rgb(var(--ink) / 0.08); color: var(--fg); }
.mode-trigger:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
@media (pointer: coarse), (max-width: 899.98px) {
  .mode-trigger { min-height: 44px; min-width: 44px; }
}
.mode-trigger-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mode-icon,
.mode-item-icon { display: inline-flex; flex: none; }
.mode-icon :deep(svg) { width: 15px; height: 15px; }

/* Anything but manual is a deliberate choice: keep it visible at a glance */
.mode-trigger.is-plan,
.mode-trigger.is-auto {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.mode-trigger.is-bypass {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 40%, transparent);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
}

.mode-menu {
  position: fixed;
  z-index: 1000;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 2px 4px rgb(15 23 42 / 0.08), 0 18px 40px -12px rgb(15 23 42 / 0.4);
}
.mode-menu-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px 8px;
  font-size: 12px;
  color: rgb(var(--ink) / 0.6);
}
.mode-menu-title { font-weight: 600; color: rgb(var(--ink) / 0.75); }
.mode-menu-keys kbd {
  font: inherit;
  font-size: 11px;
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--surface-raised);
}
.mode-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--fg);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.mode-item:hover,
.mode-item:focus-visible { background: rgb(var(--ink) / 0.07); outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.mode-item:focus-visible { box-shadow: inset 0 0 0 2px var(--focus-ring); }
.mode-item.is-selected { background: rgb(var(--ink) / 0.09); }
.mode-item-icon { margin-top: 2px; color: rgb(var(--ink) / 0.7); }
.mode-item-icon :deep(svg) { width: 18px; height: 18px; }
.mode-item.is-bypass .mode-item-icon { color: var(--danger); }
.mode-item-text { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.mode-item-label { font-size: 13.5px; font-weight: 600; }
.mode-item-desc { font-size: 12px; line-height: 1.4; color: rgb(var(--ink) / 0.6); }
.mode-item-check { flex: none; margin-top: 3px; color: var(--accent); }
.mode-menu-note {
  margin: 4px 8px 4px;
  font-size: 11.5px;
  color: rgb(var(--ink) / 0.55);
}

.mode-menu-enter-active,
.mode-menu-leave-active { transition: opacity 0.14s var(--ease-out), transform 0.14s var(--ease-out); }
.mode-menu-enter-from,
.mode-menu-leave-to { opacity: 0; transform: translateY(4px); }

@media (max-width: 520px) {
  .mode-trigger-label { display: none; }
  .mode-trigger { padding: 0 8px; }
}
@media (prefers-reduced-motion: reduce) {
  .mode-trigger, .mode-menu-enter-active, .mode-menu-leave-active { transition: none; }
}
</style>
