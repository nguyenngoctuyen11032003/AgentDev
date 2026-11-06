<template>
  <div class="connections-view page">
    <header class="hero">
      <div class="hero-text">
        <p class="hero-kicker">{{ $t('connections.kicker') }}</p>
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
        <div v-for="n in 3" :key="n" class="skeleton"></div>
      </div>

      <div v-else-if="loadError" class="empty-state load-error" role="alert">
        <p class="empty-title">{{ $t('connections.load_failed_title') }}</p>
        <p class="empty-desc">{{ $t('connections.load_failed_hint') }}</p>
        <p v-if="loadError.detail" class="empty-desc load-error-detail">{{ loadError.detail }}</p>
        <button type="button" class="btn sm" @click="load">{{ $t('connections.retry') }}</button>
      </div>

      <div v-else-if="!connections.length" class="empty-state">
        <span class="empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1" /></svg>
        </span>
        <p class="empty-title">{{ $t('connections.empty_title') }}</p>
        <p class="empty-desc">{{ $t('connections.empty_desc') }}</p>
      </div>

      <ul v-else class="connection-list">
        <li v-for="conn in connections" :key="conn.id" class="connection-card">
          <button
            type="button"
            class="card-open"
            @click="openDetail(conn)"
          >
            <ProviderLogo :vendor="conn.vendor" :label="vendorLabel(conn.vendor)" :size="44" />

            <span class="connection-main">
              <span class="connection-top">
                <span class="connection-label">{{ conn.label }}</span>
                <span class="status-pill" :class="`is-${statusOf(conn.id)}`">
                  <span class="status-dot" aria-hidden="true"></span>
                  {{ $t(`connections.status_${statusOf(conn.id)}`) }}
                </span>
                <span v-if="accounts[conn.id]?.plan" class="plan-badge">{{ accounts[conn.id].plan }}</span>
                <span v-if="conn.id === defaultId" class="default-badge" :title="$t('connections.default_hint')">
                  {{ $t('connections.default_badge') }}
                </span>
              </span>

              <span class="connection-meta">
                <span>{{ vendorLabel(conn.vendor) }}</span>
                <span class="sep" aria-hidden="true">·</span>
                <span>{{ accounts[conn.id]?.authMethod || authLabel(conn.authType) }}</span>
                <template v-if="accountName(accounts[conn.id])">
                  <span class="sep" aria-hidden="true">·</span>
                  <span class="account-name">
                    {{ accountName(accounts[conn.id]) }}
                    <span v-if="accounts[conn.id].displayName && accounts[conn.id].email" class="account-email">({{ accounts[conn.id].email }})</span>
                  </span>
                </template>
              </span>

              <span v-if="modelsOf(conn).length" class="model-chips">
                <span
                  v-for="model in primaryModels(conn).slice(0, 4)"
                  :key="model.id"
                  class="chip"
                  :class="{ 'is-premium': isPremiumModel(model.id) }"
                >{{ model.id }}</span>
                <span v-if="modelsOf(conn).length > Math.min(4, primaryModels(conn).length)" class="chip chip-more">
                  +{{ modelsOf(conn).length - Math.min(4, primaryModels(conn).length) }}
                </span>
              </span>
              <span v-if="errorOf(conn.id)" class="connection-error">{{ errorOf(conn.id) }}</span>
            </span>
          </button>

          <div class="connection-actions">
            <button v-if="conn.id !== defaultId" type="button" class="btn sm" @click="makeDefault(conn)">
              {{ $t('connections.make_default') }}
            </button>
            <button type="button" class="btn sm" :disabled="busyId === conn.id" @click="runTest(conn)">
              {{ busyId === conn.id ? $t('connections.testing') : $t('connections.test') }}
            </button>
            <button type="button" class="btn sm secondary btn-danger" :aria-label="`${$t('connections.logout')}: ${conn.label}`" @click="logout(conn)">
              {{ $t('connections.logout') }}
            </button>
          </div>
        </li>
      </ul>

      <p v-if="connections.length" class="tip">{{ $t('connections.used_in') }}</p>
    </section>

    <!-- What happens when an account runs out of quota (runtime/node/agent/account_fallback.py) -->
    <section v-if="!loading && connections.length" class="block" :aria-label="$t('connections.fallback_title')">
      <h2 class="block-title">{{ $t('connections.fallback_title') }}</h2>
      <div class="fallback-card" :class="{ 'is-warn': !hasBackup }">
        <p class="fallback-desc">{{ $t('connections.fallback_desc') }}</p>
        <ol class="fallback-chain" :aria-label="$t('connections.fallback_order')">
          <li
            v-for="(vendorId, index) in fallbackOrder"
            :key="vendorId"
            class="fallback-step"
            :class="{ 'is-linked': readyFor(vendorId) > 0 }"
          >
            <span v-if="index" class="fallback-arrow" aria-hidden="true">→</span>
            <ProviderLogo :vendor="vendorId" :label="vendorLabel(vendorId)" :size="20" bare />
            <span>{{ fallbackName(vendorId) }}</span>
            <span class="fallback-state">
              {{ readyFor(vendorId) ? $t('connections.fallback_ready') :$t('connections.fallback_missing') }}
            </span>
          </li>
        </ol>
        <p class="fallback-note" :class="{ 'is-warn': !hasBackup }">
          {{ hasBackup ? $t('connections.fallback_ok') : $t('connections.fallback_no_backup') }}
        </p>
      </div>
    </section>

    <ConnectDialog
      v-if="activeVendor"
      :open="dialogOpen"
      :vendor="activeVendor"
      @close="dialogOpen = false"
      @created="refreshQuietly"
    />

    <ConnectionDetail
      :open="!!detailConn"
      :connection="detailConn"
      :account="detailConn ? accounts[detailConn.id] : null"
      :models="detailConn ? modelsOf(detailConn) : []"
      :vendor-label="detailConn ? vendorLabel(detailConn.vendor) : ''"
      :status="detailConn ? statusOf(detailConn.id) : 'unchecked'"
      :loading="detailConn ? !!accountLoading[detailConn.id] : false"
      :busy="detailConn ? busyId === detailConn.id : false"
      @close="detailId = ''"
      @test="runTest"
      @logout="logout"
      @copy-id="copyId"
    />
  </div>
