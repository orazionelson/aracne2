<script setup lang="ts">
/**
 * Trismegistos config page — API key (Fernet-encrypted at rest,
 * never echoed back; only a ``api_key_set`` boolean is returned).
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useTrismegistosStore } from "@/stores/trismegistos";

const { t } = useI18n();
const store = useTrismegistosStore();

const newKey = ref("");
const saveMessage = ref("");
const saveError = ref("");

onMounted(async () => {
  await store.fetchConfig();
});

async function save(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ api_key: newKey.value.trim() });
    saveMessage.value = t("common.saved");
    newKey.value = "";
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}

async function clearKey(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ api_key: "" });
    saveMessage.value = t("common.saved");
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">{{ t("trismegistos.panel_subtitle") }}</p>
    <div class="space-y-4 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">{{ t("trismegistos.field_api_key") }}</label>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ store.config?.api_key_set ? t("trismegistos.field_api_key_set") : t("trismegistos.field_api_key_unset") }}
        </p>
        <input v-model="newKey" type="password" autocomplete="off" maxlength="512" class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" :placeholder="t('trismegistos.field_api_key_placeholder')" />
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("trismegistos.field_api_key_hint") }}
          <a :href="store.config?.registration_url ?? 'https://www.trismegistos.org/api'" target="_blank" rel="noopener" class="text-indigo-600 hover:underline dark:text-indigo-400">trismegistos.org/api</a>.
        </p>
      </div>
      <div class="flex items-center gap-3 pt-2">
        <button type="button" :disabled="store.isSaving || !newKey" class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50" @click="save">
          {{ store.isSaving ? t("common.loading") : t("common.save") }}
        </button>
        <button v-if="store.config?.api_key_set" type="button" :disabled="store.isSaving" class="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/40" @click="clearKey">
          {{ t("trismegistos.clear_key") }}
        </button>
        <span v-if="saveMessage" class="text-xs text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-xs text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>
    </div>
  </div>
</template>
