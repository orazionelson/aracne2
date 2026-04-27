<script setup lang="ts">
/**
 * "Deposita" → Zenodo tab body. Owns the resource-type override
 * dropdown, the ZIP-bundle toggle, and the manual (re-)deposit action.
 * Emits @status-changed after a manual deposit so the parent can
 * refresh the collection-header DOI badge.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useZenodoStore, type DepositStatus } from "@/stores/zenodo";
import { useCollectionStore } from "@/stores/collections";

const props = defineProps<{ slug: string }>();
const emit = defineEmits<{
  (e: "status-changed", status: DepositStatus | null): void;
}>();

const { t } = useI18n();
const store = useZenodoStore();
const collectionStore = useCollectionStore();

// Per-collection override drafts. Empty string → "use platform default"
// (sent as null to the backend, which clears the override).
const resourceTypeDraft = ref<string>("");
const uploadAsZipDraft = ref<boolean>(false);
const isSaving = ref(false);
const saveError = ref<string | null>(null);
const justSaved = ref(false);

// Deposit action state.
const status = ref<DepositStatus | null>(null);
const isDepositing = ref(false);
const depositError = ref<string | null>(null);

const groupedResourceTypes = computed(() => {
  const groups = new Map<string, { id: string; label: string }[]>();
  for (const opt of store.resourceTypes) {
    const bucket = groups.get(opt.group);
    if (bucket) bucket.push({ id: opt.id, label: opt.label });
    else groups.set(opt.group, [{ id: opt.id, label: opt.label }]);
  }
  return Array.from(groups, ([group, options]) => ({ group, options }));
});

const dirty = computed(() => {
  const c = collectionStore.current;
  if (!c) return false;
  return (
    resourceTypeDraft.value !== (c.zenodo_resource_type ?? "") ||
    uploadAsZipDraft.value !== (c.zenodo_upload_as_zip ?? false)
  );
});

async function loadStatus(): Promise<void> {
  try {
    status.value = await store.fetchStatus(props.slug);
  } catch {
    status.value = null;
  }
  emit("status-changed", status.value);
}

async function deposit(): Promise<void> {
  depositError.value = null;
  isDepositing.value = true;
  try {
    status.value = await store.forceDeposit(props.slug);
    emit("status-changed", status.value);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    depositError.value = msg ?? t("common.error");
  } finally {
    isDepositing.value = false;
  }
}

async function save(): Promise<void> {
  const c = collectionStore.current;
  if (!c) return;
  saveError.value = null;
  justSaved.value = false;
  isSaving.value = true;
  try {
    await collectionStore.updateCollection(c.id, {
      zenodo_resource_type: resourceTypeDraft.value || null,
      zenodo_upload_as_zip: uploadAsZipDraft.value,
    });
    justSaved.value = true;
    setTimeout(() => {
      justSaved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

// Seed drafts from the loaded collection. The parent fetches the
// collection during its onMounted, so we watch for it appearing.
watch(
  () => collectionStore.current,
  (c) => {
    if (c && c.slug === props.slug) {
      resourceTypeDraft.value = c.zenodo_resource_type ?? "";
      uploadAsZipDraft.value = c.zenodo_upload_as_zip ?? false;
    }
  },
  { immediate: true },
);

onMounted(async () => {
  // Load both the controlled vocabulary and the current deposit status.
  // Failures are silent — the section just renders an empty dropdown.
  await Promise.all([
    store.fetchResourceTypes().catch(() => undefined),
    loadStatus(),
  ]);
});
</script>

<template>
  <div>
    <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
      {{ t("zenodo.collection_section_hint") }}
    </p>

    <p v-if="saveError" class="mb-2 text-sm text-red-600 dark:text-red-400">
      {{ saveError }}
    </p>
    <p v-if="justSaved" class="mb-2 text-sm text-green-600 dark:text-green-400">
      {{ t("zenodo.collection_section_saved") }}
    </p>

    <div class="space-y-3">
      <!-- Resource type dropdown -->
      <div class="flex flex-wrap items-center gap-2">
        <select
          v-model="resourceTypeDraft"
          class="min-w-[18rem] rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        >
          <option value="">{{ t("zenodo.collection_use_default") }}</option>
          <optgroup
            v-for="grp in groupedResourceTypes"
            :key="grp.group"
            :label="grp.group"
          >
            <option
              v-for="opt in grp.options"
              :key="opt.id"
              :value="opt.id"
            >{{ opt.label }}</option>
          </optgroup>
        </select>
      </div>

      <!-- ZIP bundle toggle -->
      <div class="flex items-start justify-between rounded border border-gray-200 p-3 dark:border-gray-700">
        <div class="mr-4">
          <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
            {{ t("zenodo.collection_upload_as_zip") }}
          </p>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.collection_upload_as_zip_hint") }}
          </p>
        </div>
        <button
          class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
          :class="uploadAsZipDraft ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
          @click="uploadAsZipDraft = !uploadAsZipDraft"
        >
          <span
            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
            :class="uploadAsZipDraft ? 'translate-x-5' : 'translate-x-0'"
          />
        </button>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
        <!-- Left: manual (re-)deposit, only once the collection is published. -->
        <div
          v-if="collectionStore.current?.status === 'published'"
          class="flex flex-wrap items-center gap-2"
        >
          <button
            :disabled="isDepositing"
            class="inline-flex items-center gap-1.5 rounded border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-200 dark:hover:bg-indigo-900/50"
            @click="deposit"
          >
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            {{ isDepositing ? t("zenodo.working") : (status ? t("zenodo.redeposit_btn") : t("zenodo.deposit_btn")) }}
          </button>
          <span v-if="depositError" class="text-xs text-red-600 dark:text-red-400">
            {{ depositError }}
          </span>
        </div>
        <span v-else />

        <!-- Right: save the per-collection overrides. -->
        <button
          :disabled="isSaving || !dirty"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="save"
        >
          {{ isSaving ? t("common.saving") : t("common.save") }}
        </button>
      </div>
    </div>
  </div>
</template>
