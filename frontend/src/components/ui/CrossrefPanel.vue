<script setup lang="ts">
/**
 * CrossRef DOI resolver panel.
 *
 * The editor pastes a DOI, the backend fetches CrossRef and returns a
 * ready-to-insert ``<biblStruct>`` fragment plus a human-readable
 * preview. Clicking "Insert" hands the XML back to the parent view
 * (DocumentEditView), which drops it into the CodeMirror buffer at the
 * cursor via ``insertXmlFragment``.
 */

import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  useCrossrefStore,
  type CrossrefLookupResult,
} from '@/stores/crossref';

const props = defineProps<{
  /** Pre-filled DOI — usually the editor's current selection when it looks like one. */
  initialDoi?: string;
  /**
   * Called when the editor clicks "Insert" — hands back the biblStruct
   * XML so the parent can drop it into the CodeMirror buffer.
   */
  onInsert: (xml: string) => void;
}>();

const emit = defineEmits<{ (e: 'close'): void }>();

const { t } = useI18n();
const biblio = useCrossrefStore();

// Strip common pastes of the form "https://doi.org/10.x/y" or "doi:10.x/y"
// so the editor does not have to clean the input before hitting Resolve.
function normaliseDoi(raw: string): string {
  return raw
    .trim()
    .replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')
    .replace(/^doi:/i, '');
}

const doiInput = ref(props.initialDoi ?? '');
const result = ref<CrossrefLookupResult | null>(null);
const error = ref<string | null>(null);
const justInserted = ref(false);

const canResolve = computed(() => doiInput.value.trim().length >= 3);

async function doResolve(): Promise<void> {
  const doi = normaliseDoi(doiInput.value);
  if (!doi) return;
  error.value = null;
  result.value = null;
  justInserted.value = false;
  try {
    result.value = await biblio.lookupDoi(doi);
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      error.value = t('crossref.error_not_found');
    } else if (status === 502) {
      error.value = t('crossref.error_upstream');
    } else {
      const msg = (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message;
      error.value = msg ?? t('common.error');
    }
  }
}

function doInsert(): void {
  if (!result.value) return;
  props.onInsert(result.value.biblstruct_xml);
  justInserted.value = true;
}

function doReset(): void {
  doiInput.value = '';
  result.value = null;
  error.value = null;
  justInserted.value = false;
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-gray-500 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t('crossref.panel_title') }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <!-- Input form -->
    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-3 dark:border-gray-700">
      <label class="text-xs font-medium text-gray-600 dark:text-gray-400">{{ t('crossref.doi_label') }}</label>
      <div class="flex items-center gap-2">
        <input
          v-model="doiInput"
          type="text"
          :placeholder="t('crossref.doi_placeholder')"
          autocomplete="off"
          class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          @keydown.enter.prevent="doResolve"
        />
        <button
          type="button"
          :disabled="!canResolve || biblio.isResolving"
          class="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="doResolve"
        >
          {{ biblio.isResolving ? t('common.loading') : t('crossref.resolve') }}
        </button>
      </div>
      <p class="text-[11px] text-gray-400 dark:text-gray-500">
        {{ t('crossref.doi_hint') }}
      </p>
    </div>

    <!-- Feedback -->
    <div v-if="error" class="flex-shrink-0 border-b border-gray-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-gray-700 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>
    <div v-else-if="justInserted" class="flex-shrink-0 border-b border-gray-200 bg-green-50 px-3 py-2 text-xs text-green-700 dark:border-gray-700 dark:bg-green-900/20 dark:text-green-300">
      {{ t('crossref.inserted', { id: result?.xml_id }) }}
    </div>

    <!-- Preview -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p
        v-if="!result && !error"
        class="px-3 py-4 text-xs text-gray-400 dark:text-gray-500"
      >
        {{ t('crossref.idle_hint') }}
      </p>
      <div v-if="result" class="space-y-3 px-3 py-3 text-sm">
        <!-- Preview card -->
        <div class="rounded border border-gray-200 p-3 dark:border-gray-700">
          <p v-if="result.preview.type" class="mb-1 inline-block rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
            {{ result.preview.type }}
          </p>
          <p v-if="result.preview.title" class="font-medium text-gray-800 dark:text-gray-100">
            {{ result.preview.title }}
          </p>
          <p v-if="result.preview.authors.length" class="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
            {{ result.preview.authors.join(', ') }}
          </p>
          <p v-if="result.preview.container" class="mt-1 text-xs italic text-gray-600 dark:text-gray-400">
            {{ result.preview.container }}
          </p>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-500">
            <span v-if="result.preview.year">{{ result.preview.year }}</span>
            <span v-if="result.preview.publisher"> · {{ result.preview.publisher }}</span>
          </p>
          <p v-if="result.preview.doi" class="mt-1 font-mono text-[11px] text-gray-400 dark:text-gray-500">
            <a
              :href="`https://doi.org/${result.preview.doi}`"
              target="_blank"
              rel="noopener"
              class="hover:underline"
            >{{ result.preview.doi }}</a>
          </p>
          <p class="mt-2 font-mono text-[11px] text-gray-400 dark:text-gray-500">
            xml:id = <span class="text-indigo-600 dark:text-indigo-400">{{ result.xml_id }}</span>
          </p>
        </div>

        <!-- Raw XML preview (collapsed style, selectable) -->
        <details class="rounded border border-gray-200 dark:border-gray-700">
          <summary class="cursor-pointer px-3 py-2 text-xs text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800/60">
            {{ t('crossref.show_xml') }}
          </summary>
          <pre class="max-h-60 overflow-auto border-t border-gray-200 bg-gray-50 px-3 py-2 text-[11px] dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"><code>{{ result.biblstruct_xml }}</code></pre>
        </details>

        <!-- Action buttons -->
        <div class="flex items-center justify-end gap-2">
          <button
            type="button"
            class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            @click="doReset"
          >
            {{ t('crossref.reset') }}
          </button>
          <button
            type="button"
            class="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            @click="doInsert"
          >
            {{ t('crossref.insert') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Footer hint -->
    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t('crossref.footer_hint') }}
    </div>
  </div>
</template>
