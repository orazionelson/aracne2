<script setup lang="ts">
/**
 * "Save Page Now" section for a website.
 *
 * Mounted in WebsiteEditView's ``deposit`` tab when the
 * ``internet_archive`` plugin is active. Submits the website's public
 * URL to the Wayback Machine and exposes a Refresh button that
 * re-polls a pending SPN2 job.
 *
 * All three rendering modes (STATIC / HYBRID / DYNAMIC) are valid
 * targets — Wayback only needs a URL that returns HTML, which the
 * Aracne2 server emits in every mode. So unlike the Zenodo section,
 * the only precondition this component enforces is that the plugin
 * is active and a website slug exists.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useInternetArchiveStore,
  type ArchiveStatus,
} from "@/stores/internet_archive";
import type { Website } from "@/stores/websites";

const props = defineProps<{ website: Website }>();

const { t } = useI18n();
const ia = useInternetArchiveStore();

const status = ref<ArchiveStatus | null>(null);
const error = ref<string | null>(null);
const isRefreshing = ref(false);

onMounted(async () => {
  await refresh();
});

async function refresh(): Promise<void> {
  try {
    status.value = await ia.fetchWebsiteStatus(props.website.slug);
  } catch {
    status.value = null;
  }
}

async function archive(): Promise<void> {
  error.value = null;
  try {
    status.value = await ia.forceWebsiteArchive(props.website.slug);
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function poll(): Promise<void> {
  error.value = null;
  isRefreshing.value = true;
  try {
    status.value = await ia.refreshWebsiteArchive(props.website.slug);
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  } finally {
    isRefreshing.value = false;
  }
}

function badgeClass(s: ArchiveStatus["status"]): string {
  if (s === "success") {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300";
  }
  if (s === "pending") {
    return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200";
  }
  return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
}
</script>

<template>
  <section class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
    <div class="mb-3 flex items-start justify-between">
      <div>
        <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {{ t("internet_archive.website_section_title") }}
        </h2>
        <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {{ t("internet_archive.website_section_hint") }}
        </p>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </p>

    <!-- Most recent archive summary -->
    <div v-if="status" class="mb-4 rounded border border-gray-100 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-900">
      <p class="flex flex-wrap items-center gap-2">
        <span :class="['rounded px-1.5 py-0.5 text-[11px] font-medium', badgeClass(status.status)]">
          {{ t(`internet_archive.status_${status.status}`) }}
        </span>
        <a v-if="status.wayback_url" :href="status.wayback_url" target="_blank" rel="noopener" class="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
          {{ t("internet_archive.open_snapshot") }}
        </a>
        <span v-if="status.original_url" class="font-mono text-[11px] text-gray-500 dark:text-gray-400">
          {{ status.original_url }}
        </span>
      </p>
      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {{ t("internet_archive.submitted_at") }}: {{ new Date(status.submitted_at).toLocaleString() }}
      </p>
      <p v-if="status.error" class="mt-1 text-xs text-red-600 dark:text-red-400">
        {{ status.error }}
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        :disabled="ia.isArchivingWebsite"
        class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
        @click="archive"
      >
        {{ ia.isArchivingWebsite
          ? t("internet_archive.working")
          : (status ? t("internet_archive.rearchive_btn") : t("internet_archive.archive_btn")) }}
      </button>
      <button
        v-if="status?.status === 'pending'"
        type="button"
        :disabled="isRefreshing"
        class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
        @click="poll"
      >
        {{ isRefreshing ? t("common.loading") : t("internet_archive.refresh_btn") }}
      </button>
    </div>
  </section>
</template>
