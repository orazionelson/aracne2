<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  noteType: 'alpha' | 'numeric';
  /** Pre-filled content when editing an existing note. */
  initialContent?: string;
  /** True when re-opening an existing note (vs. inserting a new one). */
  isEditing?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  confirm: [content: string];
}>();

const noteContent = ref('');
const textareaRef = ref<HTMLTextAreaElement | null>(null);

// Reset / pre-fill content and focus textarea whenever the modal opens.
watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      noteContent.value = props.initialContent ?? '';
      await nextTick();
      textareaRef.value?.focus();
    }
  },
);

function handleConfirm(): void {
  emit('confirm', noteContent.value);
  emit('update:modelValue', false);
}

function handleCancel(): void {
  emit('update:modelValue', false);
}

function title(): string {
  if (props.isEditing) {
    return props.noteType === 'alpha'
      ? t('documents.note_edit_alpha_title')
      : t('documents.note_edit_numeric_title');
  }
  return props.noteType === 'alpha'
    ? t('documents.note_alpha_title')
    : t('documents.note_numeric_title');
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="handleCancel"
    >
      <div class="w-[480px] rounded-lg border border-gray-200 bg-white shadow-xl">
        <!-- Header -->
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <span class="text-sm font-semibold text-gray-700">{{ title() }}</span>
          <button class="text-gray-400 hover:text-gray-700" @click="handleCancel">✕</button>
        </div>

        <!-- Body -->
        <div class="px-4 py-4">
          <textarea
            ref="textareaRef"
            v-model="noteContent"
            rows="4"
            :placeholder="t('documents.note_content_placeholder')"
            class="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm focus:border-indigo-400 focus:outline-none"
            @keydown.ctrl.enter.prevent="handleConfirm"
          />
          <p class="mt-1 text-xs text-gray-400">{{ t('documents.note_ctrl_enter') }}</p>
        </div>

        <!-- Footer -->
        <div class="flex justify-end gap-2 border-t border-gray-100 px-4 py-3">
          <button
            class="rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            @click="handleCancel"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            @click="handleConfirm"
          >
            {{ isEditing ? t('documents.note_save') : t('documents.note_insert') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
