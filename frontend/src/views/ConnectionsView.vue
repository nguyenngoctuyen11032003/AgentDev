<template>
  <div class="connections-view">
    <header class="hero">
      <div class="hero-text">
        <h1 class="hero-title">{{ $t('connections.title') }}</h1>
        <p class="hero-sub">{{ $t('connections.subtitle') }}</p>
      </div>
      <span v-if="connections.length" class="hero-count">
        <span class="count-dot" aria-hidden="true"></span>
        {{ $t('connections.connected_count', { count: connections.length }) }}
      </span>
    </header>

    <!-- Providers -->
    <section class="block" :aria-label="$t('connections.section_providers')">
      <h2 class="block-title">{{ $t('connections.section_providers') }}</h2>
      <div class="provider-grid">
        <button
          v-for="vendor in vendors"
          :key="vendor.id"
          type="button"
          class="provider-card"
          :class="`is-${vendor.id}`"
          @click="openDialog(vendor)"
        >
          <ProviderLogo :vendor="vendor.id" :label="vendor.label" :size="40" />
          <span class="provider-text">
            <span class="provider-name">{{ vendor.label }}</span>
            <span class="provider-tagline">{{ $t(`connections.tagline_${vendor.id}`) }}</span>
          </span>
          <span v-if="countFor(vendor.id)" class="provider-linked">
            <span class="count-dot" aria-hidden="true"></span>
            {{ $t('connections.n_connections', { count: countFor(vendor.id) }) }}
          </span>
          <svg class="provider-chevron" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        </button>
      </div>
    </section>

    <!-- Connected -->
    <section class="block" :aria-label="$t('connections.section_connected')" :aria-busy="loading">
      <h2 class="block-title">{{ $t('connections.section_connected') }}</h2>

      <div v-if="loading" class="skeleton-list" aria-hidden="true">
        <div class="skeleton"></div>
      </div>

      <div v-else-if="!connections.length" class="empty">
        <span class="empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1" /></svg>
        </span>
        <p class="empty-title">{{ $t('connections.empty_title') }}</p>
        <p class="empty-desc">{{ $t('connections.empty_desc') }}</p>
      </div>

      <ul v-else class="connection-list">
        <li v-for="conn in connections" :key="conn.id" class="connection-card">
          <ProviderLogo :vendor="conn.vendor" :label="vendorLabel(conn.vendor)" :size="44" />

          <div class="connection-main">
            <div class="connection-top">
              <span class="connection-label">{{ conn.label }}</span>
              <span class="status-pill" :class="`is-${statusOf(conn.id)}`">
                <span class="status-dot" aria-hidden="true"></span>
                {{ $t(`connections.status_${statusOf(conn.id)}`) }}
              </span>
            </div>
            <div class="connection-meta">
              <span>{{ vendorLabel(conn.vendor) }}</span>
              <span class="sep" aria-hidden="true">·</span>
              <span>{{ authLabel(conn.authType) }}</span>
              <template v-if="conn.secretHint">
                <span class="sep" aria-hidden="true">·</span>
                <code>{{ conn.secretHint }}</code>
              </template>
            </div>

            <div v-if="modelsOf(conn).length" class="model-chips">
              <span v-for="model in modelsOf(conn).slice(0, 4)" :key="model" class="chip">{{ model }}</span>
              <span v-if="modelsOf(conn).length > 4" class="chip chip-more">+{{ modelsOf(conn).length - 4 }}</span>
            </div>
            <p v-if="results[conn.id] && !results[conn.id].ok" class="connection-error">{{ results[conn.id].error }}</p>
          </div>

          <div class="connection-actions">
            <button type="button" class="chip-btn" :title="$t('connections.used_in')" @click="copyId(conn.id)">
              <code>{{ conn.id }}</code>
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>
            </button>
            <button type="button" class="btn" :disabled="busyId === conn.id" @click="runTest(conn)">
              {{ busyId === conn.id ? $t('connections.testing') : $t('connections.test') }}
            </button>
            <button type="button" class="btn btn-danger" :aria-label="`${$t('connections.remove')}: ${conn.label}`" @click="remove(conn)">
              {{ $t('connections.remove') }}
            </button>
          </div>
        </li>
      </ul>

      <p v-if="connections.length" class="tip">{{ $t('connections.used_in') }}</p>
    </section>

    <ConnectDialog
      v-if="activeVendor"
      :open="dialogOpen"
      :vendor="activeVendor"
      @close="dialogOpen = false"
      @created="refresh"
    />
  </div>
