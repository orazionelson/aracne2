<script setup lang="ts">
import { useI18n } from "vue-i18n";
const { t } = useI18n();
</script>
<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">{{ t("gnd.panel_subtitle") }}</p>
    <div class="rounded border border-gray-200 bg-white p-5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
      <p>{{ t("gnd.no_config_notice") }}</p>
      <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">{{ t("gnd.usage_hint") }}</p>
    </div>
  </div>
</template>
