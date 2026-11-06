import { defineComponent, h, ref, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'

/**
 * Wrap a dynamic import in a component with every state a lazy panel needs:
 * loading (status text), error (alert + retry button) and ready (the real
 * component, with all attrs, listeners and slots passed through).
 *
 * `overlay: true` centers the loading/error box over the page, for modals that
 * render nothing of their own until the chunk arrives.
 */
export function lazyPanel(loader, { overlay = false } = {}) {
  return defineComponent({
    name: 'LazyPanel',
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      const { t } = useI18n()
      const comp = shallowRef(null)
      const failed = ref(false)
      let alive = true

      const load = () => {
        failed.value = false
        loader().then(
          (mod) => { if (alive) comp.value = mod.default || mod },
          () => { if (alive) failed.value = true }
        )
      }
      onMounted(load)
      onBeforeUnmount(() => { alive = false })

      return () => {
        if (comp.value) return h(comp.value, attrs, slots)
        const cls = ['lazy-panel-state', overlay ? 'lazy-panel-overlay' : '']
        if (failed.value) {
          return h('div', { class: [...cls, 'lazy-panel-error'], role: 'alert' }, [
            h('p', t('common.lazy.load_failed')),
            h('button', { type: 'button', class: 'lazy-panel-retry', onClick: load }, t('common.retry'))
          ])
        }
        return h('p', { class: cls, role: 'status' }, t('common.lazy.loading'))
      }
    }
  })
}
