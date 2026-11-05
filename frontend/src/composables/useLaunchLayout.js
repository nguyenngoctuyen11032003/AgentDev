import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { readStorage, writeStorage } from '@/views/launch/layoutStorage.js'

/**
 * Launch view layout: wide vs narrow, the status sheet / sessions drawer on narrow screens,
 * the foldable status column (chat view) and the right panel (other views), Esc handling.
 * Must be called during setup (registers listeners and onUnmounted hooks).
 *
 * @param {object} deps
 * @param {import('vue').Ref<string>} deps.viewMode
 * @param {import('vue').Ref<boolean>} deps.isRightPanelOpen
 * @param {import('vue').Ref<boolean>} deps.showSettingsModal
 * @param {() => void} deps.toggleSessionSidebar flips the wide-screen sessions column
 */
export function useLaunchLayout({ viewMode, isRightPanelOpen, showSettingsModal, toggleSessionSidebar }) {
  // Below 900px the status panel becomes a bottom sheet and the session list a drawer
  const NARROW_QUERY = '(max-width: 899.98px)'
  const narrowMql = typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(NARROW_QUERY) : null
  const isNarrow = ref(Boolean(narrowMql?.matches))
  const isControlSheetOpen = ref(false)
  const isSessionsDrawerOpen = ref(false)
  const onNarrowChange = (event) => {
    isNarrow.value = event.matches
    isControlSheetOpen.value = false
    isSessionsDrawerOpen.value = false
  }
  narrowMql?.addEventListener?.('change', onNarrowChange)
  onUnmounted(() => narrowMql?.removeEventListener?.('change', onNarrowChange))

  // Narrow: the status sheet opens above the pinned composer, never over it, so typing stays possible.
  // --composer-h = distance from the composer's top edge to the viewport bottom (0 when it is off screen).
  const inputAreaRef = ref(null)
  const launchRootRef = ref(null)
  let composerObserver = null
  const measureComposer = () => {
    const root = launchRootRef.value
    if (!root) return
    const area = inputAreaRef.value
    const rect = area?.getBoundingClientRect?.()
    const onScreen = rect && rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.left < window.innerWidth
    const offset = onScreen ? Math.max(0, Math.round(root.getBoundingClientRect().bottom - rect.top)) : 0
    root.style.setProperty('--composer-h', `${offset}px`)
  }
  const stopComposerWatch = () => {
    composerObserver?.disconnect()
    composerObserver = null
    window.removeEventListener('resize', measureComposer)
    launchRootRef.value?.style.setProperty('--composer-h', '0px')
  }
  watch([isControlSheetOpen, isNarrow], ([open, narrow]) => {
    stopComposerWatch()
    if (!open || !narrow) return
    nextTick(() => {
      measureComposer()
      if (typeof ResizeObserver === 'function' && inputAreaRef.value) {
        composerObserver = new ResizeObserver(measureComposer)
        composerObserver.observe(inputAreaRef.value)
      }
      window.addEventListener('resize', measureComposer)
    })
  })
  onUnmounted(stopComposerWatch)

  // Chat view (wide): the control panel is a column the person can fold away (remembered)
  const STATUS_COLUMN_KEY = 'agentdev.launch.statusColumnOpen'
  const isStatusColumnOpen = ref(readStorage(STATUS_COLUMN_KEY) !== '0')
  watch(isStatusColumnOpen, (open) => writeStorage(STATUS_COLUMN_KEY, open ? '1' : '0'))
  const isControlsVisible = computed(() => {
    if (isNarrow.value) return isControlSheetOpen.value
    return viewMode.value === 'chat' ? isStatusColumnOpen.value : isRightPanelOpen.value
  })
  const setControlsOpen = (open) => {
    if (isNarrow.value) {
      if (open) isSessionsDrawerOpen.value = false
      isControlSheetOpen.value = open
    } else if (viewMode.value === 'chat') {
      isStatusColumnOpen.value = open
    } else {
      isRightPanelOpen.value = open
    }
  }
  const toggleControls = () => setControlsOpen(!isControlsVisible.value)
  const closeControls = () => setControlsOpen(false)
  // Show the panel (workflow picker) wherever it lives in the current layout
  const revealControls = () => setControlsOpen(true)
  const toggleSessionsPanel = () => {
    if (isNarrow.value) {
      isControlSheetOpen.value = false
      isSessionsDrawerOpen.value = !isSessionsDrawerOpen.value
    } else {
      toggleSessionSidebar()
    }
  }
  // Esc closes whichever sheet is open
  const onSheetEscape = (event) => {
    if (event.key !== 'Escape' || event.defaultPrevented || showSettingsModal.value) return
    if (isControlSheetOpen.value) isControlSheetOpen.value = false
    else if (isSessionsDrawerOpen.value) isSessionsDrawerOpen.value = false
    else if (!isNarrow.value && viewMode.value !== 'chat' && isRightPanelOpen.value) isRightPanelOpen.value = false
  }
  document.addEventListener('keydown', onSheetEscape)
  onUnmounted(() => document.removeEventListener('keydown', onSheetEscape))

  return {
    isNarrow,
    isControlSheetOpen,
    isSessionsDrawerOpen,
    inputAreaRef,
    launchRootRef,
    isStatusColumnOpen,
    isControlsVisible,
    setControlsOpen,
    toggleControls,
    closeControls,
    revealControls,
    toggleSessionsPanel
  }
}

