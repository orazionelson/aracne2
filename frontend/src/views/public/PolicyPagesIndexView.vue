<script setup lang="ts">
/**
 * /policies — public index of currently-published policies.
 *
 * Served by the platform under the public layout. Reads the
 * anonymous endpoint ``GET /api/v1/policies`` which returns one
 * entry per published policy. Each entry routes to the per-policy
 * render view at /policies/<url_slug>.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";

interface PolicyIndexItem {
  url_slug: string;
  template_slug: string;
  title_key: string;
  categories: string[];
}

const { t, te } = useI18n();
const items = ref<PolicyIndexItem[]>([]);
const isLoading = ref(false);

onMounted(async () => {
  isLoading.value = true;
  try {
    items.value = await apiClient.get<PolicyIndexItem[]>("/policies");
  } finally {
    isLoading.value = false;
  }
});

function titleFor(item: PolicyIndexItem): string {
  return te(item.title_key) ? t(item.title_key) : item.template_slug;
}
</script>

<template>
  <main class="mx-auto max-w-3xl px-4 py-10">
    <h1 class="text-2xl font-bold text-gray-900">{{ t("policy_pages.public_index_title") }}</h1>
    <p class="mt-1 text-sm text-gray-500">
      {{ t("policy_pages.public_index_subtitle") }}
    </p>

    <p v-if="isLoading" class="mt-6 text-sm text-gray-500">{{ t("common.loading") }}</p>

    <p v-else-if="items.length === 0" class="mt-6 text-sm italic text-gray-500">
      {{ t("policy_pages.public_index_empty") }}
    </p>

    <ul v-else class="mt-6 divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
      <li v-for="item in items" :key="item.url_slug">
        <router-link
          :to="{ name: 'public-policy', params: { url_slug: item.url_slug } }"
          class="flex items-center justify-between px-4 py-3 text-sm hover:bg-indigo-50/40"
        >
          <span class="font-medium text-gray-800">{{ titleFor(item) }}</span>
          <span class="text-xs text-gray-400">
            <span
              v-for="cat in item.categories"
              :key="cat"
              class="ml-2 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] uppercase"
            >
              {{ cat }}
            </span>
          </span>
        </router-link>
      </li>
    </ul>
  </main>
</template>
