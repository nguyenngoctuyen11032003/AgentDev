// Small guards for the workflow editor: stale-load protection, layout-save error reporting,
// and the node-count switch for VueFlow viewport culling.

export const ONLY_RENDER_VISIBLE_THRESHOLD = 60

export const shouldOnlyRenderVisible = (nodeCount) => nodeCount > ONLY_RENDER_VISIBLE_THRESHOLD

// Monotonic token: a load that started earlier must not write results after a newer one began.
export function createSequenceGuard() {
  let current = 0
  return {
    next() {
      current += 1
      return current
    },
    current: () => current,
    isStale: (seq) => seq !== current,
  }
}

// Wraps a layout save so a failure (false or throw) is reported, at most once per cooldown,
// so dragging many nodes against a failing backend does not flood toasts.
export function createLayoutSaver({ save, notify, cooldownMs = 3000 }) {
  let lastNotified = -Infinity
  return {
    async save() {
      let ok = false
      try {
        ok = (await save()) === true
      } catch {
        ok = false
      }
      if (!ok) {
        const now = Date.now()
        if (now - lastNotified >= cooldownMs) {
          lastNotified = now
          notify()
        }
      }
      return ok
    },
  }
}
