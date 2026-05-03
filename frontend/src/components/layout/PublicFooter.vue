<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { usePublicNav, usePublicNavLabel } from "@/composables/usePublicNav";

// Public-only footer. Same baseline as ``AppFooter`` for the © + powered-by
// row, plus the plugin-declared ``public_navigation`` footer-section
// iterator. Authenticated layouts continue to use ``AppFooter`` — the
// public-only links never appear in the editor chrome.

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const year = computed(() => new Date().getFullYear());
const footerLinks = usePublicNav("footer");
const labelFor = usePublicNavLabel();
</script>

<template>
  <footer class="border-t border-gray-300 bg-white">
    <div class="mx-auto max-w-screen-xl px-6 py-4 text-xs text-gray-600">
      <!-- Plugin-declared footer links -->
      <nav
        v-if="footerLinks.length > 0"
        class="ph-footer-links mb-3 flex flex-wrap items-center gap-x-4 gap-y-1"
        aria-label="Plugin footer links"
      >
        <router-link
          v-for="entry in footerLinks"
          :key="entry.plugin_name"
          :to="entry.url"
          class="ph-footer-link text-gray-600 hover:text-indigo-600 hover:underline"
        >
          {{ labelFor(entry) }}
        </router-link>
      </nav>
      <div class="flex items-center justify-between">
        <span>© {{ year }} {{ uiConfig.config.platform_name }}</span>
        <span>{{ t("footer.powered_by") }}</span>
      </div>
    </div>
  </footer>
</template>
