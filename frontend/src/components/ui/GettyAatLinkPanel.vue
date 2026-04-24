<script setup lang="ts">
/**
 * Getty AAT lookup panel. Writes @ref on a TEI <term> element —
 * AAT concepts are materials / techniques / object types, not
 * persons / places / institutions.
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useGettyAatStore, type GettyAatHit } from "@/stores/getty_aat";

type ApplyOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: "no_enclosing_tag" }
  | { ok: false; reason: "not_entity_tag"; tagName: string };

const props = defineProps<{
  initialQuery?: string;
  onApply: (uri: string) => ApplyOutcome;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const { t } = useI18n();
const getty = useGettyAatStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<GettyAatHit[]>([]);
const error = ref<string | null>(null);
const lastApplied = ref<{ aatId: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

async function runSearch(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) { results.value = []; error.value = null; return; }
  error.value = null;
  try {
    results.value = await getty.search(q);
  } catch (err) {
    error.value = (err as Error).message ?? t("common.error");
    results.value = [];
  }
}
const debouncedSearch = useDebounceFn(runSearch, 400);
watch(query, () => { debouncedSearch(); });
onMounted(() => { if (query.value.trim().length >= 2) runSearch(); });
function clearQuery(): void { query.value = ""; results.value = []; error.value = null; }
function applyHit(hit: GettyAatHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) { lastApplied.value = { aatId: hit.aat_id, tagName: outcome.tagName }; return; }
  applyError.value = outcome.reason === "no_enclosing_tag"
    ? t("getty_aat.apply_error_no_enclosing_tag")
    : t("getty_aat.apply_error_not_entity_tag", { tag: outcome.tagName });
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#b87333]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3l7 4v10l-7 4-7-4V7z" />
          <path d="M12 11l7-4M12 11l-7-4M12 11v10" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t("getty_aat.panel_title") }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <input v-model="query" type="text" :placeholder="t('getty_aat.search_placeholder')" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100" @keydown.enter.prevent="runSearch()" />
        <button v-if="query" type="button" class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800" @click="clearQuery">✕</button>
      </div>
      <p v-if="getty.isSearching" class="text-xs text-gray-400 animate-pulse">{{ t("common.loading") }}</p>
    </div>

    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">{{ t("getty_aat.applied_success", { aat: lastApplied.aatId, tag: lastApplied.tagName }) }}</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!getty.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400">{{ t("getty_aat.idle_hint") }}</p>
      <p v-else-if="!getty.isSearching && results.length === 0" class="px-3 py-3 text-xs text-gray-400">{{ t("getty_aat.no_results") }}</p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.aat_id" class="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.label }}</p>
              <p v-if="hit.scope_note" class="mt-0.5 line-clamp-3 text-xs text-gray-500 dark:text-gray-400">{{ hit.scope_note }}</p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400">
                AAT {{ hit.aat_id }} · <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">vocab.getty.edu</a>
              </p>
            </div>
            <button type="button" class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700" @click="applyHit(hit)">{{ t("getty_aat.apply") }}</button>
          </div>
        </li>
      </ul>
    </div>

    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("getty_aat.footer_hint") }}
    </div>
  </div>
</template>
