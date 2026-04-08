<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute, RouterView } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useSettingStore } from "@/stores/settings";
import { useUiConfigStore } from "@/stores/ui_config";
import AppNavbar from "@/components/layout/AppNavbar.vue";

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const settingStore = useSettingStore();
const uiConfig = useUiConfigStore();

// Fetch public UI config at boot so the navbar has the correct logo/colour
// even before the user logs in.
onMounted(() => { uiConfig.fetchConfig(); });

// Show navbar on all authenticated pages; hide on login and 404
const showNav = computed(() => auth.isAuthenticated && route.name !== "not-found");

// Fetch platform settings once as soon as the user is authenticated (login or
// session restore at boot). Settings are small and needed by multiple views.
watch(
  () => auth.isAuthenticated,
  (authenticated) => { if (authenticated) settingStore.fetchSettings(); },
  { immediate: true },
);

// Banner height in px — must match the h-10 class on the banner element.
const BANNER_HEIGHT = 40;
</script>

<template>
  <!-- Impersonation banner: always visible on top of everything -->
  <div
    v-if="auth.impersonating"
    class="fixed inset-x-0 top-0 z-[60] flex h-10 items-center justify-between bg-amber-400 px-4 text-sm font-medium text-amber-900"
  >
    <span>
      ⚠ {{ t("auth.impersonating", { username: auth.impersonating.username, role: auth.impersonating.role }) }}
    </span>
    <button
      class="rounded border border-amber-700 px-3 py-0.5 text-xs hover:bg-amber-500"
      @click="auth.exitImpersonation()"
    >
      {{ t("auth.exit_impersonation") }}
    </button>
  </div>

  <AppNavbar
    v-if="showNav"
    :top-offset="auth.impersonating ? BANNER_HEIGHT : 0"
  />

  <main :class="showNav ? (auth.impersonating ? 'pt-24' : 'pt-14') : ''">
    <RouterView />
  </main>
</template>
