<template>
  <div class="form-field" v-show="isVisible">
    <template v-if="field.childNode">
      <div v-if="recursive" class="form-group form-group-inline child-node-group">
        <label>
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div class="child-node-container">
          <div class="child-node-controls">
            <button @click="$emit('open-child-modal', field)" class="add-child-button">
              <span class="plus-icon" aria-hidden="true">
                <!-- Edit icon when configured -->
                <svg
                  v-if="!isList && hasChildValue"
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <rect
                    x="3"
                    y="2"
                    width="8"
                    height="11"
                    rx="1"
                    ry="1"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.2"
                  />
                  <path
                    fill="currentColor"
                    d="M10.9 3.1a.9.9 0 0 1 1.27 0l.73.73a.9.9 0 0 1 0 1.27l-4.3 4.3-1.7.5.5-1.7 4.3-4.3z"
                  />
                </svg>
                <!-- Configure icon when not yet configured -->
                <svg
                  v-else
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    fill="currentColor"
                    d="M8 2.5a.75.75 0 0 1 .75.75v4h4a.75.75 0 0 1 0 1.5h-4v4a.75.75 0 0 1-1.5 0v-4h-4a.75.75 0 0 1 0-1.5h4v-4A.75.75 0 0 1 8 2.5z"
                  />
                </svg>
              </span>
              {{ childNodeButtonLabel }}
            </button>
            <!-- Show clear button only when child is already configured ("Edit" mode) -->
            <button
              v-if="hasChildValue"
              class="clear-child-button"
              @click.stop="$emit('clear-child-entry', field.name)"
              :title="$t('dynamic_form_field.clear_configuration')"
            >
              ×
            </button>
          </div>
          <div
            v-if="isList && formData[field.name] && formData[field.name].length"
            class="child-node-list"
          >
            <div
              v-for="(childEntry, childIndex) in formData[field.name]"
              :key="childIndex"
              class="child-node-item-wrapper"
            >
              <div
                class="child-node-item"
                @click="$emit('open-child-modal', field, childIndex)"
              >
                <span class="child-node-name">
                  {{ describeChildEntry(childEntry, childIndex) }}
                </span>
                <div class="child-node-actions">
                  <button
                    class="delete-child-button"
                    @click.stop="$emit('delete-child-entry', field.name, childIndex)"
                    :title="$t('dynamic_form_field.delete_child')"
                  >
                    ×
                  </button>
                </div>
              </div>
              <div
                v-if="childSummaries[field.name] && childSummaries[field.name][childIndex]"
                class="child-node-summary"
              >
                {{ childSummaries[field.name][childIndex] }}
              </div>
            </div>
          </div>
          <div
            v-else-if="!isList && hasChildValue && childSummaries[field.name]"
            class="child-node-summary"
          >
            {{ childSummaries[field.name] }}
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="hasChildRoutes">
      <!-- Logic for expanded inline config will go here in FormGenerator usage or via prop controls -->
      <!-- But for now, we implement standard behavior. The expanding logic will be handled by the parent using slots or a different prop -->
      
      <!-- Standard Popup Style (if not expanded) -->
      <div v-if="!expandInline" class="form-group form-group-inline child-node-group">
        <label>
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div class="child-node-container">
          <div class="child-node-controls">
            <button
              @click="$emit('open-conditional-child-modal', field)"
              class="add-child-button"
              :disabled="!canOpenConditionalChildModal"
            >
              <span class="plus-icon" aria-hidden="true">
                <!-- Edit icon when a child config already exists -->
                <svg
                  v-if="formData[field.name]"
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <rect
                    x="3"
                    y="2"
                    width="8"
                    height="11"
                    rx="1"
                    ry="1"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.2"
                  />
                  <path
                    fill="currentColor"
                    d="M10.9 3.1a.9.9 0 0 1 1.27 0l.73.73a.9.9 0 0 1 0 1.27l-4.3 4.3-1.7.5.5-1.7 4.3-4.3z"
                  />
                </svg>
                <!-- Configure/Add icon when not yet configured -->
                <svg
                  v-else
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    fill="currentColor"
                    d="M8 2.5a.75.75 0 0 1 .75.75v4h4a.75.75 0 0 1 0 1.5h-4v4a.75.75 0 0 1-1.5 0v-4h-4a.75.75 0 0 1 0-1.5h4v-4A.75.75 0 0 1 8 2.5z"
                  />
                </svg>
              </span>
              {{ conditionalChildButtonLabel || $t('dynamic_form_field.configure') }}
            </button>
            <button
              v-if="hasChildValue"
              class="clear-child-button"
              @click.stop="$emit('clear-child-entry', field.name)"
              :title="$t('dynamic_form_field.clear_configuration')"
            >
              ×
            </button>
          </div>
          <div
            v-if="!canOpenConditionalChildModal"
            class="child-node-hint"
          >
            {{ $t('dynamic_form_field.select_type_and_configure') }}
          </div>
          <div
            v-if="hasChildValue && childSummaries[field.name]"
            class="child-node-summary"
          >
            {{ childSummaries[field.name] }}
          </div>
        </div>
      </div>
      
      <!-- Expanded Inline Style is NOT rendered here. The parent will check `expandInline` 
           and simply NOT render this button-based UI, and instead render the inline form. 
           Wait, if I am extracting this, I should support both or let parent handle the expanded part adjacent to this component?
           The requirement says: "display type selection" (which is a standard field), 
           then "display expanded config below".
           So the "config" field (which is `hasChildRoutes`) should be rendered DIFFERENTLY if expanded.
           If it's expanded, we might just want to render NOTHING for this field here, 
           and let the parent render the separator + sub-form?
           OR we render the separator + sub-form HERE? 
           But complex recursion logic is easier in parent.
           
           DECISION: If `expandInline` is true, this component renders NOTHING for the `childRoutes` field,
           because the content is rendered by the parent (the "separator" + "inline fields").
           Actually, the `type` field is a separate field. This component renders it.
           The `config` field IS the field with `childRoutes`.
           So if `expandInline` is true, we render NOTHING?
           Yes. The parent will detect this field and render the specialized inline UI instead.
           
           However, I need to make sure I don't break existing logic.
           If I pass `expandInline` prop:
      -->
      <div v-else-if="expandInline">
        <!-- Render nothing, parent handles it -->
      </div>
    </template>

    <template v-else>
      <!-- Choice dropdown fields-->
      <div v-if="field.enum && !isList" class="form-group">
        <label :for="`${modalId}-${field.name}`">
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div ref="selectWrapper" class="custom-select-wrapper" :class="{ 'select-disabled': isReadOnly }" @click="toggleDropdown">
          <input
            :id="`${modalId}-${field.name}`"
            :value="inputValue"
            class="form-input custom-select-input"
            readonly
            :class="{'input-readonly': isReadOnly}"
            :placeholder="$t('dynamic_form_field.type_to_filter')"
            autocomplete="off"
          />
          <Teleport to="body">
            <div
              v-if="showDropdown && !isReadOnly"
              class="custom-select-dropdown"
              data-local-scroll
              :style="dropdownStyle"
              @mousedown.prevent
              @wheel="handleLocalScrollWheel"
              @scroll.stop
              @touchmove.stop
            >
              <div
                v-if="!field.required"
                class="custom-select-option"
                :class="{ 'option-selected': formData[field.name] === null }"
                @mousedown.stop="selectOption(null)"
              >
                {{ $t('dynamic_form_field.none') }}
              </div>
              <div
                v-for="option in filteredOptions"
                :key="typeof option === 'string' ? option : option.value"
                class="custom-select-option"
                :class="{ 'option-selected': formData[field.name] === (typeof option === 'string' ? option : option.value) }"
                :title="optionDescription(option)"
                @mousedown.stop="selectOption(typeof option === 'string' ? option : option.value)"
              >
                {{ optionLabel(option) }}
              </div>
              <div v-if="filteredOptions.length === 0" class="custom-select-no-results">
                {{ $t('dynamic_form_field.no_options_found') }}
              </div>
            </div>
          </Teleport>
          <div class="custom-select-arrow" :class="{ 'arrow-open': showDropdown }">
            ▼
          </div>
        </div>
      </div>

      <!-- Multi-choice fields -->
      <div v-else-if="field.enum && isList" class="form-group">
        <label>
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div class="multi-select-options">
          <label
            v-for="option in (field.enumOptions || field.enum)"
            :key="typeof option === 'string' ? option : option.value"
            class="multi-select-option"
            :title="optionDescription(option)"
          >
            <input
              type="checkbox"
              :value="typeof option === 'string' ? option : option.value"
              v-model="internalFormData[field.name]"
            />
            <span class="option-label">
              {{ optionLabel(option) }}
            </span>
          </label>
        </div>
      </div>

      <!-- Boolean switch fields -->
      <div v-else-if="field.type === 'bool' && !isList" class="form-group">
        <div class="switch-wrapper">
          <label :for="`${modalId}-${field.name}`" class="switch-label-text">
            {{ fieldLabel }}
            <span v-if="field.required" class="required-asterisk">*</span>
            <RichTooltip
              v-if="field.description"
              :content="{ description: fieldDescription }"
              placement="top"
            >
              <span class="help-icon" tabindex="0">?</span>
            </RichTooltip>
          </label>
          <label class="switch-container">
            <input
              type="checkbox"
              :id="`${modalId}-${field.name}`"
              :checked="formData[field.name] === true"
              @change="onBooleanSwitchChange($event.target.checked)"
              :disabled="isReadOnly"
            />
            <span class="switch-slider"></span>
          </label>
        </div>
      </div>

      <!-- String input fields -->
      <div v-else-if="field.type === 'str' && !isList" class="form-group">
        <label :for="`${modalId}-${field.name}`">
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <input
          :id="`${modalId}-${field.name}`"
          :value="formData[field.name]"
          @input="onInput($event.target.value)"
          type="text"
          class="form-input"
          :readonly="isReadOnly"
          :class="{'input-readonly': isReadOnly}"
        />
      </div>

      <!-- Multiline text fields -->
      <div v-else-if="field.type === 'text' && !isList" class="form-group">
        <label :for="`${modalId}-${field.name}`">
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <textarea
          :id="`${modalId}-${field.name}`"
          :value="formData[field.name]"
          @input="onInput($event.target.value)"
          @wheel="handleLocalScrollWheel"
          @scroll.stop
          class="form-textarea"
          data-local-scroll
          rows="4"
          :readonly="isReadOnly"
          :class="{'input-readonly': isReadOnly}"
        />
      </div>

      <!-- Integer input fields -->
      <div v-else-if="field.type === 'int' && !isList" class="form-group">
        <label :for="`${modalId}-${field.name}`">
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <input
          :id="`${modalId}-${field.name}`"
          :value="formData[field.name]"
          @input="onInputNumber($event.target.value)"
          type="number"
          step="1"
          class="form-input"
          :readonly="isReadOnly"
          :class="{'input-readonly': isReadOnly}"
        />
      </div>

      <!-- Float input fields -->
      <div v-else-if="field.type === 'float' && !isList" class="form-group">
        <label :for="`${modalId}-${field.name}`">
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <input
          :id="`${modalId}-${field.name}`"
          :value="formData[field.name]"
          @input="onInputNumber($event.target.value)"
          type="number"
          step="any"
          class="form-input"
          :readonly="isReadOnly"
          :class="{'input-readonly': isReadOnly}"
        />
      </div>

      <!-- Key-value fields -->
      <div v-else-if="field.type === 'dict[str, Any]' || field.type === 'dict[str, str]'" class="form-group form-group-inline">
        <label>
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div class="vars-container">
          <button @click="$emit('open-var-modal', field.name)" class="add-var-button">
            <span class="plus-icon" aria-hidden="true">
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  fill="currentColor"
                  d="M8 2.5a.75.75 0 0 1 .75.75v4h4a.75.75 0 0 1 0 1.5h-4v4a.75.75 0 0 1-1.5 0v-4h-4a.75.75 0 0 1 0-1.5h4v-4A.75.75 0 0 1 8 2.5z"
                />
              </svg>
            </span>
            {{ $t('dynamic_form_field.add_key_value') }}
          </button>
          <div
            v-if="formData[field.name] && hasDictEntries(formData[field.name])"
            class="vars-list"
          >
            <div
              v-for="(varValue, varKey) in formData[field.name]"
              :key="varKey"
              class="var-item"
              @click="$emit('edit-var', field.name, varKey)"
            >
              <span class="var-name">{{ varKey }}</span>
              <span class="var-separator">|</span>
              <span class="var-value">{{ varValue }}</span>
              <button
                class="delete-var-button"
                @click.stop="$emit('delete-var', field.name, varKey)"
                :title="$t('dynamic_form_field.delete_variable')"
              >
                ×
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- List of strings field -->
      <div v-else-if="isList && field.type.includes('str')" class="form-group form-group-inline">
        <label>
          {{ fieldLabel }}
          <span v-if="field.required" class="required-asterisk">*</span>
          <RichTooltip
            v-if="field.description"
            :content="{ description: fieldDescription }"
            placement="top"
          >
            <span class="help-icon" tabindex="0">?</span>
          </RichTooltip>
        </label>
        <div class="list-container">
          <button @click="$emit('open-list-item-modal', field.name)" class="add-list-button">
            <span class="plus-icon" aria-hidden="true">
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  fill="currentColor"
                  d="M8 2.5a.75.75 0 0 1 .75.75v4h4a.75.75 0 0 1 0 1.5h-4v4a.75.75 0 0 1-1.5 0v-4h-4a.75.75 0 0 1 0-1.5h4v-4A.75.75 0 0 1 8 2.5z"
                />
              </svg>
            </span>
            {{ $t('dynamic_form_field.add_entry') }}
          </button>
          <div v-if="formData[field.name] && formData[field.name].length > 0" class="list-items">
            <div
              v-for="(item, index) in formData[field.name]"
              :key="index"
              class="list-item"
            >
              <span class="item-value">{{ item }}</span>
              <button
                class="delete-item-button"
                @click.stop="$emit('delete-list-item', field.name, index)"
                :title="$t('dynamic_form_field.delete_item')"
              >
                ×
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import RichTooltip from '@/components/common/RichTooltip.vue'
import { getFieldLabel, getFieldDescription, getEnumOptionLabel, getEnumOptionDescription } from '@/utils/formUtils.js'

