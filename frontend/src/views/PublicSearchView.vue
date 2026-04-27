<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
usePublicCustomCss();

// The chosen engine renders its own self-contained HTML page at
// /api/v1/search-pages/<slug>/, so we just embed it. When the
// admin disables the feature mid-session the iframe URL becomes
// empty and we render a polite empty state instead.
const slug = computed(() => uiConfig.config.public_search_engine_slug || "");
const enabled = computed(
  () => uiConfig.config.public_search_engine_enabled && !!slug.value,
);
const embedUrl = computed(() =>
  enabled.value ? `/api/v1/search-pages/${slug.value}/` : "",
);
</script>

<template>
  <div class="ps-page">
    <main class="ps-main mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-6">
      <p
        v-if="!enabled"
        class="ps-disabled rounded border border-dashed border-gray-200 px-4 py-12 text-center text-sm text-gray-500"
      >
        {{ t("public_search.disabled") }}
      </p>
      <iframe
        v-else
        :src="embedUrl"
        class="ps-frame flex-1 w-full rounded-xl border border-gray-200 bg-white shadow-sm"
        style="min-height: 80vh;"
        :title="t('nav.search')"
      />
    </main>
  </div>
</template>
