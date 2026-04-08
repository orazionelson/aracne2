<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCollectionStore } from '@/stores/collections';
import { useSchemaStore } from '@/stores/schemas';
import { useSettingStore } from '@/stores/settings';
import type { ValidationResult } from '@/stores/schemas';
import { useCodeMirror } from '@/composables/useCodeMirror';
import { loadTeiSchema, type CM5Schema } from '@/utils/teiSchema';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const settingStore = useSettingStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

// ── Editor mode ────────────────────────────────────────────────────────────────
const splitMode = computed(() => settingStore.getSetting('document_editor_mode') === 'split');

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
const schemaWarning = ref<string | null>(null);

// ── Split-mode state ───────────────────────────────────────────────────────────
const activeEditorTab = ref<'header' | 'body'>('header');
// Outer XML context preserved for reassembly
const outerBefore = ref('');
const outerBetween = ref(''); // whitespace/elements between </teiHeader> and <text>
const outerAfter = ref('');
// Drafts for each tab (updated on every tab switch and on save)
const headerXmlDraft = ref('');
const bodyXmlDraft = ref('');
// False when the document lacks <teiHeader>/<text> — falls back to single editor
const canSplit = ref(true);

// ── Editor ─────────────────────────────────────────────────────────────────────
const editorContainer = ref<HTMLElement | null>(null);

const { getValue, setValue, refresh, toggleFullscreen, prettyPrint, isFullscreen } = useCodeMirror(
  editorContainer,
  {
    get schema() { return schema.value; },
    onChange: () => { saved.value = false; },
  },
);

// ── XML split utilities ────────────────────────────────────────────────────────

/**
 * Find the start/end byte offsets of the first <tagName>…</tagName> block.
 * Uses depth tracking so nested same-name elements are handled correctly.
 */
function findBlock(xml: string, tagName: string): { start: number; end: number } | null {
  const openTag = `<${tagName}`;
  const closeTag = `</${tagName}>`;

  // Find the first occurrence of <tagName followed by whitespace, > or /
  let firstOpen = -1;
  for (let i = 0; i <= xml.length - openTag.length; i++) {
    if (xml.startsWith(openTag, i)) {
      const next = xml[i + openTag.length];
      if (next === '>' || next === '/' || next === ' ' || next === '\t' || next === '\n' || next === '\r') {
        firstOpen = i;
        break;
      }
    }
  }
  if (firstOpen === -1) return null;

  let depth = 0;
  let i = firstOpen;
  while (i < xml.length) {
    if (xml.startsWith(closeTag, i)) {
      depth--;
      if (depth === 0) return { start: firstOpen, end: i + closeTag.length };
      i += closeTag.length;
    } else if (xml.startsWith(openTag, i)) {
      const next = xml[i + openTag.length];
      if (next === '>' || next === '/' || next === ' ' || next === '\t' || next === '\n' || next === '\r') {
        depth++;
      }
      i++;
    } else {
      i++;
    }
  }
  return null; // unbalanced — document is malformed
}

/** Split a TEI XML string into its structural parts. Returns null if the
 *  document does not contain both <teiHeader> and <text>. */
function splitXml(xml: string): {
  header: string;
  body: string;
  before: string;
  between: string;
  after: string;
} | null {
  const hb = findBlock(xml, 'teiHeader');
  const tb = findBlock(xml, 'text');
  if (!hb || !tb) return null;

  return {
    before:   xml.slice(0, hb.start),
    header:   xml.slice(hb.start, hb.end),
    between:  xml.slice(hb.end, tb.start),
    body:     xml.slice(tb.start, tb.end),
    after:    xml.slice(tb.end),
  };
}

/** Reassemble a full TEI XML string from its parts. */
function reassembleXml(newHeader: string, newBody: string): string {
  return outerBefore.value + newHeader + outerBetween.value + newBody + outerAfter.value;
}

// ── CM5 schema loader ──────────────────────────────────────────────────────────
async function loadCm5Schema(schemaId: string | null): Promise<CM5Schema | undefined> {
  if (schemaId) {
    const schemaRecord = schemaStore.schemas.find((s) => s.id === schemaId);
    if (schemaRecord?.cm5_filename) {
      try {
        const xmlText = await schemaStore.fetchCm5Content(schemaId);
        return await loadTeiSchema(xmlText, 'text');
      } catch (err) {
        schemaWarning.value = err instanceof Error ? err.message : String(err);
      }
    }
  }
  try {
    return await loadTeiSchema('/cmschemas/tei-p5.xml', 'url');
  } catch {
    return undefined;
  }
}

// ── Tab switching ──────────────────────────────────────────────────────────────
function switchTab(tab: 'header' | 'body'): void {
  if (tab === activeEditorTab.value) return;
  const current = getValue();
  if (tab === 'body') {
    headerXmlDraft.value = current;
    setValue(bodyXmlDraft.value);
  } else {
    bodyXmlDraft.value = current;
    setValue(headerXmlDraft.value);
  }
  activeEditorTab.value = tab;
  saved.value = false;
}

