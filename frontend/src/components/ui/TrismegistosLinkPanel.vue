<script setup lang="ts">
/**
 * Trismegistos lookup panel. Covers persons and places in the TM
 * registry (texts are also returned by the backend but are shown as
 * context only — they cannot be applied as @ref because they map to
 * <bibl>, not an entity tag).
 *
 * When the admin has not configured an API key, the backend returns
 * ``503 TMG_API_KEY_MISSING``. The panel intercepts that and renders
 * a banner prompting registration at trismegistos.org/api.
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useTrismegistosStore, type TrismegistosHit } from "@/stores/trismegistos";

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
const tm = useTrismegistosStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<TrismegistosHit[]>([]);
const error = ref<string | null>(null);
const needsKey = ref(false);
const lastApplied = ref<{ tmId: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

async function runSearch(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) { results.value = []; error.value = null; needsKey.value = false; return; }
  error.value = null;
  needsKey.value = false;
  try {
    results.value = await tm.search(q);
  } catch (err) {
    const resp = (err as { response?: { status?: number; data?: { error?: { message?: string } }; data_detail?: unknown } }).response;
    const code = (err as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code;
    if (resp?.status === 503 && code === "TMG_API_KEY_MISSING") {
      needsKey.value = true;
      results.value = [];
      return;
    }
    error.value = resp?.data?.error?.message ?? (err as Error).message ?? t("common.error");
    results.value = [];
  }
}
const debouncedSearch = useDebounceFn(runSearch, 400);
watch(query, () => { debouncedSearch(); });
onMounted(() => { if (query.value.trim().length >= 2) runSearch(); });
function clearQuery(): void { query.value = ""; results.value = []; error.value = null; needsKey.value = false; }
function applyHit(hit: TrismegistosHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) { lastApplied.value = { tmId: hit.tm_id, tagName: outcome.tagName }; return; }
  applyError.value = outcome.reason === "no_enclosing_tag"
    ? t("trismegistos.apply_error_no_enclosing_tag")
    : t("trismegistos.apply_error_not_entity_tag", { tag: outcome.tagName });
}
function kindBadge(kind: TrismegistosHit["kind"]): string {
  const map: Record<TrismegistosHit["kind"], string> = {
    person: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    place: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    text: "bg-violet-50 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  };
  return map[kind];
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#c49a6c]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 3h14v18H5z" />
          <path d="M9 7h6M9 11h6M9 15h6" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t("trismegistos.panel_title") }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <div v-if="needsKey" class="flex-shrink-0 border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
      <p class="font-semibold">{{ t("trismegistos.api_key_missing_title") }}</p>
      <p class="mt-1">{{ t("trismegistos.api_key_missing_body") }}</p>
      <a href="https://www.trismegistos.org/api" target="_blank" rel="noopener" class="mt-1 inline-block underline">trismegistos.org/api</a>
    </div>

    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <input v-model="query" type="text" :placeholder="t('trismegistos.search_placeholder')" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100" @keydown.enter.prevent="runSearch()" />
        <button v-if="query" type="button" class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800" @click="clearQuery">✕</button>
      </div>
      <p v-if="tm.isSearching" class="text-xs text-gray-400 animate-pulse">{{ t("common.loading") }}</p>
    </div>

    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">{{ t("trismegistos.applied_success", { tm: lastApplied.tmId, tag: lastApplied.tagName }) }}</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!needsKey && !tm.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400">{{ t("trismegistos.idle_hint") }}</p>
      <p v-else-if="!needsKey && !tm.isSearching && results.length === 0 && query.trim().length >= 2" class="px-3 py-3 text-xs text-gray-400">{{ t("trismegistos.no_results") }}</p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.uri" class="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.label }}</p>
              <p class="mt-0.5 text-[11px]">
                <span :class="['rounded px-1.5 py-0.5 font-mono', kindBadge(hit.kind)]">{{ hit.kind }}</span>
              </p>
              <p v-if="hit.detail" class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{{ hit.detail }}</p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400">
                TM {{ hit.tm_id }} · <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">trismegistos.org</a>
              </p>
            </div>
            <button v-if="hit.kind !== 'text'" type="button" class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700" @click="applyHit(hit)">{{ t("trismegistos.apply") }}</button>
            <span v-else class="shrink-0 text-[11px] text-gray-400">{{ t("trismegistos.text_not_applicable") }}</span>
          </div>
        </li>
      </ul>
    </div>

    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("trismegistos.footer_hint") }}
    </div>
  </div>
</template>
