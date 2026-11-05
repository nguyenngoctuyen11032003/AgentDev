import { ref, computed, watch } from 'vue'
import { fetchSessions } from '@/api/client.js'
import { toast } from '@/utils/toast.js'

/**
 * Saved sessions of the Launch view: the sidebar list, polling (fast while a run is live,
 * here or in the background), toasts when a background session needs an answer or ends,
 * and the "(n) title" badge for sessions waiting elsewhere.
 * Call startSessionsPolling() once mounted and stopSessionsPolling() on unmount.
 *
 * @param {object} deps
 * @param {Function} deps.t i18n translate
 * @param {import('vue').Ref<string>} deps.activeSessionId
 * @param {(item: object) => ({ name?: string } | null | undefined)} deps.sessionProject
 * @param {(item: object) => unknown} deps.openSession
 * @param {() => void} deps.onVisible called when the tab becomes visible again
 */
export function useSessions({ t, activeSessionId, sessionProject, openSession, onVisible }) {
  const sessions = ref([])
  const sessionsLoaded = ref(false)
  const sessionsLoadFailed = ref(false)
  const hasLiveSession = computed(() => sessions.value.some((item) => ['running', 'cancelling', 'waiting_for_input'].includes(item.status)))

  // Runs keep going on the server while another session is open here. Watch their
  // status and say when one needs an answer or has finished.
  const LIVE_STATUSES = new Set(['running', 'waiting_for_input'])
  const knownStatuses = new Map()
  let statusesPrimed = false
  const notifyBackgroundChanges = (list) => {
    for (const item of list) {
      const previous = knownStatuses.get(item.session_id)
      knownStatuses.set(item.session_id, item.status)
      if (!statusesPrimed || !previous || previous === item.status) continue
      if (item.session_id === activeSessionId.value) continue
      const title = item.title || t('launch.sessions.untitled')
      const project = sessionProject(item)?.name
      const name = project ? `${project} · ${title}` : title
      const action = { label: t('launch.sessions.menu.open'), run: () => openSession(item) }
      if (item.status === 'waiting_for_input') {
        toast.warning(t('launch.sessions.bg_waiting', { name }), { action, duration: 15000 })
      } else if (item.status === 'completed') {
        toast.success(t('launch.sessions.bg_completed', { name }), { action, duration: 8000 })
      } else if (item.status === 'error') {
        toast.error(t('launch.sessions.bg_error', { name }), { action, duration: 12000 })
      }
    }
    statusesPrimed = true
  }
  const waitingElsewhere = computed(
    () => sessions.value.filter((item) => item.status === 'waiting_for_input' && item.session_id !== activeSessionId.value).length
  )
  const BASE_TITLE = document.title
  watch(waitingElsewhere, (count) => {
    document.title = count ? `(${count}) ${BASE_TITLE}` : BASE_TITLE
  })

  let sessionsPollTimer = null
  let sessionsRefreshTimer = null
  // A slow answer must not overwrite a newer one, and an unchanged list is not re-assigned
  // (the poll runs every few seconds: a new array would re-render the whole sidebar)
  let sessionsRequestSeq = 0
  let sessionsSnapshot = ''
  // What the sidebar shows of each session, as one string: compared on every poll instead of the
  // whole list (whose items carry up to 200 changed files each). Any change the server makes to a
  // session moves its updated_at; the rest covers fields derived without touching it.
  const sessionsFingerprint = (list) =>
    list
      .map((item) =>
        [
          item.session_id,
          item.updated_at,
          item.status,
          item.title,
          item.yaml_file,
          item.message_count,
          item.current_node_id,
          item.awaiting_plan,
          item.has_work,
          item.resumable,
          item.projects?.length || 0
        ].join('|')
      )
      .join(';')

  const refreshSessions = async () => {
    const seq = ++sessionsRequestSeq
    try {
      const list = await fetchSessions()
      if (seq !== sessionsRequestSeq) return
      const snapshot = sessionsFingerprint(list)
      if (snapshot !== sessionsSnapshot) {
        sessionsSnapshot = snapshot
        sessions.value = list
        notifyBackgroundChanges(list)
      }
      sessionsLoadFailed.value = false
    } catch (error) {
      console.warn('Failed to load sessions:', error)
      if (seq === sessionsRequestSeq) sessionsLoadFailed.value = true
    } finally {
      sessionsLoaded.value = true
    }
  }
  // Coalesce bursts of status changes into one request
  const scheduleSessionsRefresh = () => {
    clearTimeout(sessionsRefreshTimer)
    sessionsRefreshTimer = setTimeout(refreshSessions, 400)
  }
  // Poll often while a run is live (here or in the background), slowly otherwise
  const schedulePoll = () => {
    clearTimeout(sessionsPollTimer)
    const live = sessions.value.some((item) => LIVE_STATUSES.has(item.status))
    sessionsPollTimer = setTimeout(async () => {
      if (document.visibilityState === 'visible') await refreshSessions()
      schedulePoll()
    }, live ? 4000 : 15000)
  }
  const onVisibilityChange = () => {
    if (document.visibilityState !== 'visible') return
    refreshSessions()
    onVisible()
  }

  const startSessionsPolling = () => {
    document.addEventListener('visibilitychange', onVisibilityChange)
    refreshSessions().finally(schedulePoll)
  }
  const stopSessionsPolling = () => {
    clearTimeout(sessionsPollTimer)
    clearTimeout(sessionsRefreshTimer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    document.title = BASE_TITLE
  }

  return {
    sessions,
    sessionsLoaded,
    sessionsLoadFailed,
    hasLiveSession,
    refreshSessions,
    scheduleSessionsRefresh,
    startSessionsPolling,
    stopSessionsPolling
  }
}
