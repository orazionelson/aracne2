<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { MagnifyingGlassIcon } from "@heroicons/vue/24/outline";
import { usePluginStore, type PluginInfo } from "@/stores/plugins";
import { hasPluginConfig } from "@/components/plugins/registry";
import PluginAvatar from "@/components/ui/PluginAvatar.vue";

type Tab = "core" | "extensions";
type StatusFilter = "all" | "active" | "inactive";

const { t } = useI18n();
const pluginStore = usePluginStore();

const activeTab = ref<Tab>("core");
const searchQuery = ref("");
const statusFilter = ref<StatusFilter>("all");
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const confirmTarget = ref<{ name: string; action: "deactivate" | "delete" } | null>(null);

async function load(): Promise<void> {
  error.value = null;
  try {
    await pluginStore.fetchPlugins();
  } catch {
    error.value = t("common.error");
  }
}

const corePlugins = computed<PluginInfo[]>(() =>
  pluginStore.plugins.filter((p) => p.is_native),
);
const extensionPlugins = computed<PluginInfo[]>(() =>
  pluginStore.plugins.filter((p) => !p.is_native),
);

const filteredCore = computed<PluginInfo[]>(() => applySearch(corePlugins.value));
const filteredExtensions = computed<PluginInfo[]>(() => {
  let list = applySearch(extensionPlugins.value);
  if (statusFilter.value !== "all") {
    list = list.filter((p) => p.status === statusFilter.value);
  }
  return list;
});

function applySearch(list: PluginInfo[]): PluginInfo[] {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return list;
  return list.filter((p) => {
    const haystack = `${p.display_name} ${p.description ?? ""} ${p.name}`.toLowerCase();
    return haystack.includes(q);
  });
}

function askConfirm(name: string, action: "deactivate" | "delete"): void {
  confirmTarget.value = { name, action };
  actionError.value = null;
}

function cancelConfirm(): void {
  confirmTarget.value = null;
}

async function runConfirmed(): Promise<void> {
  if (!confirmTarget.value) return;
  const { name, action } = confirmTarget.value;
  confirmTarget.value = null;
  actionError.value = null;
  try {
    if (action === "deactivate") {
      await pluginStore.deactivate(name);
    } else {
      await pluginStore.removePlugin(name);
    }
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    actionError.value = msg ?? t("common.error");
  }
}

async function handleActivate(name: string): Promise<void> {
  actionError.value = null;
  try {
    await pluginStore.activate(name);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    actionError.value = msg ?? t("common.error");
  }
}

onMounted(load);
</script>

