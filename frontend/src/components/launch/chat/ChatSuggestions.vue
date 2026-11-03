<template>
  <ul class="chat-suggestions" :aria-label="$t('launch.chat_ui.suggestions_label')">
    <li v-for="key in SUGGESTION_KEYS" :key="key" class="chat-suggestion-item">
      <button
        type="button"
        class="chat-suggestion"
        :disabled="disabled"
        @click="$emit('pick', $t(key))"
      >
        {{ $t(key) }}
      </button>
    </li>
  </ul>
</template>

<script setup>
// Starter prompts for an empty chat: a click puts the text in the composer (it is not sent),
// so the user can still edit it, like the suggestion chips of a new ChatGPT / Claude chat.
defineProps({
  disabled: { type: Boolean, default: false }
})
defineEmits(['pick'])

const SUGGESTION_KEYS = [
  'launch.chat_ui.suggestion_intro',
  'launch.chat_ui.suggestion_plan',
  'launch.chat_ui.suggestion_review'
]
</script>

<style scoped>
.chat-suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}
.chat-suggestion-item { max-width: 100%; display: flex; }
.chat-suggestion {
  max-width: 100%;
  min-height: 40px;
  padding: 8px 16px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}
.chat-suggestion:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-raised));
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
}
.chat-suggestion:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.chat-suggestion:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (pointer: coarse) {
  .chat-suggestion { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
  .chat-suggestion {
    transition: none;
  }
}
</style>
