<script setup lang="ts">
/**
 * Github Integration — plugin config page.
 *
 * Manages the *global* PAT used when a collection link has no
 * per-link override. The per-link override lives on the collection
 * detail page, not here.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useGithubStore } from "@/stores/github";

const { t } = useI18n();
const store = useGithubStore();

const newPat = ref("");
const saveMessage = ref("");
const saveError = ref("");

onMounted(async () => {
  await store.fetchConfig();
});

async function save(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ pat: newPat.value.trim() });
    saveMessage.value = t("common.saved");
    newPat.value = "";
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}

async function clearPat(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ pat: "" });
    saveMessage.value = t("common.saved");
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("github.panel_subtitle") }}
    </p>

    <div class="space-y-4 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("github.field_global_pat") }}
        </label>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ store.config?.pat_set
            ? t("github.field_pat_set")
            : t("github.field_pat_unset") }}
        </p>
        <input
          v-model="newPat"
          type="password"
          autocomplete="off"
          maxlength="512"
          class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          :placeholder="t('github.field_pat_placeholder')"
        />
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("github.field_pat_hint") }}
          <a href="https://github.com/settings/tokens" target="_blank" rel="noopener" class="text-indigo-600 hover:underline dark:text-indigo-400">
            github.com/settings/tokens
          </a>
          — {{ t("github.field_pat_scope_hint") }}
        </p>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button
          type="button"
          :disabled="store.isSaving || !newPat"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ store.isSaving ? t("common.loading") : t("common.save") }}
        </button>
        <button
          v-if="store.config?.pat_set"
          type="button"
          :disabled="store.isSaving"
          class="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/40"
          @click="clearPat"
        >
          {{ t("github.clear_pat") }}
        </button>
        <span v-if="saveMessage" class="text-xs text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-xs text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>

      <p class="border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
        {{ t("github.global_hint") }}
      </p>
    </div>
  </div>
</template>