<template>
  <div class="p-6">
    <h1 class="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("plugins.title") }}</h1>
    <p class="mb-4 rounded border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
      {{ t("plugins.restart_notice") }}
    </p>

    <p v-if="error" class="mb-4 text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-if="actionError" class="mb-4 text-red-600 dark:text-red-400">{{ actionError }}</p>

    <p v-if="pluginStore.isLoading" class="text-gray-500 dark:text-gray-400">{{ t("common.loading") }}</p>

    <template v-else-if="pluginStore.plugins.length > 0">
      <!-- Tabs -->
      <div class="mb-4 flex border-b border-gray-200 dark:border-gray-700">
        <button
          class="relative -mb-px px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'core'
            ? 'border-b-2 border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'"
          @click="activeTab = 'core'"
        >
          {{ t("plugins.tab_core") }}
          <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            {{ corePlugins.length }}
          </span>
        </button>
        <button
          class="relative -mb-px px-4 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'extensions'
            ? 'border-b-2 border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'"
          @click="activeTab = 'extensions'"
        >
          {{ t("plugins.tab_extensions") }}
          <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            {{ extensionPlugins.length }}
          </span>
        </button>
      </div>

      <!-- Intro + filters -->
      <p class="mb-3 text-sm text-gray-500 dark:text-gray-400">
        {{ activeTab === "core" ? t("plugins.core_intro") : t("plugins.extensions_intro") }}
      </p>

      <div class="mb-4 flex flex-wrap items-center gap-3">
        <div class="relative">
          <MagnifyingGlassIcon class="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="t('plugins.search_placeholder')"
            class="w-64 rounded border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          />
        </div>
        <div v-if="activeTab === 'extensions'" class="flex items-center gap-2 text-sm">
          <label class="text-gray-500 dark:text-gray-400">{{ t("plugins.filter_status") }}:</label>
          <select
            v-model="statusFilter"
            class="rounded border border-gray-300 bg-white py-1.5 px-2 text-sm text-gray-800 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          >
            <option value="all">{{ t("plugins.filter_all") }}</option>
            <option value="active">{{ t("plugins.status_active") }}</option>
            <option value="inactive">{{ t("plugins.status_inactive") }}</option>
          </select>
        </div>
      </div>

      <!-- Core tab — no status, no actions besides Configure -->
      <div
        v-if="activeTab === 'core'"
        class="overflow-x-auto rounded border border-gray-200 dark:border-gray-700"
      >
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-gray-100 text-left text-gray-700 dark:bg-gray-800 dark:text-gray-200">
              <th class="px-4 py-2 font-semibold">{{ t("plugins.name") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("plugins.version") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("plugins.author") }}</th>
              <th class="px-4 py-2 font-semibold"></th>
            </tr>
          </thead>
          <tbody class="bg-white dark:bg-gray-900">
            <tr v-if="filteredCore.length === 0">
              <td colspan="4" class="px-4 py-6 text-center text-gray-400 dark:text-gray-500">
                {{ t("plugins.no_results") }}
              </td>
            </tr>
            <tr
              v-for="plugin in filteredCore"
              :key="plugin.name"
              class="border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
            >
              <td class="px-4 py-3">
                <div class="flex items-start gap-3">
                  <PluginAvatar :name="plugin.name" :display-name="plugin.display_name" />
                  <div class="min-w-0">
                    <div class="font-medium text-gray-900 dark:text-gray-100">{{ plugin.display_name }}</div>
                    <div v-if="plugin.description" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                      {{ plugin.description }}
                    </div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-400">{{ plugin.version ?? "—" }}</td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-400">{{ plugin.author ?? "—" }}</td>
              <td class="px-4 py-3">
                <RouterLink
                  v-if="hasPluginConfig(plugin.name)"
                  :to="{ name: 'admin-plugin-config', params: { slug: plugin.name } }"
                  class="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  {{ t("plugins.configure") }}
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Extensions tab — status + full action set -->
      <div
        v-else
        class="overflow-x-auto rounded border border-gray-200 dark:border-gray-700"
      >
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-gray-100 text-left text-gray-700 dark:bg-gray-800 dark:text-gray-200">
              <th class="px-4 py-2 font-semibold">{{ t("plugins.name") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("plugins.version") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("plugins.author") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("plugins.status_label") }}</th>
              <th class="px-4 py-2 font-semibold"></th>
            </tr>
          </thead>
          <tbody class="bg-white dark:bg-gray-900">
            <tr v-if="filteredExtensions.length === 0">
              <td colspan="5" class="px-4 py-6 text-center text-gray-400 dark:text-gray-500">
                {{ t("plugins.no_results") }}
              </td>
            </tr>
            <tr
              v-for="plugin in filteredExtensions"
              :key="plugin.name"
              class="border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
            >
              <td class="px-4 py-3">
                <div class="flex items-start gap-3">
                  <PluginAvatar :name="plugin.name" :display-name="plugin.display_name" />
                  <div class="min-w-0">
                    <div class="font-medium text-gray-900 dark:text-gray-100">{{ plugin.display_name }}</div>
                    <div v-if="plugin.description" class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                      {{ plugin.description }}
                    </div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-400">{{ plugin.version ?? "—" }}</td>
              <td class="px-4 py-3 text-gray-500 dark:text-gray-400">{{ plugin.author ?? "—" }}</td>
              <td class="px-4 py-3">
                <span
                  :class="{
                    'text-green-600 dark:text-green-400': plugin.status === 'active',
                    'text-gray-400 dark:text-gray-500': plugin.status === 'inactive',
                    'text-red-600 dark:text-red-400': plugin.status === 'error',
                  }"
                >
                  {{
                    plugin.status === "active"
                      ? t("plugins.status_active")
                      : plugin.status === "inactive"
                        ? t("plugins.status_inactive")
                        : t("plugins.status_error")
                  }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div class="flex gap-3">
                  <button
                    v-if="plugin.status !== 'active'"
                    class="text-sm text-blue-600 hover:underline dark:text-blue-400"
                    @click="handleActivate(plugin.name)"
                  >
                    {{ t("plugins.activate") }}
                  </button>
                  <RouterLink
                    v-if="plugin.status === 'active' && hasPluginConfig(plugin.name)"
                    :to="{ name: 'admin-plugin-config', params: { slug: plugin.name } }"
                    class="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    {{ t("plugins.configure") }}
                  </RouterLink>
                  <button
                    v-if="plugin.status === 'active'"
                    class="text-sm text-orange-600 hover:underline dark:text-orange-400"
                    @click="askConfirm(plugin.name, 'deactivate')"
                  >
                    {{ t("plugins.deactivate") }}
                  </button>
                  <button
                    v-if="plugin.status !== 'active'"
                    class="text-sm text-red-600 hover:underline dark:text-red-400"
                    @click="askConfirm(plugin.name, 'delete')"
                  >
                    {{ t("plugins.delete") }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <p v-else class="mt-4 text-gray-500 dark:text-gray-400">{{ t("plugins.no_plugins") }}</p>

    <!-- Confirm dialog -->
    <Teleport to="body">
      <div
        v-if="confirmTarget"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="cancelConfirm"
      >
        <div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
          <p class="mb-6 text-sm text-gray-700 dark:text-gray-200">
            {{
              confirmTarget.action === "deactivate"
                ? t("plugins.confirm_deactivate")
                : t("plugins.confirm_delete")
            }}
          </p>
          <div class="flex justify-end gap-3">
            <button
              class="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="cancelConfirm"
            >
              {{ t("common.cancel") }}
            </button>
            <button
              class="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
              @click="runConfirmed"
            >
              {{ t("common.confirm") }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
