<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import {
  Squares2X2Icon,
  FolderOpenIcon,
  TagIcon,
  RectangleStackIcon,
  UsersIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  DocumentTextIcon,
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
  SunIcon,
  MoonIcon,
  QuestionMarkCircleIcon,
} from "@heroicons/vue/24/outline";
import type { FunctionalComponent } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notifications";
import { usePluginStore } from "@/stores/plugins";
import { useUiStore, type SidebarSectionKey } from "@/stores/ui";

// Fixed admin branding — not affected by uiConfig (which controls the public
// face). All assets live under frontend/public/aracne-icons/.
//
// - Expanded sidebar: VT·WHT·512 (light theme) / VT·INK·512 (dark theme) —
//   vertical lockup with "Aracne" wordmark underneath the marchio. The
//   wordmark replaces the separate platform-name text span next to it.
// - Collapsed sidebar: favicon.svg — just the marchio (octagonal chevron),
//   fits the icon strip without text.
const ADMIN_LOGO_LIGHT = "/aracne-icons/lockup/aracne-lockup-vertical-512.png";
const ADMIN_LOGO_DARK = "/aracne-icons/lockup/aracne-lockup-vertical-512-inverse.png";
const ADMIN_LOGO_COLLAPSED = "/aracne-icons/favicon/favicon.svg";
const ADMIN_PLATFORM_NAME = "Aracne2";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const notif = useNotificationStore();
const plugins = usePluginStore();
const ui = useUiStore();

onMounted(async () => {
  if (auth.isAuthenticated) {
    await notif.fetchUnreadCount().catch(() => undefined);
    if (plugins.plugins.length === 0) {
      await plugins.fetchPlugins().catch(() => undefined);
    }
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
      {
        labelKey: "nav.help",
        to: { name: "help" },
        icon: QuestionMarkCircleIcon,
        visible: () => plugins.isActive("help"),
      },
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
        labelKey: "nav.public_pages",
        to: { name: "admin-public-pages" },
        icon: DocumentTextIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
    ],
  },
  {
    key: "admin",
    labelKey: "nav.sections.admin",
    items: [
      {
        labelKey: "nav.users",
        to: { name: "users" },
        icon: UsersIcon,
        visible: () => auth.hasMinRole("EditorInChief"),
      },
      {
        labelKey: "nav.plugins",
        to: { name: "admin-plugins" },
        icon: PuzzlePieceIcon,
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "nav.corpora",
        to: { name: "admin-corpora" },
        icon: RectangleStackIcon,
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
        labelKey: "nav.audit_log",
        to: { name: "admin-audit-log" },
        icon: DocumentTextIcon,
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
const isDark = computed(() => ui.theme === "dark");

async function handleLogout(): Promise<void> {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <aside
    class="flex flex-col shrink-0 border-r border-gray-200 bg-white text-gray-800 transition-[width] duration-200 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
    :class="collapsed ? 'w-16' : 'w-60'"
  >
    <!-- Brand -->
    <router-link
      to="/dashboard"
      class="flex items-center justify-center px-2 py-3 font-bold tracking-tight hover:opacity-80"
      :class="collapsed ? 'h-14' : 'h-28'"
      :title="ADMIN_PLATFORM_NAME"
    >
      <img
        v-if="collapsed"
        :src="ADMIN_LOGO_COLLAPSED"
        alt="Aracne2"
        class="h-8 w-8 shrink-0 object-contain"
      />
      <img
        v-else
        :src="isDark ? ADMIN_LOGO_DARK : ADMIN_LOGO_LIGHT"
        alt="Aracne2"
        class="max-h-24 max-w-full object-contain"
      />
    </router-link>

    <!-- Nav sections -->
    <nav class="flex-1 overflow-y-auto overflow-x-hidden py-2">
      <div v-for="section in visibleSections" :key="section.key" class="mb-2">
        <!-- Section header (hidden when collapsed) -->
        <button
          v-if="!collapsed"
          class="flex w-full items-center justify-between px-4 py-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
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
            class="flex items-center gap-3 rounded px-2 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
            :class="collapsed ? 'justify-center' : ''"
            active-class="!text-indigo-700 bg-indigo-50 dark:!text-indigo-300 dark:bg-indigo-900/40"
            :title="collapsed ? t(item.labelKey) : undefined"
          >
            <component :is="item.icon" class="h-5 w-5 shrink-0" />
            <span v-if="!collapsed" class="truncate">{{ t(item.labelKey) }}</span>
          </router-link>
        </div>
      </div>
    </nav>

    <!-- Account area (pinned to bottom) -->
    <div class="border-t border-gray-200 p-2 dark:border-gray-800">
      <router-link
        to="/notifications"
        class="relative flex items-center gap-3 rounded px-2 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        active-class="!text-indigo-700 bg-indigo-50 dark:!text-indigo-300 dark:bg-indigo-900/40"
        :title="collapsed ? t('nav.notifications') : undefined"
      >
        <BellIcon class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ t("nav.notifications") }}</span>
        <span
          v-if="notif.unreadCount > 0"
          class="flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white"
          :class="collapsed ? 'absolute right-1 top-1' : 'ml-auto'"
        >
          {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
        </span>
      </router-link>

      <router-link
        to="/profile"
        class="flex items-center gap-3 rounded px-2 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        active-class="!text-indigo-700 bg-indigo-50 dark:!text-indigo-300 dark:bg-indigo-900/40"
        :title="collapsed ? (auth.user?.username ?? t('nav.profile')) : undefined"
      >
        <UserCircleIcon class="h-5 w-5 shrink-0" />
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <div class="truncate text-sm leading-tight">{{ auth.user?.username }}</div>
          <div class="truncate text-[11px] leading-tight text-gray-400 dark:text-gray-500">{{ auth.user?.role }}</div>
        </div>
      </router-link>

      <button
        class="mt-0.5 flex w-full items-center gap-3 rounded px-2 py-1.5 text-left text-sm text-gray-700 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
        :class="collapsed ? 'justify-center' : ''"
        :title="collapsed ? t('auth.sign_out') : undefined"
        @click="handleLogout"
      >
        <ArrowRightOnRectangleIcon class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">{{ t("auth.sign_out") }}</span>
      </button>

      <!-- Theme toggle -->
      <button
        class="mt-1 flex w-full items-center gap-3 rounded px-2 py-1.5 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
        :class="collapsed ? 'justify-center' : ''"
        :title="isDark ? t('nav.theme_light') : t('nav.theme_dark')"
        @click="ui.toggleTheme()"
      >
        <SunIcon v-if="isDark" class="h-5 w-5 shrink-0" />
        <MoonIcon v-else class="h-5 w-5 shrink-0" />
        <span v-if="!collapsed" class="truncate">
          {{ isDark ? t("nav.theme_light") : t("nav.theme_dark") }}
        </span>
      </button>

      <!-- Collapse toggle -->
      <button
        class="mt-0.5 flex w-full items-center gap-3 rounded px-2 py-1.5 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
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
