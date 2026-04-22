<script setup lang="ts">
import { computed } from "vue";
import { useUiConfigStore } from "@/stores/ui_config";
import { useJsonLd } from "@/composables/useJsonLd";
import PublicHomeSection from "@/components/PublicHomeSection.vue";

const uiConfig = useUiConfigStore();

// Emit a WebSite structured-data block so search engines / aggregators
// identify the landing page as the site's canonical entry.
useJsonLd(
  computed(() => {
    const name = uiConfig.config.platform_name;
    if (!name) return null;
    return {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name,
      url: typeof window !== "undefined" ? window.location.origin : undefined,
    };
  }),
);
</script>

<template>
  <PublicHomeSection />
</template>