// Chat column outside the chat view: resizable by drag or arrow keys (double-click resets),
// remembered per browser.
export const CHAT_MIN_W = 320
export const CHAT_MAX_W = 560
export const CHAT_DEFAULT_W = 380
export const CHAT_RAIL_W = 48
const CHAT_WIDTH_KEY = 'agentdev.launch.chatWidth'

/**
 * @param {object} deps
 * @param {import('vue').Ref<string>} deps.viewMode
 * @param {import('vue').Ref<boolean>} deps.isChatPanelOpen
 * @param {() => boolean} deps.isChatRailMerged wide screen with the sessions list folded
 */
export function useChatColumn({ viewMode, isChatPanelOpen, isChatRailMerged }) {
  const clampChatWidth = (value) => Math.round(Math.min(CHAT_MAX_W, Math.max(CHAT_MIN_W, Number(value) || CHAT_DEFAULT_W)))
  const chatWidth = ref(clampChatWidth(readStorage(CHAT_WIDTH_KEY)))
  const setChatWidth = (value) => { chatWidth.value = clampChatWidth(value) }
  const leftPanelRef = ref(null)
  const isResizingChat = ref(false)
  let chatResizeRaf = 0
  let chatResizeCleanup = null
  const startChatResize = (event) => {
    if (event.button !== 0) return
    event.preventDefault()
    const left = leftPanelRef.value?.getBoundingClientRect().left || 0
    isResizingChat.value = true
    const onMove = (moveEvent) => {
      cancelAnimationFrame(chatResizeRaf)
      chatResizeRaf = requestAnimationFrame(() => setChatWidth(moveEvent.clientX - left))
    }
    const onUp = () => chatResizeCleanup?.()
    chatResizeCleanup = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
      cancelAnimationFrame(chatResizeRaf)
      isResizingChat.value = false
      writeStorage(CHAT_WIDTH_KEY, String(chatWidth.value))
      chatResizeCleanup = null
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }
  const onChatResizeKey = (event) => {
    const step = event.shiftKey ? 64 : 16
    const next = {
      ArrowLeft: chatWidth.value - step,
      ArrowRight: chatWidth.value + step,
      Home: CHAT_MIN_W,
      End: CHAT_MAX_W
    }[event.key]
    if (next === undefined) return
    event.preventDefault()
    setChatWidth(next)
    writeStorage(CHAT_WIDTH_KEY, String(chatWidth.value))
  }
  onUnmounted(() => chatResizeCleanup?.())
  // The chat column never takes more than half the work area
  const chatColumnCss = computed(() => `min(${chatWidth.value}px, 50%)`)
  const chatWidthStyle = computed(() => ({ '--chat-w': chatColumnCss.value }))
  // The width the chat covers on the left of a view: its column, or the rail when folded
  const chatCoverCss = computed(() => {
    if (viewMode.value === 'chat') return '0px'
    if (isChatPanelOpen.value) return chatColumnCss.value
    // Folded into the sessions rail: the view gets the whole width
    return isChatRailMerged() ? '0px' : `${CHAT_RAIL_W}px`
  })
  // Views pad their content by --inset-left + 34px (room for an old edge toggle): subtract it
  // so content starts one gutter (16px) right of the chat column or rail
  const insetStyle = computed(() => ({
    '--inset-left': `calc(${chatCoverCss.value} - 18px)`,
    '--graph-inset': chatCoverCss.value
  }))
  // the office map cancels the page zoom (see OfficeView), so convert the chat width into its units
  const officeInsetStyle = computed(() => ({ '--office-inset-left': `calc(${chatCoverCss.value} * var(--ui-zoom, 1))` }))

  return {
    chatWidth,
    setChatWidth,
    leftPanelRef,
    isResizingChat,
    startChatResize,
    onChatResizeKey,
    chatWidthStyle,
    insetStyle,
    officeInsetStyle
  }
}
