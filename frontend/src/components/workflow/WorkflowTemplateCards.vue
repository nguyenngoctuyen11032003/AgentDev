<template>
  <ul class="tpl-cards" :aria-label="$t('workbench.start_templates')">
    <li v-for="tpl in visible" :key="tpl.file">
      <button type="button" class="tpl-card" @click="emit('open', tpl.file.replace(/\.ya?ml$/i, ''))">
        <span class="tpl-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="6" r="2.5" /><circle cx="5.5" cy="18" r="2.5" /><circle cx="18.5" cy="18" r="2.5" /><path d="M12 8.5v3.5M12 12l-5 3.5M12 12l5 3.5" /></svg>
        </span>
        <span class="tpl-name">{{ $t(tpl.labelKey) }}</span>
        <span class="tpl-desc">{{ $t(tpl.descKey) }}</span>
      </button>
    </li>
  </ul>
</template>

<script setup>
import { computed } from 'vue'

// Same department templates the "create" picker offers (DepartmentTemplatePicker); here a card
// simply opens the template workflow so the team can be inspected before copying it.
const TEMPLATES = [
  { file: 'software_company.yaml', labelKey: 'workflow_list.dept_software', descKey: 'workflow_list.dept_software_desc', always: true },
  { file: 'marketing_agency.yaml', labelKey: 'workflow_list.dept_marketing', descKey: 'workflow_list.dept_marketing_desc' },
  { file: 'content_studio.yaml', labelKey: 'workflow_list.dept_content', descKey: 'workflow_list.dept_content_desc' }
]

const props = defineProps({
  // Workflow file names that exist; templates missing from the list are hidden
  existingFiles: { type: Array, default: () => [] }
})
const emit = defineEmits(['open'])

const visible = computed(() => {
  const existing = new Set(props.existingFiles.map((name) => String(name).toLowerCase()))
  return TEMPLATES.filter((tpl) => tpl.always || existing.has(tpl.file))
})
</script>

<style scoped>
.tpl-cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
  width: 100%;
}

.tpl-card {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-4);
  text-align: left;
  font: inherit;
  color: var(--fg);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: border-color 0.2s var(--ease-out), background-color 0.2s var(--ease-out), transform 0.2s var(--ease-out);
}

.tpl-card:hover {
  border-color: var(--accent);
  background: var(--surface-raised);
  transform: translateY(-1px);
}

.tpl-card:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.tpl-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}

.tpl-name {
  font-size: 15px;
  font-weight: 600;
}

.tpl-desc {
  color: var(--fg-muted);
  font-size: 13px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .tpl-card { transition-duration: 0.01s; }
  .tpl-card:hover { transform: none; }
}
</style>
