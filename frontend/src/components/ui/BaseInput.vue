<script setup>
import { computed, useId } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  type: { type: String, default: 'text' },
  textarea: { type: Boolean, default: false },
  rows: { type: Number, default: 4 },
  placeholder: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  id: { type: String, default: '' }
})
defineEmits(['update:modelValue'])

const uid = useId()
const fieldId = computed(() => props.id || uid)
const describedBy = computed(() => {
  const ids = []
  if (props.error) ids.push(`${fieldId.value}-error`)
  if (props.hint) ids.push(`${fieldId.value}-hint`)
  return ids.join(' ') || undefined
})
</script>

<template>
  <div class="field">
    <label v-if="label" class="field-label" :for="fieldId">{{ label }}</label>
    <textarea
      v-if="textarea"
      :id="fieldId"
      class="input"
      :rows="rows"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @input="$emit('update:modelValue', $event.target.value)"
    ></textarea>
    <input
      v-else
      :id="fieldId"
      class="input"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @input="$emit('update:modelValue', $event.target.value)"
    />
    <p v-if="error" :id="`${fieldId}-error`" class="field-error" role="alert">{{ error }}</p>
    <p v-if="hint" :id="`${fieldId}-hint`" class="field-hint">{{ hint }}</p>
  </div>
</template>
