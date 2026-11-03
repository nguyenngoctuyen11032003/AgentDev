// In-app confirmation dialog (replaces window.confirm so prompts match the UI theme).
// Rendered by components/common/ConfirmHost.vue, mounted once in App.vue.
import { shallowRef } from 'vue'

export const pendingConfirm = shallowRef(null)

/**
 * @param {{title: string, message?: string, confirmText?: string, cancelText?: string,
 *          tone?: 'danger'|'default'}} options
 * @returns {Promise<boolean>} true when the user confirms.
 */
export function confirmDialog(options) {
  // Only one question at a time: a newer one cancels the previous.
  pendingConfirm.value?.resolve(false)
  return new Promise((resolve) => {
    pendingConfirm.value = {
      tone: 'default',
      ...options,
      resolve: (answer) => {
        pendingConfirm.value = null
        resolve(answer)
      }
    }
  })
}
