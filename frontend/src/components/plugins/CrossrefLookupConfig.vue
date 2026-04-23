<script setup lang="ts">
/**
 * CrossRef Lookup plugin — admin config page.
 *
 * The plugin's only tunable is the polite-pool contact email. When
 * empty, the backend falls back to the platform's ``admin_email``
 * (shown here read-only) so a freshly-activated install still
 * identifies the operator correctly in the outbound User-Agent.
 */

import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useCrossrefStore } from "@/stores/crossref";

const { t } = useI18n();
const store = useCrossrefStore();

const draft = ref({ contact_email: "" });
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);

async function load(): Promise<void> {
  loadError.value = null;
  try {
    await store.fetchConfig();
    if (store.config) {
      draft.value.contact_email = store.config.contact_email ?? "";
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) {
      loadError.value = t("crossref.restart_required");
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
    await store.updateConfig({ contact_email: draft.value.contact_email.trim() });
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

onMounted(load);
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("crossref.panel_subtitle") }}
    </p>

    <p v-if="loadError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ loadError }}</p>
    <p v-if="saveError" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ saveError }}</p>
    <p v-if="saved" class="mb-4 text-sm text-green-600 dark:text-green-400">
      {{ t("crossref.saved") }}
    </p>

    <div class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">
        {{ t("crossref.contact_email") }}
      </label>
      <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
        {{ t("crossref.contact_email_hint") }}
      </p>
      <input
        v-model="draft.contact_email"
        type="email"
        class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        :placeholder="store.config?.fallback_email ?? 'admin@example.org'"
      />
      <p
        v-if="!draft.contact_email.trim() && store.config?.fallback_email"
        class="mt-1 text-xs text-gray-500 dark:text-gray-400"
      >
        {{ t("crossref.fallback_notice", { email: store.config.fallback_email }) }}
      </p>

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
