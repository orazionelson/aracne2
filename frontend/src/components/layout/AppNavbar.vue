<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { onClickOutside } from "@vueuse/core";
import {
  HomeIcon,
  FolderOpenIcon,
  WrenchScrewdriverIcon,
  UsersIcon,
  PuzzlePieceIcon,
  BoltIcon,
  TagIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  BellIcon,
  Cog6ToothIcon,
  UserCircleIcon,
  ArrowRightOnRectangleIcon,
} from "@heroicons/vue/24/outline";
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
const toolsOpen = ref(false);
const toolsRef = ref<HTMLElement | null>(null);

onClickOutside(toolsRef, () => {
  toolsOpen.value = false;
});

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

function closeTools(): void {
  toolsOpen.value = false;
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
      <!-- Brand -->
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
      <div class="hidden flex-1 items-center gap-1 text-sm md:flex">
        <router-link
          to="/"
          class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          exact-active-class="!text-white bg-white/10"
        >
          <HomeIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.home") }}
        </router-link>

        <router-link
          to="/collections"
          class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
        >
          <FolderOpenIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.collections") }}
        </router-link>

        <!-- Tools dropdown -->
        <div ref="toolsRef" class="relative">
          <button
            class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
            :class="toolsOpen ? '!text-white bg-white/10' : ''"
            @click="toolsOpen = !toolsOpen"
          >
            <WrenchScrewdriverIcon class="h-4 w-4 shrink-0" />
            {{ t("nav.tools") }}
            <svg
              class="h-3 w-3 transition-transform"
              :class="toolsOpen ? 'rotate-180' : ''"
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M6 8L1 3h10z" />
            </svg>
          </button>

          <div
            v-if="toolsOpen"
            class="absolute left-0 top-full z-50 mt-1 w-48 overflow-hidden rounded-lg border border-white/10 bg-gray-900 py-1 shadow-xl"
          >
            <router-link
              v-if="auth.hasMinRole('EditorInChief')"
              to="/users"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <UsersIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.users") }}
            </router-link>
            <router-link
              v-if="auth.hasMinRole('Admin')"
              to="/admin/plugins"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <PuzzlePieceIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.plugins") }}
            </router-link>
            <router-link
              v-if="auth.hasMinRole('Admin')"
              to="/admin/webhooks"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <BoltIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.webhooks") }}
            </router-link>
            <router-link
              to="/entities"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <TagIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.entities") }}
            </router-link>
            <router-link
              v-if="auth.hasRole('Designer') || auth.hasMinRole('EditorInChief')"
              to="/admin/websites"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <GlobeAltIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.websites") }}
            </router-link>
            <router-link
              v-if="auth.hasRole('Designer') || auth.hasMinRole('EditorInChief')"
              to="/admin/search-engines"
              class="flex items-center gap-2.5 px-4 py-2 text-sm text-white/70 hover:bg-white/10 hover:text-white"
              active-class="!text-white bg-white/5"
              @click="closeTools"
            >
              <MagnifyingGlassIcon class="h-4 w-4 shrink-0" />
              {{ t("nav.search_engines") }}
            </router-link>
          </div>
        </div>
      </div>

      <!-- Desktop right side -->
      <div class="ml-auto hidden items-center gap-1 text-sm md:flex">
        <span class="mr-2 text-xs text-white/40">
          {{ auth.user?.username }} &middot; {{ auth.user?.role }}
        </span>

        <router-link
          to="/notifications"
          class="relative flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
        >
          <BellIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.notifications") }}
          <span
            v-if="notif.unreadCount > 0"
            class="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] text-white"
          >
            {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
          </span>
        </router-link>

        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/settings"
          class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
        >
          <Cog6ToothIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.settings") }}
        </router-link>

        <router-link
          to="/profile"
          class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
        >
          <UserCircleIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.profile") }}
        </router-link>

        <button
          class="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          @click="handleLogout"
        >
          <ArrowRightOnRectangleIcon class="h-4 w-4 shrink-0" />
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
      <p class="mb-3 text-xs text-white/40">
        {{ auth.user?.username }} &middot; {{ auth.user?.role }}
      </p>
      <div class="flex flex-col gap-0.5">
        <router-link
          to="/"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          exact-active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <HomeIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.home") }}
        </router-link>
        <router-link
          to="/collections"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <FolderOpenIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.collections") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('EditorInChief')"
          to="/users"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <UsersIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.users") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/plugins"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <PuzzlePieceIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.plugins") }}
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/webhooks"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <BoltIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.webhooks") }}
        </router-link>
        <router-link
          to="/entities"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <TagIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.entities") }}
        </router-link>
        <router-link
          v-if="auth.hasRole('Designer') || auth.hasMinRole('EditorInChief')"
          to="/admin/websites"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <GlobeAltIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.websites") }}
        </router-link>
        <router-link
          v-if="auth.hasRole('Designer') || auth.hasMinRole('EditorInChief')"
          to="/admin/search-engines"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <MagnifyingGlassIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.search_engines") }}
        </router-link>
        <router-link
          to="/notifications"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <BellIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.notifications") }}
          <span
            v-if="notif.unreadCount > 0"
            class="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] text-white"
          >
            {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
          </span>
        </router-link>
        <router-link
          v-if="auth.hasMinRole('Admin')"
          to="/admin/settings"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <Cog6ToothIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.settings") }}
        </router-link>
        <router-link
          to="/profile"
          class="flex items-center gap-3 rounded px-3 py-2 text-white/75 hover:bg-white/10 hover:text-white"
          active-class="!text-white bg-white/10"
          @click="closeMenu"
        >
          <UserCircleIcon class="h-4 w-4 shrink-0" />
          {{ t("nav.profile") }}
        </router-link>
        <button
          class="flex items-center gap-3 rounded px-3 py-2 text-left text-white/75 hover:bg-white/10 hover:text-white"
          @click="handleLogout"
        >
          <ArrowRightOnRectangleIcon class="h-4 w-4 shrink-0" />
          {{ t("auth.sign_out") }}
        </button>
      </div>
    </div>
  </nav>
</template>
