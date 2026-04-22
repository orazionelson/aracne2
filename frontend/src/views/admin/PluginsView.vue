<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { usePluginStore } from "@/stores/plugins";
import {
  useZenodoStore,
  type ZenodoAccessRight,
  type ZenodoPublicationType,
} from "@/stores/zenodo";

const { t } = useI18n();
const pluginStore = usePluginStore();
const zenodoStore = useZenodoStore();

const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const confirmTarget = ref<{ name: string; action: "deactivate" | "delete" } | null>(null);

// Zenodo panel local draft — kept separate from the store config so the
// admin can edit fields before committing with Save.
const zenodoDraft = ref({
  api_token: "",
  base_url: "https://sandbox.zenodo.org" as "https://sandbox.zenodo.org" | "https://zenodo.org",
  default_community: "",
  auto_publish: false,
  access_right: "open" as ZenodoAccessRight,
  publication_type: "other" as ZenodoPublicationType,
  public_base_url: "",
});
const zenodoError = ref<string | null>(null);
const zenodoSaved = ref(false);

const zenodoPlugin = computed(() =>
  pluginStore.plugins.find((p) => p.name === "zenodo_deposit"),
);

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

async function loadZenodoConfig(): Promise<void> {
  if (!zenodoPlugin.value) return;
  zenodoError.value = null;
  try {
    await zenodoStore.fetchConfig();
    const cfg = zenodoStore.config;
    if (cfg) {
      zenodoDraft.value = {
        api_token: "",
        base_url: (cfg.base_url as typeof zenodoDraft.value.base_url) ?? "https://sandbox.zenodo.org",
        default_community: cfg.default_community ?? "",
        auto_publish: cfg.auto_publish,
        access_right: cfg.access_right,
        publication_type: cfg.publication_type,
        public_base_url: cfg.public_base_url ?? "",
      };
    }
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    zenodoError.value = msg ?? t("common.error");
  }
}

