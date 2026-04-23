<script setup lang="ts">
/**
 * VIAF lookup panel for the TEI editor.
 *
 * Mirrors OrcidLinkPanel / RorLinkPanel but searches VIAF and writes
 * the chosen URI as ``@ref`` on the enclosing ``<persName>`` or
 * ``<orgName>`` element. VIAF covers both persons (``nametype``
 * "personal") and corporate bodies ("corporate"), so the allowed
 * target set is wider than ROR (orgName only) or ORCID (persName
 * only).
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useViafStore, type ViafHit } from "@/stores/viaf";

type ApplyOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: "no_enclosing_tag" }
  | { ok: false; reason: "not_entity_tag"; tagName: string };

const props = defineProps<{
  /** Pre-filled search query (typically the current editor selection). */
  initialQuery?: string;
  /** Callback that writes @ref back to the CodeMirror buffer. */
  onApply: (uri: string) => ApplyOutcome;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const { t } = useI18n();
const viaf = useViafStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<ViafHit[]>([]);
const error = ref<string | null>(null);
const lastApplied = ref<{ viafId: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

async function runSearch(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) {
    results.value = [];
    error.value = null;
    return;
  }
  error.value = null;
  try {
    results.value = await viaf.search(q);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    error.value = msg ?? t("common.error");
    results.value = [];
  }
}

const debouncedSearch = useDebounceFn(runSearch, 400);
watch(query, () => {
  debouncedSearch();
});

onMounted(() => {
  if (query.value.trim().length >= 2) runSearch();
});

function clearQuery(): void {
  query.value = "";
  results.value = [];
  error.value = null;
}

function applyHit(hit: ViafHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) {
    lastApplied.value = { viafId: hit.viaf_id, tagName: outcome.tagName };
    return;
  }
  applyError.value =
    outcome.reason === "no_enclosing_tag"
      ? t("viaf.apply_error_no_enclosing_tag")
      : t("viaf.apply_error_not_entity_tag", { tag: outcome.tagName });
}

function badgeColourForType(nameType: string): string {
  // personal → slate, corporate → amber (matches TEI persName vs orgName
  // colour coding in the rest of the UI, loosely).
  if (nameType === "corporate") return "bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300";
  if (nameType === "personal") return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200";
  return "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#cc0000]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 20 L12 4 L20 20 Z" />
          <path d="M8 14 h8" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">
          {{ t("viaf.panel_title") }}
        </span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">
        ✕
      </button>
    </div>

    <!-- Search form -->
    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <input
          v-model="query"
          type="text"
          :placeholder="t('viaf.search_placeholder')"
          class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          @keydown.enter.prevent="runSearch()"
        />
        <button
          v-if="query"
          type="button"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
          @click="clearQuery"
        >
          ✕
        </button>
      </div>
      <p v-if="viaf.isSearching" class="text-xs text-gray-400 dark:text-gray-500 animate-pulse">
        {{ t("common.loading") }}
      </p>
    </div>

    <!-- Feedback -->
    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">
        {{ t("viaf.applied_success", { viaf: lastApplied.viafId, tag: lastApplied.tagName }) }}
      </p>
    </div>

    <!-- Results -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!viaf.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500">
        {{ t("viaf.idle_hint") }}
      </p>
      <p v-else-if="!viaf.isSearching && results.length === 0" class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500">
        {{ t("viaf.no_results") }}
      </p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.viaf_id" class="group px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.display }}</p>
              <p class="mt-0.5 text-[11px]">
                <span v-if="hit.name_type" :class="['rounded px-1.5 py-0.5 font-mono', badgeColourForType(hit.name_type)]">
                  {{ hit.name_type }}
                </span>
              </p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400 dark:text-gray-500">
                VIAF {{ hit.viaf_id }} ·
                <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">viaf.org</a>
              </p>
            </div>
            <button
              type="button"
              class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              @click="applyHit(hit)"
            >
              {{ t("viaf.apply") }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- Footer hint -->
    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("viaf.footer_hint") }}
    </div>
  </div>
</template>