const { t } = useI18n()

// Labels/descriptions: locale key first, then backend-provided text (see formUtils).
const fieldLabel = computed(() => getFieldLabel(props.field))
const fieldDescription = computed(() => getFieldDescription(props.field))
const optionLabel = (option) => getEnumOptionLabel(props.field, option)

const optionDescription = (option) => getEnumOptionDescription(props.field, option)

const props = defineProps({
  field: {
    type: Object,
    required: true
  },
  modalId: {
    type: String,
    required: true
  },
  formData: {
    type: Object,
    required: true
  },
  childSummaries: {
    type: Object,
    default: () => ({})
  },
  recursive: {
    type: Boolean,
    default: false
  },
  isVisible: {
    type: Boolean,
    default: true
  },
  // If true, and this field is a childRoute config, render nothing (handled by parent inline)
  expandInline: {
    type: Boolean,
    default: false
  },
  // Helpers passed from parent or reimplemented
  canOpenConditionalChildModal: {
    type: Boolean,
    default: true
  },
  conditionalChildButtonLabel: {
    type: String,
    default: ''
  },
  activeChildRoute: {
    type: Object,
    default: null
  },
  isReadOnly: {
    type: Boolean,
    default: false
  }
})

const isReadOnly = computed(() => props.isReadOnly)

