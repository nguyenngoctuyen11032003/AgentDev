<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: { type: String, default: 'secondary' }, // primary | secondary | ghost | danger
  size: { type: String, default: 'md' }, // md | sm
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
  to: { type: [String, Object], default: null },
  iconOnly: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' }
})

if (import.meta.env?.DEV && props.iconOnly && !props.ariaLabel) {
  console.warn('[BaseButton] icon-only buttons require ariaLabel')
}

const inactive = computed(() => props.disabled || props.loading)
const classes = computed(() => [
  'btn',
  props.variant,
  { sm: props.size === 'sm', 'icon-only': props.iconOnly, loading: props.loading }
])
</script>

<template>
  <router-link
    v-if="to"
    :to="to"
    :class="classes"
    :aria-label="ariaLabel || undefined"
    :aria-disabled="inactive || undefined"
    :aria-busy="loading || undefined"
    :tabindex="inactive ? -1 : undefined"
  >
    <span v-if="loading" class="btn-spinner" aria-hidden="true"></span>
    <slot />
  </router-link>
  <button
    v-else
    :type="type"
    :class="classes"
    :disabled="inactive"
    :aria-label="ariaLabel || undefined"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="btn-spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>