</template>

<script setup>
defineOptions({ name: 'ConnectionsView' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ConnectDialog from '@/components/connections/ConnectDialog.vue'
import ProviderLogo from '@/components/connections/ProviderLogo.vue'
import { deleteConnection, fetchConnectionVendors, fetchConnections, testConnection } from '@/api/client'
import { invalidateConnectionModels } from '@/utils/connectionModels'
import { toast } from '@/utils/toast'

const { t } = useI18n()
const route = useRoute()

const vendors = ref([])
const connections = ref([])
const loading = ref(true)
const busyId = ref('')
const results = reactive({})
const activeVendor = ref(null)
const dialogOpen = ref(false)

const vendorLabel = (id) => vendors.value.find((vendor) => vendor.id === id)?.label || id
const authLabel = (id) => t(`connections.auth_${id}`)
const countFor = (vendorId) => connections.value.filter((conn) => conn.vendor === vendorId).length

const statusOf = (id) => {
  const result = results[id]
  if (!result) return 'unchecked'
  return result.ok ? 'ok' : 'error'
}

const modelsOf = (conn) =>
  results[conn.id]?.models || vendors.value.find((vendor) => vendor.id === conn.vendor)?.models || []

function openDialog(vendor) {
  activeVendor.value = vendor
  dialogOpen.value = true
}

async function refresh() {
  const data = await fetchConnections()
  connections.value = data.connections
  invalidateConnectionModels()
}

async function runTest(conn) {
  busyId.value = conn.id
  try {
    const result = await testConnection(conn.id)
    results[conn.id] = result
    if (result.ok) {
      toast.success(t('connections.test_ok', { count: result.models.length }))
    } else {
      toast.error(t('connections.test_failed'), { detail: result.error })
    }
  } catch (error) {
    toast.error(error.message)
  } finally {
    busyId.value = ''
  }
}

async function remove(conn) {
  if (!window.confirm(t('connections.confirm_remove', { name: conn.label }))) return
  try {
    await deleteConnection(conn.id)
    delete results[conn.id]
    await refresh()
    toast.success(t('connections.removed'))
  } catch (error) {
    toast.error(error.message)
  }
}

async function copyId(id) {
  try {
    await navigator.clipboard.writeText(id)
    toast.success(t('connections.id_copied'))
  } catch {
    toast.info(id)
  }
}

onMounted(async () => {
  try {
    vendors.value = (await fetchConnectionVendors()).vendors
    await refresh()
    // Deep link, e.g. /connections?connect=anthropic opens that provider's dialog.
    const wanted = vendors.value.find((vendor) => vendor.id === route.query.connect)
    if (wanted) openDialog(wanted)
  } catch (error) {
    toast.error(error.message)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.connections-view {
  box-sizing: border-box;
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
  padding: 40px 24px 72px;
  color: var(--text-1);
  font-family: 'Inter', system-ui, sans-serif;
}

/* ---- hero ---- */
.hero {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 36px;
}

.hero-title {
  margin: 0 0 8px;
  width: fit-content;
  font-size: 34px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo));
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

:root[data-theme='light'] .hero-title {
  background: linear-gradient(90deg, #047857, #0369a1, #4338ca);
  background-clip: text;
  -webkit-background-clip: text;
}

.hero-sub {
  margin: 0;
  max-width: 60ch;
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--text-muted-4);
}

.hero-count {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-mint);
  background: color-mix(in srgb, var(--accent-mint) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-mint) 30%, transparent);
}

.count-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-mint);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-mint) 22%, transparent);
}

