<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { useCollectionStore, type CollectionBibliography } from "@/stores/collections";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

const { t } = useI18n();
const route = useRoute();
const uiConfig = useUiConfigStore();
const collectionsStore = useCollectionStore();
usePublicCustomCss();

const slug = route.params.slug as string;
const isLoading = ref(true);
const error = ref<string | null>(null);
const bibliography = ref<CollectionBibliography | null>(null);

onMounted(async () => {
  uiConfig.fetchConfig().catch(() => { /* non-fatal */ });
  try {
    bibliography.value = await collectionsStore.fetchPublicBibliography(slug);
  } catch {
    error.value = t("public.bibliography_not_found");
  } finally {
    isLoading.value = false;
  }
});

interface BibEntry {
  text: string;
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
        if (text) result.push({ text });
      }
    }
    return result;
  } catch {
    return [];
  }
});
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Public header -->
    <header
      class="flex h-14 items-center gap-3 px-6 text-white shadow"
      :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
    >
      <router-link to="/" class="flex items-center gap-2 text-lg font-bold hover:opacity-80">
        <img
          v-if="uiConfig.config.platform_logo_url"
          :src="uiConfig.config.platform_logo_url"
          alt="Logo"
          class="h-8 w-auto object-contain"
        />
        <span>{{ uiConfig.config.platform_name }}</span>
      </router-link>
      <span class="ml-auto text-sm opacity-80">
        <router-link to="/login" class="hover:underline">
          {{ t("auth.sign_in") }}
        </router-link>
      </span>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-10">
      <!-- Loading -->
      <p v-if="isLoading" class="text-sm text-gray-400">{{ t("common.loading") }}</p>

      <!-- Error / not found -->
      <div v-else-if="error" class="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
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
        <div class="mb-6">
          <router-link
            :to="{ name: 'public-collection', params: { slug } }"
            class="mb-2 inline-block text-xs text-gray-400 hover:text-gray-600"
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
        <ol v-else class="space-y-3">
          <li
            v-for="(entry, idx) in entries"
            :key="idx"
            class="flex gap-3 rounded-lg border border-gray-100 bg-white px-5 py-3 shadow-sm"
          >
            <span class="mt-0.5 shrink-0 font-mono text-sm text-gray-300">{{ idx + 1 }}.</span>
            <span class="text-sm leading-relaxed text-gray-800">{{ entry.text }}</span>
          </li>
        </ol>
      </template>
    </main>
  </div>
</template>
