<script setup lang="ts">
/**
 * OpenAlex config page — polite-pool contact email (same pattern as
 * CrossRef's contact email).
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useOpenAlexStore } from "@/stores/openalex";

const { t } = useI18n();
const store = useOpenAlexStore();

const contactEmail = ref("");
const saveMessage = ref("");
const saveError = ref("");

onMounted(async () => {
  await store.fetchConfig();
  contactEmail.value = store.config?.contact_email ?? "";
});

async function save(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ contact_email: contactEmail.value.trim() || null });
    saveMessage.value = t("common.saved");
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">{{ t("openalex.panel_subtitle") }}</p>
    <div class="space-y-4 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">{{ t("openalex.field_contact_email") }}</label>
        <input v-model="contactEmail" type="email" maxlength="256" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" :placeholder="store.config?.fallback_email ?? ''" />
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("openalex.field_contact_email_hint", { fallback: store.config?.fallback_email ?? "" }) }}
        </p>
      </div>
      <div class="flex items-center gap-3 pt-2">
        <button type="button" :disabled="store.isSaving" class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50" @click="save">
          {{ store.isSaving ? t("common.loading") : t("common.save") }}
        </button>
        <span v-if="saveMessage" class="text-xs text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-xs text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>
    </div>
  </div>
</template>