.block {
  margin-bottom: 40px;
}

.block-title {
  margin: 0 0 14px;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted-4);
}

/* ---- provider cards ---- */
.provider-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.provider-card {
  --brand: var(--accent-indigo);
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 14px 18px;
  border-radius: 16px;
  border: 1px solid var(--line-4);
  background: var(--surface-1);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.provider-card.is-anthropic { --brand: #d97757; }
.provider-card.is-openai { --brand: #74d3ae; }
.provider-card.is-gemini { --brand: #8ab4f8; }

.provider-card:hover,
.provider-card:focus-visible {
  border-color: color-mix(in srgb, var(--brand) 55%, transparent);
  background: color-mix(in srgb, var(--brand) 5%, var(--surface-1));
}

.provider-text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.provider-name {
  font-size: 15px;
  font-weight: 650;
}

.provider-tagline {
  overflow: hidden;
  font-size: 13px;
  color: var(--text-muted-4);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-linked {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--accent-mint);
}

.provider-chevron {
  flex: none;
  color: var(--text-muted-4);
  transition: transform 0.15s ease, color 0.15s ease;
}

.provider-card:hover .provider-chevron {
  color: var(--brand);
  transform: translateX(2px);
}

/* ---- connected list ---- */
.connection-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.connection-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid var(--line-4);
  background: var(--surface-1);
}

.connection-main {
  flex: 1;
  min-width: 0;
}

.connection-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.connection-label {
  font-size: 15px;
  font-weight: 650;
}

.connection-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--text-muted-4);
}

.connection-meta code {
  font-size: 12px;
}

.sep {
  opacity: 0.5;
}

.model-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.chip {
  padding: 3px 9px;
  border-radius: 8px;
  font-size: 11.5px;
  background: var(--surface-3);
  color: var(--text-muted-4);
}

.chip-more {
  background: transparent;
  border: 1px dashed var(--line-4);
}

.connection-error {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--danger);
  overflow-wrap: anywhere;
}

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

.status-pill.is-ok {
  color: var(--accent-mint);
  background: color-mix(in srgb, var(--accent-mint) 13%, transparent);
}

.status-pill.is-ok .status-dot {
  background: var(--accent-mint);
}

.status-pill.is-error {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
}

.status-pill.is-error .status-dot {
  background: var(--danger);
}

.connection-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}

.chip-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
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

.btn {
  padding: 8px 14px;
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
  color: var(--text-muted-4);
}

.btn-danger:hover:not(:disabled) {
  border-color: var(--danger);
  color: var(--danger);
}

.tip {
  margin: 14px 2px 0;
  font-size: 12.5px;
  color: var(--text-muted-4);
}

/* ---- empty + loading ---- */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
  border-radius: 18px;
  border: 1px dashed var(--line-4);
  background: var(--surface-1);
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  margin-bottom: 14px;
  border-radius: 16px;
  color: var(--accent-sky);
  background: color-mix(in srgb, var(--accent-sky) 12%, transparent);
}

.empty-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 650;
}

.empty-desc {
  margin: 0;
  max-width: 42ch;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--text-muted-4);
}

.skeleton {
  height: 78px;
  border-radius: 16px;
  background: linear-gradient(90deg, var(--surface-1), var(--surface-3), var(--surface-1));
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}

@keyframes shimmer {
  to { background-position: -200% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
  .provider-card,
  .provider-chevron { transition: none; }
}

:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
}

@media (max-width: 720px) {
  .connections-view { padding: 28px 16px 56px; }
  .hero-title { font-size: 28px; }

  .connection-card {
    flex-wrap: wrap;
  }

  .connection-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
