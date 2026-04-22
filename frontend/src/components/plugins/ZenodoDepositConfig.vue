<script setup lang="ts">
/**
 * Configuration panel for the Zenodo Deposit plugin.
 *
 * Rendered standalone under /admin/plugins/zenodo_deposit/config. The panel
 * fetches its own state from the store on mount; the parent view only has
 * to supply the page chrome (title, back link).
 */

import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  useZenodoStore,
  type ZenodoAccessRight,
  type ZenodoPublicationType,
} from "@/stores/zenodo";

const { t } = useI18n();
const zenodoStore = useZenodoStore();

const draft = ref({
  api_token: "",
  base_url: "https://sandbox.zenodo.org" as "https://sandbox.zenodo.org" | "https://zenodo.org",
  default_community: "",
  auto_publish: false,
  access_right: "open" as ZenodoAccessRight,
  publication_type: "other" as ZenodoPublicationType,
  public_base_url: "",
});
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

async function load(): Promise<void> {
  loadError.value = null;
  try {
    await zenodoStore.fetchConfig();
    const cfg = zenodoStore.config;
    if (cfg) {
      draft.value = {
        api_token: "",
        base_url: (cfg.base_url as typeof draft.value.base_url) ?? "https://sandbox.zenodo.org",
        default_community: cfg.default_community ?? "",
        auto_publish: cfg.auto_publish,
        access_right: cfg.access_right,
        publication_type: cfg.publication_type,
        public_base_url: cfg.public_base_url ?? "",
      };
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    // 404 = router not mounted yet (plugin activated but backend not restarted).
    // Surface an explicit, actionable message rather than the raw HTTP message.
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
    // Only send fields that actually changed, so an empty api_token draft
    // does not wipe the stored token on save.
    const patch: Record<string, unknown> = {};
    if (draft.value.api_token) patch.api_token = draft.value.api_token;
    if (!cfg || draft.value.base_url !== cfg.base_url) patch.base_url = draft.value.base_url;
    if (!cfg || draft.value.default_community !== cfg.default_community)
      patch.default_community = draft.value.default_community;
    if (!cfg || draft.value.auto_publish !== cfg.auto_publish)
      patch.auto_publish = draft.value.auto_publish;
    if (!cfg || draft.value.access_right !== cfg.access_right)
      patch.access_right = draft.value.access_right;
    if (!cfg || draft.value.publication_type !== cfg.publication_type)
      patch.publication_type = draft.value.publication_type;
    if (!cfg || draft.value.public_base_url !== cfg.public_base_url)
      patch.public_base_url = draft.value.public_base_url;

    if (Object.keys(patch).length === 0) {
      saved.value = true;
      return;
    }
    await zenodoStore.updateConfig(patch);
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

        <!-- Access right -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("zenodo.access_right") }}
          </label>
          <select
            v-model="draft.access_right"
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
            v-model="draft.publication_type"
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