const emit = defineEmits([
  'update:form-data',
  'open-child-modal',
  'clear-child-entry',
  'delete-child-entry',
  'open-conditional-child-modal',
  'handle-enum-change',
  'open-var-modal',
  'edit-var',
  'delete-var',
  'open-list-item-modal',
  'delete-list-item'
])

// Computed property to allow v-model binding with mutation of prop object (common in complex forms)
// OR better, just use props.formData[field.name] directly as Vue 3 proxies allow it, though strict mode warns.
// For FormGenerator, we generally mutate the reactive modal object.
const internalFormData = computed(() => props.formData)

// Custom select filtering state
const showDropdown = ref(false)
const filterText = ref('')
const selectWrapper = ref(null)
const dropdownRect = reactive({
  top: 0,
  left: 0,
  width: 0
})

const updateDropdownPosition = () => {
  if (selectWrapper.value) {
    const rect = selectWrapper.value.getBoundingClientRect()
    dropdownRect.top = rect.bottom
    dropdownRect.left = rect.left
    dropdownRect.width = rect.width
  }
}

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownRect.top + 4}px`,
  left: `${dropdownRect.left}px`,
  width: `${dropdownRect.width}px`,
  zIndex: 10000
}))

const toggleDropdown = () => {
  if (props.isReadOnly) return
  if (!showDropdown.value) {
    updateDropdownPosition()
    showDropdown.value = true
    // Add escape listener
    window.addEventListener('scroll', closeOnScroll, true)
    window.addEventListener('mousedown', handleOutsideClick)
  } else {
    closeDropdown()
  }
}

const closeDropdown = () => {
  showDropdown.value = false
  window.removeEventListener('scroll', closeOnScroll, true)
  window.removeEventListener('mousedown', handleOutsideClick)
}

const closeOnScroll = () => {
  if (showDropdown.value) closeDropdown()
}

const handleOutsideClick = (e) => {
  if (selectWrapper.value && !selectWrapper.value.contains(e.target)) {
    closeDropdown()
  }
}

// The dropdown listeners are attached to window while open; make sure they do not
// outlive the component (e.g. field re-keyed/unmounted while its dropdown is open).
onUnmounted(() => {
  window.removeEventListener('scroll', closeOnScroll, true)
  window.removeEventListener('mousedown', handleOutsideClick)
})

const isList = computed(() => {
  return props.field.type && props.field.type.includes('list[')
})

const hasChildRoutes = computed(() => {
  return Array.isArray(props.field?.childRoutes) && props.field.childRoutes.length > 0
})

const hasChildValue = computed(() => {
  const value = props.formData?.[props.field.name]
  if (Array.isArray(value)) {
    return value.length > 0
  }
  return value !== null && value !== undefined && value !== ''
})

const childNodeButtonLabel = computed(() => {
  if (isList.value) {
    return t('dynamic_form_field.add_entry')
  }
  return props.formData[props.field.name] ? t('dynamic_form_field.edit_child', { child: props.field.childNode }) : t('dynamic_form_field.configure_child', { child: props.field.childNode })
})

// Filtered options for custom select
const filteredOptions = computed(() => {
  const options = props.field.enumOptions || props.field.enum || []
  if (!filterText.value.trim()) {
    return options
  }
  const filter = filterText.value.toLowerCase()
  return options.filter(option => {
    return String(optionLabel(option)).toLowerCase().includes(filter)
  })
})

// Computed input value for custom select
const inputValue = computed(() => {
  if (showDropdown.value) {
    return filterText.value
  }
  return getSelectedLabel()
})

// Helpers
const hasDictEntries = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  return Object.keys(value).length > 0
}

const describeChildEntry = (entry, index) => {
  if (entry && typeof entry === 'object') {
    if (entry.id) return entry.id
    if (entry.name) return entry.name
    if (entry.type) return entry.type
  }
  return `${props.field.childNode} #${index + 1}`
}

