<script setup lang="ts">
/**
 * VIAF plugin config page — informational only.
 *
 * The plugin has no credentials or tunables; it proxies the public
 * VIAF AutoSuggest API. This page exists purely so the "Configure"
 * link in /admin/plugins resolves to something meaningful.
 */
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("viaf.panel_subtitle") }}
    </p>
    <div class="rounded border border-gray-200 bg-white p-5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
      <p>{{ t("viaf.no_config_notice") }}</p>
      <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
        {{ t("viaf.usage_hint") }}
      </p>
    </div>
  </div>
</template>
