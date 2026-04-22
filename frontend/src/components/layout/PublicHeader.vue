<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { ArrowRightOnRectangleIcon } from "@heroicons/vue/24/outline";
import { useUiConfigStore } from "@/stores/ui_config";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const auth = useAuthStore();
</script>

<template>
  <header
    class="flex h-14 items-center gap-4 px-4 text-white"
    :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
  >
    <router-link
      to="/"
      class="flex shrink-0 items-center gap-2 text-lg font-bold tracking-tight hover:opacity-80"
    >
      <img
        v-if="uiConfig.config.platform_logo_url"
        :src="uiConfig.config.platform_logo_url"
        alt="Logo"
        class="h-8 w-auto object-contain"
      />
      <span>{{ uiConfig.config.platform_name }}</span>
    </router-link>

    <div class="ml-auto flex items-center gap-2 text-sm">
      <router-link
        v-if="auth.isAuthenticated"
        to="/dashboard"
        class="rounded px-3 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
      >
        {{ t("nav.dashboard") }}
      </router-link>
      <router-link
        v-else
        to="/login"
        class="flex items-center gap-1.5 rounded px-3 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
      >
        <ArrowRightOnRectangleIcon class="h-4 w-4 shrink-0" />
        {{ t("auth.sign_in") }}
      </router-link>
    </div>
  </header>
</template>
