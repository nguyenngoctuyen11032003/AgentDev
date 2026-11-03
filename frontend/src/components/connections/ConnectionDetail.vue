<template>
  <Teleport to="body">
    <div v-if="open && connection" class="dialog-backdrop" @mousedown.self="$emit('close')">
      <section
        ref="dialogEl"
        class="dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        @keydown.esc.stop="$emit('close')"
      >
        <button type="button" class="icon-btn close-btn" :aria-label="$t('connections.close')" @click="$emit('close')">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>

        <header class="detail-head">
          <ProviderLogo :vendor="connection.vendor" :label="vendorLabel" :size="52" />
          <div class="head-text">
            <h2 :id="titleId">{{ connection.label }}</h2>
            <div class="head-meta">
              <span>{{ vendorLabel }}</span>
              <span class="status-pill" :class="`is-${status}`">
                <span class="status-dot" aria-hidden="true"></span>
                {{ $t(`connections.status_${status}`) }}
              </span>
            </div>
          </div>
        </header>

        <div class="detail-body" :aria-busy="loading">
          <!-- Account -->
          <section class="panel">
            <h3 class="panel-title">{{ $t('connections.detail_account') }}</h3>
            <div v-if="loading && !account" class="skeleton" aria-hidden="true"></div>
            <dl v-else class="kv">
              <template v-for="row in accountRows" :key="row.key">
                <dt>{{ $t(`connections.field_${row.key}`) }}</dt>
                <dd>
                  <span v-if="row.badge" class="plan-badge">{{ row.value }}</span>
                  <template v-else>{{ row.value }}</template>
                  <span v-if="row.extra" class="kv-extra">{{ row.extra }}</span>
                </dd>
              </template>
            </dl>
            <p v-if="account && account.loggedIn === false" class="notice is-error">{{ account.detail || $t('connections.not_signed_in') }}</p>
          </section>

          <!-- Models -->
          <section v-if="models.length" class="panel">
            <div class="panel-row">
              <h3 class="panel-title">{{ $t('connections.detail_models') }}</h3>
              <span class="panel-note">{{ $t('connections.models_count', { count: models.length }) }}</span>
            </div>
            <div class="model-chips">
              <span
                v-for="model in visibleModels"
                :key="model.id"
                class="chip"
                :class="{ 'is-premium': isPremiumModel(model.id), 'is-secondary': !model.primary }"
                :title="model.id"
              >
                <svg v-if="isPremiumModel(model.id)" viewBox="0 0 24 24" width="11" height="11" fill="currentColor" aria-hidden="true"><path d="M12 2l2.4 6.9L21 10l-5.2 4.3L17.4 21 12 17.3 6.6 21l1.6-6.7L3 10l6.6-1.1z" /></svg>
                <code>{{ model.id }}</code>
              </span>
              <button v-if="hiddenCount" type="button" class="chip chip-more" @click="showAllModels = true">
                {{ $t('connections.models_more', { count: hiddenCount }) }}
              </button>
            </div>
          </section>

          <!-- Connection -->
          <section class="panel">
            <h3 class="panel-title">{{ $t('connections.detail_connection') }}</h3>
            <dl class="kv">
              <dt>{{ $t('connections.field_id') }}</dt>
              <dd>
                <button type="button" class="chip-btn" @click="$emit('copy-id', connection.id)">
                  <code>{{ connection.id }}</code>
                  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>
                </button>
              </dd>
              <dt>{{ $t('connections.field_created') }}</dt>
              <dd>{{ formatDateTime(connection.createdAt, locale) }}</dd>
            </dl>
            <p class="panel-note">{{ $t('connections.used_in') }}</p>
          </section>
        </div>

        <footer class="detail-foot">
          <button type="button" class="btn btn-danger" @click="$emit('logout', connection)">
            {{ $t('connections.logout') }}
          </button>
          <button type="button" class="btn btn-primary" :disabled="busy" @click="$emit('test', connection)">
            {{ busy ? $t('connections.testing') : $t('connections.refresh') }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ProviderLogo from './ProviderLogo.vue'
import { formatDateTime, isPremiumModel } from '@/utils/accountFormat'

const props = defineProps({
  open: { type: Boolean, default: false },
  connection: { type: Object, default: null },
  account: { type: Object, default: null },
  models: { type: Array, default: () => [] },
  vendorLabel: { type: String, default: '' },
  status: { type: String, default: 'unchecked' },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false }
})
defineEmits(['close', 'test', 'logout', 'copy-id'])

const { t, locale } = useI18n()
const titleId = `conn-detail-${Math.random().toString(36).slice(2, 8)}`
const dialogEl = ref(null)
const showAllModels = ref(false)

const accountRows = computed(() => {
  const account = props.account || {}
  const rows = [{ key: 'auth_method', value: account.authMethod || t(`connections.auth_${props.connection?.authType}`) }]
  if (account.displayName) rows.push({ key: 'name', value: account.displayName })
  if (account.email) rows.push({ key: 'email', value: account.email })
  if (account.organization) rows.push({ key: 'organization', value: account.organization })
  if (account.plan) rows.push({ key: 'plan', value: account.plan, badge: true, extra: account.seat ? t('connections.seat', { seat: account.seat }) : '' })
  return rows
})


