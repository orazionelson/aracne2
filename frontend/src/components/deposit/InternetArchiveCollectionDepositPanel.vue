<script setup lang="ts">
/**
 * "Deposita" → Internet Archive tab body. Owns its own status fetch +
 * archive / refresh actions. Emits @status-changed so the parent can
 * refresh any collection-header badge that depends on the SPN2 state.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useInternetArchiveStore,
  type ArchiveStatus,
} from "@/stores/internet_archive";
import { useCollectionStore } from "@/stores/collections";

const props = defineProps<{ slug: string }>();
const emit = defineEmits<{
  (e: "status-changed", status: ArchiveStatus | null): void;
}>();

const { t } = useI18n();
const store = useInternetArchiveStore();
const collectionStore = useCollectionStore();

const status = ref<ArchiveStatus | null>(null);
const isWorking = ref(false);
const errorMsg = ref<string | null>(null);

async function loadStatus(): Promise<void> {
  try {
    status.value = await store.fetchStatus(props.slug);
  } catch {
    status.value = null;
  }
  emit("status-changed", status.value);
}

async function archive(): Promise<void> {
  errorMsg.value = null;
  isWorking.value = true;
  try {
    status.value = await store.forceArchive(props.slug);
    emit("status-changed", status.value);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    errorMsg.value = msg ?? t("common.error");
  } finally {
    isWorking.value = false;
  }
}

async function refresh(): Promise<void> {
  errorMsg.value = null;
  isWorking.value = true;
  try {
    status.value = await store.refreshArchive(props.slug);
    emit("status-changed", status.value);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    errorMsg.value = msg ?? t("common.error");
  } finally {
    isWorking.value = false;
  }
}

onMounted(loadStatus);
</script>

<template>
  <div>
    <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
      {{ t("internet_archive.collection_section_hint") }}
    </p>
    <div
      v-if="collectionStore.current?.status === 'published'"
      class="flex flex-wrap items-center gap-2"
    >
      <button
        v-if="!status || status.status !== 'pending'"
        :disabled="isWorking"
        class="inline-flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
        @click="archive"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 8v13H3V8" /><path d="M1 3h22v5H1z" /><path d="M10 12h4" />
        </svg>
        {{
          isWorking
            ? t("internet_archive.working")
            : (status ? t("internet_archive.rearchive_btn") : t("internet_archive.archive_btn"))
        }}
      </button>
      <button
        v-else
        :disabled="isWorking"
        class="inline-flex items-center gap-1.5 rounded border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200 dark:hover:bg-amber-900/50"
        @click="refresh"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-6.22-8.56" /><path d="M21 3v6h-6" />
        </svg>
        {{ isWorking ? t("internet_archive.working") : t("internet_archive.refresh_btn") }}
      </button>
      <span v-if="errorMsg" class="text-xs text-red-600 dark:text-red-400">{{ errorMsg }}</span>
    </div>
    <p v-else class="text-sm text-gray-500 dark:text-gray-400">
      {{ t("internet_archive.collection_needs_published") }}
    </p>
  </div>
</template>
