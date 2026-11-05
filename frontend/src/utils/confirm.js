// In-app confirmation dialog (replaces window.confirm so prompts match the UI theme).
// Rendered by components/common/ConfirmHost.vue, mounted once in App.vue.
import { shallowRef } from 'vue'

export const pendingConfirm = shallowRef(null)

/**
 * @param {{title: string, message?: string, confirmText?: string, cancelText?: string,
 *          tone?: 'danger'|'default', checkbox?: {label: string}}} options
 * @returns {Promise<boolean|{confirmed: boolean, checked: boolean}>} true when the user confirms
 *          (an object when options.checkbox is set).
 */
export function confirmDialog(options) {
  // Only one question at a time: a newer one cancels the previous.
  pendingConfirm.value?.resolve(false)
  return new Promise((resolve) => {
    pendingConfirm.value = {
      tone: 'default',
      ...options,
      resolve: (answer, checked = false) => {
        pendingConfirm.value = null
        // With an opt-in checkbox the caller needs both answers.
        resolve(options.checkbox ? { confirmed: answer, checked: answer && checked } : answer)
      }
    }
  })
}