// Input handlers
// formData is the parent's reactive modal state shared by reference (see FormGenerator);
// writing into it directly is the intended data flow, so the lint rule is silenced here.
const onInput = (value) => {
  // eslint-disable-next-line vue/no-mutating-props
  props.formData[props.field.name] = value
}

const onInputNumber = (value) => {
    // Check if empty string
    if (value === "") {
        // eslint-disable-next-line vue/no-mutating-props
        props.formData[props.field.name] = null
        return
    }
  // eslint-disable-next-line vue/no-mutating-props
  props.formData[props.field.name] = Number(value)
}

const onBooleanSwitchChange = (checked) => {
  // eslint-disable-next-line vue/no-mutating-props
  props.formData[props.field.name] = checked
}

const handleLocalScrollWheel = (event) => {
  const target = event.currentTarget
  if (!target) {
    return
  }

  const isDropdown = target.classList.contains('custom-select-dropdown')

  if (target.scrollHeight <= target.clientHeight) {
    if (isDropdown) {
      event.stopPropagation()
      event.preventDefault()
    }
    return
  }

  const isScrollingUp = event.deltaY < 0
  const isScrollingDown = event.deltaY > 0
  const atTop = target.scrollTop <= 0
  const atBottom = Math.ceil(target.scrollTop + target.clientHeight) >= target.scrollHeight

  event.stopPropagation()

  if ((isScrollingUp && atTop) || (isScrollingDown && atBottom)) {
    event.preventDefault()
  }
}

