<script setup lang="ts">
/**
 * "Deposit on Zenodo" section for a website.
 *
 * Mounted in WebsiteEditView's ``deposit`` tab when the
 * ``zenodo_deposit`` plugin is active. Shows the most recent deposit
 * status (DOI / draft URL / failure) and exposes a manual deposit
 * button with a "as zip" toggle that lets the operator choose
 * between a single archive (default — best for archival) or per-file
 * uploads (browsable in Zenodo's Files tab).
 *
 * Refuses on DYNAMIC sites and on sites that have not been built;
 * the backend is the source of truth and surfaces these as 409 with
 * a clear message that this component just displays.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useZenodoStore,
  type WebsiteDepositStatus,
} from "@/stores/zenodo";
import type { Website } from "@/stores/websites";

const props = defineProps<{ website: Website }>();

const { t } = useI18n();
const zenodo = useZenodoStore();

const status = ref<WebsiteDepositStatus | null>(null);
const error = ref<string | null>(null);

// User's choice for the next deposit. Defaults to True — bundling is
// almost always what an archival deposit wants.
const uploadAsZip = ref(true);

const canDeposit = computed(
  () => props.website.rendering_mode !== "DYNAMIC"
    && props.website.build_status === "done",
);

const whyCannotDeposit = computed<string | null>(() => {
  if (props.website.rendering_mode === "DYNAMIC") {
    return t("zenodo.website_cannot_deposit_dynamic");
  }
  if (props.website.build_status !== "done") {
    return t("zenodo.website_cannot_deposit_not_built");
  }
  return null;
});

onMounted(async () => {
  await refresh();
});

async function refresh(): Promise<void> {
  try {
    status.value = await zenodo.fetchWebsiteStatus(props.website.slug);
  } catch {
    status.value = null;
  }
}

async function deposit(): Promise<void> {
  error.value = null;
  try {
    status.value = await zenodo.forceWebsiteDeposit(
      props.website.slug,
      { upload_as_zip: uploadAsZip.value },
    );
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

function statusBadgeClass(s: WebsiteDepositStatus["status"]): string {
  if (s === "published") {
    return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
  }
  if (s === "draft") {
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
          {{ t("zenodo.website_section_title") }}
        </h2>
        <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {{ t("zenodo.website_section_hint") }}
        </p>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </p>

    <!-- Most recent deposit summary -->
    <div v-if="status" class="mb-4 rounded border border-gray-100 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-900">
      <p class="flex flex-wrap items-center gap-2">
        <span :class="['rounded px-1.5 py-0.5 text-[11px] font-medium', statusBadgeClass(status.status)]">
          {{ t(`zenodo.status_${status.status}`) }}
        </span>
        <span v-if="status.doi" class="font-mono text-xs text-gray-700 dark:text-gray-200">
          DOI: {{ status.doi }}
        </span>
        <a v-if="status.record_url" :href="status.record_url" target="_blank" rel="noopener" class="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
          {{ t("zenodo.open_record") }}
        </a>
      </p>
      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {{ t("zenodo.submitted_at") }}: {{ new Date(status.submitted_at).toLocaleString() }}
        <span v-if="status.file_count !== null && status.file_count !== undefined">
          · {{ t("zenodo.file_count", { n: status.file_count }) }}
        </span>
        <span v-if="status.uploaded_as_zip">
          · {{ t("zenodo.bundled_as_zip") }}
        </span>
      </p>
      <p v-if="status.error" class="mt-1 text-xs text-red-600 dark:text-red-400">
        {{ status.error }}
      </p>
    </div>

    <p v-if="whyCannotDeposit" class="mb-3 text-xs text-amber-700 dark:text-amber-300">
      {{ whyCannotDeposit }}
    </p>

    <!-- Deposit form -->
    <div class="space-y-3">
      <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
        <input v-model="uploadAsZip" type="checkbox" class="mt-1" />
        <span>
          <span class="font-medium">{{ t("zenodo.upload_as_zip_label") }}</span>
          <span class="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.upload_as_zip_hint") }}
          </span>
        </span>
      </label>

      <div class="flex items-center gap-2">
        <button
          type="button"
          :disabled="!canDeposit || zenodo.isDepositingWebsite"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="deposit"
        >
          {{ zenodo.isDepositingWebsite
            ? t("common.loading")
            : (status ? t("zenodo.redeposit_btn") : t("zenodo.deposit_btn")) }}
        </button>
      </div>
    </div>
  </section>
</template>
