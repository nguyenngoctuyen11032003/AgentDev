<template>
  <BaseDialog
    :model-value="open && !!connection"
    :labelledby="titleId"
    width="560px"
    @update:model-value="(value) => !value && $emit('close')"
  >
    <template #header>
      <header v-if="connection" class="detail-head">
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
    </template>

        <div v-if="connection" class="detail-body" :aria-busy="loading">
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

          <!-- Usage limits (session / weekly windows reported by the CLI) -->
          <section v-if="usageWindows.length" class="panel">
            <div class="panel-row">
              <h3 class="panel-title">{{ $t('connections.detail_usage') }}</h3>
              <span v-if="account?.usage?.fetchedAt" class="panel-note">
                {{ $t('connections.usage_updated', { time: formatReset(account.usage.fetchedAt, locale) }) }}
              </span>
            </div>
            <ul class="usage-list">
              <li v-for="win in usageWindows" :key="win.kind">
                <div class="usage-top">
                  <span class="usage-label">{{ windowLabel(win) }}</span>
                  <span class="usage-value" :class="`is-${usageLevel(win.percent)}`">{{ win.percent }}%</span>
                </div>
                <div
                  class="bar"
                  role="progressbar"
                  :aria-label="windowLabel(win)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-valuenow="win.percent"
                >
                  <span class="bar-fill" :class="`is-${usageLevel(win.percent)}`" :style="{ width: `${win.percent}%` }"></span>
                </div>
                <span class="usage-reset">
                  {{ win.resetsAt ? $t('connections.usage_resets', { time: formatReset(win.resetsAt, locale) }) : $t('connections.usage_fresh') }}
                </span>
              </li>
            </ul>
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

    <template #footer>
      <div class="detail-foot">
          <button type="button" class="btn secondary btn-danger" @click="$emit('logout', connection)">
            {{ $t('connections.logout') }}
          </button>
          <button type="button" class="btn primary" :disabled="busy" @click="$emit('test', connection)">
            {{ busy ? $t('connections.testing') : $t('connections.refresh') }}
          </button>
      </div>
    </template>
  </BaseDialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ProviderLogo from './ProviderLogo.vue'
import BaseDialog from '@/components/common/BaseDialog.vue'
import { formatDateTime, formatReset, isPremiumModel, usageLabel, usageLevel } from '@/utils/accountFormat'

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

const { t, te, locale } = useI18n()
const titleId = `conn-detail-${Math.random().toString(36).slice(2, 8)}`
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


const usageWindows = computed(() =>
  (props.account?.usage?.windows || [])
    .filter((win) => win && Number.isFinite(Number(win.percent)))
    .map((win) => ({ ...win, percent: Math.max(0, Math.min(100, Math.round(Number(win.percent)))) }))
)
// A dedicated label (e.g. Claude's per-model weekly limit) wins over the generic "period · scope" one.
const windowLabel = (win) => (te(`connections.usage_${win.kind}`) ? t(`connections.usage_${win.kind}`) : usageLabel(t, win))

const MODEL_PREVIEW = 8
const visibleModels = computed(() => (showAllModels.value ? props.models : props.models.slice(0, MODEL_PREVIEW)))
const hiddenCount = computed(() => props.models.length - visibleModels.value.length)

watch(
  () => props.open,
  (open) => {
    if (open) showAllModels.value = false
  },
  { immediate: true }
)
</script>

<style scoped>
.detail-head {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1;
  min-width: 0;
  padding: 4px 0;
}

.head-text {
  flex: 1;
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
  color: var(--fg-muted);
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--border-strong);
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
  font-size: 13px;
  font-weight: 650;
  color: var(--fg-muted);
}

.panel-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--fg-muted);
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
  color: var(--fg-muted);
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
  color: var(--fg-muted);
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
  background: var(--accent);
  transition: width 0.3s ease;
}

.bar-fill.is-warn,
.usage-value.is-warn { --tone: var(--warn); }
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
  color: var(--fg-muted);
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
  color: var(--fg);
}

.chip code {
  font-size: 11.5px;
}

.chip.is-secondary {
  color: var(--fg-muted);
}

.chip.is-premium {
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
}

.chip-more {
  min-height: 40px;
  border: 1px dashed var(--border-strong);
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.chip-more:hover {
  color: var(--fg);
  border-color: var(--accent);
}

.chip-btn {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 8px;
  border: 1px dashed var(--border-strong);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
}

.chip-btn code {
  font-size: 11.5px;
}

.chip-btn:hover {
  border-color: var(--accent);
  color: var(--fg);
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
  color: var(--fg-muted);
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
  flex: 1 1 100%;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

/* footer buttons: global .btn (ui.css); only the destructive tint is local */
.btn.btn-danger {
  color: var(--danger);
}

.btn.btn-danger:hover:not(:disabled) {
  background: transparent;
  border-color: var(--danger);
}

.skeleton {
  height: 96px;
  border-radius: 10px;
}

@media (prefers-reduced-motion: reduce) {
  .bar-fill {
    animation: none;
    transition: none;
  }
}

@media (max-width: 520px) {
  .kv { grid-template-columns: 1fr; gap: 2px; }
  .kv dd { margin-bottom: 8px; }
}
</style>