</template>

<script setup>
defineOptions({ name: 'ConnectionsView' })
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ConnectDialog from '@/components/connections/ConnectDialog.vue'
import ConnectionDetail from '@/components/connections/ConnectionDetail.vue'
import ProviderLogo from '@/components/connections/ProviderLogo.vue'
import {
  deleteConnection,
  fetchConnectionAccount,
  fetchConnectionVendors,
  fetchConnections,
  setDefaultConnection,
  testConnection
} from '@/api/client'
import { needsLiveModels, logoutToast, readyCount, sharesCliLogin } from '@/utils/connectionsLogic'
import { accountName, isPremiumModel, normalizeModels } from '@/utils/accountFormat'
import { invalidateConnectionModels, modelsForConnection } from '@/utils/connectionModels'
import { confirmDialog } from '@/utils/confirm'
import { localizeBackendError } from '@/utils/errorTranslate'
import { toast } from '@/utils/toast'

const { t } = useI18n()
const route = useRoute()

const vendors = ref([])
const connections = ref([])
const defaultId = ref(null) // connection every agent node without its own one runs on
const loading = ref(true)
const loadError = ref(null) // {detail} when the list could not be loaded
const busyId = ref('')
const results = reactive({})
const accounts = reactive({})
const accountLoading = reactive({})
const activeVendor = ref(null)
const dialogOpen = ref(false)
const detailId = ref('')

const detailConn = computed(() => connections.value.find((conn) => conn.id === detailId.value) || null)

