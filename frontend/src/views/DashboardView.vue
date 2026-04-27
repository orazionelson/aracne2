<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import {
  FolderOpenIcon,
  TagIcon,
  DocumentTextIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  Cog6ToothIcon,
  UsersIcon,
  ArchiveBoxArrowDownIcon,
  BoltIcon,
  PuzzlePieceIcon,
  QuestionMarkCircleIcon,
  BellIcon,
  UserCircleIcon,
} from "@heroicons/vue/24/outline";
import type { FunctionalComponent } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useDashboardStore } from "@/stores/dashboard";
import { useNotificationStore } from "@/stores/notifications";
import { usePluginStore } from "@/stores/plugins";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const dashboard = useDashboardStore();
const notif = useNotificationStore();
const plugins = usePluginStore();

onMounted(async () => {
  await dashboard.fetchDashboard(auth.userRole);
  if (plugins.plugins.length === 0) {
    await plugins.fetchPlugins().catch(() => undefined);
  }
  // Refresh the unread badge — already happens in the sidebar but the
  // dashboard may render before that mounts on direct deep-links.
  notif.fetchUnreadCount().catch(() => undefined);
});

function statusClass(s: string): string {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    assigned: "bg-blue-100 text-blue-700",
    review: "bg-amber-100 text-amber-700",
    published: "bg-green-100 text-green-700",
  };
  return map[s] ?? "bg-gray-100 text-gray-600";
}

function goToCollections(status?: string): void {
  router.push({ name: "collections", query: status ? { status } : {} });
}

// ── Quick access: sectioned shortcuts ─────────────────────────────────────────
//
// Three thematic blocks — Cura (editorial work), Pubblica (everything
// the public sees), Amministra (system + access). Help and Notifiche
// live below as standalone cards because they're cross-cutting and
// should always be one click away regardless of role.

interface Shortcut {
  labelKey: string;
  routeName: string;
  icon: FunctionalComponent;
  // Tailwind classes — kept as full literals so the JIT picks them up.
  // ``iconColor`` paints the heroicon, ``ringHover`` tints the border /
  // background on hover so each card has a distinct accent.
  iconColor: string;
  ringHover: string;
  visible?: () => boolean;
}

interface ShortcutSection {
  titleKey: string;
  items: Shortcut[];
}

const SECTIONS: ShortcutSection[] = [
  {
    titleKey: "home.section_curate",
    items: [
      {
        labelKey: "home.shortcut_collections",
        routeName: "collections",
        icon: FolderOpenIcon,
        iconColor: "text-indigo-500",
        ringHover: "hover:border-indigo-300 hover:bg-indigo-50 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/40",
      },
      {
        labelKey: "home.shortcut_entities",
        routeName: "entities",
        icon: TagIcon,
        iconColor: "text-emerald-500",
        ringHover: "hover:border-emerald-300 hover:bg-emerald-50 dark:hover:border-emerald-700 dark:hover:bg-emerald-900/40",
      },
    ],
  },
  {
    titleKey: "home.section_publish",
    items: [
      {
        labelKey: "home.shortcut_public_pages",
        routeName: "admin-public-pages",
        icon: DocumentTextIcon,
        iconColor: "text-sky-500",
        ringHover: "hover:border-sky-300 hover:bg-sky-50 dark:hover:border-sky-700 dark:hover:bg-sky-900/40",
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "home.shortcut_websites",
        routeName: "admin-websites",
        icon: GlobeAltIcon,
        iconColor: "text-cyan-500",
        ringHover: "hover:border-cyan-300 hover:bg-cyan-50 dark:hover:border-cyan-700 dark:hover:bg-cyan-900/40",
        visible: () => auth.hasRole("Designer") || auth.hasMinRole("EditorInChief"),
      },
      {
        labelKey: "home.shortcut_search_engines",
        routeName: "admin-search-engines",
        icon: MagnifyingGlassIcon,
        iconColor: "text-violet-500",
        ringHover: "hover:border-violet-300 hover:bg-violet-50 dark:hover:border-violet-700 dark:hover:bg-violet-900/40",
        visible: () => auth.hasRole("Designer") || auth.hasMinRole("EditorInChief"),
      },
    ],
  },
  {
    titleKey: "home.section_administer",
    items: [
      {
        labelKey: "home.shortcut_users",
        routeName: "users",
        icon: UsersIcon,
        iconColor: "text-rose-500",
        ringHover: "hover:border-rose-300 hover:bg-rose-50 dark:hover:border-rose-700 dark:hover:bg-rose-900/40",
        visible: () => auth.hasMinRole("EditorInChief"),
      },
      {
        labelKey: "home.shortcut_plugins",
        routeName: "admin-plugins",
        icon: PuzzlePieceIcon,
        iconColor: "text-fuchsia-500",
        ringHover: "hover:border-fuchsia-300 hover:bg-fuchsia-50 dark:hover:border-fuchsia-700 dark:hover:bg-fuchsia-900/40",
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "home.shortcut_webhooks",
        routeName: "admin-webhooks",
        icon: BoltIcon,
        iconColor: "text-yellow-500",
        ringHover: "hover:border-yellow-300 hover:bg-yellow-50 dark:hover:border-yellow-700 dark:hover:bg-yellow-900/40",
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "home.shortcut_settings",
        routeName: "admin-settings",
        icon: Cog6ToothIcon,
        iconColor: "text-slate-500",
        ringHover: "hover:border-slate-300 hover:bg-slate-50 dark:hover:border-slate-700 dark:hover:bg-slate-900/40",
        visible: () => auth.hasMinRole("Admin"),
      },
      {
        labelKey: "home.shortcut_backup",
        routeName: "admin-backup",
        icon: ArchiveBoxArrowDownIcon,
        iconColor: "text-orange-500",
        ringHover: "hover:border-orange-300 hover:bg-orange-50 dark:hover:border-orange-700 dark:hover:bg-orange-900/40",
        visible: () => auth.hasMinRole("Admin"),
      },
    ],
  },
];