const MODEL_PREVIEW = 8
const visibleModels = computed(() => (showAllModels.value ? props.models : props.models.slice(0, MODEL_PREVIEW)))
const hiddenCount = computed(() => props.models.length - visibleModels.value.length)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    showAllModels.value = false
    await nextTick()
    dialogEl.value?.focus()
  },
  { immediate: true }
)
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  overflow-y: auto;
  background: rgb(8 8 10 / 0.66);
  backdrop-filter: blur(4px);
  animation: fade 0.16s ease-out;
}

.dialog {
  position: relative;
  box-sizing: border-box;
  width: min(560px, 100%);
  max-height: calc(100dvh - 48px);
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
}

@keyframes fade {
  from { opacity: 0; }
}

@keyframes rise {
  from { opacity: 0; transform: translateY(8px) scale(0.99); }
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--surface-3);
  color: var(--text-1);
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 24px 56px 16px 24px;
  border-bottom: 1px solid var(--line-4);
}

.head-text {
  min-width: 0;
}

.head-text h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}

.head-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-muted-4);
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 24px;
  overflow-y: auto;
}

.panel {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--line-4);
  background: color-mix(in srgb, var(--surface-3) 40%, transparent);
}

.panel-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 12px;
}

.panel-title {
  margin: 0 0 10px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted-4);
}

.panel-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-muted-4);
}

.panel-row .panel-note {
  margin: 0 0 10px;
}

.kv {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 9px 16px;
  margin: 0;
  font-size: 13.5px;
}

.kv dt {
  color: var(--text-muted-4);
}

.kv dd {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0;
  min-width: 0;
  font-weight: 550;
  overflow-wrap: anywhere;
}

.kv-extra {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted-4);
}

.plan-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--accent-indigo);
  background: color-mix(in srgb, var(--accent-indigo) 14%, transparent);
}

.notice {
  margin: 10px 0 0;
  font-size: 12.5px;
}

.notice.is-error {
  color: var(--danger);
}

/* ---- usage ---- */
.usage-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.usage-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  font-size: 13.5px;
}

.usage-label {
  font-weight: 600;
}

.usage-value {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.bar {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface-3);
}

.bar-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent-sky);
  transition: width 0.3s ease;
}

.bar-fill.is-warn,
.usage-value.is-warn { --tone: #f59e0b; }
.bar-fill.is-danger,
.usage-value.is-danger { --tone: var(--danger); }
.bar-fill.is-warn,
.bar-fill.is-danger { background: var(--tone); }
.usage-value.is-warn,
.usage-value.is-danger { color: var(--tone); }

.usage-reset {
  display: block;
  margin-top: 5px;
  font-size: 12px;
  color: var(--text-muted-4);
}

/* ---- models ---- */
.model-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 8px;
  font-size: 11.5px;
  background: var(--surface-3);
  color: var(--text-1);
}

.chip code {
  font-size: 11.5px;
}

.chip.is-secondary {
  color: var(--text-muted-4);
}

.chip.is-premium {
  color: #b45309;
  background: color-mix(in srgb, #f59e0b 16%, transparent);
  border: 1px solid color-mix(in srgb, #f59e0b 40%, transparent);
}

:root[data-theme='dark'] .chip.is-premium {
  color: #fbbf24;
}

.chip-more {
  border: 1px dashed var(--line-4);
  background: transparent;
  color: var(--text-muted-4);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.chip-more:hover {
  color: var(--text-1);
  border-color: var(--accent-sky);
}

.chip-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 8px;
  border: 1px dashed var(--line-4);
  background: transparent;
  color: var(--text-muted-4);
  cursor: pointer;
}

.chip-btn code {
  font-size: 11.5px;
}

.chip-btn:hover {
  border-color: var(--accent-sky);
  color: var(--text-1);
}

/* ---- status ---- */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-muted-4);
  background: var(--surface-3);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted-6);
}

.status-pill.is-ok { color: var(--accent-mint); background: color-mix(in srgb, var(--accent-mint) 13%, transparent); }
.status-pill.is-ok .status-dot { background: var(--accent-mint); }
.status-pill.is-error { color: var(--danger); background: color-mix(in srgb, var(--danger) 14%, transparent); }
.status-pill.is-error .status-dot { background: var(--danger); }

/* ---- footer ---- */
.detail-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 24px 18px;
  border-top: 1px solid var(--line-4);
}

.btn {
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid var(--line-4);
  background: var(--surface-3);
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s;
}

.btn:hover:not(:disabled) {
  border-color: var(--accent-sky);
}

.btn:disabled {
  opacity: 0.55;
  cursor: progress;
}

.btn-danger {
  background: transparent;
  color: var(--danger);
}

.btn-danger:hover:not(:disabled) {
  border-color: var(--danger);
}

.skeleton {
  height: 96px;
  border-radius: 10px;
  background: linear-gradient(90deg, var(--surface-1), var(--surface-3), var(--surface-1));
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}

@keyframes shimmer {
  to { background-position: -200% 0; }
}

:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .dialog-backdrop,
  .dialog,
  .skeleton,
  .bar-fill {
    animation: none;
    transition: none;
  }
}

@media (max-width: 520px) {
  .detail-head { padding: 20px 52px 14px 16px; }
  .detail-body { padding: 14px 16px; }
  .detail-foot { padding: 12px 16px 16px; }
  .kv { grid-template-columns: 1fr; gap: 2px; }
  .kv dd { margin-bottom: 8px; }
}
</style>
