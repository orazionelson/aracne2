<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useUiConfigStore } from '@/stores/ui_config';

const { t } = useI18n();
const route = useRoute();
const uiConfig = useUiConfigStore();

const slug = route.params.slug as string;

// In development fall back to the EVT container port if VITE_EVT_BASE_URL is unset.
const EVT_BASE =
  (import.meta.env.VITE_EVT_BASE_URL as string | undefined) ||
  (import.meta.env.DEV ? 'http://localhost:8181' : '');
const evtSrc = `${EVT_BASE}/evt/${slug}/`;

// ``uiConfig.config.evt_enabled`` is the combined (plugin-active ∧ setting-on)
// flag exposed by the backend. When false the iframe points at an endpoint
// the server doesn't mount, so render a friendly notice instead.
const viewerAvailable = computed(() => uiConfig.config.evt_enabled);

onMounted(async () => {
  if (!uiConfig.fetched) await uiConfig.fetchConfig();
});
</script>

<template>
  <div class="flex h-screen flex-col">
    <!-- Minimal header -->
    <div class="flex flex-shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-4 py-2">
      <RouterLink
        to="/"
        class="text-sm text-gray-500 hover:text-gray-800"
      >
        ← {{ t('nav.home') }}
      </RouterLink>
      <span class="text-gray-300">/</span>
      <span class="text-sm font-semibold text-gray-800">{{ t('evt.viewer_title') }}</span>
    </div>

    <!-- EVT iframe — fills remaining viewport -->
    <iframe
      v-if="viewerAvailable"
      :src="evtSrc"
      class="flex-1 border-0"
      :title="t('evt.viewer_title')"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />

    <!-- Friendly fallback when the EVT plugin is not active on this installation. -->
    <div
      v-else
      class="flex flex-1 items-center justify-center bg-gray-50 p-8 dark:bg-gray-900"
    >
      <div class="max-w-md rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">
          {{ t('evt.viewer_unavailable_title') }}
        </h2>
        <p class="mt-3 text-sm text-gray-600 dark:text-gray-300">
          {{ t('evt.viewer_unavailable_body') }}
        </p>
        <RouterLink
          to="/"
          class="mt-6 inline-block rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          {{ t('evt.back_home') }}
        </RouterLink>
      </div>
    </div>
  </div>
</template>