const vendorLabel = (id) => vendors.value.find((vendor) => vendor.id === id)?.label || id
const authLabel = (id) => (id === 'cli' || id === 'oauth' ? t(`connections.auth_${id}`) : t('connections.auth_legacy'))
const countFor = (vendorId) => connections.value.filter((conn) => conn.vendor === vendorId).length
const readyFor = (vendorId) => readyCount(connections.value, accounts, vendorId)
const backendError = (message) => localizeBackendError(message) || message

// A test result wins; otherwise the account lookup tells whether the sign-in is live.
const statusOf = (id) => {
  const result = results[id]
  if (result) return result.ok ? 'ok' : 'error'
  if (accountLoading[id]) return 'checking'
  const loggedIn = accounts[id]?.loggedIn
  if (loggedIn === true) return 'ok'
  if (loggedIn === false) return 'error'
  return 'unchecked'
}

const errorOf = (id) => {
  if (results[id] && !results[id].ok) return backendError(results[id].error)
  if (!results[id] && accounts[id]?.loggedIn === false) return localizeBackendError(accounts[id].detail) || accounts[id].detail
  return ''
}

// Live model list for Google sign-in connections, loaded as soon as the page opens so the card
// does not show the 2-model static catalog until someone presses "Test".
const liveModels = reactive({})

async function loadLiveModels(conn) {
  if (!needsLiveModels(conn) || liveModels[conn.id]) return
  try {
    const data = await modelsForConnection(conn.id)
    if (data.ok && data.models.length) liveModels[conn.id] = data.models
  } catch {
    // Keep the static catalog when the listing cannot be fetched.
  }
}

const modelsOf = (conn) =>
  normalizeModels(
    accounts[conn.id]?.models ||
      liveModels[conn.id] ||
      results[conn.id]?.models ||
      vendors.value.find((vendor) => vendor.id === conn.vendor)?.models
  )

const primaryModels = (conn) => modelsOf(conn).filter((model) => model.primary)

// Mirrors the backend preference (Claude -> Codex, Codex -> Claude, then Gemini).
const fallbackOrder = ['anthropic', 'openai', 'gemini']
const fallbackName = (id) => ({ anthropic: 'Claude', openai: 'Codex', gemini: 'Gemini' })[id] || vendorLabel(id)
// A backup exists when accounts from at least two providers are signed in.
const hasBackup = computed(() => fallbackOrder.filter((vendorId) => readyFor(vendorId) > 0).length >= 2)

function openDialog(vendor) {
  activeVendor.value = vendor
  dialogOpen.value = true
}

function openDetail(conn) {
  detailId.value = conn.id
}

async function loadAccount(id) {
  accountLoading[id] = true
  try {
    accounts[id] = await fetchConnectionAccount(id)
  } catch {
    // Account details are optional; the card still works without them.
  } finally {
    accountLoading[id] = false
  }
}

// Refresh after a change that already succeeded: a failure here must not look like the change failed.
async function refreshQuietly() {
  try {
    await refresh()
  } catch (error) {
    toast.warning(t('connections.refresh_failed'), { detail: backendError(error.message) })
  }
}

async function refresh() {
  const data = await fetchConnections()
  connections.value = data.connections
  defaultId.value = data.defaultConnection || null
  invalidateConnectionModels()
  for (const id of Object.keys(liveModels)) delete liveModels[id] // listings may have changed
  for (const conn of data.connections) {
    loadLiveModels(conn)
    if (!accounts[conn.id] && !accountLoading[conn.id]) loadAccount(conn.id)
  }
}

async function runTest(conn) {
  busyId.value = conn.id
  try {
    const result = await testConnection(conn.id)
    results[conn.id] = result
    if (result.account) accounts[conn.id] = result.account
    if (result.ok) {
      toast.success(t('connections.test_ok', { count: result.models.length }))
    } else {
      toast.error(t('connections.test_failed'), { detail: backendError(result.error) })
    }
  } catch (error) {
    toast.error(backendError(error.message))
  } finally {
    busyId.value = ''
  }
}

