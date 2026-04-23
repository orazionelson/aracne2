<script setup lang="ts">
/**
 * ORCID lookup panel for the TEI editor.
 *
 * Mirrors WikidataLinkPanel's interaction but searches the ORCID
 * public registry and writes the chosen URI as ``@ref`` on the
 * enclosing ``<persName>`` element (only — ORCID identifies people,
 * not places or organisations). The parent view supplies an
 * ``onApply`` callback so the panel stays UI-only.
 */

import { ref, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useDebounceFn } from '@vueuse/core';
import { useOrcidStore, type OrcidHit } from '@/stores/orcid';

type ApplyOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: 'no_enclosing_tag' }
  | { ok: false; reason: 'not_entity_tag'; tagName: string };

const props = defineProps<{
  /** Pre-filled search query (typically the current editor selection). */
  initialQuery?: string;
  /** Callback that writes @ref back to the CodeMirror buffer. */
  onApply: (uri: string) => ApplyOutcome;
}>();

const emit = defineEmits<{ (e: 'close'): void }>();

const { t } = useI18n();
const orcid = useOrcidStore();

const query = ref(props.initialQuery?.trim() ?? '');
const results = ref<OrcidHit[]>([]);
const error = ref<string | null>(null);
const lastApplied = ref<{ orcid: string; tagName: string } | null>(null);
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
    results.value = await orcid.search(q);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    error.value = msg ?? t('common.error');
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
  query.value = '';
  results.value = [];
  error.value = null;
}

function applyHit(hit: OrcidHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) {
    lastApplied.value = { orcid: hit.orcid, tagName: outcome.tagName };
    return;
  }
  applyError.value =
    outcome.reason === 'no_enclosing_tag'
      ? t('orcid.apply_error_no_enclosing_tag')
      : t('orcid.apply_error_not_entity_tag', { tag: outcome.tagName });
}

function displayLabel(hit: OrcidHit): string {
  if (hit.credit_name) return hit.credit_name;
  const parts = [hit.given_names, hit.family_name].filter(Boolean);
  if (parts.length) return parts.join(' ');
  return hit.orcid;
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#a6ce39]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 7v10" />
          <path d="M8 17h4" />
          <path d="M8 12a4 4 0 0 1 4-4" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">
          {{ t('orcid.panel_title') }}
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
          :placeholder="t('orcid.search_placeholder')"
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
      <p v-if="orcid.isSearching" class="text-xs text-gray-400 dark:text-gray-500 animate-pulse">
        {{ t('common.loading') }}
      </p>
    </div>

    <!-- Feedback -->
    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">
        {{ t('orcid.applied_success', { orcid: lastApplied.orcid, tag: lastApplied.tagName }) }}
      </p>
    </div>

    <!-- Results -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p
        v-else-if="!orcid.isSearching && query.trim().length < 2"
        class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500"
      >
        {{ t('orcid.idle_hint') }}
      </p>
      <p
        v-else-if="!orcid.isSearching && results.length === 0"
        class="px-3 py-3 text-xs text-gray-400 dark:text-gray-500"
      >
        {{ t('orcid.no_results') }}
      </p>
      <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
        <li
          v-for="hit in results"
          :key="hit.orcid"
          class="group px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">
                {{ displayLabel(hit) }}
              </p>
              <p v-if="hit.affiliations.length" class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">
                {{ hit.affiliations.join(' · ') }}
              </p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400 dark:text-gray-500">
                {{ hit.orcid }} ·
                <a
                  :href="hit.uri"
                  target="_blank"
                  rel="noopener"
                  class="hover:underline"
                >orcid.org</a>
              </p>
            </div>
            <button
              type="button"
              class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              @click="applyHit(hit)"
            >
              {{ t('orcid.apply') }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- Footer hint -->
    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t('orcid.footer_hint') }}
    </div>
  </div>
</template>
