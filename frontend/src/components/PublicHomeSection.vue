<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { usePublicCollections } from "@/composables/usePublicCollections";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const { collections, isLoading, fetchCollections } = usePublicCollections();

const searchInput = ref("");
const activeSearch = ref("");

const showCollections = computed(() => uiConfig.config.home_show_collections);
const showSearch = computed(() => uiConfig.config.home_show_search);

function handleSearch(): void {
  activeSearch.value = searchInput.value.trim();
  fetchCollections(activeSearch.value);
}

function clearSearch(): void {
  searchInput.value = "";
  activeSearch.value = "";
  fetchCollections();
}

onMounted(() => {
  if (showCollections.value) fetchCollections();
});
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Public header -->
    <header
      class="flex h-14 items-center gap-3 px-6 text-white shadow"
      :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
    >
      <router-link to="/" class="flex items-center gap-2 font-bold text-lg hover:opacity-80">
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

    <main class="mx-auto max-w-4xl px-4 py-10">
      <!-- Search bar -->
      <div v-if="showSearch" class="mb-8">
        <form class="flex gap-2" @submit.prevent="handleSearch">
          <input
            v-model="searchInput"
            type="search"
            :placeholder="t('public.search_placeholder')"
            class="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            class="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {{ t("collections.search_button") }}
          </button>
          <button
            v-if="activeSearch"
            type="button"
            class="rounded-lg border px-4 py-2.5 text-sm hover:bg-gray-100"
            @click="clearSearch"
          >
            {{ t("collections.search_reset") }}
          </button>
        </form>
      </div>

      <!-- Collection list -->
      <template v-if="showCollections">
        <p v-if="isLoading" class="text-gray-400 text-sm">{{ t("common.loading") }}</p>

        <p v-else-if="collections.length === 0 && activeSearch" class="text-gray-500 text-sm">
          {{ t("collections.no_results", { q: activeSearch }) }}
        </p>

        <p v-else-if="collections.length === 0" class="text-gray-500 text-sm">
          {{ t("public.no_collections") }}
        </p>

        <ul v-else class="space-y-4">
          <li
            v-for="col in collections"
            :key="col.id"
            class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md"
          >
            <h2 class="text-lg font-semibold text-gray-900">{{ col.title }}</h2>
            <p v-if="col.description" class="mt-1 text-sm text-gray-500 line-clamp-2">
              {{ col.description }}
            </p>
            <div class="mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
              <span v-if="col.author">{{ col.author }}</span>
              <span v-if="col.publisher">{{ col.publisher }}</span>
              <span v-if="col.pub_year">{{ col.pub_year }}</span>
              <span v-if="col.published_at">
                {{ t("public.published") }}
                {{ new Date(col.published_at).toLocaleDateString() }}
              </span>
            </div>
            <!-- Document snippets (only shown when search matched document content) -->
            <ul v-if="col.doc_hits.length > 0" class="mt-3 space-y-1">
              <li v-for="hit in col.doc_hits" :key="hit.filename">
                <router-link
                  :to="{ name: 'public-document', params: { slug: col.slug, filename: hit.filename } }"
                  class="block rounded bg-yellow-50 px-3 py-1.5 text-xs text-gray-700 hover:bg-yellow-100"
                >
                  <span class="font-medium text-gray-500">{{ hit.filename }}</span>
                  <span class="mx-1 text-gray-300">—</span>
                  <span class="italic">…{{ hit.snippet }}…</span>
                </router-link>
              </li>
            </ul>

            <div class="mt-4 flex gap-2">
              <router-link
                :to="{ name: 'public-collection', params: { slug: col.slug } }"
                class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                {{ t("public.browse") }}
              </router-link>
              <router-link
                v-if="uiConfig.config.evt_enabled && col.doc_count === 1"
                :to="{ name: 'collection-read', params: { slug: col.slug } }"
                class="rounded border border-indigo-300 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50"
              >
                {{ t("public.view_in_evt") }}
              </router-link>
            </div>
          </li>
        </ul>
      </template>
    </main>
  </div>
</template>
