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

const xmlContent = ref("");
const isLoading = ref(true);
const isSaving = ref(false);
const error = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

onMounted(async () => {
  try {
    xmlContent.value = await store.fetchDocumentRaw(slug, filename);
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});

async function handleSave(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  isSaving.value = true;
  try {
    await store.updateDocument(slug, filename, xmlContent.value);
    saved.value = true;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}
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
    <div class="mb-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h1 class="font-mono text-lg font-semibold text-gray-800">{{ filename }}</h1>
        <span class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
          {{ t("documents.action_edit") }}
        </span>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="saved" class="text-xs text-green-600">{{ t("documents.saved") }}</span>
        <p v-if="saveError" class="text-xs text-red-600">{{ saveError }}</p>
        <button
          :disabled="isSaving || isLoading"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="handleSave"
        >
          {{ isSaving ? t("common.loading") : t("common.save") }}
        </button>
      </div>
    </div>

    <p v-if="isLoading" class="text-sm text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <textarea
      v-else
      v-model="xmlContent"
      spellcheck="false"
      class="h-[70vh] w-full rounded border border-gray-300 bg-gray-50 p-4 font-mono text-xs leading-relaxed text-gray-800 focus:border-indigo-400 focus:outline-none"
      @input="saved = false"
    />
  </div>
</template>
