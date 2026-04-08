<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notifications";
import { useUiConfigStore } from "@/stores/ui_config";

const props = defineProps<{ topOffset?: number }>();

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const notif = useNotificationStore();

const uiConfig = useUiConfigStore();
const menuOpen = ref(false);

onMounted(async () => {
  if (auth.isAuthenticated) {
    await notif.fetchUnreadCount().catch(() => undefined);
  }
});

async function handleLogout(): Promise<void> {
  menuOpen.value = false;
  await auth.logout();
  router.push({ name: "login" });
}

function closeMenu(): void {
  menuOpen.value = false;
}
</script>

<template>
  <nav
    class="fixed inset-x-0 z-50 text-white"
    :style="{
      top: props.topOffset ? `${props.topOffset}px` : '0',
      backgroundColor: uiConfig.config.navbar_bg_color,
    }"
  >
    <!-- Top bar -->
    <div class="flex h-14 items-center gap-4 px-4">
      <!-- Brand: logo + platform name -->
      <router-link
        to="/"
        class="flex shrink-0 items-center gap-2 text-lg font-bold tracking-tight hover:opacity-80"
        @click="closeMenu"
      >
        <img
          v-if="uiConfig.config.platform_logo_url"
          :src="uiConfig.config.platform_logo_url"
          alt="Logo"
          class="h-8 w-auto object-contain"
        />
        <span>{{ uiConfig.config.platform_name }}</span>
      </router-link>

      <!-- Desktop primary links -->
      <div class="hidden flex-1 items-center gap-4 text-sm md:flex">
        <router-link
          to="/"
          class="text-gray-400 transition-colors hover:text-white"
          exact-active-class="!text-white font-medium"
        >
          {{ t("nav.home") }}
        </router-link>
        <router-link
          to="/collections"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.collections") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('EditorInChief')"
          to="/users"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.users") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/plugins"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.plugins") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/webhooks"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.webhooks") }}
        </router-link>
        <router-link
          to="/entities"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.entities") }}
        </router-link>
      </div>

      <!-- Desktop right side -->
      <div class="ml-auto hidden items-center gap-5 text-sm md:flex">
        <span class="text-xs text-gray-500">
          {{ auth.user?.username }} &middot; {{ auth.user?.role }}
        </span>
        <router-link
          to="/notifications"
          class="relative text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.notifications") }}
          <span
            v-if="notif.unreadCount > 0"
            class="absolute -right-3 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] text-white"
          >
            {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
          </span>
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/settings"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.settings") }}
        </router-link>
        <router-link
          to="/profile"
          class="text-gray-400 transition-colors hover:text-white"
          active-class="!text-white font-medium"
        >
          {{ t("nav.profile") }}
        </router-link>
        <button
          class="text-gray-400 transition-colors hover:text-white"
          @click="handleLogout"
        >
          {{ t("auth.sign_out") }}
        </button>
      </div>

      <!-- Hamburger (mobile only) -->
      <button
        class="ml-auto flex flex-col gap-1.5 p-1 md:hidden"
        :aria-label="t('nav.menu')"
        @click="menuOpen = !menuOpen"
      >
        <span
          class="block h-0.5 w-5 bg-white transition-transform"
          :class="menuOpen ? 'translate-y-2 rotate-45' : ''"
        />
        <span
          class="block h-0.5 w-5 bg-white transition-opacity"
          :class="menuOpen ? 'opacity-0' : ''"
        />
        <span
          class="block h-0.5 w-5 bg-white transition-transform"
          :class="menuOpen ? '-translate-y-2 -rotate-45' : ''"
        />
      </button>
    </div>

    <!-- Mobile menu -->
    <div
      v-if="menuOpen"
      class="border-t border-white/20 px-4 pb-4 pt-2 text-sm md:hidden"
    >
      <p class="mb-3 text-xs text-gray-500">
        {{ auth.user?.username }} &middot; {{ auth.user?.role }}
      </p>
      <div class="flex flex-col gap-3">
        <router-link
          to="/"
          class="text-gray-400 hover:text-white"
          exact-active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.home") }}
        </router-link>
        <router-link
          to="/collections"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.collections") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('EditorInChief')"
          to="/users"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.users") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/plugins"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.plugins") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/webhooks"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.webhooks") }}
        </router-link>
        <router-link
          to="/entities"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.entities") }}
        </router-link>
        <router-link
          to="/notifications"
          class="relative text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.notifications") }}
          <span
            v-if="notif.unreadCount > 0"
            class="ml-2 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] text-white"
          >
            {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
          </span>
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/settings"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.settings") }}
        </router-link>
        <router-link
          to="/profile"
          class="text-gray-400 hover:text-white"
          active-class="!text-white font-medium"
          @click="closeMenu"
        >
          {{ t("nav.profile") }}
        </router-link>
        <button
          class="text-left text-gray-400 hover:text-white"
          @click="handleLogout"
        >
          {{ t("auth.sign_out") }}
        </button>
      </div>
    </div>
  </nav>
</template>
