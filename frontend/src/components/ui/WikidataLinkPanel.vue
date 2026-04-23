<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useDebounceFn } from '@vueuse/core';
import { apiClient } from '@/services/api';

interface WikidataHit {
  qid: string;
  label: string;
  description: string | null;
  uri: string;
}

type ApplyOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: 'no_enclosing_tag' }
  | { ok: false; reason: 'not_entity_tag'; tagName: string };

const props = defineProps<{
  /** Text pre-filled in the search box (usually the current editor selection). */
  initialQuery?: string;
  /** Callback invoked when the editor picks a hit — writes @ref back to CM. */
  onApply: (uri: string) => ApplyOutcome;
}>();

const emit = defineEmits<{ (e: 'close'): void }>();

const { t, locale } = useI18n();

const query = ref(props.initialQuery?.trim() ?? '');
// Default search language to the current UI locale; Wikidata has labels in
// most languages but falls back to English on miss, so this keeps the
// dropdown descriptions in the editor's language when available.
const lang = ref(locale.value || 'it');
const results = ref<WikidataHit[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const lastApplied = ref<{ qid: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

async function search(): Promise<void> {
  const q = query.value.trim();
  if (q.length < 2) {
    results.value = [];
    error.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const data = await apiClient.get<WikidataHit[]>('/plugins/wikidata/search', {
      params: { q, lang: lang.value, limit: 15 },
    });
    results.value = data;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    error.value = msg ?? t('common.error');
    results.value = [];
  } finally {
    loading.value = false;
  }
}

const debouncedSearch = useDebounceFn(search, 400);
watch(query, () => {
  debouncedSearch();
});
watch(lang, () => {
  if (query.value.trim().length >= 2) search();
});

onMounted(() => {
  if (query.value.trim().length >= 2) search();
});

function applyHit(hit: WikidataHit): void {
  applyError.value = null;
  const outcome = props.onApply(hit.uri);
  if (outcome.ok) {
    lastApplied.value = { qid: hit.qid, tagName: outcome.tagName };
  } else if (outcome.reason === 'not_entity_tag') {
    applyError.value = t('wikidata.apply_error_not_entity_tag', { tag: outcome.tagName });
  } else {
    applyError.value = t('wikidata.apply_error_no_enclosing_tag');
  }
}

function clearQuery(): void {
  query.value = '';
  results.value = [];
  error.value = null;
  applyError.value = null;
}
</script>

<template>
  <div class="flex h-full flex-col bg-white">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span class="text-sm font-semibold text-gray-700">{{ t('wikidata.panel_title') }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700" @click="emit('close')">✕</button>
    </div>

    <!-- Search form -->
    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2">
      <div class="flex items-center gap-2">
        <input
          v-model="query"
          type="text"
          :placeholder="t('wikidata.search_placeholder')"
          class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none"
          @keydown.enter.prevent="search()"
        />
        <button
          v-if="query"
          type="button"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50"
          @click="clearQuery"
        >
          ✕
        </button>
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <label class="flex items-center gap-1">
          {{ t('wikidata.lang_label') }}
          <select
            v-model="lang"
            class="rounded border border-gray-300 bg-white px-1 py-0.5 text-xs"
          >
            <option value="it">it</option>
            <option value="en">en</option>
            <option value="fr">fr</option>
            <option value="de">de</option>
            <option value="es">es</option>
            <option value="la">la</option>
          </select>
        </label>
        <span v-if="loading" class="text-gray-400 animate-pulse">{{ t('common.loading') }}</span>
      </div>
    </div>

    <!-- Feedback area -->
    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs">
      <p v-if="applyError" class="text-red-600">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700">
        {{ t('wikidata.applied_success', { qid: lastApplied.qid, tag: lastApplied.tagName }) }}
      </p>
    </div>

    <!-- Results -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600">{{ error }}</p>
      <p
        v-else-if="!loading && query.trim().length < 2"
        class="px-3 py-3 text-xs text-gray-400"
      >
        {{ t('wikidata.idle_hint') }}
      </p>
      <p
        v-else-if="!loading && results.length === 0"
        class="px-3 py-3 text-xs text-gray-400"
      >
        {{ t('wikidata.no_results') }}
      </p>
      <ul v-else class="divide-y divide-gray-100">
        <li
          v-for="hit in results"
          :key="hit.qid"
          class="group px-3 py-2 hover:bg-gray-50"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-gray-800">{{ hit.label }}</p>
              <p v-if="hit.description" class="mt-0.5 line-clamp-2 text-xs text-gray-500">
                {{ hit.description }}
              </p>
              <p class="mt-0.5 font-mono text-[11px] text-gray-400">
                {{ hit.qid }} · <a :href="hit.uri" target="_blank" rel="noopener" class="hover:underline">wikidata.org</a>
              </p>
            </div>
            <button
              type="button"
              class="shrink-0 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              @click="applyHit(hit)"
            >
              {{ t('wikidata.apply') }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- Footer hint -->
    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400">
      {{ t('wikidata.footer_hint') }}
    </div>
  </div>
</template>
