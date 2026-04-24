<script setup lang="ts">
/**
 * EVT Viewer plugin config page.
 *
 * The plugin has one tunable: the global ``evt_enabled`` flag in
 * ``system_settings``. When off, the "Read in EVT" buttons are hidden
 * on public pages even for collections where per-collection
 * ``evt_enabled`` is true. Per-collection opt-in is edited from the
 * collection detail page.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useSettingStore } from "@/stores/settings";

const { t } = useI18n();
const settings = useSettingStore();

const SETTING_KEY = "evt_enabled";

const saveMessage = ref("");
const saveError = ref("");

const enabled = computed({
  get: () => settings.getSetting(SETTING_KEY) === "true",
  set: async (value: boolean) => {
    saveMessage.value = "";
    saveError.value = "";
    try {
      await settings.updateSetting(SETTING_KEY, value ? "true" : "false");
      saveMessage.value = t("common.saved");
      setTimeout(() => { saveMessage.value = ""; }, 2500);
    } catch (err) {
      saveError.value = (err as Error).message ?? t("common.error");
    }
  },
});

onMounted(async () => {
  if (settings.settings.length === 0) {
    await settings.fetchSettings();
  }
});
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("evt.panel_subtitle") }}
    </p>

    <div class="space-y-4 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <label class="flex cursor-pointer items-start gap-3">
        <input
          :checked="enabled"
          type="checkbox"
          class="mt-1 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          @change="enabled = ($event.target as HTMLInputElement).checked"
        />
        <span>
          <span class="font-medium text-gray-700 dark:text-gray-200">
            {{ t("evt.global_toggle_label") }}
          </span>
          <span class="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
            {{ t("evt.global_toggle_hint") }}
          </span>
        </span>
      </label>

      <div v-if="saveMessage || saveError" class="text-xs">
        <span v-if="saveMessage" class="text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>

      <p class="border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
        {{ t("evt.container_hint") }}
      </p>
    </div>
  </div>
</template>
