<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { apiClient } from "@/services/api";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

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
</script>

<template>
  <div class="pc-page min-h-screen bg-gray-50">
    <!-- Public header -->
    <header
      class="pc-header flex h-14 items-center gap-3 px-6 text-white shadow"
      :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
    >
      <router-link to="/" class="pc-logo flex items-center gap-2 font-bold text-lg hover:opacity-80">
        <img
          v-if="uiConfig.config.platform_logo_url"
          :src="uiConfig.config.platform_logo_url"
          alt="Logo"
          class="pc-logo-img h-8 w-auto object-contain"
        />
        <span class="pc-site-name">{{ uiConfig.config.platform_name }}</span>
      </router-link>
      <span class="pc-login ml-auto text-sm opacity-80">
        <router-link to="/login" class="hover:underline">{{ t("auth.sign_in") }}</router-link>
      </span>
    </header>

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

        <ul v-else class="doc-list divide-y divide-gray-200 rounded-xl border border-gray-200 bg-white shadow-sm">
          <li
            v-for="doc in collection.documents"
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
      </template>
    </main>
  </div>
</template>
