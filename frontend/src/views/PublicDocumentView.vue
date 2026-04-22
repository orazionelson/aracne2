<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useUiConfigStore } from "@/stores/ui_config";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

const route = useRoute();
const uiConfig = useUiConfigStore();
usePublicCustomCss();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

const renderUrl = computed(() => {
  const base = `/api/v1/public/collections/${slug}/documents/${filename}`;
  const h = route.query.highlight;
  return h ? `${base}?highlight=${encodeURIComponent(String(h))}` : base;
});
</script>

<template>
  <div class="pd-page flex flex-col bg-gray-50">
    <main class="pd-main mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-10">
      <!-- Breadcrumb -->
      <nav class="pd-breadcrumb mb-6 text-sm text-gray-400">
        <router-link to="/" class="hover:text-gray-700">
          {{ uiConfig.config.platform_name }}
        </router-link>
        <span class="mx-1">/</span>
        <router-link
          :to="{ name: 'public-collection', params: { slug } }"
          class="hover:text-gray-700"
        >
          {{ slug }}
        </router-link>
        <span class="mx-1">/</span>
        <span class="font-mono text-gray-700">{{ filename }}</span>
      </nav>

      <!-- Rendered document -->
      <iframe
        :src="renderUrl"
        class="doc-frame flex-1 w-full rounded-xl border border-gray-200 bg-white shadow-sm"
        style="min-height: 70vh;"
        :title="filename"
      />
    </main>
  </div>
</template>
