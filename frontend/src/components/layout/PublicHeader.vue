<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { ArrowRightOnRectangleIcon } from "@heroicons/vue/24/outline";
import { useUiConfigStore } from "@/stores/ui_config";
import { useAuthStore } from "@/stores/auth";
import { useNavbarColors } from "@/composables/useNavbarColors";
import { usePublicNav, usePublicNavLabel } from "@/composables/usePublicNav";

const { t } = useI18n();
const uiConfig = useUiConfigStore();
const auth = useAuthStore();
// Text colour auto-picked (WCAG) against the admin-configured background.
const { bg, text } = useNavbarColors();
// Plugin-declared header links — surfaced when the plugin is active and
// its admin toggle (``public_link_<name>_enabled``) is on.
const headerLinks = usePublicNav("header");
const labelFor = usePublicNavLabel();
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
      <!-- Plugin-declared header links (public_navigation, section=header) -->
      <router-link
        v-for="entry in headerLinks"
        :key="entry.plugin_name"
        :to="entry.url"
        class="rounded px-3 py-1.5 opacity-80 transition-colors hover:bg-black/10 hover:opacity-100"
      >
        {{ labelFor(entry) }}
      </router-link>
      <router-link
        v-if="uiConfig.config.public_search_engine_enabled && uiConfig.config.public_search_engine_slug"
        to="/search"
        class="rounded px-3 py-1.5 opacity-80 transition-colors hover:bg-black/10 hover:opacity-100"
      >
        {{ t("nav.search") }}
      </router-link>
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
