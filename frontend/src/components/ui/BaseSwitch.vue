<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, default: '' },
  ariaLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

function toggle() {
  if (!props.disabled) emit('update:modelValue', !props.modelValue)
}
</script>

<template>
  <span class="switch-row">
    <!-- native button: Space/Enter activate via click -->
    <button
      type="button"
      role="switch"
      class="ui-switch"
      :aria-checked="modelValue ? 'true' : 'false'"
      :aria-label="ariaLabel || undefined"
      :disabled="disabled"
      @click="toggle"
    >
      <span class="ui-switch-thumb"></span>
    </button>
    <span v-if="label" class="switch-text" @click="toggle">{{ label }}</span>
  </span>
</template>
