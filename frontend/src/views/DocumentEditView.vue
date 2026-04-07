<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCollectionStore } from '@/stores/collections';
import { useSchemaStore } from '@/stores/schemas';
import type { ValidationResult } from '@/stores/schemas';
import { useCodeMirror } from '@/composables/useCodeMirror';
import { loadTeiSchema, type CM5Schema } from '@/utils/teiSchema';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();
const schemaStore = useSchemaStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

// ── State ──────────────────────────────────────────────────────────────────────
const isLoading = ref(true);
const isSchemaLoading = ref(true);
const isSaving = ref(false);
const isValidating = ref(false);
const error = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);
const schema = ref<CM5Schema | undefined>(undefined);
const hasValidationSchema = ref(false);
const validationResult = ref<ValidationResult | null>(null);

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

// ── CM5 schema loader ──────────────────────────────────────────────────────────
async function loadCm5Schema(schemaId: string | null): Promise<CM5Schema | undefined> {
  if (schemaId) {
    // Try to load CM5 schema from the API (collection-specific schema)
    const schemaRecord = schemaStore.schemas.find((s) => s.id === schemaId);
    if (schemaRecord?.cm5_filename) {
      try {
        const xmlText = await schemaStore.fetchCm5Content(schemaId);
        return loadTeiSchema(xmlText, 'text');
      } catch {
        // Fall through to global fallback
      }
    }
  }
  // Global fallback: static tei-p5.xml served from /cmschemas/
  try {
    return await loadTeiSchema('/cmschemas/tei-p5.xml', 'url');
  } catch {
    return undefined;
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Load collection (for schema_id), document XML, and available schemas in parallel
  const [collectionResult, xmlResult] = await Promise.allSettled([
    store.fetchCollection(slug),
    store.fetchDocumentRaw(slug, filename),
  ]);

  // Also ensure schemas list is populated (needed to look up cm5_filename)
  if (schemaStore.schemas.length === 0) {
    try { await schemaStore.fetchSchemas(); } catch { /* non-fatal */ }
  }

  if (xmlResult.status === 'fulfilled') {
    xmlContent.value = xmlResult.value;
    setValue(xmlResult.value);
  } else {
    error.value = t('common.error');
  }

  const schemaId = collectionResult.status === 'fulfilled'
    ? (store.current?.schema_id ?? null)
    : null;

  // Check if the collection has a validation schema for the Validate button
  if (schemaId) {
    const rec = schemaStore.schemas.find((s) => s.id === schemaId);
    hasValidationSchema.value = !!rec?.validation_format;
  }

  schema.value = await loadCm5Schema(schemaId);

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
    // Run validation after save (non-blocking)
    if (hasValidationSchema.value) {
      runValidation();
    }
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t('common.error');
  } finally {
    isSaving.value = false;
  }
}

// ── Validate ───────────────────────────────────────────────────────────────────
async function runValidation(): Promise<void> {
  isValidating.value = true;
  validationResult.value = null;
  try {
    validationResult.value = await schemaStore.validateDocument(slug, filename);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    validationResult.value = {
      valid: false,
      errors: [{ line: 0, col: 0, message: msg ?? t('common.error') }],
    };
  } finally {
    isValidating.value = false;
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
          :title="isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen') }}
        </button>
        <!-- Validate button -->
        <button
          v-if="hasValidationSchema"
          :disabled="isValidating || isLoading"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          @click="runValidation"
        >
          {{ isValidating ? t('documents.validating') : t('documents.validate') }}
        </button>
        <!-- Validation status badge -->
        <span
          v-if="validationResult && validationResult.valid"
          class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700"
        >
          {{ t('documents.valid') }}
        </span>
        <span
          v-else-if="validationResult && !validationResult.valid"
          class="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
        >
          {{ t('documents.invalid', { n: validationResult.errors.length }) }}
        </span>
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

    <!-- Validation errors panel -->
    <div
      v-if="validationResult && !validationResult.valid"
      class="mt-2 flex-shrink-0 max-h-40 overflow-y-auto rounded border border-red-200 bg-red-50"
    >
      <table class="w-full text-xs">
        <tbody>
          <tr
            v-for="(err, i) in validationResult.errors"
            :key="i"
            class="border-b border-red-100 last:border-0"
          >
            <td class="px-3 py-1 font-mono text-red-400 whitespace-nowrap w-20">
              {{ err.line }}:{{ err.col }}
            </td>
            <td class="px-3 py-1 text-red-700">{{ err.message }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
