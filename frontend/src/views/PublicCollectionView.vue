<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { apiClient } from "@/services/api";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";
import { useJsonLd } from "@/composables/useJsonLd";

interface PublicDocumentInfo { filename: string; title: string | null; author: string | null }
interface PublicCollectionDetail {
  slug: string;
  title: string;
  description: string | null;
  author: string | null;
  publisher: string | null;
  pub_year: number | null;
  documents: PublicDocumentInfo[];
}

const { t } = useI18n();
const route = useRoute();
const uiConfig = useUiConfigStore();
usePublicCustomCss();

const slug = route.params.slug as string;
const collection = ref<PublicCollectionDetail | null>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

// ── Filter / sort / paginate ────────────────────────────────────────────
//
// Same browsing affordances we already give website visitors (filter
// box + sortable columns + page control), now also on the public
// collection landing page so editors of long corpora are not forced
// to scroll a 200-row list.
type SortKey = "title" | "filename" | "author";
const PAGE_SIZE = 20;

const filterQuery = ref("");
const sortKey = ref<SortKey>("title");
const sortAsc = ref(true);
const currentPage = ref(1);

function toggleSort(key: SortKey): void {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortKey.value = key;
    sortAsc.value = true;
  }
  currentPage.value = 1;
}

function compareStrings(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
}

const filteredDocs = computed<PublicDocumentInfo[]>(() => {
  if (!collection.value) return [];
  const q = filterQuery.value.trim().toLowerCase();
  let docs = collection.value.documents;
  if (q) {
    docs = docs.filter((d) => {
      const title = (d.title || "").toLowerCase();
      const author = (d.author || "").toLowerCase();
      const filename = d.filename.toLowerCase();
      return title.includes(q) || author.includes(q) || filename.includes(q);
    });
  }
  const sorted = [...docs].sort((a, b) => {
    let av: string;
    let bv: string;
    if (sortKey.value === "filename") {
      av = a.filename;
      bv = b.filename;
    } else if (sortKey.value === "author") {
      av = a.author || "";
      bv = b.author || "";
    } else {
      av = a.title || a.filename;
      bv = b.title || b.filename;
    }
    const c = compareStrings(av, bv);
    return sortAsc.value ? c : -c;
  });
  return sorted;
});

const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredDocs.value.length / PAGE_SIZE)),
);

const pagedDocs = computed<PublicDocumentInfo[]>(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE;
  return filteredDocs.value.slice(start, start + PAGE_SIZE);
});

function goToPage(p: number): void {
  if (p < 1 || p > totalPages.value) return;
  currentPage.value = p;
}

