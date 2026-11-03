<template>
  <div class="mascot-picker">
    <div class="mascot-preview" :style="{ '--accent': selectedMeta.accent, '--accent-soft': selectedMeta.accentSoft }">
      <img :src="SPRITE_PATH(selected, 'D', 1)" alt="" class="preview-sprite" />
      <div class="preview-text">
        <span class="preview-name">{{ getCharacterName(selected, t) }}</span>
        <span class="preview-tagline">{{ t(`sprites.characters.${selected}.tagline`) }}</span>
        <span v-if="isAuto" class="preview-auto">{{ t('mascot.auto_hint') }}</span>
        <span v-else-if="sharedWith.length" class="preview-warn">{{ t('mascot.shared_with', { nodes: sharedWith.join(', ') }) }}</span>
      </div>
    </div>

    <div class="mascot-grid" role="radiogroup" :aria-label="label">
      <button
        v-for="character in SPRITE_CHARACTERS"
        :key="character.id"
        type="button"
        role="radio"
        class="mascot-option"
        :class="{ 'is-selected': character.id === selected, 'is-used': usedBy(character.id).length }"
        :style="{ '--accent': character.accent, '--accent-soft': character.accentSoft }"
        :aria-checked="character.id === selected"
        :title="optionTitle(character.id)"
        :disabled="disabled"
        @click="choose(character.id)"
      >
        <img :src="SPRITE_PATH(character.id, 'D', 1)" alt="" loading="lazy" />
        <span class="option-name">{{ getCharacterName(character.id, t) }}</span>
        <span v-if="usedBy(character.id).length && character.id !== selected" class="option-used" aria-hidden="true"></span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { SPRITE_CHARACTERS, SPRITE_PATH, getCharacterMeta, getCharacterName } from '@/utils/spriteCharacters.js'
import { parseMascot, spriteFetcher } from '@/utils/spriteFetcher.js'

const props = defineProps({
  modelValue: { type: [Number, String], default: null },
  nodeId: { type: String, default: '' },
  // Character shown when nothing is saved yet (the node's current auto mascot)
  fallback: { type: Number, default: 1 },
  label: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const saved = computed(() => parseMascot(props.modelValue))
const selected = computed(() => saved.value || props.fallback)
const isAuto = computed(() => !saved.value)
const selectedMeta = computed(() => getCharacterMeta(selected.value))

// Other nodes of this workflow that already show a character
const usedBy = (character) => spriteFetcher.nodesUsing(character, props.nodeId || null)
const sharedWith = computed(() => usedBy(selected.value))

const optionTitle = (character) => {
  const name = getCharacterName(character, t)
  const nodes = usedBy(character)
  return nodes.length ? `${name} · ${t('mascot.used_by', { nodes: nodes.join(', ') })}` : name
}

function choose(character) {
  if (!props.disabled) emit('update:modelValue', character)
}
</script>

<style scoped>
.mascot-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mascot-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-soft);
}

.preview-sprite {
  width: 44px;
  height: 44px;
  flex: none;
  image-rendering: pixelated;
  object-fit: contain;
}

.preview-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.preview-name {
  font-size: 14px;
  font-weight: 650;
}

.preview-tagline,
.preview-auto {
  font-size: 12px;
  opacity: 0.75;
}

.preview-warn {
  font-size: 12px;
  color: var(--warn-soft-1);
}

.mascot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(66px, 1fr));
  gap: 6px;
}

.mascot-option {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 4px 5px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: rgb(127 127 127 / 0.08);
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, transform 0.15s;
}

.mascot-option img {
  width: 34px;
  height: 34px;
  image-rendering: pixelated;
  object-fit: contain;
}

.option-name {
  max-width: 100%;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mascot-option:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
  transform: translateY(-1px);
}

.mascot-option.is-selected {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: 0 0 0 1px var(--accent);
}

.mascot-option.is-used:not(.is-selected) img {
  opacity: 0.55;
}

.option-used {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
}

.mascot-option:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.mascot-option:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .mascot-option { transition: none; }
}
</style>
