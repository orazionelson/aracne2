<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import {
  Squares2X2Icon,
  FolderOpenIcon,
  TagIcon,
  UsersIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  PuzzlePieceIcon,
  BoltIcon,
  ArchiveBoxArrowDownIcon,
  BellIcon,
  Cog6ToothIcon,
  UserCircleIcon,
  ArrowRightOnRectangleIcon,
  ChevronDownIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
} from "@heroicons/vue/24/outline";
import type { FunctionalComponent } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notifications";
import { useUiConfigStore } from "@/stores/ui_config";
import { useUiStore, type SidebarSectionKey } from "@/stores/ui";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const notif = useNotificationStore();
const uiConfig = useUiConfigStore();
const ui = useUiStore();

onMounted(async () => {
  if (auth.isAuthenticated) {
    await notif.fetchUnreadCount().catch(() => undefined);
  }
});

interface NavItem {
  labelKey: string;
  to: { name: string } | string;
  icon: FunctionalComponent;
  visible?: () => boolean;
  badge?: () => number;
}

interface NavSection {
  key: SidebarSectionKey;
  labelKey: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    key: "content",
    labelKey: "nav.sections.content",
    items: [
      { labelKey: "nav.dashboard", to: { name: "dashboard" }, icon: Squares2X2Icon },
      { labelKey: "nav.collections", to: { name: "collections" }, icon: FolderOpenIcon },
      { labelKey: "nav.entities", to: { name: "entities" }, icon: TagIcon },
    ],
  },
  {
    key: "tools",
    labelKey: "nav.sections.tools",
    items: [
      {
        labelKey: "nav.websites",
        to: { name: "admin-websites" },
        icon: GlobeAltIcon,
        visible: () => auth.hasRole("Designer") || auth.hasMinRole("EditorInChief"),
      },
      {
        labelKey: "nav.search_engines",
        to: { name: "admin-search-engines" },
        icon: MagnifyingGlassIcon,
        visible: () => auth.hasRole("Designer") || auth.hasMinRole("EditorInChief"),
      },
      {
        labelKey: "nav.users",
        to: { name: "users" },
        icon: UsersIcon,
        visible: () => auth.hasMinRole("EditorInChief"),
      },
    ],
  },
  {
    key: "admin",
    labelKey: "nav.sections.admin",
    items: [
      {
        labelKey: "nav.plugins",
        to: { name: "admin-plugins" },
        icon: PuzzlePieceIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "nav.webhooks",
        to: { name: "admin-webhooks" },
        icon: BoltIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "nav.backup",
        to: { name: "admin-backup" },
        icon: ArchiveBoxArrowDownIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "nav.settings",
        to: { name: "admin-settings" },
        icon: Cog6ToothIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
    ],
  },
];

const visibleSections = computed<NavSection[]>(() =>
  SECTIONS
    .map((s) => ({ ...s, items: s.items.filter((i) => !i.visible || i.visible()) }))
    .filter((s) => s.items.length > 0),
);

const collapsed = computed(() => ui.isSidebarCollapsed);

async function handleLogout(): Promise<void> {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <aside
    class="flex flex-col text-white shrink-0 transition-[width] duration-200"
    :class="collapsed ? 'w-16' : 'w-60'"
    :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
  >
    <!-- Brand -->
    <router-link
      to="/dashboard"
      class="flex h-14 items-center gap-2 px-4 font-bold tracking-tight hover:opacity-80"
      :title="uiConfig.config.platform_name"
    >
      <img
        v-if="uiConfig.config.platform_logo_url"
        :src="uiConfig.config.platform_logo_url"
        alt="Logo"
        class="h-7 w-7 shrink-0 object-contain"
      />
      <span v-if="!collapsed" class="truncate">{{ uiConfig.config.platform_name }}</span>
    </router-link>

    <!-- Nav sections -->
    <nav class="flex-1 overflow-y-auto overflow-x-hidden py-2">
      <div v-for="section in visibleSections" :key="section.key" class="mb-2">
        <!-- Section header (hidden when collapsed) -->
        <button
          v-if="!collapsed"
          class="flex w-full items-center justify-between px-4 py-1 text-[11px] font-semibold uppercase tracking-wider text-white/45 hover:text-white/80"
          @click="ui.toggleSection(section.key)"
        >
          <span>{{ t(section.labelKey) }}</span>
          <ChevronDownIcon
            class="h-3 w-3 transition-transform"
            :class="ui.sidebarSections[section.key] ? '' : '-rotate-90'"
          />
        </button>

        <!-- Items -->
        <div v-if="collapsed || ui.sidebarSections[section.key]" class="mt-0.5 flex flex-col gap-0.5 px-2">
          <router-link
            v-for="item in section.items"
            :key="item.labelKey"
            :to="item.to"
            class="flex items-center gap-3 rounded px-2 py-1.5 text-sm text-white/75 transition-colors hover:bg-white/10 hover:text-white"
            :class="collapsed ? 'justify-center' : ''"
            active-class="!text-white bg-white/10"
            :title="collapsed ? t(item.labelKey) : undefined"
          >
            <component :is="item.icon" class="h-5 w-5 shrink-0" />
            <span v-if="!collapsed" class="truncate">{{ t(item.labelKey) }}</span>
          </router-link>
        </div>
      </div>
    </nav>

    <!-- Account area (pinned to bottom) -->
    <div class="border-t border-white/10 p-2">
      <router-link
        to="/notifications"
        class="relative flex items-center gap-3 rounded px-2 py-1.5 text-sm text-white/75 transition-colors hover:bg-white/10 hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        active-class="!text-white bg-white/10"
        :title="collapsed ? t('nav.notifications') : undefined"
      >
        <BellIcon class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ t("nav.notifications") }}</span>
        <span
          v-if="notif.unreadCount > 0"
          class="flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium"
          :class="collapsed ? 'absolute right-1 top-1' : 'ml-auto'"
        >
          {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
        </span>
      </router-link>

      <router-link
        to="/profile"
        class="flex items-center gap-3 rounded px-2 py-1.5 text-sm text-white/75 transition-colors hover:bg-white/10 hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        active-class="!text-white bg-white/10"
        :title="collapsed ? (auth.user?.username ?? t('nav.profile')) : undefined"
      >
        <UserCircleIcon class="h-5 w-5 shrink-0" />
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <div class="truncate text-sm leading-tight">{{ auth.user?.username }}</div>
          <div class="truncate text-[11px] text-white/45 leading-tight">{{ auth.user?.role }}</div>
        </div>
      </router-link>

      <button
        class="mt-0.5 flex w-full items-center gap-3 rounded px-2 py-1.5 text-left text-sm text-white/75 transition-colors hover:bg-white/10 hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        :title="collapsed ? t('auth.sign_out') : undefined"
        @click="handleLogout"
      >
        <ArrowRightOnRectangleIcon class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ t("auth.sign_out") }}</span>
      </button>

      <!-- Collapse toggle -->
      <button
        class="mt-1 flex w-full items-center gap-3 rounded px-2 py-1.5 text-sm text-white/45 transition-colors hover:bg-white/10 hover:text-white/80"
        :class="collapsed ? 'justify-center' : ''"
        :title="collapsed ? t('nav.expand_sidebar') : t('nav.collapse_sidebar')"
        @click="ui.toggleSidebar()"
      >
        <ChevronDoubleRightIcon v-if="collapsed" class="h-5 w-5 shrink-0" />
        <ChevronDoubleLeftIcon v-else class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ t("nav.collapse_sidebar") }}</span>
      </button>
    </div>
  </aside>
</template>