onMounted(async () => {
  try {
    collection.value = await apiClient.get<PublicCollectionDetail>(
      `/public/collections/${slug}`,
    );
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});

// schema.org structured data: emit a CreativeWork for the collection
// with its documents listed as ``hasPart`` CreativeWork entries. We use
// CreativeWork (not Book) because TEI corpora range across genres (letters,
// charters, poems, critical editions) and CreativeWork is the superclass
// that does not mis-classify any of them.
const origin = computed(() =>
  typeof window !== "undefined" ? window.location.origin : "",
);
useJsonLd(
  computed(() => {
    const c = collection.value;
    if (!c) return null;
    const collectionUrl = `${origin.value}/browse/${c.slug}`;
    const payload: Record<string, unknown> = {
      "@context": "https://schema.org",
      "@type": "CreativeWork",
      name: c.title,
      url: collectionUrl,
    };
    if (c.description) payload.description = c.description;
    if (c.author) payload.author = { "@type": "Person", name: c.author };
    if (c.publisher)
      payload.publisher = { "@type": "Organization", name: c.publisher };
    if (c.pub_year !== null && c.pub_year !== undefined)
      payload.datePublished = String(c.pub_year);
    if (c.documents.length > 0) {
      payload.hasPart = c.documents.map((d) => {
        const docUrl = `${origin.value}/browse/${c.slug}/${encodeURIComponent(d.filename)}`;
        const doc: Record<string, unknown> = {
          "@type": "CreativeWork",
          name: d.title || d.filename,
          url: docUrl,
        };
        if (d.author) doc.author = { "@type": "Person", name: d.author };
        return doc;
      });
    }
    return payload;
  }),
);
</script>

<template>
  <div class="pc-page">
    <main class="pc-main mx-auto max-w-4xl px-4 py-10">
      <p v-if="isLoading" class="text-gray-400 text-sm">{{ t("common.loading") }}</p>
      <p v-else-if="error" class="text-red-600 text-sm">{{ error }}</p>

      <template v-else-if="collection">
        <!-- Breadcrumb -->
        <nav class="pc-breadcrumb mb-6 text-sm text-gray-400">
          <router-link to="/" class="hover:text-gray-700">
            {{ uiConfig.config.platform_name }}
          </router-link>
          <span class="mx-1">/</span>
          <span class="text-gray-700">{{ collection.title }}</span>
        </nav>

        <!-- Collection header -->
        <div class="pc-collection-header mb-8">
          <h1 class="col-title text-3xl font-bold text-gray-900">{{ collection.title }}</h1>
          <p v-if="collection.author" class="col-author mt-1 text-gray-500 italic">{{ collection.author }}</p>
          <p v-if="collection.description" class="col-desc mt-3 text-gray-600">{{ collection.description }}</p>
          <div class="col-meta mt-3 flex flex-wrap gap-4 text-xs text-gray-400">
            <span v-if="collection.publisher" class="col-publisher">{{ collection.publisher }}</span>
            <span v-if="collection.pub_year" class="col-year">{{ collection.pub_year }}</span>
          </div>
        </div>

        <!-- Document list -->
        <h2 class="doc-list-heading mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          {{ t("collections.documents") }}
          <span class="ml-1 font-normal">({{ collection.documents.length }})</span>
        </h2>

        <p v-if="collection.documents.length === 0" class="text-gray-400 text-sm">
          {{ t("collections.no_documents") }}
        </p>

        <template v-else>
          <!-- Filter input -->
          <input
            v-model="filterQuery"
            type="search"
            :placeholder="t('public_browse.filter_placeholder')"
            class="public-browse-filter mb-3 w-full max-w-lg rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            @input="currentPage = 1"
          />

          <!-- Sort buttons -->
          <div class="public-browse-sort mb-4 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <span class="public-browse-sort-label">{{ t("public_browse.sort_by") }}</span>
            <button
              v-for="key in (['title', 'filename', 'author'] as SortKey[])"
              :key="key"
              type="button"
              class="public-browse-sort-btn rounded-full border px-3 py-1 transition"
              :class="sortKey === key
                ? 'border-indigo-500 text-indigo-700 bg-indigo-50'
                : 'border-gray-300 text-gray-600 hover:bg-gray-100'"
              @click="toggleSort(key)"
            >
              {{ t(`public_browse.sort_${key}`) }}
              <span v-if="sortKey === key" class="ml-1">{{ sortAsc ? '↑' : '↓' }}</span>
            </button>
            <span class="public-browse-result-count ml-auto text-xs text-gray-400">
              {{ t("public_browse.results", { n: filteredDocs.length, total: collection.documents.length }) }}
            </span>
          </div>

          <p
            v-if="filteredDocs.length === 0"
            class="public-browse-empty rounded border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400"
          >
            {{ t("public_browse.no_match") }}
          </p>

          <ul
            v-else
            class="doc-list divide-y divide-gray-200 rounded-xl border border-gray-200 bg-white shadow-sm"
          >
            <li
              v-for="doc in pagedDocs"
              :key="doc.filename"
              class="doc-item flex items-center justify-between px-5 py-3 hover:bg-gray-50"
            >
              <div class="min-w-0 flex-1">
                <p class="doc-title truncate text-sm font-medium text-gray-800">
                  {{ doc.title || doc.filename }}
                </p>
                <p v-if="doc.author" class="doc-author truncate text-xs text-gray-400 italic">
                  {{ doc.author }}
                </p>
              </div>
              <router-link
                :to="{ name: 'public-document', params: { slug, filename: doc.filename } }"
                class="doc-view-link ml-4 shrink-0 text-sm text-indigo-600 hover:underline"
              >
                {{ t("documents.action_view") }}
              </router-link>
            </li>
          </ul>

          <!-- Pagination -->
          <div
            v-if="totalPages > 1"
            class="public-browse-pagination mt-4 flex items-center justify-between text-xs text-gray-500"
          >
            <button
              type="button"
              class="rounded border border-gray-300 px-3 py-1 hover:bg-gray-100 disabled:opacity-40"
              :disabled="currentPage <= 1"
              @click="goToPage(currentPage - 1)"
            >
              ← {{ t("public_browse.prev") }}
            </button>
            <span>{{ t("public_browse.page", { page: currentPage, total: totalPages }) }}</span>
            <button
              type="button"
              class="rounded border border-gray-300 px-3 py-1 hover:bg-gray-100 disabled:opacity-40"
              :disabled="currentPage >= totalPages"
              @click="goToPage(currentPage + 1)"
            >
              {{ t("public_browse.next") }} →
            </button>
          </div>
        </template>
      </template>
    </main>
  </div>
</template>
