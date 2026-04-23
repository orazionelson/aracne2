<script setup lang="ts">
/**
 * GeoNames lookup panel for the TEI editor.
 *
 * Mirrors OrcidLinkPanel / RorLinkPanel but searches GeoNames and
 * writes the chosen URI as ``@ref`` on the enclosing ``<placeName>``
 * element. The URI format (web vs semantic-web) respects the
 * plugin's ``url_format`` setting — the frontend does not compute it
 * locally; the backend already applies the format so the panel
 * simply renders ``hit.uri``.
 */

import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useDebounceFn } from "@vueuse/core";
import { useGeonamesLookupStore, type GeonamesHit } from "@/stores/geonames_lookup";

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
const geo = useGeonamesLookupStore();

const query = ref(props.initialQuery?.trim() ?? "");
const results = ref<GeonamesHit[]>([]);
const error = ref<string | null>(null);
const lastApplied = ref<{ geoId: string; tagName: string } | null>(null);
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
    results.value = await geo.search(q);
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

function applyHit(hit: GeonamesHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) {
    lastApplied.value = { geoId: hit.geoname_id, tagName: outcome.tagName };
    return;
  }
  applyError.value =
    outcome.reason === "no_enclosing_tag"
      ? t("geonames.apply_error_no_enclosing_tag")
      : t("geonames.apply_error_not_entity_tag", { tag: outcome.tagName });
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#2e7d32]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2 C7 2 3 6 3 11 c0 7 9 11 9 11 s9-4 9-11 c0-5-4-9-9-9 z" />
          <circle cx="12" cy="11" r="3" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">
          {{ t("geonames.panel_title") }}
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
          :placeholder="t('geonames.search_placeholder')"
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
      <p v-if="geo.isSearching" class="text-xs text-gray-400 dark:text-gray-500 animate-pulse">
        {{ t("common.loading") }}
      </p>
    </div>

    <!-- Feedback -->
    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">
        {{ t("geonames.applied_success", { geo: lastApplied.geoId, tag: lastApplied.tagName }) }}
      </p>
    </div>

    <!-- Results -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="!geo.isSearching && query.trim().length < 2" class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500">
        {{ t("geonames.idle_hint") }}
      </p>
      <p v-else-if="!geo.isSearching && results.length === 0" class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500">
        {{ t("geonames.no_results") }}
      </p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li v-for="hit in results" :key="hit.geoname_id" class="group px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.name }}</p>
              <p v-if="hit.region || hit.country" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                <span v-if="hit.region">{{ hit.region }}</span>
                <span v-if="hit.region && hit.country"> · </span>
                <span v-if="hit.country">{{ hit.country }}</span>
              </p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400 dark:text-gray-500">
                GeoNames {{ hit.geoname_id }} ·
                <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">resolve</a>
              </p>
            </div>
            <button
              type="button"
              class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              @click="applyHit(hit)"
            >
              {{ t("geonames.apply") }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- Footer hint -->
    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("geonames.footer_hint") }}
    </div>
  </div>
</template>
