<script setup lang="ts">
import { computed } from "vue";
import { useRoute, RouterView } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import AppNavbar from "@/components/layout/AppNavbar.vue";

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();

// Show navbar on all authenticated pages; hide on login and 404
const showNav = computed(() => auth.isAuthenticated && route.name !== "not-found");

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