// Removes the AgentDev record. Signing the CLI out (machine-wide) is an explicit opt-in checkbox.
async function logout(conn) {
  const isCli = conn.authType === 'cli'
  const answer = await confirmDialog({
    title: t('connections.logout_title', { name: conn.label }),
    message: t('connections.confirm_logout_detail'),
    confirmText: t('connections.logout'),
    tone: 'danger',
    checkbox: isCli ? { label: t('connections.sign_out_cli_label') } : undefined
  })
  const confirmed = isCli ? answer.confirmed : answer
  if (!confirmed) return
  const signOutCli = isCli && answer.checked
  const sharedWithOther = sharesCliLogin(connections.value, conn)
  let result
  try {
    result = await deleteConnection(conn.id, { signOutCli })
  } catch (error) {
    toast.error(backendError(error.message))
    return
  }
  delete results[conn.id]
  delete accounts[conn.id]
  if (detailId.value === conn.id) detailId.value = ''
  const kind = logoutToast(result, signOutCli, sharedWithOther)
  if (kind === 'logout_cli_failed') toast.warning(t('connections.logout_cli_failed'))
  else if (kind === 'logout_cli_kept') toast.info(t('connections.logout_cli_kept'))
  else toast.success(t(`connections.${kind}`))
  await refreshQuietly()
}

