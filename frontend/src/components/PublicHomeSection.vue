<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { usePublicCollections } from "@/composables/usePublicCollections";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const { collections, total, page, totalPages, isLoading, fetchCollections } =
  usePublicCollections();

const searchInput = ref("");
const activeSearch = ref("");

const showCollections = computed(() => uiConfig.config.home_show_collections);
const showSearch = computed(() => uiConfig.config.home_show_search);
const isSearching = computed(() => activeSearch.value !== "");

/** First 3 items from page 1, used as the "recent additions" feature row. */
const recentItems = computed(() =>
  !isSearching.value && page.value === 1 ? collections.value.slice(0, 3) : [],
);

function handleSearch(): void {
  activeSearch.value = searchInput.value.trim();
  fetchCollections(activeSearch.value, 1);
}

function clearSearch(): void {
  searchInput.value = "";
  activeSearch.value = "";
  fetchCollections("", 1);
}

function isSafeUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === "http:" || parsed.protocol === "https:"
  } catch {
    return false
  }
}

function goToPage(p: number): void {
  if (p < 1 || p > totalPages.value) return;
  fetchCollections("", p);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/** Compact page number list: always show first, last, current ±1, with ellipsis. */
const pageNumbers = computed<Array<number | "…">>(() => {
  const n = totalPages.value;
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1);
  const cur = page.value;
  const set = new Set([1, n, cur - 1, cur, cur + 1].filter((x) => x >= 1 && x <= n));
  const sorted = [...set].sort((a, b) => a - b);
  const result: Array<number | "…"> = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && (sorted[i] as number) - (sorted[i - 1] as number) > 1) result.push("…");
    result.push(sorted[i]);
  }
  return result;
});

onMounted(() => {
  if (showCollections.value) fetchCollections();
});
</script>

