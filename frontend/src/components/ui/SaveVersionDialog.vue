<script setup lang="ts">
/**
 * SaveVersionDialog — modal that captures a free-text checkpoint message
 * and posts a manual save through ``useDocumentVersionsStore``. Two
 * failure modes get explicit copy: the soft cap (409
 * MANUAL_VERSIONS_LIMIT_REACHED → friendly banner) and any other error
 * (generic banner with the backend message when available).
 */
import { ref, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { useDocumentVersionsStore } from '@/stores/documentVersions';

const { t } = useI18n();
const store = useDocumentVersionsStore();

const props = defineProps<{
  modelValue: boolean;
  slug: string;
  filename: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [versionNumber: number];
}>();

const message = ref('');
const localError = ref<string | null>(null);
const limitReached = ref<{ current: number; limit: number } | null>(null);
const textareaRef = ref<HTMLTextAreaElement | null>(null);

watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      message.value = '';
      localError.value = null;
      limitReached.value = null;
      await nextTick();
      textareaRef.value?.focus();
    }
  },
);

async function onSubmit(): Promise<void> {
  const trimmed = message.value.trim();
  if (!trimmed) {
    localError.value = t('version.manual.message_required');
    return;
  }
  localError.value = null;
  limitReached.value = null;

  const created = await store.manualSave(props.slug, props.filename, trimmed);
  if (created) {
    emit('saved', created.version_number);
    emit('update:modelValue', false);
    return;
  }
  // Try to surface the soft-cap 409 specifically.
  const raw = store.error ?? '';
  const limitMatch = raw.match(/\((\d+)\/(\d+)\)/);
  if (limitMatch) {
    limitReached.value = {
      current: Number(limitMatch[1]),
      limit: Number(limitMatch[2]),
    };
  } else {
    localError.value = raw || t('version.errors.save_failed');
  }
}

function onCancel(): void {
  emit('update:modelValue', false);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="onCancel"
    >
      <div class="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 class="mb-2 text-lg font-semibold text-slate-900">
          {{ t('version.manual.title') }}
        </h2>
        <p class="mb-4 text-sm text-slate-600">
          {{ t('version.manual.intro') }}
        </p>

        <div
          v-if="limitReached"
          class="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm"
        >
          <p class="font-medium text-amber-900">
            {{ t('version.manual.limit_reached_title') }}
          </p>
          <p class="mt-1 text-amber-800">
            {{
              t('version.manual.limit_reached_body', {
                limit: limitReached.limit,
              })
            }}
          </p>
          <p class="mt-2 text-xs text-amber-700">
            {{ t('version.manual.limit_help') }}
          </p>
        </div>

        <label
          for="version-save-message"
          class="mb-1 block text-sm font-medium text-slate-700"
        >
          {{ t('version.manual.message_label') }}
        </label>
        <textarea
          id="version-save-message"
          ref="textareaRef"
          v-model="message"
          rows="4"
          class="w-full rounded-md border border-slate-300 p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          :placeholder="t('version.manual.message_placeholder')"
          :disabled="store.isSaving"
        ></textarea>

        <p
          v-if="localError"
          class="mt-2 text-sm text-red-700"
        >
          {{ localError }}
        </p>

        <div class="mt-4 flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            :disabled="store.isSaving"
            @click="onCancel"
          >
            {{ t('version.manual.cancel') }}
          </button>
          <button
            type="button"
            class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            :disabled="store.isSaving || message.trim().length === 0"
            @click="onSubmit"
          >
            {{ t('version.manual.submit') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
