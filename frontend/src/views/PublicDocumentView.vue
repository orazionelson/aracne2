<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useUiConfigStore } from "@/stores/ui_config";

const { t } = useI18n();
const route = useRoute();
const auth = useAuthStore();
const uiConfig = useUiConfigStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

const renderUrl = computed(() => {
  const base = `/api/v1/public/collections/${slug}/documents/${filename}`;
  const h = route.query.highlight;
  return h ? `${base}?highlight=${encodeURIComponent(String(h))}` : base;
});
</script>

<template>
  <div class="flex min-h-screen flex-col bg-gray-50">
    <!-- Public header: shown only for unauthenticated visitors.
         Authenticated users already have AppNavbar from App.vue. -->
    <header
      v-if="!auth.isAuthenticated"
      class="flex h-14 items-center gap-3 px-6 text-white shadow"
      :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
    >
      <router-link to="/" class="flex items-center gap-2 font-bold text-lg hover:opacity-80">
        <img
          v-if="uiConfig.config.platform_logo_url"
          :src="uiConfig.config.platform_logo_url"
          alt="Logo"
          class="h-8 w-auto object-contain"
        />
        <span>{{ uiConfig.config.platform_name }}</span>
      </router-link>
      <span class="ml-auto text-sm opacity-80">
        <router-link to="/login" class="hover:underline">{{ t("auth.sign_in") }}</router-link>
      </span>
    </header>

    <main class="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-10">
      <!-- Breadcrumb -->
      <nav class="mb-6 text-sm text-gray-400">
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
        class="flex-1 w-full rounded-xl border border-gray-200 bg-white shadow-sm"
        style="min-height: 70vh;"
        :title="filename"
      />
    </main>
  </div>
</template>
