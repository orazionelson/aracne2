<script setup lang="ts">
/**
 * Configuration panel for the Internet Archive plugin.
 *
 * Lives at /admin/plugins/internet_archive/config. Uses the same
 * page shell as the Zenodo panel so the two plugin configs stay
 * visually coherent.
 */

import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useInternetArchiveStore } from "@/stores/internet_archive";

const { t } = useI18n();
const store = useInternetArchiveStore();

const draft = ref({
  access_key: "",
  secret_key: "",
  auto_archive: true,
});
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

async function load(): Promise<void> {
  loadError.value = null;
  try {
    await store.fetchConfig();
    const cfg = store.config;
    if (cfg) {
      draft.value = {
        access_key: "",
        secret_key: "",
        auto_archive: cfg.auto_archive,
      };
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      loadError.value = t("internet_archive.restart_required");
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
    const cfg = store.config;
    // Only send fields that actually changed, so a blank field in the
    // draft does not wipe an already-stored key.
    const patch: Record<string, unknown> = {};
    if (draft.value.access_key) patch.access_key = draft.value.access_key;
    if (draft.value.secret_key) patch.secret_key = draft.value.secret_key;
    if (!cfg || draft.value.auto_archive !== cfg.auto_archive)
      patch.auto_archive = draft.value.auto_archive;
    if (Object.keys(patch).length === 0) {
      saved.value = true;
      return;
    }
    await store.updateConfig(patch);
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

async function clearKey(which: "access" | "secret"): Promise<void> {
  saveError.value = null;
  try {
    await store.updateConfig(
      which === "access" ? { access_key: "" } : { secret_key: "" },
    );
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
      {{ t("internet_archive.panel_subtitle") }}
    </p>

    <p v-if="loadError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ loadError }}</p>
    <p v-if="saveError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ saveError }}</p>
    <p v-if="saved" class="mb-4 text-sm text-green-600 dark:text-green-400">
      {{ t("internet_archive.saved") }}
    </p>

    <div class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <div class="grid gap-4 md:grid-cols-2">
        <!-- Access key -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("internet_archive.access_key") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("internet_archive.access_key_hint") }}
            <a
              class="text-indigo-600 hover:underline dark:text-indigo-400"
              href="https://archive.org/account/s3.php"
              target="_blank"
              rel="noopener"
            >
              {{ t("internet_archive.keys_link") }}
            </a>
          </p>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="draft.access_key"
              type="password"
              autocomplete="off"
              :placeholder="
                store.config?.access_key_set
                  ? t('internet_archive.placeholder_set')
                  : t('internet_archive.placeholder_empty')
              "
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              v-if="store.config?.access_key_set"
              class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="clearKey('access')"
            >
              {{ t("internet_archive.clear") }}
            </button>
          </div>
        </div>

        <!-- Secret key -->
        <div>
          <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {{ t("internet_archive.secret_key") }}
          </label>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ t("internet_archive.secret_key_hint") }}
          </p>
          <div class="mt-1 flex items-center gap-2">
            <input
              v-model="draft.secret_key"
              type="password"
              autocomplete="off"
              :placeholder="
                store.config?.secret_key_set
                  ? t('internet_archive.placeholder_set')
                  : t('internet_archive.placeholder_empty')
              "
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              v-if="store.config?.secret_key_set"
              class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="clearKey('secret')"
            >
              {{ t("internet_archive.clear") }}
            </button>
          </div>
        </div>

        <!-- Auto archive -->
        <div class="md:col-span-2 flex items-start justify-between rounded border border-gray-200 p-3 dark:border-gray-700">
          <div>
            <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
              {{ t("internet_archive.auto_archive") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {{ t("internet_archive.auto_archive_hint") }}
            </p>
          </div>
          <button
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
            :class="draft.auto_archive ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
            @click="draft.auto_archive = !draft.auto_archive"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="draft.auto_archive ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>
      </div>

      <div class="mt-5 flex justify-end">
        <button
          :disabled="store.isSaving || !!loadError"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ store.isSaving ? t("common.saving") : t("common.save") }}
        </button>
      </div>
    </div>
  </div>
</template>
