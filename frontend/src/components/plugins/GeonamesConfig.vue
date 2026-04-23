<script setup lang="ts">
/**
 * GeoNames plugin config page.
 *
 * Two fields:
 *   - url_format (toggle): web vs semantic-web URI for the @ref inserted
 *     by the editor panel.
 *   - geonames_username: shown READ-ONLY here because it is a shared
 *     system setting (also used by the collection-create form). The
 *     admin edits it from /admin/settings, not from here.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useGeonamesLookupStore, type GeonamesUrlFormat } from "@/stores/geonames_lookup";

const { t } = useI18n();
const store = useGeonamesLookupStore();

const urlFormat = ref<GeonamesUrlFormat>("web");
const saveMessage = ref<string>("");
const saveError = ref<string>("");

onMounted(async () => {
  await store.fetchConfig();
  if (store.config) {
    urlFormat.value = store.config.url_format;
  }
});

async function save(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ url_format: urlFormat.value });
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
      {{ t("geonames.panel_subtitle") }}
    </p>

    <div class="space-y-4 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <!-- URL format toggle -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("geonames.field_url_format") }}
        </label>
        <div class="mt-2 space-y-2">
          <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
            <input v-model="urlFormat" type="radio" value="web" class="mt-0.5" />
            <span>
              <code class="rounded bg-gray-100 px-1 text-xs dark:bg-gray-900">https://www.geonames.org/{id}</code>
              <span class="block text-xs text-gray-500 dark:text-gray-400">{{ t("geonames.field_url_format_web_hint") }}</span>
            </span>
          </label>
          <label class="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
            <input v-model="urlFormat" type="radio" value="sws" class="mt-0.5" />
            <span>
              <code class="rounded bg-gray-100 px-1 text-xs dark:bg-gray-900">http://sws.geonames.org/{id}/</code>
              <span class="block text-xs text-gray-500 dark:text-gray-400">{{ t("geonames.field_url_format_sws_hint") }}</span>
            </span>
          </label>
        </div>
      </div>

      <!-- Username (read-only snapshot) -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("geonames.field_username") }}
        </label>
        <p class="mt-1 font-mono text-sm text-gray-800 dark:text-gray-100">
          {{ store.config?.geonames_username ?? "—" }}
        </p>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("geonames.field_username_hint") }}
        </p>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button
          type="button"
          :disabled="store.isSaving"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ store.isSaving ? t("common.loading") : t("common.save") }}
        </button>
        <span v-if="saveMessage" class="text-xs text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-xs text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>
    </div>
  </div>
</template>
