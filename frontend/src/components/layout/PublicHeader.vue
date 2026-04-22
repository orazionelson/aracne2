<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { ArrowRightOnRectangleIcon } from "@heroicons/vue/24/outline";
import { useUiConfigStore } from "@/stores/ui_config";
import { useAuthStore } from "@/stores/auth";
import { useNavbarColors } from "@/composables/useNavbarColors";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const auth = useAuthStore();
// Text colour auto-picked (WCAG) against the admin-configured background.
const { bg, text } = useNavbarColors();
</script>

<template>
  <header
    class="flex h-14 items-center gap-4 px-4"
    :style="{ backgroundColor: bg, color: text }"
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
        class="rounded px-3 py-1.5 opacity-80 transition-colors hover:bg-black/10 hover:opacity-100"
      >
        {{ t("nav.dashboard") }}
      </router-link>
      <router-link
        v-else-if="uiConfig.config.home_show_login_button"
        to="/login"
        class="flex items-center gap-1.5 rounded px-3 py-1.5 opacity-80 transition-colors hover:bg-black/10 hover:opacity-100"
      >
        <ArrowRightOnRectangleIcon class="h-4 w-4 shrink-0" />
        {{ t("auth.sign_in") }}
      </router-link>
    </div>
  </header>
</template>