const selectOption = (value) => {
  // eslint-disable-next-line vue/no-mutating-props
  props.formData[props.field.name] = value
  closeDropdown()
  emit('handle-enum-change', props.field)
}

const getSelectedLabel = () => {
  const currentValue = props.formData[props.field.name]
  if (currentValue === null || currentValue === undefined) {
    return ''
  }

  const options = props.field.enumOptions || props.field.enum || []
  const selectedOption = options.find(option => {
    const optionValue = typeof option === 'string' ? option : option.value
    return optionValue === currentValue
  })

  if (selectedOption) {
    return optionLabel(selectedOption)
  }

  return currentValue
}
</script>

<style scoped>
.form-field {
  margin-bottom: 18px;
}

.form-group {
  margin-bottom: 18px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-1);
  font-weight: 500;
  font-size: 13px;
}

.form-group-inline {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.form-group-inline label {
  margin-bottom: 0;
  flex-shrink: 0;
  min-width: 96px;
}

.form-group-inline > *:not(label) {
  flex: 1;
}

.required-asterisk {
  color: var(--danger);
  margin-left: 4px;
}

.help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 6px;
  border-radius: 999px;
  border: 1px solid rgb(var(--ink) / 0.3);
  font-size: 11px;
  line-height: 1;
  cursor: default;
  color: rgb(var(--ink-soft) / 0.7);
  background-color: transparent;
  transition: border-color 0.2s ease, color 0.2s ease;
}

