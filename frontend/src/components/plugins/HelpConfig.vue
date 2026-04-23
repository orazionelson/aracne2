<script setup lang="ts">
/**
 * Help plugin config page.
 *
 * The plugin has no credentials and no tunables — it renders the
 * Markdown files from backend/help_docs/ as sanitised HTML. This page
 * is purely informational so that the "Configure" link in
 * /admin/plugins resolves to something meaningful.
 */
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("help.panel_subtitle") }}
    </p>
    <div class="rounded border border-gray-200 bg-white p-5 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">
      <p>{{ t("help.no_config_notice") }}</p>
      <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
        {{ t("help.usage_hint") }}
      </p>
    </div>
  </div>
</template>