const visibleSections = computed<ShortcutSection[]>(() =>
  SECTIONS
    .map((s) => ({ ...s, items: s.items.filter((i) => !i.visible || i.visible()) }))
    .filter((s) => s.items.length > 0),
);

const helpVisible = computed(() => plugins.isActive("help"));
</script>

<template>
  <div class="p-6">
    <h1 class="mb-1 text-2xl font-bold">{{ t("home.title") }}</h1>
    <p class="text-gray-500 dark:text-gray-400 mb-6">
      {{ t("home.welcome", { name: auth.user?.display_name || auth.user?.username }) }}
    </p>

    <!-- Loading spinner -->
    <div v-if="dashboard.loading" class="flex justify-center py-12">
      <svg class="animate-spin h-8 w-8 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Stat cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8" :class="{ 'sm:grid-cols-5': dashboard.usersTotal !== null }">
        <button
          class="bg-white border border-gray-200 rounded-lg p-4 text-left hover:shadow-md transition-shadow dark:bg-gray-800 dark:border-gray-700"
          @click="goToCollections()"
        >
          <div class="text-2xl font-bold text-indigo-700">{{ dashboard.collectionsTotal }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t("home.stat_collections") }}</div>
        </button>
        <button
          class="bg-white border border-gray-200 rounded-lg p-4 text-left hover:shadow-md transition-shadow dark:bg-gray-800 dark:border-gray-700"
          @click="goToCollections('draft')"
        >
          <div class="text-2xl font-bold text-gray-700">{{ dashboard.collectionsDraft }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t("home.stat_draft") }}</div>
        </button>
        <button
          class="bg-white border border-gray-200 rounded-lg p-4 text-left hover:shadow-md transition-shadow dark:bg-gray-800 dark:border-gray-700"
          @click="goToCollections('review')"
        >
          <div class="text-2xl font-bold text-amber-600">{{ dashboard.collectionsReview }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t("home.stat_review") }}</div>
        </button>
        <button
          class="bg-white border border-gray-200 rounded-lg p-4 text-left hover:shadow-md transition-shadow dark:bg-gray-800 dark:border-gray-700"
          @click="goToCollections('published')"
        >
          <div class="text-2xl font-bold text-green-600">{{ dashboard.collectionsPublished }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t("home.stat_published") }}</div>
        </button>
        <button
          v-if="dashboard.usersTotal !== null"
          class="bg-white border border-gray-200 rounded-lg p-4 text-left hover:shadow-md transition-shadow dark:bg-gray-800 dark:border-gray-700"
          @click="router.push({ name: 'users' })"
        >
          <div class="text-2xl font-bold text-blue-700">{{ dashboard.usersTotal }}</div>
          <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t("home.stat_users") }}</div>
        </button>
      </div>

      <!-- Quick-access shortcuts — sectioned -->
      <div class="mb-8 space-y-6">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {{ t("home.shortcuts_title") }}
        </h2>

        <section
          v-for="sec in visibleSections"
          :key="sec.titleKey"
          class="space-y-3"
        >
          <h3 class="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            {{ t(sec.titleKey) }}
          </h3>
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            <button
              v-for="sc in sec.items"
              :key="sc.routeName"
              class="group flex flex-col items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-5 text-center transition-all hover:shadow-sm dark:border-gray-700 dark:bg-gray-800"
              :class="sc.ringHover"
              @click="router.push({ name: sc.routeName })"
            >
              <component
                :is="sc.icon"
                class="h-8 w-8 transition-transform group-hover:scale-110"
                :class="sc.iconColor"
              />
              <span class="text-sm font-medium text-gray-700 dark:text-gray-200">
                {{ t(sc.labelKey) }}
              </span>
            </button>
          </div>
        </section>

        <!-- Standalone Help + Notifiche + Profilo row.
             Help spans two columns when present so it stays the most
             prominent target; Notifiche and Profilo each take one. -->
        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <button
            v-if="helpVisible"
            class="group col-span-1 flex items-center gap-4 rounded-lg border-2 border-amber-200 bg-amber-50 px-5 py-5 text-left transition-all hover:border-amber-400 hover:bg-amber-100 hover:shadow-sm md:col-span-2 dark:border-amber-700 dark:bg-amber-900/20 dark:hover:border-amber-500 dark:hover:bg-amber-900/40"
            @click="router.push({ name: 'help' })"
          >
            <QuestionMarkCircleIcon class="h-10 w-10 shrink-0 text-amber-500 dark:text-amber-300" />
            <span class="flex flex-col">
              <span class="text-base font-semibold text-amber-900 dark:text-amber-100">
                {{ t("home.shortcut_help") }}
              </span>
              <span class="text-xs text-amber-700 dark:text-amber-300">
                {{ t("home.shortcut_help_hint") }}
              </span>
            </span>
          </button>
          <button
            class="group flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-5 py-5 text-left transition-all hover:border-red-300 hover:bg-red-50 hover:shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:hover:border-red-700 dark:hover:bg-red-900/30"
            @click="router.push({ name: 'notifications' })"
          >
            <span class="relative">
              <BellIcon class="h-8 w-8 text-red-500 transition-transform group-hover:scale-110" />
              <span
                v-if="notif.unreadCount > 0"
                class="absolute -right-1.5 -top-1.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white"
              >
                {{ notif.unreadCount > 99 ? "99+" : notif.unreadCount }}
              </span>
            </span>
            <span class="text-sm font-medium text-gray-700 dark:text-gray-200">
              {{ t("home.shortcut_notifications") }}
            </span>
          </button>
          <button
            class="group flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-5 py-5 text-left transition-all hover:border-sky-300 hover:bg-sky-50 hover:shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:hover:border-sky-700 dark:hover:bg-sky-900/30"
            @click="router.push({ name: 'profile' })"
          >
            <UserCircleIcon class="h-8 w-8 text-sky-500 transition-transform group-hover:scale-110" />
            <span class="text-sm font-medium text-gray-700 dark:text-gray-200">
              {{ t("home.shortcut_profile") }}
            </span>
          </button>
        </div>
      </div>

      <!-- Recent collections -->
      <div class="mb-8">
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
          {{ t("home.recent_collections") }}
        </h2>
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden dark:bg-gray-800 dark:border-gray-700">
          <p v-if="dashboard.recentCollections.length === 0" class="text-sm text-gray-400 dark:text-gray-500 p-4">
            {{ t("home.recent_empty") }}
          </p>
          <table v-else class="w-full text-sm">
            <thead class="bg-gray-50 border-b border-gray-200 dark:bg-gray-900 dark:border-gray-700">
              <tr>
                <th class="text-left px-4 py-2 font-medium text-gray-500 dark:text-gray-400">{{ t("collections.title") }}</th>
                <th class="text-left px-4 py-2 font-medium text-gray-500 dark:text-gray-400">{{ t("home.col_status") }}</th>
                <th class="text-left px-4 py-2 font-medium text-gray-500 dark:text-gray-400">{{ t("home.col_created") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="col in dashboard.recentCollections"
                :key="col.id"
                class="border-b border-gray-100 last:border-0 hover:bg-gray-50 cursor-pointer dark:border-gray-700 dark:hover:bg-gray-700/60"
                @click="router.push({ name: 'collection-detail', params: { slug: col.slug } })"
              >
                <td class="px-4 py-2 font-medium text-gray-800 dark:text-gray-100">{{ col.title }}</td>
                <td class="px-4 py-2">
                  <span
                    class="inline-block px-2 py-0.5 rounded text-xs font-medium"
                    :class="statusClass(col.status)"
                  >
                    {{ t(`collections.status_${col.status}`) }}
                  </span>
                </td>
                <td class="px-4 py-2 text-gray-500 dark:text-gray-400">
                  {{ new Date(col.created_at).toLocaleDateString() }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- System health (Admin only) -->
      <div v-if="dashboard.health !== null">
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
          {{ t("home.health_title") }}
        </h2>
        <div class="flex flex-wrap gap-3">
          <span
            v-for="(svc, name) in dashboard.health.services"
            :key="name"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border"
            :class="svc.status === 'ok'
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'"
          >
            <span
              class="w-2 h-2 rounded-full"
              :class="svc.status === 'ok' ? 'bg-green-500' : 'bg-red-500'"
            />
            {{ name }}:
            {{ svc.status === 'ok' ? t("home.health_ok") : t("home.health_error") }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>
