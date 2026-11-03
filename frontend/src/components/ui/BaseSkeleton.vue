<script setup>
defineProps({
  width: { type: String, default: '100%' },
  height: { type: String, default: '16px' },
  radius: { type: String, default: '' }
})
</script>

<template>
  <span class="skeleton" aria-hidden="true" :style="{ width, height, borderRadius: radius || undefined }"></span>
</template>
