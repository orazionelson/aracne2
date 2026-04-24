<script setup lang="ts">
/**
 * Dataverse Integration — plugin config page.
 *
 * Manages: API token, base URL (sandbox vs institutional Dataverse),
 * default Dataverse alias (the sub-collection deposits land in),
 * dataset-contact name + email, default subject (controlled
 * vocabulary), publish type, auto-deposit toggle, auto-publish
 * toggle.
 */
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useDataverseStore } from "@/stores/dataverse";

const { t } = useI18n();
const store = useDataverseStore();

// Dataverse's controlled subject vocabulary. Hard-coded — it's stable
// across versions and small enough to inline rather than fetch live.
const SUBJECTS = [
  "Agricultural Sciences",
  "Arts and Humanities",
  "Astronomy and Astrophysics",
  "Business and Management",
  "Chemistry",
  "Computer and Information Science",
  "Earth and Environmental Sciences",
  "Engineering",
  "Law",
  "Mathematical Sciences",
  "Medicine, Health and Life Sciences",
  "Physics",
  "Social Sciences",
  "Other",
];

const newToken = ref("");
const baseUrl = ref("");
const defaultAlias = ref("");
const autoDeposit = ref(false);
const autoPublish = ref(false);
const defaultSubject = ref("Arts and Humanities");
const contactName = ref("");
const contactEmail = ref("");
const publishType = ref<"major" | "minor" | "updatecurrent">("major");

const saveMessage = ref("");
const saveError = ref("");

onMounted(async () => {
  await store.fetchConfig();
  if (store.config) {
    baseUrl.value = store.config.base_url;
    defaultAlias.value = store.config.default_alias;
    autoDeposit.value = store.config.auto_deposit;
    autoPublish.value = store.config.auto_publish;
    defaultSubject.value = store.config.default_subject || "Arts and Humanities";
    contactName.value = store.config.contact_name;
    contactEmail.value = store.config.contact_email;
    publishType.value = store.config.publish_type;
  }
});

async function save(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    const patch: Record<string, unknown> = {
      base_url: baseUrl.value.trim(),
      default_alias: defaultAlias.value.trim(),
      auto_deposit: autoDeposit.value,
      auto_publish: autoPublish.value,
      default_subject: defaultSubject.value,
      contact_name: contactName.value.trim(),
      contact_email: contactEmail.value.trim(),
      publish_type: publishType.value,
    };
    if (newToken.value.trim()) {
      patch.api_token = newToken.value.trim();
    }
    await store.updateConfig(patch);
    saveMessage.value = t("common.saved");
    newToken.value = "";
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}

async function clearToken(): Promise<void> {
  saveMessage.value = "";
  saveError.value = "";
  try {
    await store.updateConfig({ api_token: "" });
    saveMessage.value = t("common.saved");
    setTimeout(() => { saveMessage.value = ""; }, 2500);
  } catch (err) {
    saveError.value = (err as Error).message ?? t("common.error");
  }
}
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      {{ t("dataverse.panel_subtitle") }}
    </p>

    <div class="space-y-5 rounded border border-gray-200 bg-white p-5 text-sm dark:border-gray-700 dark:bg-gray-800">
      <!-- API token -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("dataverse.field_api_token") }}
        </label>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ store.config?.token_set
            ? t("dataverse.field_token_set")
            : t("dataverse.field_token_unset") }}
        </p>
        <input
          v-model="newToken"
          type="password" autocomplete="off" maxlength="512"
          class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          :placeholder="t('dataverse.field_token_placeholder')"
        />
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("dataverse.field_token_hint") }}
        </p>
      </div>

      <!-- Base URL -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("dataverse.field_base_url") }}
        </label>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("dataverse.field_base_url_hint") }}
        </p>
        <input
          v-model="baseUrl"
          type="url"
          class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          placeholder="https://demo.dataverse.org"
        />
      </div>

      <!-- Default alias -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("dataverse.field_default_alias") }}
        </label>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("dataverse.field_default_alias_hint") }}
        </p>
        <input
          v-model="defaultAlias"
          type="text"
          class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          placeholder="tei-editions"
        />
      </div>

      <!-- Subject + publish type side by side -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("dataverse.field_default_subject") }}
          </label>
          <select
            v-model="defaultSubject"
            class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          >
            <option v-for="s in SUBJECTS" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("dataverse.field_publish_type") }}
          </label>
          <select
            v-model="publishType"
            class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          >
            <option value="major">{{ t("dataverse.publish_type_major") }}</option>
            <option value="minor">{{ t("dataverse.publish_type_minor") }}</option>
            <option value="updatecurrent">{{ t("dataverse.publish_type_updatecurrent") }}</option>
          </select>
        </div>
      </div>

      <!-- Contact -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("dataverse.field_contact_name") }}
          </label>
          <input
            v-model="contactName" type="text"
            class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("dataverse.field_contact_email") }}
          </label>
          <input
            v-model="contactEmail" type="email"
            class="mt-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          />
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ t("dataverse.field_contact_email_hint") }}
          </p>
        </div>
      </div>

      <!-- Toggles -->
      <div class="space-y-3 border-t border-gray-100 pt-3 dark:border-gray-700">
        <label class="flex items-start gap-2 text-sm">
          <input v-model="autoDeposit" type="checkbox" class="mt-1" />
          <span>
            <span class="font-medium text-gray-700 dark:text-gray-200">{{ t("dataverse.field_auto_deposit") }}</span>
            <span class="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
              {{ t("dataverse.field_auto_deposit_hint") }}
            </span>
          </span>
        </label>
        <label class="flex items-start gap-2 text-sm">
          <input v-model="autoPublish" type="checkbox" class="mt-1" />
          <span>
            <span class="font-medium text-gray-700 dark:text-gray-200">{{ t("dataverse.field_auto_publish") }}</span>
            <span class="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
              {{ t("dataverse.field_auto_publish_hint") }}
            </span>
          </span>
        </label>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button
          type="button" :disabled="store.isSaving"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="save"
        >
          {{ store.isSaving ? t("common.loading") : t("common.save") }}
        </button>
        <button
          v-if="store.config?.token_set" type="button" :disabled="store.isSaving"
          class="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/40"
          @click="clearToken"
        >
          {{ t("dataverse.clear_token") }}
        </button>
        <span v-if="saveMessage" class="text-xs text-green-600 dark:text-green-400">{{ saveMessage }}</span>
        <span v-if="saveError" class="text-xs text-red-600 dark:text-red-400">{{ saveError }}</span>
      </div>
    </div>
  </div>
</template>
