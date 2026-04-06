<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { usePluginStore } from "@/stores/plugins";

const { t } = useI18n();
const pluginStore = usePluginStore();

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
  <div class="mx-auto max-w-5xl p-6">
    <!-- Header -->
    <h1 class="mb-2 text-2xl font-bold">{{ t("plugins.title") }}</h1>
    <p class="mb-6 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-4 py-2">
      {{ t("plugins.restart_notice") }}
    </p>

    <!-- Errors -->
    <p v-if="error" class="mb-4 text-red-600">{{ error }}</p>
    <p v-if="actionError" class="mb-4 text-red-600">{{ actionError }}</p>

    <!-- Loading -->
    <p v-if="pluginStore.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>

    <!-- Table -->
    <div v-else-if="pluginStore.plugins.length > 0" class="overflow-x-auto">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-gray-100 text-left">
            <th class="px-4 py-2 font-semibold">{{ t("plugins.name") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("plugins.version") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("plugins.author") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("plugins.status_label") }}</th>
            <th class="px-4 py-2 font-semibold"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="plugin in pluginStore.plugins"
            :key="plugin.name"
            class="border-b hover:bg-gray-50"
          >
            <td class="px-4 py-3">
              <div class="font-medium">{{ plugin.display_name }}</div>
              <div v-if="plugin.description" class="text-xs text-gray-500 mt-0.5">
                {{ plugin.description }}
              </div>
              <span
                v-if="plugin.is_native"
                class="mt-1 inline-block rounded bg-gray-800 px-1.5 py-0.5 text-xs text-white"
              >
                {{ t("plugins.native_badge") }}
              </span>
            </td>
            <td class="px-4 py-3 text-gray-500">{{ plugin.version ?? "—" }}</td>
            <td class="px-4 py-3 text-gray-500">{{ plugin.author ?? "—" }}</td>
            <td class="px-4 py-3">
              <span
                :class="{
                  'text-green-600': plugin.status === 'active',
                  'text-gray-400': plugin.status === 'inactive',
                  'text-red-600': plugin.status === 'error',
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
              <div v-if="!plugin.is_native" class="flex gap-3">
                <button
                  v-if="plugin.status !== 'active'"
                  class="text-sm text-blue-600 hover:underline"
                  @click="handleActivate(plugin.name)"
                >
                  {{ t("plugins.activate") }}
                </button>
                <button
                  v-if="plugin.status === 'active'"
                  class="text-sm text-orange-600 hover:underline"
                  @click="askConfirm(plugin.name, 'deactivate')"
                >
                  {{ t("plugins.deactivate") }}
                </button>
                <button
                  v-if="plugin.status !== 'active'"
                  class="text-sm text-red-600 hover:underline"
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

    <p v-else class="mt-4 text-gray-500">{{ t("plugins.no_plugins") }}</p>

    <!-- Confirm dialog -->
    <Teleport to="body">
      <div
        v-if="confirmTarget"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="cancelConfirm"
      >
        <div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
          <p class="mb-6 text-sm text-gray-700">
            {{
              confirmTarget.action === "deactivate"
                ? t("plugins.confirm_deactivate")
                : t("plugins.confirm_delete")
            }}
          </p>
          <div class="flex justify-end gap-3">
            <button
              class="rounded border px-4 py-2 text-sm hover:bg-gray-50"
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