// ── Get full XML value (handles both modes) ────────────────────────────────────
function getFullValue(): string {
  if (!splitMode.value || !canSplit.value) return getValue();
  // Flush the active tab into the correct draft slot before reassembling
  if (activeEditorTab.value === 'header') {
    return reassembleXml(getValue(), bodyXmlDraft.value);
  } else {
    return reassembleXml(headerXmlDraft.value, getValue());
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────
onMounted(async () => {
  const [collectionResult, xmlResult] = await Promise.allSettled([
    store.fetchCollection(slug),
    store.fetchDocumentRaw(slug, filename),
  ]);

  if (schemaStore.schemas.length === 0) {
    try { await schemaStore.fetchSchemas(); } catch { /* non-fatal */ }
  }

  // Parse XML and populate draft slots — but do NOT call setValue yet.
  // The CM5 container is still hidden (v-show bound to isLoading). Calling
  // setValue on a display:none element leaves CM5 in a broken state where
  // the editor appears blank and inserts phantom blank lines on click.
  // We defer setValue until after the container is visible (below).
  let xmlToLoad = '';

  if (xmlResult.status === 'fulfilled') {
    const xml = xmlResult.value;
    if (splitMode.value) {
      const parts = splitXml(xml);
      if (parts) {
        headerXmlDraft.value = parts.header;
        bodyXmlDraft.value   = parts.body;
        outerBefore.value    = parts.before;
        outerBetween.value   = parts.between;
        outerAfter.value     = parts.after;
        canSplit.value = true;
        xmlToLoad = parts.header;
      } else {
        canSplit.value = false;
        xmlToLoad = xml;
      }
    } else {
      xmlToLoad = xml;
    }
  } else {
    error.value = t('common.error');
  }

  const schemaId = collectionResult.status === 'fulfilled'
    ? (store.current?.schema_id ?? null)
    : null;

  if (schemaId) {
    const rec = schemaStore.schemas.find((s) => s.id === schemaId);
    hasValidationSchema.value = !!rec?.validation_format;
  }

  schema.value = await loadCm5Schema(schemaId);
  isSchemaLoading.value = false;
  isLoading.value = false;

  // Wait for Vue to remove display:none (nextTick), then wait for the browser
  // to complete its layout pass (requestAnimationFrame) before calling
  // setValue + refresh. Without rAF, CM5 reads zero dimensions and enters
  // a broken state where clicks insert phantom blank lines.
  await nextTick();
  requestAnimationFrame(() => {
    if (xmlToLoad) setValue(xmlToLoad);
    refresh();
  });
});

// ── Save ───────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  isSaving.value = true;
  try {
    await store.updateDocument(slug, filename, getFullValue());
    saved.value = true;
    if (hasValidationSchema.value) runValidation();
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
        <span
          v-if="!isSchemaLoading && schemaWarning"
          class="max-w-sm truncate rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
          :title="schemaWarning"
        >
          {{ t('documents.schema_error') }}
        </span>
        <span
          v-if="splitMode && !isLoading && !canSplit"
          class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700"
          :title="t('documents.split_fallback_title')"
        >
          {{ t('documents.split_fallback') }}
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
        <button
          v-if="hasValidationSchema"
          :disabled="isValidating || isLoading"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          @click="runValidation"
        >
          {{ isValidating ? t('documents.validating') : t('documents.validate') }}
        </button>
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

    <!-- Split-mode tab bar -->
    <div
      v-if="splitMode && canSplit && !isLoading && !error"
      class="mb-2 flex flex-shrink-0 gap-1 border-b border-gray-200 pb-2"
    >
      <button
        :class="[
          'rounded-t px-4 py-1.5 text-xs font-medium transition-colors',
          activeEditorTab === 'header'
            ? 'bg-indigo-600 text-white'
            : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
        ]"
        @click="switchTab('header')"
      >
        &lt;teiHeader&gt;
      </button>
      <button
        :class="[
          'rounded-t px-4 py-1.5 text-xs font-medium transition-colors',
          activeEditorTab === 'body'
            ? 'bg-indigo-600 text-white'
            : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
        ]"
        @click="switchTab('body')"
      >
        &lt;text&gt;
      </button>
    </div>

    <!-- Loading / error states -->
    <p v-if="isLoading" class="text-sm text-gray-500">{{ t('common.loading') }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- CodeMirror container (single instance, content swapped on tab switch) -->
    <div
      v-show="!isLoading && !error"
      ref="editorContainer"
      class="min-h-0 flex-1 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
    />

    <!-- Validation errors panel -->
    <div
      v-if="validationResult && !validationResult.valid"
      class="mt-2 max-h-40 flex-shrink-0 overflow-y-auto rounded border border-red-200 bg-red-50"
    >
      <table class="w-full text-xs">
        <tbody>
          <tr
            v-for="(err, i) in validationResult.errors"
            :key="i"
            class="border-b border-red-100 last:border-0"
          >
            <td class="w-20 whitespace-nowrap px-3 py-1 font-mono text-red-400">
              {{ err.line }}:{{ err.col }}
            </td>
            <td class="px-3 py-1 text-red-700">{{ err.message }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
