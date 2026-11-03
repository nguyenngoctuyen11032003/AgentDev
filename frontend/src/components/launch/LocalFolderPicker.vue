<template>
  <Teleport to="body">
    <div v-if="open" class="picker-backdrop" @mousedown.self="$emit('cancel')">
      <section
        ref="dialogEl"
        class="picker"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        @keydown.esc.stop="$emit('cancel')"
      >
        <header class="picker-head">
          <span class="head-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
          </span>
          <div class="head-text">
            <h2 :id="titleId">{{ $t('launch.open_folder.title') }}</h2>
            <p>{{ $t('launch.open_folder.subtitle') }}</p>
          </div>
          <button type="button" class="icon-btn" :aria-label="$t('common.cancel')" @click="$emit('cancel')">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </header>

        <p v-if="hint && current?.name !== hint" class="hint-bar">
          {{ $t('launch.open_folder.drop_hint', { name: hint }) }}
        </p>

        <div class="picker-body">
          <nav class="places" :aria-label="$t('launch.open_folder.places')">
            <template v-if="recent.length">
              <p class="places-title">{{ $t('launch.open_folder.recent') }}</p>
              <button
                v-for="item in recent"
                :key="item"
                type="button"
                class="place"
                :class="{ active: item === current?.path }"
                :title="item"
                @click="go(item)"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
                <span>{{ baseName(item) }}</span>
              </button>
            </template>
            <p class="places-title">{{ $t('launch.open_folder.places') }}</p>
            <button
              v-for="place in locations"
              :key="place.path"
              type="button"
              class="place"
              :class="{ active: place.path === current?.path }"
              :title="place.path"
              @click="go(place.path)"
            >
              <svg v-if="place.kind === 'drive'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="18" height="10" rx="2" /><path d="M7 12h.01" /></svg>
              <svg v-else-if="place.kind === 'home'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>
              <svg v-else viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
              <span>{{ place.kind === 'home' ? $t('launch.open_folder.home') : place.name }}</span>
            </button>
          </nav>

          <div class="browser">
            <form class="path-bar" @submit.prevent="go(pathInput)">
              <button
                type="button"
                class="icon-btn"
                :disabled="!current?.parent || loading"
                :title="$t('launch.open_folder.up')"
                :aria-label="$t('launch.open_folder.up')"
                @click="go(current.parent)"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
              <input
                ref="pathInputEl"
                v-model="pathInput"
                class="path-input"
                spellcheck="false"
                :placeholder="$t('launch.open_folder.path_placeholder')"
                :aria-label="$t('launch.open_folder.path_placeholder')"
              />
            </form>

            <div class="folder-list" :aria-busy="loading">
              <p v-if="error" class="list-state is-error">{{ error }}</p>
              <p v-else-if="loading" class="list-state">{{ $t('launch.open_folder.loading') }}</p>
              <p v-else-if="current && !visibleFolders.length" class="list-state">{{ $t('launch.open_folder.empty') }}</p>
              <ul v-else>
                <li v-for="folder in visibleFolders" :key="folder.path">
                  <button
                    type="button"
                    class="folder"
                    :class="{
                      'is-dim': folder.name.startsWith('.') || ignoredNames.has(folder.name),
                      'is-hint': hint && folder.name === hint
                    }"
                    @click="go(folder.path)"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                    <span class="folder-name">{{ folder.name }}</span>
                    <svg class="chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
                  </button>
                </li>
              </ul>
              <p v-if="current?.truncated" class="list-state">{{ $t('launch.open_folder.truncated') }}</p>
            </div>
          </div>
        </div>

        <p class="note">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>
          {{ $t('launch.open_folder.in_place_note') }}
        </p>

        <footer class="picker-foot">
          <span class="selected" :title="current?.path || ''">
            <template v-if="current">{{ current.path }}</template>
          </span>
          <button type="button" class="btn btn-ghost" @click="$emit('cancel')">{{ $t('common.cancel') }}</button>
          <button type="button" class="btn btn-primary" :disabled="!current || loading || busy" @click="confirm">
            {{ busy ? $t('launch.open_folder.opening') : $t('launch.open_folder.open') }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { browseLocalFolders } from '@/api/client.js'
import { IGNORED_PROJECT_DIRS } from '@/utils/projectFiles.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  // Name of a folder dropped on the chat: shown as a reminder and highlighted when listed
  hint: { type: String, default: '' }
})
const emit = defineEmits(['open', 'cancel'])

const RECENT_KEY = 'agentdev.launch.recentFolders'
const RECENT_LIMIT = 6

const uid = Math.random().toString(36).slice(2, 8)
const titleId = `open-folder-title-${uid}`
const dialogEl = ref(null)
const pathInputEl = ref(null)
const locations = ref([])
const current = ref(null)
const pathInput = ref('')
const loading = ref(false)
const error = ref('')
const recent = ref([])
const ignoredNames = IGNORED_PROJECT_DIRS

const visibleFolders = computed(() => current.value?.folders || [])

const baseName = (path) => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path

const readRecent = () => {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(list) ? list.filter((item) => typeof item === 'string').slice(0, RECENT_LIMIT) : []
  } catch {
    return []
  }
}

const rememberRecent = (path) => {
  const list = [path, ...readRecent().filter((item) => item !== path)].slice(0, RECENT_LIMIT)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    // storage unavailable: recents are only a convenience
  }
}

