// Google sign-in popup flow (popup + status polling), kept free of Vue so it can be unit tested.
// The popup is opened synchronously (inside the user's click) and navigated once the server
// has produced the auth URL, so browsers do not treat it as an unsolicited popup.

const POLL_MS = 1500
const TIMEOUT_MS = 5 * 60 * 1000

/**
 * @param {string} label
 * @param {{start: Function, poll: Function, openWindow: Function, t: Function,
 *          win?: Window, timeoutMs?: number}} deps
 * @returns {{promise: Promise<boolean>, cancel: () => void}}
 */
export function createGoogleOAuthFlow(label, deps) {
  const { start, poll, openWindow, t, win, timeoutMs = TIMEOUT_MS } = deps
  let timer = null
  let deadline = null
  let polling = false
  let settled = false
  let onMessage = null
  let rejectFlow = () => {}
  let userCancelled = false

  let popupRef = null
  const stop = () => {
    clearInterval(timer)
    clearTimeout(deadline)
    if (onMessage && win) win.removeEventListener('message', onMessage)
  }
  // Failure paths (timeout, cancel, poll error) must not leave the sign-in window open.
  const closePopup = () => {
    try {
      popupRef?.close?.()
    } catch {
      /* already gone */
    }
  }

  const promise = new Promise((resolve, reject) => {
    const finish = (fn, value) => {
      if (settled) return
      settled = true
      stop()
      if (fn === reject) closePopup()
      fn(value)
    }
    rejectFlow = (error) => finish(reject, error)

    const popup = openWindow('', 'agentdev-oauth', 'width=520,height=680')
    if (!popup) {
      finish(reject, new Error(t('connections.popup_blocked')))
      return
    }
    popupRef = popup
    deadline = setTimeout(() => finish(reject, new Error(t('connections.sign_in_timeout'))), timeoutMs)

    if (win) {
      onMessage = (event) => {
        if (event.origin === win.location.origin && event.data?.type === 'agentdev-oauth') {
          if (event.data.ok) finish(resolve, true)
          else finish(reject, new Error(t('connections.sign_in_failed')))
        }
      }
      win.addEventListener('message', onMessage)
    }

    start(label)
      .then(({ authUrl, state }) => {
        if (settled) {
          popup.close?.()
          return
        }
        popup.location = authUrl
        timer = setInterval(async () => {
          // A slow poll must not overlap the next one.
          if (polling || settled) return
          polling = true
          try {
            const { status } = await poll(state)
            if (status === 'done') finish(resolve, true)
            else if (status === 'error') finish(reject, new Error(t('connections.sign_in_failed')))
            else if (popup.closed) finish(reject, new Error(t('connections.sign_in_cancelled')))
          } catch (error) {
            finish(reject, error)
          } finally {
            polling = false
          }
        }, POLL_MS)
      })
      .catch((error) => {
        finish(reject, error)
      })
  })

  return {
    promise,
    cancel: () => {
      userCancelled = true
      rejectFlow(new Error(t('connections.sign_in_cancelled')))
    },
    // true once the user (not an error) ended the flow, so the UI can stay silent
    get cancelled() {
      return userCancelled
    }
  }
}
