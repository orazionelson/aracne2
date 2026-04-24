<script setup lang="ts">
/**
 * "Deposit on Dataverse" section for a collection.
 *
 * Mounted on CollectionDetailView when the dataverse_integration
 * plugin is active. Shows the most recent deposit status (DOI /
 * draft URL / failure) and exposes a manual deposit button with an
 * optional alias override that wins over the plugin's default
 * Dataverse alias for this single deposit.
 *
 * The DOI is shown for both draft and published states; the link
 * always targets the Dataverse landing page (always works) rather
 * than doi.org (which only resolves after publish).
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useDataverseStore,
  type DataverseDepositStatus,
} from "@/stores/dataverse";

const props = defineProps<{ slug: string }>();

const { t } = useI18n();
const dv = useDataverseStore();

const status = ref<DataverseDepositStatus | null>(null);
const error = ref<string | null>(null);
const aliasOverride = ref("");
const showAliasInput = ref(false);

onMounted(async () => {
  await refresh();
});

async function refresh(): Promise<void> {
  try {
    status.value = await dv.fetchCollectionStatus(props.slug);
  } catch {
    status.value = null;
  }
}

async function deposit(): Promise<void> {
  error.value = null;
  try {
    status.value = await dv.forceCollectionDeposit(props.slug, {
      alias: aliasOverride.value.trim() || null,
    });
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

const badgeClass = computed(() => (s: DataverseDepositStatus["status"]): string => {
  if (s === "published") {
    return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
  }
  if (s === "draft") {
    return "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200";
  }
  return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
});
</script>

<template>
  <section class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
    <div class="mb-3 flex items-start justify-between">
      <div>
        <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {{ t("dataverse.collection_section_title") }}
        </h2>
        <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {{ t("dataverse.collection_section_hint") }}
        </p>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </p>

    <div v-if="status" class="mb-4 rounded border border-gray-100 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-900">
      <p class="flex flex-wrap items-center gap-2">
        <span :class="['rounded px-1.5 py-0.5 text-[11px] font-medium', badgeClass(status.status)]">
          {{ t(`dataverse.status_${status.status}`) }}
        </span>
        <span v-if="status.doi" class="font-mono text-xs text-gray-700 dark:text-gray-200">
          DOI: {{ status.doi }}
        </span>
        <a v-if="status.landing_url" :href="status.landing_url" target="_blank" rel="noopener" class="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
          {{ t("dataverse.open_dataset") }}
        </a>
      </p>
      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {{ t("dataverse.submitted_at") }}: {{ new Date(status.submitted_at).toLocaleString() }}
        <span v-if="status.alias">
          · {{ t("dataverse.alias") }}: <code class="font-mono">{{ status.alias }}</code>
        </span>
      </p>
      <p v-if="status.status === 'draft'" class="mt-1 text-[11px] text-amber-700 dark:text-amber-300">
        {{ t("dataverse.draft_doi_caveat") }}
      </p>
      <p v-if="status.error" class="mt-1 text-xs text-red-600 dark:text-red-400">
        {{ status.error }}
      </p>
    </div>

    <div class="space-y-2">
      <div v-if="!showAliasInput" class="flex items-center gap-2">
        <button
          type="button" :disabled="dv.isDepositingCollection"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="deposit"
        >
          {{ dv.isDepositingCollection
            ? t("common.loading")
            : (status ? t("dataverse.redeposit_btn") : t("dataverse.deposit_btn")) }}
        </button>
        <button
          type="button"
          class="rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
          @click="showAliasInput = true"
        >
          {{ t("dataverse.override_alias_link") }}
        </button>
      </div>
      <div v-else class="flex items-center gap-2">
        <input
          v-model="aliasOverride" type="text"
          class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm font-mono dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          :placeholder="t('dataverse.override_alias_placeholder')"
        />
        <button
          type="button" :disabled="dv.isDepositingCollection"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="deposit"
        >
          {{ dv.isDepositingCollection ? t("common.loading") : t("dataverse.deposit_btn") }}
        </button>
        <button
          type="button"
          class="rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
          @click="showAliasInput = false; aliasOverride = ''"
        >
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>
  </section>
</template>