<template>
  <div class="ph-page bg-gray-50">
    <main class="ph-main mx-auto max-w-4xl px-4 py-10">
      <!-- Search bar -->
      <div v-if="showSearch" class="ph-search mb-8">
        <form class="ph-search-form flex gap-2" @submit.prevent="handleSearch">
          <input
            v-model="searchInput"
            type="search"
            :placeholder="t('public.search_placeholder')"
            class="ph-search-input flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            class="ph-search-btn rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {{ t("collections.search_button") }}
          </button>
          <button
            v-if="activeSearch"
            type="button"
            class="ph-search-reset rounded-lg border px-4 py-2.5 text-sm hover:bg-gray-100"
            @click="clearSearch"
          >
            {{ t("collections.search_reset") }}
          </button>
        </form>
      </div>

      <template v-if="showCollections">
        <!-- Stats bar -->
        <p
          v-if="!isLoading && total > 0 && !isSearching"
          class="ph-stats mb-6 text-sm text-gray-500"
        >
          {{ t("public.stat_collections", { n: total }) }}
        </p>

        <p v-if="isLoading" class="ph-loading text-gray-400 text-sm">{{ t("common.loading") }}</p>

        <template v-else-if="collections.length > 0">
          <!-- Ultime aggiunte (only on page 1 when not searching) -->
          <section v-if="recentItems.length > 0" class="last-add mb-10">
            <h2 class="last-add-title mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {{ t("public.recent_title") }}
            </h2>
            <div class="last-add-grid grid gap-4 sm:grid-cols-3">
              <div
                v-for="col in recentItems"
                :key="col.id"
                class="last-add-card rounded-xl border border-indigo-100 bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <h3 class="col-title font-semibold text-gray-900 line-clamp-2 text-sm leading-snug">
                  {{ col.title }}
                </h3>
                <p v-if="col.description" class="col-desc mt-1 text-xs text-gray-500 line-clamp-2">
                  {{ col.description }}
                </p>
                <div class="col-meta mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-400">
                  <span class="col-author" v-if="col.author">{{ col.author }}</span>
                  <span class="col-year" v-if="col.pub_year">{{ col.pub_year }}</span>
                </div>
                <div class="col-actions mt-3 flex flex-wrap gap-2">
                  <router-link
                    :to="{ name: 'public-collection', params: { slug: col.slug } }"
                    class="btn-browse rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-50"
                  >
                    {{ t("public.browse") }}
                  </router-link>
                  <router-link
                    v-if="uiConfig.config.evt_enabled && col.doc_count === 1 && col.evt_enabled"
                    :to="{ name: 'collection-read', params: { slug: col.slug } }"
                    class="btn-evt rounded border border-indigo-300 px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
                  >
                    {{ t("public.view_in_evt") }}
                  </router-link>
                  <router-link
                    v-if="col.has_public_bibliography"
                    :to="{ name: 'public-bibliography', params: { slug: col.slug } }"
                    class="btn-bibliography rounded border border-amber-300 px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-50"
                  >
                    {{ t("public.bibliography_btn") }}
                  </router-link>
                  <router-link
                    v-if="col.entity_count && col.entity_count > 0"
                    :to="{ name: 'public-entities', params: { slug: col.slug } }"
                    class="btn-entities rounded border border-violet-300 px-2.5 py-1 text-xs text-violet-700 hover:bg-violet-50"
                  >
                    {{ t("public.entities_btn") }}
                  </router-link>
                  <a
                    v-if="isSafeUrl(col.website_link)"
                    :href="col.website_link"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="btn-website rounded border border-teal-300 px-2.5 py-1 text-xs text-teal-700 hover:bg-teal-50"
                  >
                    {{ t("public.visit_website") }}
                  </a>
                </div>
              </div>
            </div>
          </section>

          <!-- Full collection list -->
          <h2
            v-if="isSearching"
            class="search-results-title mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500"
          >
            {{ t("public.search_results", { n: total }) }}
          </h2>
          <h2
            v-else-if="recentItems.length > 0"
            class="all-collections-title mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500"
          >
            {{ t("public.all_collections") }}
          </h2>

          <ul class="collection-list space-y-4">
            <li
              v-for="col in collections"
              :key="col.id"
              class="collection-item rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md"
            >
              <h2 class="col-title text-lg font-semibold text-gray-900">{{ col.title }}</h2>
              <p v-if="col.description" class="col-desc mt-1 text-sm text-gray-500 line-clamp-2">
                {{ col.description }}
              </p>
              <div class="col-meta mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
                <span class="col-author" v-if="col.author">{{ col.author }}</span>
                <span class="col-publisher" v-if="col.publisher">{{ col.publisher }}</span>
                <span class="col-year" v-if="col.pub_year">{{ col.pub_year }}</span>
                <span class="col-date" v-if="col.published_at">
                  {{ t("public.published") }}
                  {{ new Date(col.published_at).toLocaleDateString() }}
                </span>
              </div>
              <!-- Document snippets (only shown when search matched document content) -->
              <ul v-if="col.doc_hits.length > 0" class="doc-hits mt-3 space-y-1">
                <li v-for="hit in col.doc_hits" :key="hit.filename" class="doc-hit">
                  <router-link
                    :to="{ name: 'public-document', params: { slug: col.slug, filename: hit.filename } }"
                    class="doc-hit-link block rounded bg-yellow-50 px-3 py-1.5 text-xs text-gray-700 hover:bg-yellow-100"
                  >
                    <span class="hit-filename font-medium text-gray-500">{{ hit.filename }}</span>
                    <span class="mx-1 text-gray-300">—</span>
                    <span class="hit-snippet italic">…{{ hit.snippet }}…</span>
                  </router-link>
                </li>
              </ul>

              <div class="col-actions mt-4 flex flex-wrap gap-2">
                <router-link
                  :to="{ name: 'public-collection', params: { slug: col.slug } }"
                  class="btn-browse rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                >
                  {{ t("public.browse") }}
                </router-link>
                <router-link
                  v-if="uiConfig.config.evt_enabled && col.doc_count === 1 && col.evt_enabled"
                  :to="{ name: 'collection-read', params: { slug: col.slug } }"
                  class="btn-evt rounded border border-indigo-300 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50"
                >
                  {{ t("public.view_in_evt") }}
                </router-link>
                <router-link
                  v-if="col.has_public_bibliography"
                  :to="{ name: 'public-bibliography', params: { slug: col.slug } }"
                  class="btn-bibliography rounded border border-amber-300 px-3 py-1.5 text-sm text-amber-700 hover:bg-amber-50"
                >
                  {{ t("public.bibliography_btn") }}
                </router-link>
                <router-link
                  v-if="col.entity_count && col.entity_count > 0"
                  :to="{ name: 'public-entities', params: { slug: col.slug } }"
                  class="btn-entities rounded border border-violet-300 px-3 py-1.5 text-sm text-violet-700 hover:bg-violet-50"
                >
                  {{ t("public.entities_btn") }}
                </router-link>
                <a
                  v-if="isSafeUrl(col.website_link)"
                  :href="col.website_link"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-website rounded border border-teal-300 px-3 py-1.5 text-sm text-teal-700 hover:bg-teal-50"
                >
                  {{ t("public.visit_website") }}
                </a>
              </div>
            </li>
          </ul>

          <!-- Pagination (hidden during search — search has no server pagination) -->
          <nav
            v-if="!isSearching && totalPages > 1"
            class="ph-pagination mt-10 flex items-center justify-center gap-1"
            :aria-label="t('public.pagination_label')"
          >
            <button
              class="pagination-prev rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
              :disabled="page === 1"
              @click="goToPage(page - 1)"
            >
              {{ t("public.page_prev") }}
            </button>

            <template v-for="(num, idx) in pageNumbers" :key="idx">
              <span v-if="num === '…'" class="pagination-ellipsis px-2 text-gray-400 select-none">…</span>
              <button
                v-else
                class="pagination-page min-w-[2rem] rounded border px-2 py-1.5 text-sm transition"
                :class="num === page
                  ? 'bg-indigo-600 border-indigo-600 text-white font-semibold'
                  : 'hover:bg-gray-100'"
                @click="goToPage(num as number)"
              >
                {{ num }}
              </button>
            </template>

            <button
              class="pagination-next rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
              :disabled="page === totalPages"
              @click="goToPage(page + 1)"
            >
              {{ t("public.page_next") }}
            </button>
          </nav>
        </template>

        <p v-else-if="activeSearch" class="ph-no-results text-gray-500 text-sm">
          {{ t("collections.no_results", { q: activeSearch }) }}
        </p>

        <p v-else class="ph-empty text-gray-500 text-sm">
          {{ t("public.no_collections") }}
        </p>
      </template>
    </main>

    <!-- Custom homepage CSS — loaded last to allow overriding all previous styles -->
    <component
      :is="'link'"
      v-if="uiConfig.config.has_custom_homepage_css"
      rel="stylesheet"
      href="/api/v1/settings/homepage-css/file"
    />
  </div>
</template>
