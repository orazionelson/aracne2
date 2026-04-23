<script setup lang="ts">
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useDashboardStore } from "@/stores/dashboard";
import { usePluginStore } from "@/stores/plugins";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const dashboard = useDashboardStore();
const plugins = usePluginStore();

onMounted(async () => {
  await dashboard.fetchDashboard(auth.userRole);
  if (plugins.plugins.length === 0) {
    await plugins.fetchPlugins().catch(() => undefined);
  }
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

interface Shortcut {
  labelKey: string;
  routeName: string;
  icon: string;
  minRole?: string;
  pluginSlug?: string;
}

const SHORTCUTS: Shortcut[] = [
  { labelKey: "home.shortcut_collections", routeName: "collections", icon: "📁" },
  { labelKey: "home.shortcut_notifications", routeName: "notifications", icon: "🔔" },
  { labelKey: "home.shortcut_help", routeName: "help", icon: "❓", pluginSlug: "help" },
  { labelKey: "home.shortcut_users", routeName: "users", icon: "👤", minRole: "EditorInChief" },
  { labelKey: "home.shortcut_websites", routeName: "admin-websites", icon: "🌐" },
  { labelKey: "home.shortcut_search_engines", routeName: "admin-search-engines", icon: "🔍" },
  { labelKey: "home.shortcut_settings", routeName: "admin-settings", icon: "⚙️", minRole: "Admin" },
  { labelKey: "home.shortcut_plugins", routeName: "admin-plugins", icon: "🧩", minRole: "Admin" },
];

function visibleShortcuts(): Shortcut[] {
  return SHORTCUTS.filter((s) => {
    if (s.minRole && !auth.hasMinRole(s.minRole)) return false;
    if (s.pluginSlug && !plugins.isActive(s.pluginSlug)) return false;
    return true;
  });
}
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

      <!-- Quick-access shortcuts -->
      <div class="mb-8">
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
          {{ t("home.shortcuts_title") }}
        </h2>
        <div class="flex flex-wrap gap-3">
          <button
            v-for="sc in visibleShortcuts()"
            :key="sc.routeName"
            class="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700 transition-colors dark:bg-gray-800 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-indigo-900/40 dark:hover:border-indigo-700 dark:hover:text-indigo-300"
            @click="router.push({ name: sc.routeName })"
          >
            <span>{{ sc.icon }}</span>
            {{ t(sc.labelKey) }}
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
