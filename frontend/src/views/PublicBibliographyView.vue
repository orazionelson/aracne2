<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { useCollectionStore, type CollectionBibliography } from "@/stores/collections";
import { apiClient } from "@/services/api";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

const { t } = useI18n();
const route = useRoute();
const uiConfig = useUiConfigStore();
const collectionsStore = useCollectionStore();
usePublicCustomCss();

interface PublicDocumentInfo { filename: string; title: string | null; author: string | null }
interface PublicCollectionDetail { documents: PublicDocumentInfo[] }

const slug = route.params.slug as string;
const isLoading = ref(true);
const error = ref<string | null>(null);
const bibliography = ref<CollectionBibliography | null>(null);
const availableFilenames = ref<Set<string>>(new Set());

onMounted(async () => {
  uiConfig.fetchConfig().catch(() => { /* non-fatal */ });
  // Pull the collection detail in parallel so we can linkify any TEI
  // filename mentioned in a bibliography entry, but only when the
  // document is actually publicly accessible. A failure here is non-
  // fatal — the page just renders without filename links.
  apiClient.get<PublicCollectionDetail>(`/public/collections/${slug}`)
    .then((d) => { availableFilenames.value = new Set(d.documents.map((x) => x.filename)); })
    .catch(() => { /* leave the set empty */ });
  try {
    bibliography.value = await collectionsStore.fetchPublicBibliography(slug);
  } catch {
    error.value = t("public.bibliography_not_found");
  } finally {
    isLoading.value = false;
  }
});

// Bare ``foo.xml`` token. Anchored on a non-word, non-dot, non-dash
// boundary so we only catch standalone filenames and not, e.g.
// ``my-archive.xml.zip``.
const XML_FN_RE = /(?<![\w./\-])([A-Za-z0-9_][\w.\-]*\.xml)(?![\w./\-])/g;

interface BibFragment {
  kind: "text" | "link";
  value: string;
  filename?: string;
}

interface BibEntry {
  fragments: BibFragment[];
}

function splitEntry(text: string, available: Set<string>): BibFragment[] {
  if (available.size === 0) return [{ kind: "text", value: text }];
  const out: BibFragment[] = [];
  let last = 0;
  for (const m of text.matchAll(XML_FN_RE)) {
    const fn = m[1];
    const start = m.index ?? 0;
    if (!available.has(fn)) continue;
    if (start > last) out.push({ kind: "text", value: text.slice(last, start) });
    out.push({ kind: "link", value: fn, filename: fn });
    last = start + fn.length;
  }
  if (last < text.length) out.push({ kind: "text", value: text.slice(last) });
  return out.length ? out : [{ kind: "text", value: text }];
}

/**
 * Parse the stored XML <listBibl> and extract one plain-text entry per
 * <bibl> or <biblStruct> child. Uses the browser's native DOMParser so
 * no extra dependencies are needed.
 */
const entries = computed<BibEntry[]>(() => {
  if (!bibliography.value) return [];
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(bibliography.value.content, "application/xml");
    const result: BibEntry[] = [];
    const teiNs = "http://www.tei-c.org/ns/1.0";

    for (const tag of ["bibl", "biblStruct"]) {
      // Try namespaced first, fall back to no-namespace.
      let nodes = doc.getElementsByTagNameNS(teiNs, tag);
      if (nodes.length === 0) nodes = doc.getElementsByTagName(tag);
      for (let i = 0; i < nodes.length; i++) {
        const text = nodes[i].textContent?.trim().replace(/\s+/g, " ") ?? "";
        if (text) result.push({ fragments: splitEntry(text, availableFilenames.value) });
      }
    }
    return result;
  } catch {
    return [];
  }
});
</script>

<template>
  <div class="pb-page">
    <main class="pb-main mx-auto max-w-3xl px-4 py-10">
      <!-- Loading -->
      <p v-if="isLoading" class="text-sm text-gray-400">{{ t("common.loading") }}</p>

      <!-- Error / not found -->
      <div v-else-if="error" class="pb-error rounded-lg border border-red-200 bg-red-50 p-6 text-center">
        <p class="text-sm text-red-700">{{ error }}</p>
        <router-link
          :to="{ name: 'public-collection', params: { slug } }"
          class="mt-4 inline-block text-sm text-indigo-600 hover:underline"
        >
          ← {{ t("public.back_to_collection") }}
        </router-link>
      </div>

      <template v-else-if="bibliography">
        <!-- Page title -->
        <div class="pb-page-title mb-6">
          <router-link
            :to="{ name: 'public-collection', params: { slug } }"
            class="pb-back-link mb-2 inline-block text-xs text-gray-400 hover:text-gray-600"
          >
            ← {{ t("public.back_to_collection") }}
          </router-link>
          <h1 class="text-2xl font-bold text-gray-900">{{ t("public.bibliography_title") }}</h1>
          <p class="mt-1 text-xs text-gray-400">
            {{ t("bibliobuilder.saved_version", { version: bibliography.version }) }}
            · {{ new Date(bibliography.created_at).toLocaleDateString() }}
          </p>
        </div>

        <!-- No entries fallback -->
        <p v-if="entries.length === 0" class="text-sm text-gray-500">
          {{ t("public.bibliography_empty") }}
        </p>

        <!-- Bibliography list -->
        <ol v-else class="bibliography-list space-y-3">
          <li
            v-for="(entry, idx) in entries"
            :key="idx"
            class="bibliography-item flex gap-3 rounded-lg border border-gray-100 bg-white px-5 py-3 shadow-sm"
          >
            <span class="mt-0.5 shrink-0 font-mono text-sm text-gray-300">{{ idx + 1 }}.</span>
            <span class="text-sm leading-relaxed text-gray-800">
              <template v-for="(frag, fidx) in entry.fragments" :key="fidx">
                <RouterLink
                  v-if="frag.kind === 'link' && frag.filename"
                  :to="{ name: 'public-document', params: { slug, filename: frag.filename } }"
                  class="bibl-doc-link text-indigo-600 hover:underline"
                >{{ frag.value }}</RouterLink>
                <template v-else>{{ frag.value }}</template>
              </template>
            </span>
          </li>
        </ol>
      </template>
    </main>
  </div>
</template>
