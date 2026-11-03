<script setup>
import { useId } from 'vue'

defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  options: { type: Array, default: () => [] }, // [{ value, label, disabled? }] or primitives
  disabled: { type: Boolean, default: false },
  id: { type: String, default: '' }
})
defineEmits(['update:modelValue'])

const uid = useId()
const optValue = (o) => (o !== null && typeof o === 'object' ? o.value : o)
const optLabel = (o) => (o !== null && typeof o === 'object' ? (o.label ?? o.value) : o)
</script>

<template>
  <div class="field">
    <label v-if="label" class="field-label" :for="id || uid">{{ label }}</label>
    <span class="select-wrap" :class="{ 'has-icon': $slots.icon }">
      <span v-if="$slots.icon" class="select-icon" aria-hidden="true"><slot name="icon" /></span>
      <select
        :id="id || uid"
        class="select"
        :value="modelValue"
        :disabled="disabled"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <slot>
          <option v-for="o in options" :key="optValue(o)" :value="optValue(o)" :disabled="o && o.disabled">
            {{ optLabel(o) }}
          </option>
        </slot>
      </select>
      <svg class="select-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 6l4 4 4-4" />
      </svg>
    </span>
  </div>
</template>