.help-icon:hover {
  border-color: var(--accent-indigo);
  color: var(--accent-indigo);
}

.form-input,
.form-select,
.form-textarea,
.multi-select-options input[type='checkbox'] {
  font-family: 'Inter', sans-serif;
}

.form-input {
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background-color: rgb(var(--panel-10) / 0.6);
  color: var(--text-1);
  font-size: 13px;
  box-sizing: border-box;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.form-textarea {
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background-color: rgb(var(--panel-10) / 0.6);
  color: var(--text-1);
  font-size: 13px;
  box-sizing: border-box;
  min-height: 80px;
  resize: vertical;
  overscroll-behavior: contain;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.form-textarea:focus {
  outline: none;
  border-color: var(--accent-indigo);
  background-color: rgb(var(--panel-15) / 0.85);
  box-shadow: 0 0 0 1px rgb(var(--accent-indigo-rgb) / 0.5);
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-indigo);
  background-color: rgb(var(--panel-15) / 0.85);
  box-shadow: 0 0 0 1px rgb(var(--accent-indigo-rgb) / 0.5);
}

.form-input::placeholder {
  color: rgb(var(--ink) / 0.35);
}

.form-select {
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background-color: rgb(var(--panel-10) / 0.6);
  color: var(--text-1);
  font-size: 13px;
  box-sizing: border-box;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.form-select:focus {
  outline: none;
  border-color: var(--accent-indigo);
  background-color: rgb(var(--panel-15) / 0.85);
}

/* Switch Styles */
.switch-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 38px; /* Match input height roughly */
}

.switch-label-text {
  margin-bottom: 0 !important; /* Override label margin */
}

.switch-container {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  margin-left: 12px;
}

.switch-container input {
  opacity: 0;
  width: 0;
  height: 0;
}

.switch-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgb(var(--ink) / 0.14);
  transition: background-color 0.2s ease, border-color 0.2s ease;
  border-radius: 24px;
  border: 1px solid rgb(var(--ink) / 0.14);
}

