<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const year = computed(() => new Date().getFullYear());
</script>

<template>
  <footer class="border-t border-gray-200 bg-white">
    <div class="mx-auto flex max-w-screen-xl items-center justify-between px-6 py-4 text-xs text-gray-400">
      <span>© {{ year }} {{ uiConfig.config.platform_name }}</span>
      <span>{{ t("footer.powered_by") }}</span>
    </div>
  </footer>
</template>
