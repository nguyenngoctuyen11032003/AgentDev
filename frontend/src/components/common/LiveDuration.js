import { computed, ref, watch } from 'vue'

// One shared 1 s clock for every running duration on the page. It only ticks
// while at least one LiveDuration is running, and only those instances re-render:
// the views that host them (e.g. the long chat list) are not touched.
const clock = ref(Date.now())
let subscribers = 0
let timer = null

const acquire = () => {
  subscribers += 1
  if (timer) return
  clock.value = Date.now()
  timer = setInterval(() => {
    clock.value = Date.now()
  }, 1000)
}

const release = () => {
  subscribers = Math.max(0, subscribers - 1)
  if (subscribers || !timer) return
  clearInterval(timer)
  timer = null
}

/** Format a millisecond span as mm:ss. */
export const formatElapsed = (startedAt, endedAt) => {
  if (!startedAt) return ''
  const totalSeconds = Math.max(0, Math.floor((endedAt - startedAt) / 1000))
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0')
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

/**
 * Renders "mm:ss" since `startedAt` (a plain text node, no wrapper element).
 * Ticks every second until `endedAt` is set, then shows the final value.
 */
export default {
  name: 'LiveDuration',
  props: {
    startedAt: { type: Number, default: 0 },
    endedAt: { type: Number, default: 0 }
  },
  setup(props) {
    const running = computed(() => !!props.startedAt && !props.endedAt)
    watch(
      running,
      (isRunning, _previous, onCleanup) => {
        if (!isRunning) return
        acquire()
        onCleanup(release)
      },
      { immediate: true }
    )
    return () => formatElapsed(props.startedAt, props.endedAt || (running.value ? clock.value : Date.now()))
  }
}
