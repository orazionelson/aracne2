<script setup lang="ts">
/**
 * Configuration panel for the Zotero import plugin.
 *
 * Same visual grammar as the Zenodo + Internet Archive panels: four
 * inputs (api_key sensitive, library_type select, library_id string,
 * api_base optional override), Save button at the bottom right.
 */

import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  useZoteroImportStore,
  type LibraryType,
} from "@/stores/zotero_import";

const { t } = useI18n();
const store = useZoteroImportStore();

const draft = ref({
  api_key: "",
  library_type: "group" as LibraryType,
  library_id: "",
  api_base: "",
});
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

async function load(): Promise<void> {
  loadError.value = null;
  try {
    await store.fetchConfig();
    const cfg = store.config;
    if (cfg) {
      draft.value = {
        api_key: "",
        library_type: cfg.library_type,
        library_id: cfg.library_id,
        api_base: cfg.api_base,
      };
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      loadError.value = t("zotero_import.restart_required");
    } else {
      const msg = (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message;
      loadError.value = msg ?? t("common.error");
    }
  }
}

async function save(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  try {
    const cfg = store.config;
    const patch: Record<string, unknown> = {};
    if (draft.value.api_key) patch.api_key = draft.value.api_key;
    if (!cfg || draft.value.library_type !== cfg.library_type)
      patch.library_type = draft.value.library_type;
    if (!cfg || draft.value.library_id !== cfg.library_id)
      patch.library_id = draft.value.library_id;
    if (!cfg || draft.value.api_base !== cfg.api_base)
      patch.api_base = draft.value.api_base;
    if (Object.keys(patch).length === 0) {
      saved.value = true;
      return;
    }
    await store.updateConfig(patch);
    await load();
    saved.value = true;
    setTimeout(() => {
      saved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  }
}

async function clearKey(): Promise<void> {
  saveError.value = null;
  try {
    await store.updateConfig({ api_key: "" });
    await load();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  }
}

onMounted(load);
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("zotero_import.panel_subtitle") }}
    </p>

    <p v-if="loadError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ loadError }}</p>
    <p v-if="saveError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ saveError }}</p>
    <p v-if="saved" class="mb-4 text-sm text-green-600 dark:text-green-400">
      {{ t("zotero_import.saved") }}
    </p>

    <div class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <div class="grid gap-4 md:grid-cols-2">
        <!-- API key -->
        <div class="md:col-span-2">
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zotero_import.api_key") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zotero_import.api_key_hint") }}
            <a
              class="text-indigo-600 hover:underline dark:text-indigo-400"
              href="https://www.zotero.org/settings/keys"
              target="_blank"
              rel="noopener"
            >
              {{ t("zotero_import.keys_link") }}
            </a>
          </p>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="draft.api_key"
              type="password"
              autocomplete="off"
              :placeholder="
                store.config?.api_key_set
                  ? t('zotero_import.placeholder_set')
                  : t('zotero_import.placeholder_empty')
              "
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              v-if="store.config?.api_key_set"
              class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="clearKey"
            >
              {{ t("zotero_import.clear") }}
            </button>
          </div>
        </div>

        <!-- Library type -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zotero_import.library_type") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zotero_import.library_type_hint") }}
          </p>
          <select
            v-model="draft.library_type"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="group">{{ t("zotero_import.library_type_group") }}</option>
            <option value="user">{{ t("zotero_import.library_type_user") }}</option>
          </select>
        </div>

        <!-- Library ID -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zotero_import.library_id") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ t("zotero_import.library_id_hint") }}</p>
          <input
            v-model="draft.library_id"
            type="text"
            maxlength="32"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            placeholder="12345"
          />
        </div>

        <!-- API base (optional override) -->
        <div class="md:col-span-2">
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zotero_import.api_base") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ t("zotero_import.api_base_hint") }}</p>
          <input
            v-model="draft.api_base"
            type="url"
            placeholder="https://api.zotero.org"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
        </div>
      </div>

      <div class="mt-5 flex justify-end">
        <button
          :disabled="store.isSaving || !!loadError"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ store.isSaving ? t("common.saving") : t("common.save") }}
        </button>
      </div>
    </div>
  </div>
</template>
