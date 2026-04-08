<script setup lang="ts">
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const route = useRoute();

const slug = route.params.slug as string;

const EVT_BASE = (import.meta.env.VITE_EVT_BASE_URL as string | undefined) ?? '';
const evtSrc = `${EVT_BASE}/evt/${slug}/`;
</script>

<template>
  <div class="flex h-screen flex-col">
    <!-- Minimal header -->
    <div class="flex flex-shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-4 py-2">
      <RouterLink
        :to="{ name: 'collection-detail', params: { slug } }"
        class="text-sm text-gray-500 hover:text-gray-800"
      >
        ← {{ slug }}
      </RouterLink>
      <span class="text-gray-300">/</span>
      <span class="text-sm font-semibold text-gray-800">{{ t('evt.viewer_title') }}</span>
    </div>

    <!-- EVT iframe — fills remaining viewport -->
    <iframe
      :src="evtSrc"
      class="flex-1 border-0"
      :title="t('evt.viewer_title')"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />
  </div>
</template>
