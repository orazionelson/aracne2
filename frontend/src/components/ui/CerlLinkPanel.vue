<script setup lang="ts">
/**
 * CERL Thesaurus lookup panel. Writes @ref on <persName> / <placeName>
 * / <orgName>. CERL's "imprint" bucket surfaces book-printing
 * institutions and is applied to <orgName>.
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useCerlStore, type CerlHit } from "@/stores/cerl";

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
const cerl = useCerlStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<CerlHit[]>([]);
const error = ref<string | null>(null);
const lastApplied = ref<{ cerlId: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

async function runSearch(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) { results.value = []; error.value = null; return; }
  error.value = null;
  try {
    results.value = await cerl.search(q);
  } catch (err) {
    error.value = (err as Error).message ?? t("common.error");
    results.value = [];
  }
}
const debouncedSearch = useDebounceFn(runSearch, 400);
watch(query, () => { debouncedSearch(); });
onMounted(() => { if (query.value.trim().length >= 2) runSearch(); });

function clearQuery(): void { query.value = ""; results.value = []; error.value = null; }
function applyHit(hit: CerlHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) { lastApplied.value = { cerlId: hit.cerl_id, tagName: outcome.tagName }; return; }
  applyError.value = outcome.reason === "no_enclosing_tag"
    ? t("cerl.apply_error_no_enclosing_tag")
    : t("cerl.apply_error_not_entity_tag", { tag: outcome.tagName });
}

function kindBadge(kind: CerlHit["kind"]): string {
  const map: Record<CerlHit["kind"], string> = {
    person: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    corporate: "bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    place: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    imprint: "bg-orange-50 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
    other: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
  };
  return map[kind];
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#6b4420]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 4h9a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4z" />
          <path d="M16 4h4v13h-4" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t("cerl.panel_title") }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <input v-model="query" type="text" :placeholder="t('cerl.search_placeholder')" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100" @keydown.enter.prevent="runSearch()" />
        <button v-if="query" type="button" class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800" @click="clearQuery">✕</button>
      </div>
      <p v-if="cerl.isSearching" class="text-xs text-gray-400 animate-pulse">{{ t("common.loading") }}</p>
    </div>

    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">{{ t("cerl.applied_success", { cerl: lastApplied.cerlId, tag: lastApplied.tagName }) }}</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!cerl.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400">{{ t("cerl.idle_hint") }}</p>
      <p v-else-if="!cerl.isSearching && results.length === 0" class="px-3 py-3 text-xs text-gray-400">{{ t("cerl.no_results") }}</p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.cerl_id" class="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.label }}</p>
              <p class="mt-0.5 text-[11px]">
                <span :class="['rounded px-1.5 py-0.5 font-mono', kindBadge(hit.kind)]">{{ hit.kind }}</span>
              </p>
              <p v-if="hit.detail" class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{{ hit.detail }}</p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400">
                CERL {{ hit.cerl_id }} · <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">data.cerl.org</a>
              </p>
            </div>
            <button type="button" class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700" @click="applyHit(hit)">{{ t("cerl.apply") }}</button>
          </div>
        </li>
      </ul>
    </div>

    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("cerl.footer_hint") }}
    </div>
  </div>
</template>
