<template>
  <div class="chat-suggestions" role="list" :aria-label="$t('launch.chat_ui.suggestions_label')">
    <button
      v-for="key in SUGGESTION_KEYS"
      :key="key"
      type="button"
      role="listitem"
      class="chat-suggestion"
      :disabled="disabled"
      @click="$emit('pick', $t(key))"
    >
      {{ $t(key) }}
    </button>
  </div>
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
  gap: 8px;
  margin-top: 10px;
}
.chat-suggestion {
  max-width: 100%;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(var(--ink) / 0.04);
  color: var(--text-1);
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.chat-suggestion:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.24);
}
.chat-suggestion:focus-visible {
  outline: 2px solid var(--accent-blue-1);
  outline-offset: 2px;
}
.chat-suggestion:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (prefers-reduced-motion: reduce) {
  .chat-suggestion {
    transition: none;
  }
}
</style>