async function saveZenodoConfig(): Promise<void> {
  zenodoError.value = null;
  zenodoSaved.value = false;
  try {
    const cfg = zenodoStore.config;
    // Only send fields that actually changed, so an empty api_token draft
    // does not wipe the stored token on save.
    const patch: Record<string, unknown> = {};
    if (zenodoDraft.value.api_token) {
      patch.api_token = zenodoDraft.value.api_token;
    }
    if (!cfg || zenodoDraft.value.base_url !== cfg.base_url) {
      patch.base_url = zenodoDraft.value.base_url;
    }
    if (!cfg || zenodoDraft.value.default_community !== cfg.default_community) {
      patch.default_community = zenodoDraft.value.default_community;
    }
    if (!cfg || zenodoDraft.value.auto_publish !== cfg.auto_publish) {
      patch.auto_publish = zenodoDraft.value.auto_publish;
    }
    if (!cfg || zenodoDraft.value.access_right !== cfg.access_right) {
      patch.access_right = zenodoDraft.value.access_right;
    }
    if (!cfg || zenodoDraft.value.publication_type !== cfg.publication_type) {
      patch.publication_type = zenodoDraft.value.publication_type;
    }
    if (!cfg || zenodoDraft.value.public_base_url !== cfg.public_base_url) {
      patch.public_base_url = zenodoDraft.value.public_base_url;
    }
    if (Object.keys(patch).length === 0) {
      zenodoSaved.value = true;
      return;
    }
    await zenodoStore.updateConfig(patch);
    // Refresh draft from the canonical server response (e.g. token_set toggled).
    await loadZenodoConfig();
    zenodoSaved.value = true;
    setTimeout(() => {
      zenodoSaved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    zenodoError.value = msg ?? t("common.error");
  }
}

async function clearZenodoToken(): Promise<void> {
  zenodoError.value = null;
  try {
    await zenodoStore.updateConfig({ api_token: "" });
    await loadZenodoConfig();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    zenodoError.value = msg ?? t("common.error");
  }
}

onMounted(async () => {
  await load();
  await loadZenodoConfig();
});
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <h1 class="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("plugins.title") }}</h1>
    <p class="mb-6 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-4 py-2 dark:text-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
      {{ t("plugins.restart_notice") }}
    </p>

    <!-- Errors -->
    <p v-if="error" class="mb-4 text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-if="actionError" class="mb-4 text-red-600 dark:text-red-400">{{ actionError }}</p>

    <!-- Loading -->
    <p v-if="pluginStore.isLoading" class="text-gray-500 dark:text-gray-400">{{ t("common.loading") }}</p>

    <!-- Table -->
    <div v-else-if="pluginStore.plugins.length > 0" class="overflow-x-auto rounded border border-gray-200 dark:border-gray-700">
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
          <tr
            v-for="plugin in pluginStore.plugins"
            :key="plugin.name"
            class="border-t border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
          >
            <td class="px-4 py-3">
              <div class="font-medium text-gray-900 dark:text-gray-100">{{ plugin.display_name }}</div>
              <div v-if="plugin.description" class="text-xs text-gray-500 mt-0.5 dark:text-gray-400">
                {{ plugin.description }}
              </div>
              <span
                v-if="plugin.is_native"
                class="mt-1 inline-block rounded bg-gray-800 px-1.5 py-0.5 text-xs text-white dark:bg-gray-700"
              >
                {{ t("plugins.native_badge") }}
              </span>
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
              <div v-if="!plugin.is_native" class="flex gap-3">
                <button
                  v-if="plugin.status !== 'active'"
                  class="text-sm text-blue-600 hover:underline dark:text-blue-400"
                  @click="handleActivate(plugin.name)"
                >
                  {{ t("plugins.activate") }}
                </button>
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

    <p v-else class="mt-4 text-gray-500 dark:text-gray-400">{{ t("plugins.no_plugins") }}</p>

    <!-- Zenodo deposit configuration panel -->
    <section
      v-if="zenodoPlugin"
      class="mt-8 rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"
    >
      <div class="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ t("zenodo.panel_title") }}
          </h2>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.panel_subtitle") }}
          </p>
        </div>
        <span
          v-if="zenodoPlugin.status !== 'active'"
          class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300"
        >
          {{ t("zenodo.inactive_notice") }}
        </span>
      </div>

      <p v-if="zenodoError" class="mb-3 text-sm text-red-600 dark:text-red-400">
        {{ zenodoError }}
      </p>
      <p v-if="zenodoSaved" class="mb-3 text-sm text-green-600 dark:text-green-400">
        {{ t("zenodo.saved") }}
      </p>

      <div class="grid gap-4 md:grid-cols-2">
        <!-- API token -->
        <div class="md:col-span-2">
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.api_token") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.api_token_hint") }}
            <a
              class="text-indigo-600 hover:underline dark:text-indigo-400"
              :href="zenodoDraft.base_url + '/account/settings/applications/tokens/new/'"
              target="_blank"
              rel="noopener"
            >
              {{ t("zenodo.api_token_link") }}
            </a>
          </p>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="zenodoDraft.api_token"
              type="password"
              autocomplete="off"
              :placeholder="
                zenodoStore.config?.token_set
                  ? t('zenodo.api_token_placeholder_set')
                  : t('zenodo.api_token_placeholder_empty')
              "
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              v-if="zenodoStore.config?.token_set"
              class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="clearZenodoToken"
            >
              {{ t("zenodo.clear_token") }}
            </button>
          </div>
        </div>

        <!-- Endpoint -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.endpoint") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ t("zenodo.endpoint_hint") }}</p>
          <select
            v-model="zenodoDraft.base_url"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="https://sandbox.zenodo.org">{{ t("zenodo.endpoint_sandbox") }}</option>
            <option value="https://zenodo.org">{{ t("zenodo.endpoint_production") }}</option>
          </select>
        </div>

        <!-- Default community -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.community") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ t("zenodo.community_hint") }}</p>
          <input
            v-model="zenodoDraft.default_community"
            type="text"
            maxlength="128"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            placeholder="digital-editions"
          />
        </div>

        <!-- Access right -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.access_right") }}
          </label>
          <select
            v-model="zenodoDraft.access_right"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="open">{{ t("zenodo.access_open") }}</option>
            <option value="embargoed">{{ t("zenodo.access_embargoed") }}</option>
            <option value="restricted">{{ t("zenodo.access_restricted") }}</option>
            <option value="closed">{{ t("zenodo.access_closed") }}</option>
          </select>
        </div>

        <!-- Publication type -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.publication_type") }}
          </label>
          <select
            v-model="zenodoDraft.publication_type"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="article">{{ t("zenodo.pub_article") }}</option>
            <option value="book">{{ t("zenodo.pub_book") }}</option>
            <option value="section">{{ t("zenodo.pub_section") }}</option>
            <option value="preprint">{{ t("zenodo.pub_preprint") }}</option>
            <option value="thesis">{{ t("zenodo.pub_thesis") }}</option>
            <option value="report">{{ t("zenodo.pub_report") }}</option>
            <option value="other">{{ t("zenodo.pub_other") }}</option>
          </select>
        </div>

        <!-- Public base URL -->
        <div class="md:col-span-2">
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.public_base_url") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.public_base_url_hint") }}
          </p>
          <input
            v-model="zenodoDraft.public_base_url"
            type="url"
            placeholder="https://edition.example.org"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
        </div>

        <!-- Auto publish -->
        <div class="md:col-span-2 flex items-start justify-between rounded border border-gray-200 p-3 dark:border-gray-700">
          <div>
            <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
              {{ t("zenodo.auto_publish") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {{ t("zenodo.auto_publish_hint") }}
            </p>
          </div>
          <button
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
            :class="zenodoDraft.auto_publish ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
            @click="zenodoDraft.auto_publish = !zenodoDraft.auto_publish"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="zenodoDraft.auto_publish ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>
      </div>

      <div class="mt-5 flex justify-end">
        <button
          :disabled="zenodoStore.isSaving"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="saveZenodoConfig"
        >
          {{ zenodoStore.isSaving ? t("common.saving") : t("common.save") }}
        </button>
      </div>
    </section>

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