.switch-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1);
  border-radius: 50%;
  will-change: transform;
}

input:checked + .switch-slider {
  background-color: var(--accent-indigo);
  border-color: #4facfe;
}

input:focus + .switch-slider {
  box-shadow: 0 0 1px #4facfe;
}

input:checked + .switch-slider:before {
  transform: translateX(20px);
}

.form-select option {
  background-color: var(--surface-3);
  color: var(--text-1);
}

.multi-select-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.multi-select-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background-color: rgb(var(--ink) / 0.04);
  border: 1px solid rgb(var(--ink) / 0.14);
  font-size: 12px;
  color: rgb(var(--ink-soft) / 0.9);
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.multi-select-option:hover {
  background-color: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--accent-indigo-rgb) / 0.6);
}

.option-label {
  white-space: nowrap;
}

/* Variables styles */
.vars-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-readonly {
  background-color: rgb(var(--ink) / 0.05); /* Slightly lighter background to indicate disabled-ish but readable */
  border-color: rgb(var(--ink) / 0.05);
  cursor: text; /* Allow text selection */
  color: rgb(var(--ink-soft) / 0.6);
}

.input-readonly:focus {
  border-color: rgb(var(--ink) / 0.05);
  box-shadow: none;
}

.vars-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.var-name {
  flex: 0 0 auto;
  font-weight: 600;
  min-width: 90px;
  margin-left: 10px;
  font-size: 12px;
}

.var-separator {
  font-size: 12px;
  color: var(--text-muted-1);
  margin: 0 5px;
}

.var-value {
  flex: 1;
  color: var(--text-soft-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.delete-var-button {
  background: transparent;
  border: none;
  color: var(--text-muted-5);
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
  line-height: 1;
  margin-left: 8px;
}

.delete-var-button:hover {
  color: var(--danger);
}

/* List items styles */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.list-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.var-item,
.list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 420px;
  padding: 7px 12px;
  background-color: rgb(var(--chip-90) / 0.9);
  border: 1px solid rgb(var(--ink) / 0.14);
  border-radius: 10px;
  color: var(--text-1);
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease;
  font-size: 13px;
  gap: 12px;
}

.var-item:hover,
.list-item:hover {
  background-color: rgb(var(--chip-110) / 0.95);
  border-color: rgb(var(--accent-indigo-rgb) / 0.7);
}

.item-value {
  flex: 1;
}

.delete-item-button {
  background: transparent;
  border: none;
  color: var(--text-muted-5);
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
  line-height: 1;
  margin-left: 8px;
}

.delete-item-button:hover {
  color: var(--danger);
}

.child-node-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.child-node-controls {
  display: flex;
  align-items: center;
  gap: 5px;
}

.clear-child-button {
  background: transparent;
  border: none;
  color: var(--text-muted-5);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
  line-height: 1;
}

.clear-child-button:hover {
  color: var(--danger);
}

.add-child-button,
.add-list-button,
.add-var-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.16);
  background-color: rgb(var(--ink) / 0.14);
  color: rgb(var(--ink-soft) / 0.9);
  cursor: pointer;
  font-size: 13px;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.add-child-button:hover,
.add-list-button:hover,
.add-var-button:hover {
  background-color: rgb(var(--ink) / 0.08);
}

.add-child-button .plus-icon,
.add-list-button .plus-icon,
.add-var-button .plus-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}