let requestId = 0
const go = async (path) => {
  const target = (path || '').trim()
  if (!target) return
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const listing = await browseLocalFolders(target)
    if (id !== requestId) return
    current.value = listing
    pathInput.value = listing.path
  } catch (err) {
    if (id !== requestId) return
    error.value = err?.message || String(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}

const confirm = () => {
  if (!current.value) return
  rememberRecent(current.value.path)
  emit('open', current.value.path)
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    recent.value = readRecent()
    error.value = ''
    if (!locations.value.length) {
      try {
        locations.value = (await browseLocalFolders()).locations || []
      } catch (err) {
        error.value = err?.message || String(err)
      }
    }
    // A dropped folder that was opened before: go straight to it
    const known = props.hint ? recent.value.find((item) => baseName(item) === props.hint) : ''
    if (known) {
      await go(known)
    } else if (!current.value) {
      await go(recent.value[0] || locations.value[0]?.path || '')
    }
    await nextTick()
    dialogEl.value?.focus()
  },
  { immediate: true }
)
</script>

<style scoped>
.picker-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: var(--backdrop-color);
  animation: fade 0.16s ease-out;
}

.picker {
  box-sizing: border-box;
  width: min(760px, 100%);
  height: min(560px, calc(100dvh - 48px));
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  border: 1px solid var(--line-4);
  background: var(--surface-1);
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
  box-shadow: 0 24px 64px -20px rgb(0 0 0 / 0.7);
  animation: rise 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
  outline: none;
  overflow: hidden;
}

@keyframes fade {
  from { opacity: 0; }
}

@keyframes rise {
  from { opacity: 0; transform: translateY(8px) scale(0.99); }
}

.picker-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 16px 14px 20px;
  border-bottom: 1px solid var(--line-4);
}

.head-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: var(--accent-sky);
  background: color-mix(in srgb, var(--accent-sky) 13%, transparent);
}

.head-text {
  flex: 1;
  min-width: 0;
}

.head-text h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
}

.head-text p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--text-muted-4);
}

.icon-btn {
  position: relative;
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
}

.icon-btn::before { content: ''; position: absolute; inset: -6px; }
@media (pointer: coarse) { .icon-btn { width: 44px; height: 44px; } }

.icon-btn:hover:not(:disabled) {
  background: var(--surface-3);
  color: var(--text-1);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.picker-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px 1fr;
}

.places {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 8px;
  overflow-y: auto;
  border-right: 1px solid var(--line-4);
  background: color-mix(in srgb, var(--surface-3) 35%, transparent);
}

.places-title {
  margin: 8px 10px 4px;
  font-size: var(--fs-xs);
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted-4);
}

.places-title:first-child {
  margin-top: 2px;
}

.place {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.place span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.place svg {
  flex: none;
  color: var(--text-muted-4);
}

.place:hover {
  background: var(--surface-3);
}

.place.active {
  background: color-mix(in srgb, var(--accent-sky) 14%, transparent);
}

.place.active svg {
  color: var(--accent-sky);
}

.browser {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.path-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line-4);
}

.path-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--line-4);
  background: var(--surface-2, var(--surface-1));
  color: var(--text-1);
  font: 13px ui-monospace, SFMono-Regular, Consolas, monospace;
}

.path-input:focus {
  outline: 2px solid var(--focus-ring);
  outline-offset: 1px;
  border-color: var(--accent-sky);
}

.folder-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
}

.folder-list ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.folder {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
}

.folder > svg:first-child {
  flex: none;
  color: #e8b44a;
}

.folder:hover {
  background: var(--surface-3);
}

.folder.is-dim {
  opacity: 0.55;
}

.folder.is-hint {
  background: color-mix(in srgb, var(--accent-sky) 14%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent-sky) 45%, transparent);
}

.hint-bar {
  margin: 0;
  padding: 9px 20px;
  font-size: 12.5px;
  color: var(--text-1);
  border-bottom: 1px solid var(--line-4);
  background: color-mix(in srgb, var(--accent-sky) 9%, transparent);
}

.folder-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  flex: none;
  color: var(--text-muted-4);
  opacity: 0;
}

.folder:hover .chevron {
  opacity: 1;
}

.list-state {
  margin: 0;
  padding: 18px 12px;
  font-size: 13px;
  color: var(--text-muted-4);
  text-align: center;
}

.list-state.is-error {
  color: var(--danger);
}

.note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 9px 20px;
  font-size: 12.5px;
  color: var(--text-1);
  border-top: 1px solid var(--line-4);
  background: color-mix(in srgb, var(--warn) 9%, transparent);
}

.note svg {
  flex: none;
  color: var(--warn);
}

.picker-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px 14px 20px;
  border-top: 1px solid var(--line-4);
}

.selected {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 12.5px ui-monospace, SFMono-Regular, Consolas, monospace;
  color: var(--text-muted-4);
  direction: rtl;
  text-align: left;
}

.btn {
  flex: none;
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid var(--line-4);
  background: var(--surface-3);
  color: var(--text-1);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, filter 0.15s;
}

.btn-ghost {
  background: transparent;
}

.btn-ghost:hover {
  border-color: var(--accent-sky);
}

.btn-primary {
  border-color: transparent;
  color: var(--on-accent);
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky));
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.08);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .picker-backdrop,
  .picker {
    animation: none;
  }
}

@media (max-width: 640px) {
  .picker-body {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }

  .places {
    flex-direction: row;
    flex-wrap: nowrap;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid var(--line-4);
  }

  .places-title {
    display: none;
  }

  .selected {
    display: none;
  }
}
</style>
