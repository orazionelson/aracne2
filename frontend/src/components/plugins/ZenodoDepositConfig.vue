<script setup lang="ts">
/**
 * Configuration panel for the Zenodo Deposit plugin (InvenioRDM API).
 *
 * Lives at /admin/plugins/zenodo_deposit/config. Fetches both the saved
 * config and the live resource-type vocabulary from Zenodo on mount so
 * the dropdown matches the authoritative list the deposit endpoint will
 * accept.
 */

import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  useZenodoStore,
  type AccessMode,
  type ResourceTypeOption,
} from "@/stores/zenodo";

const { t } = useI18n();
const zenodoStore = useZenodoStore();

const draft = ref({
  api_token: "",
  base_url: "https://sandbox.zenodo.org" as "https://sandbox.zenodo.org" | "https://zenodo.org",
  default_community: "",
  auto_publish: false,
  access: "open" as AccessMode,
  resource_type: "publication-other",
  public_base_url: "",
});
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

// Resource types grouped for a <select> with <optgroup> rendering. We
// preserve the order the backend returns (already sorted by group/label)
// and split into an array of {group, options[]} tuples.
const groupedResourceTypes = computed(() => {
  const groups: Map<string, ResourceTypeOption[]> = new Map();
  for (const opt of zenodoStore.resourceTypes) {
    const bucket = groups.get(opt.group);
    if (bucket) {
      bucket.push(opt);
    } else {
      groups.set(opt.group, [opt]);
    }
  }
  return Array.from(groups, ([group, options]) => ({ group, options }));
});

async function load(): Promise<void> {
  loadError.value = null;
  try {
    await Promise.all([
      zenodoStore.fetchConfig(),
      zenodoStore.fetchResourceTypes().catch(() => {
        /* fallback list still shows up via the backend */
      }),
    ]);
    const cfg = zenodoStore.config;
    if (cfg) {
      draft.value = {
        api_token: "",
        base_url: (cfg.base_url as typeof draft.value.base_url) ?? "https://sandbox.zenodo.org",
        default_community: cfg.default_community ?? "",
        auto_publish: cfg.auto_publish,
        access: cfg.access,
        resource_type: cfg.resource_type || "publication-other",
        public_base_url: cfg.public_base_url ?? "",
      };
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      loadError.value = t("zenodo.restart_required");
    } else {
      const msg = (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message;
      loadError.value = msg ?? t("common.error");
    }
  }
}

async function save(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  try {
    const cfg = zenodoStore.config;
    const patch: Record<string, unknown> = {};
    if (draft.value.api_token) patch.api_token = draft.value.api_token;
    if (!cfg || draft.value.base_url !== cfg.base_url) patch.base_url = draft.value.base_url;
    if (!cfg || draft.value.default_community !== cfg.default_community)
      patch.default_community = draft.value.default_community;
    if (!cfg || draft.value.auto_publish !== cfg.auto_publish)
      patch.auto_publish = draft.value.auto_publish;
    if (!cfg || draft.value.access !== cfg.access) patch.access = draft.value.access;
    if (!cfg || draft.value.resource_type !== cfg.resource_type)
      patch.resource_type = draft.value.resource_type;
    if (!cfg || draft.value.public_base_url !== cfg.public_base_url)
      patch.public_base_url = draft.value.public_base_url;

    if (Object.keys(patch).length === 0) {
      saved.value = true;
      return;
    }
    await zenodoStore.updateConfig(patch);
    // After saving a token, refetch the vocabulary too — the first call
    // may have returned the fallback because no token was configured yet.
    await load();
    saved.value = true;
    setTimeout(() => {
      saved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  }
}

async function clearToken(): Promise<void> {
  saveError.value = null;
  try {
    await zenodoStore.updateConfig({ api_token: "" });
    await load();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  }
}

onMounted(load);
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("zenodo.panel_subtitle") }}
    </p>

    <p v-if="loadError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ loadError }}</p>
    <p v-if="saveError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ saveError }}</p>
    <p v-if="saved" class="mb-4 text-sm text-green-600 dark:text-green-400">{{ t("zenodo.saved") }}</p>

    <div class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
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
              :href="draft.base_url + '/account/settings/applications/tokens/new/'"
              target="_blank"
              rel="noopener"
            >
              {{ t("zenodo.api_token_link") }}
            </a>
          </p>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="draft.api_token"
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
              @click="clearToken"
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
            v-model="draft.base_url"
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
            v-model="draft.default_community"
            type="text"
            maxlength="128"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            placeholder="digital-editions"
          />
        </div>

        <!-- Access mode -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.access") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{{ t("zenodo.access_hint") }}</p>
          <select
            v-model="draft.access"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="open">{{ t("zenodo.access_open") }}</option>
            <option value="restricted">{{ t("zenodo.access_restricted") }}</option>
          </select>
        </div>

        <!-- Resource type (grouped, from live Zenodo vocabulary) -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.resource_type") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("zenodo.resource_type_hint") }}
            <span v-if="zenodoStore.isLoadingResourceTypes" class="italic">
              {{ t("common.loading") }}
            </span>
          </p>
          <select
            v-model="draft.resource_type"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          >
            <optgroup
              v-for="grp in groupedResourceTypes"
              :key="grp.group"
              :label="grp.group"
            >
              <option
                v-for="opt in grp.options"
                :key="opt.id"
                :value="opt.id"
              >{{ opt.label }}</option>
            </optgroup>
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
            v-model="draft.public_base_url"
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
            :class="draft.auto_publish ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
            @click="draft.auto_publish = !draft.auto_publish"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="draft.auto_publish ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>
      </div>

      <div class="mt-5 flex justify-end">
        <button
          :disabled="zenodoStore.isSaving || !!loadError"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ zenodoStore.isSaving ? t("common.saving") : t("common.save") }}
        </button>
      </div>
    </div>
  </div>
</template>