async function makeDefault(conn) {
  try {
    defaultId.value = (await setDefaultConnection(conn.id)).defaultConnection
    toast.success(t('connections.default_set', { name: conn.label }))
  } catch (error) {
    toast.error(backendError(error.message))
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

async function load() {
  loading.value = true
  loadError.value = null
  try {
    vendors.value = (await fetchConnectionVendors()).vendors
    await refresh()
    // Deep link, e.g. /connections?connect=anthropic opens that provider's dialog.
    const wanted = vendors.value.find((vendor) => vendor.id === route.query.connect)
    if (wanted && !activeVendor.value) openDialog(wanted)
  } catch (error) {
    loadError.value = { detail: backendError(error.message) }
    toast.error(backendError(error.message))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.connections-view {
  padding-bottom: 72px;
  color: var(--fg);
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

.hero-kicker {
  margin: 0 0 8px;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
}

.hero-title {
  margin: 0 0 10px;
  font-size: 32px;
  line-height: 1.15;
  font-weight: 750;
  letter-spacing: -0.03em;
  color: var(--text-strong);
}

.hero-sub {
  margin: 0;
  max-width: 64ch;
  font-size: 15px;
  line-height: 1.65;
  color: var(--fg-muted);
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

/* Light theme: darker mint keeps the count >= 4.5:1 on its tint */
:root[data-theme='light'] .hero-count { color: color-mix(in srgb, var(--accent-mint) 75%, #000); }

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
  font-size: 15px;
  font-weight: 650;
  color: var(--fg-muted);
}

/* ---- provider cards ---- */
.provider-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.provider-card {
  --pc: var(--accent-indigo);
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  align-items: start;
  column-gap: 14px;
  row-gap: 14px;
  width: 100%;
  min-height: 128px;
  box-sizing: border-box;
  padding: 18px;
  border-radius: 16px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.provider-card.is-anthropic { --pc: var(--brand); }
.provider-card.is-openai { --pc: var(--accent-mint); }
.provider-card.is-gemini { --pc: var(--accent-blue-1); }

.provider-card:hover,
.provider-card:focus-visible {
  border-color: color-mix(in srgb, var(--pc) 55%, transparent);
  background: color-mix(in srgb, var(--pc) 5%, var(--surface));
}

.provider-text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding-right: 22px; /* room for the chevron */
}

.provider-name {
  font-size: 15px;
  font-weight: 650;
}

.provider-tagline {
  font-size: 13px;
  line-height: 1.5;
  color: var(--fg-muted);
}

.provider-linked {
  grid-column: 1 / -1;
  align-self: end;
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--accent-mint);
}

.provider-chevron {
  position: absolute;
  top: 18px;
  right: 16px;
  flex: none;
  color: var(--fg-muted);
  transition: transform 0.15s ease, color 0.15s ease;
}

.provider-card:hover .provider-chevron {
  color: var(--pc);
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
  padding: 0 18px 0 0;
  border-radius: 16px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.connection-card:hover {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border-strong));
  background: color-mix(in srgb, var(--accent) 3%, var(--surface));
}

.card-open {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 16px;
  min-width: 0;
  padding: 16px 0 16px 18px;
  border: 0;
  border-radius: 16px 0 0 16px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.connection-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.plan-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 650;
  color: var(--accent-indigo);
  background: color-mix(in srgb, var(--accent-indigo) 14%, transparent);
}

.default-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 650;
  color: var(--accent-mint);
  background: color-mix(in srgb, var(--accent-mint) 14%, transparent);
}

:root[data-theme='light'] .default-badge { color: color-mix(in srgb, var(--accent-mint) 75%, #000); }

.account-name {
  color: var(--fg);
  font-weight: 550;
}

.account-email {
  margin-left: 2px;
  color: var(--fg-muted);
  font-weight: 400;
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
  color: var(--fg-muted);
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
  color: var(--fg-muted);
}

.chip.is-premium {
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 16%, transparent);
}

.chip-more {
  background: transparent;
  border: 1px dashed var(--border-strong);
}

.connection-error {
  display: block;
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
  color: var(--fg-muted);
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

/* actions use the global .btn.sm.secondary (ui.css); only the destructive tint is local */
.btn.btn-danger {
  color: var(--fg-muted);
}

.btn.btn-danger:hover:not(:disabled) {
  background: transparent;
  border-color: var(--danger);
  color: var(--danger);
}

.tip {
  margin: 14px 2px 0;
  font-size: 12.5px;
  color: var(--fg-muted);
}

/* ---- quota fallback ---- */
.fallback-card {
  padding: 18px 20px;
  border-radius: 14px;
  background: rgb(var(--panel-20) / 0.5);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.1);
}

.fallback-desc {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--text-soft-1);
}

.fallback-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.fallback-step {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--fg-muted);
}

.fallback-step.is-linked {
  color: var(--fg);
}

.fallback-arrow {
  margin-right: 2px;
  color: var(--fg-muted);
}

.fallback-state {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--fg-muted);
  background: rgb(var(--ink) / 0.06);
}

.fallback-step.is-linked .fallback-state {
  color: var(--accent-mint);
  background: rgb(var(--accent-mint-rgb) / 0.12);
}

:root[data-theme='light'] .fallback-step.is-linked .fallback-state { color: color-mix(in srgb, var(--accent-mint) 75%, #000); }

.fallback-note {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: var(--fg-muted);
}

.fallback-note.is-warn {
  color: var(--warn);
}

/* ---- empty + loading ---- */
.empty-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.empty-title {
  font-weight: 650;
}

.empty-desc {
  max-width: 42ch;
  line-height: 1.55;
}

.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton {
  height: 78px;
  border-radius: 16px;
}

@media (prefers-reduced-motion: reduce) {
  .provider-card,
  .provider-chevron { transition: none; }
}

@media (max-width: 900px) {
  .provider-grid { grid-template-columns: 1fr; }
  .provider-card { min-height: 0; }

  .connection-card {
    flex-wrap: wrap;
    padding: 0;
  }

  .card-open {
    flex-basis: 100%;
    padding: 16px 16px 4px;
    border-radius: 16px 16px 0 0;
  }

  .connection-actions {
    box-sizing: border-box;
    width: 100%;
    flex-wrap: wrap;
    padding: 0 16px 14px;
  }
}

@media (max-width: 720px) {
  .connections-view { padding-bottom: 56px; }
  .hero-title { font-size: 27px; }
}
</style>
