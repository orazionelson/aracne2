<script setup lang="ts">
/**
 * OpenAlex search panel. Unlike the name-authority panels, this one
 * does not write @ref on an enclosing tag — it inserts a full TEI
 * <biblStruct> fragment at the cursor (same shape as the CrossRef
 * panel).
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useOpenAlexStore, type OpenAlexHit } from "@/stores/openalex";

const props = defineProps<{
  initialQuery?: string;
  /** Callback that drops the biblStruct XML at the cursor. */
  onInsert: (xml: string) => void;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const { t } = useI18n();
const store = useOpenAlexStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<OpenAlexHit[]>([]);
const error = ref<string | null>(null);
const lastInserted = ref<string | null>(null);

async function runSearch(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) { results.value = []; error.value = null; return; }
  error.value = null;
  try {
    results.value = await store.search(q);
  } catch (err) {
    error.value = (err as Error).message ?? t("common.error");
    results.value = [];
  }
}
const debouncedSearch = useDebounceFn(runSearch, 400);
watch(query, () => { debouncedSearch(); });
onMounted(() => { if (query.value.trim().length >= 2) runSearch(); });
function clearQuery(): void { query.value = ""; results.value = []; error.value = null; }
function insertHit(hit: OpenAlexHit): void {
  props.onInsert(hit.biblstruct_xml);
  lastInserted.value = hit.xml_id;
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#0b5394]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12a9 9 0 0 0 9 9 9 9 0 0 0 9-9 9 9 0 0 0-9-9" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t("openalex.panel_title") }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <input v-model="query" type="text" :placeholder="t('openalex.search_placeholder')" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100" @keydown.enter.prevent="runSearch()" />
        <button v-if="query" type="button" class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800" @click="clearQuery">✕</button>
      </div>
      <p v-if="store.isSearching" class="text-xs text-gray-400 animate-pulse">{{ t("common.loading") }}</p>
    </div>

    <div v-if="lastInserted" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs text-green-700 dark:border-gray-700 dark:text-green-400">
      {{ t("openalex.inserted", { id: lastInserted }) }}
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!store.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400">{{ t("openalex.idle_hint") }}</p>
      <p v-else-if="!store.isSearching && results.length === 0" class="px-3 py-3 text-xs text-gray-400">{{ t("openalex.no_results") }}</p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.preview.openalex_id" class="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="line-clamp-2 text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.preview.title }}</p>
              <p v-if="hit.preview.authors.length" class="mt-0.5 line-clamp-1 text-xs text-gray-500 dark:text-gray-400">
                {{ hit.preview.authors.slice(0, 3).join(" · ") }}<span v-if="hit.preview.authors.length > 3"> · +{{ hit.preview.authors.length - 3 }}</span>
              </p>
              <p class="mt-0.5 text-[11px] text-gray-400">
                <span v-if="hit.preview.year">{{ hit.preview.year }}</span>
                <span v-if="hit.preview.container"> · <span class="italic">{{ hit.preview.container }}</span></span>
                <span v-if="hit.preview.type"> · {{ hit.preview.type }}</span>
              </p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400">
                OpenAlex {{ hit.preview.openalex_id }}<span v-if="hit.preview.doi"> · DOI {{ hit.preview.doi }}</span>
              </p>
            </div>
            <button type="button" class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700" @click="insertHit(hit)">{{ t("openalex.insert") }}</button>
          </div>
        </li>
      </ul>
    </div>

    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("openalex.footer_hint") }}
    </div>
  </div>
</template>
