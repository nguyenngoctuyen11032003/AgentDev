<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import RichTooltip from '@/components/common/RichTooltip.vue'
import { helpContent } from '@/utils/helpContent.js'
import { configStore } from '@/stores/configStore.js'

defineProps({
  id: {
    type: String,
    required: true
  },
  data: {
    type: Object,
    default: () => ({})
  }
})

const shouldShowTooltip = computed(() => configStore.ENABLE_HELP_TOOLTIPS)
</script>

<template>
  <RichTooltip v-if="shouldShowTooltip" :content="helpContent.startNode" placement="right">
    <div class="start-node" :style="{ opacity: data.opacity ?? 1 }">
      <div class="start-node-bubble" :title="$t('components.start_node.title')"></div>
      <!-- Provide source handle at right -->
      <Handle id="source" type="source" :position="Position.Right" class="start-node-handle" />
    </div>
  </RichTooltip>
  <div v-else class="start-node" :style="{ opacity: data.opacity ?? 1 }">
    <div class="start-node-bubble" :title="$t('components.start_node.title')"></div>
    <!-- Provide source handle at right -->
    <Handle id="source" type="source" :position="Position.Right" class="start-node-handle" />
  </div>
</template>

<style scoped>
/*
 * The gradient "shift" is done by cross-fading two static gradient layers
 * (opacity only, runs on the compositor) instead of animating
 * background-position, which repainted the node on every frame.
 */
.start-node{
  display:flex;
  align-items:center;
  gap: 10px;
  padding:6px 6px;
  position: relative;
  isolation: isolate;
  background: linear-gradient(90deg, var(--accent-mint-2), var(--accent-blue-2), var(--accent-indigo-5));
  color:var(--bg-base);
  border-radius:18px;
  box-shadow: 0 6px 18px rgb(var(--shade) / 0.35);
  font-weight:600;
  font-size:13px;
  transition: opacity 0.10s ease-in-out;
}
.start-node::before{
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  z-index: -1;
  pointer-events: none;
  /* The gradient as seen at background-position 100% of the old 200%-wide image */
  background: linear-gradient(90deg, var(--accent-blue-2), var(--accent-indigo-5));
  opacity: 0;
  animation: gradientFade 5s ease-in-out infinite;
  will-change: opacity;
}
.start-node-bubble{
  width:20px;
  height:20px;
  border-radius:50%;
  background: var(--text-1);
  opacity:0.9;
  box-shadow: 0 2px 2px rgb(var(--shade) / 0.25);
}
.start-node-label{
  white-space:nowrap;
}
.start-node-handle{
  position:absolute;
  left:21px;
  width: 10px;
  height: 10px;
  background: linear-gradient(90deg, var(--accent-mint-2), var(--accent-blue-2), var(--accent-indigo-5));
  border: 1.5px solid var(--bg-base);
  border-radius: 50%;
  transition: filter 0.2s ease, transform 0.2s ease;
}

.start-node-handle:hover {
  filter: brightness(1.2);
}
@keyframes gradientFade {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .start-node::before {
    animation: none;
    will-change: auto;
  }
}
</style>


