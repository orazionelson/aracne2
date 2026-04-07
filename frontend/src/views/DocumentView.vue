<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useCollectionStore } from "@/stores/collections";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

const xmlContent = ref<string | null>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    xmlContent.value = await store.fetchDocumentRaw(slug, filename);
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-8">
    <!-- Back -->
    <button
      class="mb-6 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800"
      @click="router.push({ name: 'collection-detail', params: { slug } })"
    >
      ← {{ slug }}
    </button>

    <!-- Header -->
    <div class="mb-4 flex items-center gap-3">
      <h1 class="font-mono text-lg font-semibold text-gray-800">{{ filename }}</h1>
      <span class="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
        {{ t("documents.action_view") }}
      </span>
    </div>

    <p v-if="isLoading" class="text-sm text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <pre
      v-else
      class="overflow-x-auto rounded border border-gray-200 bg-gray-50 p-5 font-mono text-xs leading-relaxed text-gray-800"
    >{{ xmlContent }}</pre>
  </div>
</template>