.add-child-button .plus-icon svg,
.add-list-button .plus-icon svg,
.add-var-button .plus-icon svg {
  display: block;
}

.add-child-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  border-color: rgb(var(--ink) / 0.1);
  background-color: rgb(var(--panel-74) / 0.8);
  color: rgb(var(--ink-mute) / 0.7);
}

.child-node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.child-node-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 14px;
  background-color: rgb(var(--chip-90) / 0.9);
  border: 1px solid rgb(var(--ink) / 0.14);
  border-radius: 10px;
  color: var(--text-1);
  font-size: 13px;
  gap: 12px;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.child-node-item:hover {
  background-color: rgb(var(--chip-110) / 0.95);
  border-color: rgb(var(--accent-indigo-rgb) / 0.7);
}

.child-node-name {
  flex: 1;
}

.child-node-actions {
  display: flex;
  gap: 8px;
}

.child-node-item-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.child-node-summary {
  padding: 6px 12px;
  margin-left: 0;
  background-color: rgb(var(--panel-60) / 0.6);
  border: 1px solid rgb(var(--ink) / 0.08);
  border-radius: 8px;
  color: rgb(var(--ink-mute) / 0.85);
  font-size: 12px;
  line-height: 1.4;
  word-wrap: break-word;
  overflow-wrap: break-word;
  white-space: pre-line;
}

.edit-child-button,
.delete-child-button {
  padding: 6px 10px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.edit-child-button {
  background-color: rgb(var(--chip-117) / 0.95);
  color: var(--text-1);
}

.edit-child-button:hover {
  background-color: rgb(var(--chip-136) / 0.98);
}

.delete-child-button {
  background-color: rgb(var(--chip-90) / 0.9);
  color: var(--text-1);
}

.delete-child-button:hover {
  background-color: rgb(var(--chip-110) / 0.95);
}

.child-node-hint {
  padding: 6px 8px;
  color: rgb(var(--ink-muter) / 0.9);
  font-size: 12px;
}

/* Custom select styles */

.custom-select-wrapper {
  position: relative;
  height: 38px; /* Fixed height to prevent absolute child from stretching parent */
}

.custom-select-input {
  cursor: pointer;
  height: 100%;
}

.custom-select-input:focus {
  cursor: text;
}

.custom-select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: rgb(var(--ink-soft) / 0.7);
  font-size: 12px;
  pointer-events: none;
  transition: transform 0.2s ease;
}

.custom-select-arrow.arrow-open {
  transform: translateY(-50%) rotate(180deg);
}

:global(.custom-select-dropdown) {
  position: fixed;
  z-index: 10000;
  max-height: 200px;
  overflow-y: auto;
  overscroll-behavior: contain;
  background-color: var(--surface-1);
  border: 1px solid rgb(var(--ink) / 0.2);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgb(var(--shade) / 0.8);
  box-sizing: border-box;
}

:global(.custom-select-option) {
  padding: 10px 14px;
  cursor: pointer;
  color: var(--text-1);
  font-size: 13px;
  transition: background-color 0.2s ease;
}

:global(.custom-select-option:hover) {
  background-color: rgb(var(--ink) / 0.1);
}

:global(.custom-select-option.option-selected) {
  background-color: rgb(var(--accent-indigo-rgb) / 0.2);
  color: var(--accent-indigo);
  font-weight: 500;
}

:global(.custom-select-no-results) {
  padding: 10px 12px;
  color: rgb(var(--ink-muter) / 0.7);
  font-size: 12px;
  text-align: center;
  font-style: italic;
}

.select-disabled .custom-select-input {
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .help-icon,
  .form-input,
  .form-textarea,
  .form-select,
  .switch-slider,
  .switch-slider:before,
  .multi-select-option,
  .var-item,
  .list-item,
  .delete-var-button,
  .delete-item-button,
  .clear-child-button,
  .add-child-button,
  .add-list-button,
  .add-var-button,
  .child-node-item,
  .edit-child-button,
  .delete-child-button,
  .custom-select-arrow,
  :global(.custom-select-option) {
    transition: none;
  }
}
</style>
