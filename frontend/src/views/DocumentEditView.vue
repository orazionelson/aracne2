<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCollectionStore } from '@/stores/collections';
import { useCodeMirror } from '@/composables/useCodeMirror';
import { loadTeiSchema, type CM5Schema } from '@/utils/teiSchema';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

// ── State ──────────────────────────────────────────────────────────────────────
const isLoading = ref(true);
const isSchemaLoading = ref(true);
const isSaving = ref(false);
const error = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);
const schema = ref<CM5Schema | undefined>(undefined);

// ── Editor ─────────────────────────────────────────────────────────────────────
const editorContainer = ref<HTMLElement | null>(null);
const xmlContent = ref('');

const { getValue, setValue, toggleFullscreen, prettyPrint, isFullscreen } = useCodeMirror(
  editorContainer,
  {
    get schema() { return schema.value; },
    onChange: () => { saved.value = false; },
  },
);

// ── Init ───────────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Load XML content and schema in parallel
  const [xmlResult, schemaResult] = await Promise.allSettled([
    store.fetchDocumentRaw(slug, filename),
    loadTeiSchema('/cmschemas/tei-p5.xml'),
  ]);

  if (xmlResult.status === 'fulfilled') {
    xmlContent.value = xmlResult.value;
    setValue(xmlResult.value);
  } else {
    error.value = t('common.error');
  }

  if (schemaResult.status === 'fulfilled') {
    schema.value = schemaResult.value;
  }
  // Schema failure is non-fatal: editor works without autocomplete.

  isSchemaLoading.value = false;
  isLoading.value = false;
});

// ── Save ───────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  isSaving.value = true;
  try {
    await store.updateDocument(slug, filename, getValue());
    saved.value = true;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t('common.error');
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="flex h-[calc(100vh-3.5rem)] flex-col px-4 py-4">
    <!-- Header bar -->
    <div class="mb-3 flex flex-shrink-0 items-center justify-between">
      <div class="flex items-center gap-3">
        <button
          class="text-sm text-gray-500 hover:text-gray-800"
          @click="router.push({ name: 'collection-detail', params: { slug } })"
        >
          ← {{ slug }}
        </button>
        <span class="text-gray-300">/</span>
        <span class="font-mono text-sm font-semibold text-gray-800">{{ filename }}</span>
        <span class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
          {{ t('documents.action_edit') }}
        </span>
        <span
          v-if="!isSchemaLoading && schema"
          class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700"
          :title="t('documents.schema_loaded')"
        >
          TEI P5
        </span>
      </div>

      <!-- Toolbar -->
      <div class="flex items-center gap-2">
        <button
          :title="t('documents.pretty_print')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          @click="prettyPrint"
        >
          {{ t('documents.pretty_print') }}
        </button>
        <button
          :title="t('documents.fullscreen')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen') }}
        </button>
        <span v-if="saved" class="text-xs text-green-600">{{ t('documents.saved') }}</span>
        <span v-if="saveError" class="max-w-xs truncate text-xs text-red-600">{{ saveError }}</span>
        <button
          :disabled="isSaving || isLoading"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="handleSave"
        >
          {{ isSaving ? t('common.loading') : t('common.save') }}
        </button>
      </div>
    </div>

    <!-- Hints bar -->
    <p class="mb-2 flex-shrink-0 text-xs text-gray-400">
      Ctrl+Space autocomplete · Ctrl+/ commento · Ctrl+J tag corrispondente · F11 fullscreen · Ctrl+F cerca
    </p>

    <!-- Loading / error states -->
    <p v-if="isLoading" class="text-sm text-gray-500">{{ t('common.loading') }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- CodeMirror container -->
    <div
      v-show="!isLoading && !error"
      ref="editorContainer"
      class="min-h-0 flex-1 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
    />
  </div>
</template>
