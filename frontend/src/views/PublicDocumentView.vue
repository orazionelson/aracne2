<script setup lang="ts">
import { computed, ref, onBeforeUnmount, onMounted } from "vue";
import { useRoute } from "vue-router";
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

const route = useRoute();
const uiConfig = useUiConfigStore();
usePublicCustomCss();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

const renderUrl = computed(() => {
  const base = `/api/v1/public/collections/${slug}/documents/${filename}`;
  const h = route.query.highlight;
  return h ? `${base}?highlight=${encodeURIComponent(String(h))}` : base;
});

// Frame mode (default true) keeps the historical fixed-height,
// internally-scrolling iframe. When the admin turns the setting off
// in Settings → Homepage → "Opzioni documento", the iframe auto-grows
// to the document's height so the parent page scrolls instead — no
// visible chrome, no nested scrollbars.
const frameEnabled = computed(() => uiConfig.config.public_pages_doc_frame_enabled);

const docFrame = ref<HTMLIFrameElement | null>(null);
const docHeight = ref<number | null>(null);
let resizeObs: ResizeObserver | null = null;

function syncFrameHeight(): void {
  const iframe = docFrame.value;
  if (!iframe) return;
  const doc = iframe.contentDocument;
  if (!doc || !doc.documentElement) return;
  // Pick the larger of body/html so we cover both quirks-mode and
  // standards-mode rendering of long TEI bodies.
  const h = Math.max(
    doc.documentElement.scrollHeight,
    doc.body ? doc.body.scrollHeight : 0,
  );
  if (h > 0) docHeight.value = h;
}

function onFrameLoad(): void {
  syncFrameHeight();
  // Reflow on async content (image loads, facsimile gallery, hover
  // tooltips). ResizeObserver covers the steady state.
  const iframe = docFrame.value;
  const doc = iframe?.contentDocument;
  if (doc && "ResizeObserver" in window) {
    resizeObs?.disconnect();
    resizeObs = new ResizeObserver(syncFrameHeight);
    resizeObs.observe(doc.documentElement);
  }
}

onBeforeUnmount(() => {
  resizeObs?.disconnect();
  resizeObs = null;
});

// Fetch the collection metadata once so the JSON-LD block can include
// isPartOf + an author / publisher inherited from the parent collection
// (the public-document render endpoint returns HTML, not structured
// metadata; cheapest way to get that data is reusing the collection
// detail endpoint).
const collection = ref<PublicCollectionDetail | null>(null);
onMounted(async () => {
  try {
    collection.value = await apiClient.get<PublicCollectionDetail>(
      `/public/collections/${slug}`,
    );
  } catch {
    // Non-blocking: the page still renders; JSON-LD will simply be absent.
    collection.value = null;
  }
});

const origin = computed(() =>
  typeof window !== "undefined" ? window.location.origin : "",
);

useJsonLd(
  computed(() => {
    const c = collection.value;
    if (!c) return null;
    const doc = c.documents.find((d) => d.filename === filename);
    const docUrl = `${origin.value}/browse/${c.slug}/${encodeURIComponent(filename)}`;
    const collectionUrl = `${origin.value}/browse/${c.slug}`;
    const payload: Record<string, unknown> = {
      "@context": "https://schema.org",
      "@type": "CreativeWork",
      name: doc?.title || filename,
      url: docUrl,
      isPartOf: {
        "@type": "CreativeWork",
        name: c.title,
        url: collectionUrl,
      },
    };
    const author = doc?.author || c.author;
    if (author) payload.author = { "@type": "Person", name: author };
    if (c.publisher)
      payload.publisher = { "@type": "Organization", name: c.publisher };
    if (c.pub_year !== null && c.pub_year !== undefined)
      payload.datePublished = String(c.pub_year);
    return payload;
  }),
);
</script>

<template>
  <div class="pd-page flex flex-col bg-gray-50">
    <main class="pd-main mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-10">
      <!-- Breadcrumb -->
      <nav class="pd-breadcrumb mb-6 text-sm text-gray-400">
        <router-link to="/" class="hover:text-gray-700">
          {{ uiConfig.config.platform_name }}
        </router-link>
        <span class="mx-1">/</span>
        <router-link
          :to="{ name: 'public-collection', params: { slug } }"
          class="hover:text-gray-700"
        >
          {{ slug }}
        </router-link>
        <span class="mx-1">/</span>
        <span class="font-mono text-gray-700">{{ filename }}</span>
      </nav>

      <!-- Rendered document — fixed-height frame OR auto-grow inline -->
      <iframe
        v-if="frameEnabled"
        :src="renderUrl"
        class="doc-frame flex-1 w-full rounded-xl border border-gray-200 bg-white shadow-sm"
        style="min-height: 70vh;"
        :title="filename"
      />
      <iframe
        v-else
        ref="docFrame"
        :src="renderUrl"
        class="doc-frame-inline w-full"
        :style="{ height: docHeight ? docHeight + 'px' : 'auto', border: 'none', background: 'transparent' }"
        scrolling="no"
        :title="filename"
        @load="onFrameLoad"
      />
    </main>
  </div>
</template>
