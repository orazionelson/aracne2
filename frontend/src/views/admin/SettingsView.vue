<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useSettingStore } from "@/stores/settings";
import { useSchemaStore } from "@/stores/schemas";
import { useLicenseStore } from "@/stores/licenses";
import type { TeiSchema } from "@/stores/schemas";

const { t } = useI18n();
const settingStore = useSettingStore();
const schemaStore = useSchemaStore();
const licenseStore = useLicenseStore();

// ── Tab ───────────────────────────────────────────────────────────────────────
const activeTab = ref<"settings" | "schemas" | "licenses">("settings");

// ── System settings ──────────────────────────────────────────────────────────
const error = ref<string | null>(null);
const drafts = ref<Record<string, string>>({});
const saving = ref<Record<string, boolean>>({});
const saveError = ref<Record<string, string>>({});

async function loadSettings(): Promise<void> {
  error.value = null;
  try {
    await settingStore.fetchSettings();
  } catch {
    error.value = t("common.error");
  }
}

function startEdit(key: string, currentValue: string): void {
  drafts.value[key] = currentValue;
  saveError.value[key] = "";
}

function cancelEdit(key: string): void {
  delete drafts.value[key];
  delete saveError.value[key];
}

async function save(key: string): Promise<void> {
  saving.value[key] = true;
  saveError.value[key] = "";
  try {
    await settingStore.updateSetting(key, drafts.value[key]);
    delete drafts.value[key];
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value[key] = msg ?? t("common.error");
  } finally {
    saving.value[key] = false;
  }
}

function isEditing(key: string): boolean {
  return key in drafts.value;
}

// Settings with a fixed set of allowed values — show a <select> instead of
// a free-text input.  Add new entries here when introducing enum-like settings.
const SETTING_OPTIONS: Record<string, string[]> = {
  document_editor_mode: ['single', 'split'],
};

// ── Schemas ───────────────────────────────────────────────────────────────────
const schemaError = ref<string | null>(null);
const newSchemaName = ref("");
const isCreating = ref(false);
const createError = ref<string | null>(null);

// Per-schema UI state (upload / import panels)
const activePanel = ref<Record<string, string>>({});
const importUrl = ref<Record<string, string>>({});
const isImporting = ref<Record<string, boolean>>({});
const panelError = ref<Record<string, string>>({});
const isGenerating = ref<Record<string, boolean>>({});
const generateOk = ref<Record<string, boolean>>({});

async function loadSchemas(): Promise<void> {
  schemaError.value = null;
  try {
    await schemaStore.fetchSchemas();
  } catch {
    schemaError.value = t("common.error");
  }
}

async function createSchema(): Promise<void> {
  if (!newSchemaName.value.trim()) return;
  createError.value = null;
  isCreating.value = true;
  try {
    await schemaStore.createSchema(newSchemaName.value.trim());
    newSchemaName.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    createError.value = msg ?? t("common.error");
  } finally {
    isCreating.value = false;
  }
}

async function deleteSchema(s: TeiSchema): Promise<void> {
  if (!confirm(t("schemas.confirm_delete"))) return;
  await schemaStore.deleteSchema(s.id);
}

function togglePanel(id: string, panel: string): void {
  activePanel.value[id] = activePanel.value[id] === panel ? "" : panel;
  panelError.value[id] = "";
}

async function handleFileUpload(
  id: string,
  event: Event,
  type: "validation" | "cm5",
): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  panelError.value[id] = "";
  isImporting.value[id] = true;
  try {
    if (type === "validation") {
      await schemaStore.uploadValidation(id, file);
    } else {
      await schemaStore.uploadCm5(id, file);
    }
    activePanel.value[id] = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    panelError.value[id] = msg ?? t("common.error");
  } finally {
    isImporting.value[id] = false;
    (event.target as HTMLInputElement).value = "";
  }
}

async function generateCm5(id: string): Promise<void> {
  panelError.value[id] = "";
  generateOk.value[id] = false;
  isGenerating.value[id] = true;
  try {
    await schemaStore.generateCm5(id);
    generateOk.value[id] = true;
    setTimeout(() => { generateOk.value[id] = false; }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    panelError.value[id] = msg ?? t("common.error");
  } finally {
    isGenerating.value[id] = false;
  }
}

async function handleImport(id: string, type: "validation" | "cm5"): Promise<void> {
  const url = importUrl.value[id]?.trim();
  if (!url) return;
  panelError.value[id] = "";
  isImporting.value[id] = true;
  try {
    if (type === "validation") {
      await schemaStore.importValidation(id, url);
    } else {
      await schemaStore.importCm5(id, url);
    }
    importUrl.value[id] = "";
    activePanel.value[id] = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    panelError.value[id] = msg ?? t("common.error");
  } finally {
    isImporting.value[id] = false;
  }
}

// ── Licenses ──────────────────────────────────────────────────────────────────
const licenseError = ref<string | null>(null);
const newLicenseName = ref("");
const newLicenseTarget = ref("");
const isCreatingLicense = ref(false);
const createLicenseError = ref<string | null>(null);
// Per-license edit state
const editingLicense = ref<string | null>(null);
const licenseDraft = ref<{ name: string; target: string }>({ name: "", target: "" });
const savingLicense = ref<Record<string, boolean>>({});
const saveLicenseError = ref<Record<string, string>>({});

async function loadLicenses(): Promise<void> {
  licenseError.value = null;
  try {
    await licenseStore.fetchLicenses();
  } catch {
    licenseError.value = t("common.error");
  }
}

async function createLicense(): Promise<void> {
  if (!newLicenseName.value.trim()) return;
  createLicenseError.value = null;
  isCreatingLicense.value = true;
  try {
    await licenseStore.createLicense(
      newLicenseName.value.trim(),
      newLicenseTarget.value.trim() || null,
    );
    newLicenseName.value = "";
    newLicenseTarget.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    createLicenseError.value = msg ?? t("common.error");
  } finally {
    isCreatingLicense.value = false;
  }
}

function startEditLicense(id: string, name: string, target: string | null): void {
  editingLicense.value = id;
  licenseDraft.value = { name, target: target ?? "" };
  saveLicenseError.value[id] = "";
}

function cancelEditLicense(): void {
  editingLicense.value = null;
}

async function saveEditLicense(id: string): Promise<void> {
  savingLicense.value[id] = true;
  saveLicenseError.value[id] = "";
  try {
    await licenseStore.patchLicense(id, {
      name: licenseDraft.value.name.trim(),
      target: licenseDraft.value.target.trim() || null,
    });
    editingLicense.value = null;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveLicenseError.value[id] = msg ?? t("common.error");
  } finally {
    savingLicense.value[id] = false;
  }
}

async function toggleLicenseActive(id: string, current: boolean): Promise<void> {
  await licenseStore.patchLicense(id, { is_active: !current });
}

async function deleteLicense(id: string): Promise<void> {
  if (!confirm(t("licenses.confirm_delete"))) return;
  await licenseStore.deleteLicense(id);
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadSchemas(), loadLicenses()]);
});
</script>

<template>
  <div class="mx-auto max-w-4xl p-6">
    <!-- Tab bar -->
    <div class="mb-6 flex gap-4 border-b">
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'settings'
            ? 'border-b-2 border-indigo-600 text-indigo-600'
            : 'text-gray-500 hover:text-gray-800',
        ]"
        @click="activeTab = 'settings'"
      >
        {{ t("settings.tab_settings") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'schemas'
            ? 'border-b-2 border-indigo-600 text-indigo-600'
            : 'text-gray-500 hover:text-gray-800',
        ]"
        @click="activeTab = 'schemas'"
      >
        {{ t("settings.tab_schemas") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'licenses'
            ? 'border-b-2 border-indigo-600 text-indigo-600'
            : 'text-gray-500 hover:text-gray-800',
        ]"
        @click="activeTab = 'licenses'"
      >
        {{ t("settings.tab_licenses") }}
      </button>
    </div>

    <!-- ── System Settings tab ── -->
    <template v-if="activeTab === 'settings'">
      <h1 class="mb-6 text-2xl font-bold">{{ t("settings.title") }}</h1>
      <p v-if="error" class="mb-4 text-red-600">{{ error }}</p>
      <p v-if="settingStore.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>
      <div v-else-if="settingStore.settings.length > 0" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-gray-100 text-left">
              <th class="w-56 px-4 py-2 font-semibold">{{ t("settings.key") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("settings.value") }}</th>
              <th class="w-16 px-4 py-2 font-semibold">{{ t("settings.type") }}</th>
              <th class="px-4 py-2 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in settingStore.settings"
              :key="s.key"
              class="border-b align-top hover:bg-gray-50"
            >
              <td class="px-4 py-3">
                <code class="text-xs text-gray-700">{{ s.key }}</code>
                <p v-if="s.description" class="mt-0.5 text-xs text-gray-400">
                  {{ s.description }}
                </p>
              </td>
              <td class="px-4 py-3">
                <template v-if="isEditing(s.key)">
                  <div class="flex flex-col gap-1">
                    <template v-if="SETTING_OPTIONS[s.key]">
                      <select v-model="drafts[s.key]" class="rounded border px-2 py-1 text-sm">
                        <option
                          v-for="opt in SETTING_OPTIONS[s.key]"
                          :key="opt"
                          :value="opt"
                        >{{ opt }}</option>
                      </select>
                    </template>
                    <template v-else-if="s.type === 'bool'">
                      <select v-model="drafts[s.key]" class="rounded border px-2 py-1 text-sm">
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    </template>
                    <template v-else>
                      <input
                        v-model="drafts[s.key]"
                        :type="s.type === 'int' ? 'number' : 'text'"
                        class="rounded border px-2 py-1 text-sm"
                      />
                    </template>
                    <p v-if="saveError[s.key]" class="text-xs text-red-600">
                      {{ saveError[s.key] }}
                    </p>
                  </div>
                </template>
                <span v-else class="font-mono text-sm">{{ s.value }}</span>
              </td>
              <td class="px-4 py-3 text-xs text-gray-400">{{ s.type }}</td>
              <td class="px-4 py-3">
                <template v-if="isEditing(s.key)">
                  <div class="flex gap-2">
                    <button
                      :disabled="saving[s.key]"
                      class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
                      @click="save(s.key)"
                    >
                      {{ t("common.save") }}
                    </button>
                    <button
                      class="rounded border px-3 py-1 text-xs hover:bg-gray-50"
                      @click="cancelEdit(s.key)"
                    >
                      {{ t("common.cancel") }}
                    </button>
                  </div>
                </template>
                <button
                  v-else
                  class="text-xs text-blue-600 hover:underline"
                  @click="startEdit(s.key, s.value)"
                >
                  {{ t("settings.edit") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-4 text-gray-500">{{ t("settings.empty") }}</p>
    </template>

    <!-- ── Schemas tab ── -->
    <template v-if="activeTab === 'schemas'">
      <h1 class="mb-6 text-2xl font-bold">{{ t("schemas.title") }}</h1>

      <!-- Create schema form -->
      <div class="mb-6 flex items-center gap-2">
        <input
          v-model="newSchemaName"
          type="text"
          :placeholder="t('schemas.name_placeholder')"
          class="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
          @keydown.enter="createSchema"
        />
        <button
          :disabled="isCreating || !newSchemaName.trim()"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="createSchema"
        >
          {{ t("schemas.add") }}
        </button>
        <span v-if="createError" class="text-xs text-red-600">{{ createError }}</span>
      </div>

      <p v-if="schemaError" class="mb-4 text-red-600">{{ schemaError }}</p>
      <p v-if="schemaStore.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>

      <p v-else-if="schemaStore.schemas.length === 0" class="text-gray-500">
        {{ t("schemas.no_schemas") }}
      </p>

      <div v-else class="space-y-4">
        <div
          v-for="s in schemaStore.schemas"
          :key="s.id"
          class="rounded border border-gray-200 bg-white"
        >
          <!-- Schema row -->
          <div class="flex items-center justify-between px-4 py-3">
            <div class="flex items-center gap-3">
              <span class="font-medium text-gray-800">{{ s.name }}</span>
              <!-- Validation badge -->
              <span
                v-if="s.validation_format"
                class="rounded bg-blue-100 px-2 py-0.5 text-xs font-mono text-blue-700"
              >
                {{ s.validation_format.toUpperCase() }}
              </span>
              <span v-else class="text-xs text-gray-400">{{ t("schemas.validation") }}: —</span>
              <!-- CM5 badge -->
              <span
                v-if="s.cm5_filename"
                class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700"
              >
                CM5
              </span>
              <span v-else class="text-xs text-gray-400">CM5: —</span>
            </div>

            <!-- Action buttons -->
            <div class="flex items-center gap-1">
              <button
                class="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                :class="{ 'bg-gray-100': activePanel[s.id] === 'upload-validation' }"
                @click="togglePanel(s.id, 'upload-validation')"
              >
                {{ t("schemas.upload_validation") }}
              </button>
              <button
                class="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                :class="{ 'bg-gray-100': activePanel[s.id] === 'import-validation' }"
                @click="togglePanel(s.id, 'import-validation')"
              >
                {{ t("schemas.import_validation") }}
              </button>
              <button
                :disabled="isGenerating[s.id] || !s.validation_filename"
                :title="!s.validation_filename ? t('schemas.generate_cm5_no_validation') : ''"
                class="rounded border border-amber-300 px-2 py-1 text-xs text-amber-700 hover:bg-amber-50 disabled:opacity-40"
                @click="generateCm5(s.id)"
              >
                <span v-if="isGenerating[s.id]">{{ t("common.loading") }}</span>
                <span v-else-if="generateOk[s.id]">✓ CM5</span>
                <span v-else>{{ t("schemas.generate_cm5") }}</span>
              </button>
              <button
                class="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                @click="deleteSchema(s)"
              >
                {{ t("schemas.delete") }}
              </button>
            </div>
          </div>

          <!-- Expandable panels -->
          <div
            v-if="activePanel[s.id]"
            class="border-t bg-gray-50 px-4 py-3"
          >
            <p v-if="panelError[s.id]" class="mb-2 text-xs text-red-600">
              {{ panelError[s.id] }}
            </p>

            <!-- Upload validation schema -->
            <template v-if="activePanel[s.id] === 'upload-validation'">
              <input
                type="file"
                accept=".rng,.dtd,.xsd"
                :disabled="isImporting[s.id]"
                class="text-sm"
                @change="handleFileUpload(s.id, $event, 'validation')"
              />
            </template>

            <!-- Import validation schema from URL -->
            <template v-if="activePanel[s.id] === 'import-validation'">
              <div class="flex items-center gap-2">
                <input
                  v-model="importUrl[s.id]"
                  type="url"
                  :placeholder="t('schemas.url_placeholder')"
                  class="flex-1 rounded border px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
                  @keydown.enter="handleImport(s.id, 'validation')"
                />
                <button
                  :disabled="isImporting[s.id] || !importUrl[s.id]"
                  class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-40"
                  @click="handleImport(s.id, 'validation')"
                >
                  {{ isImporting[s.id] ? t("common.loading") : t("schemas.import") }}
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- ── Licenses tab ── -->
    <template v-if="activeTab === 'licenses'">
      <h1 class="mb-6 text-2xl font-bold">{{ t("licenses.title") }}</h1>

      <!-- Add license form -->
      <div class="mb-6 space-y-2 rounded border border-gray-200 bg-gray-50 p-4">
        <div class="flex gap-2">
          <input
            v-model="newLicenseName"
            type="text"
            :placeholder="t('licenses.name_placeholder')"
            class="flex-1 rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
            @keydown.enter="createLicense"
          />
        </div>
        <div class="flex gap-2">
          <input
            v-model="newLicenseTarget"
            type="url"
            :placeholder="t('licenses.target_placeholder')"
            class="flex-1 rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
            @keydown.enter="createLicense"
          />
          <button
            :disabled="isCreatingLicense || !newLicenseName.trim()"
            class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-40"
            @click="createLicense"
          >
            {{ t("licenses.add") }}
          </button>
        </div>
        <p v-if="createLicenseError" class="text-xs text-red-600">{{ createLicenseError }}</p>
      </div>

      <p v-if="licenseError" class="mb-4 text-red-600">{{ licenseError }}</p>
      <p v-if="licenseStore.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>
      <p v-else-if="licenseStore.licenses.length === 0" class="text-gray-500">
        {{ t("licenses.no_licenses") }}
      </p>

      <div v-else class="space-y-2">
        <div
          v-for="lic in licenseStore.licenses"
          :key="lic.id"
          class="rounded border border-gray-200 bg-white"
        >
          <!-- View row -->
          <div v-if="editingLicense !== lic.id" class="flex items-start justify-between px-4 py-3">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span
                  :class="[
                    'rounded px-2 py-0.5 text-xs font-medium',
                    lic.is_active
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500',
                  ]"
                >
                  {{ lic.is_active ? t("licenses.active") : t("licenses.inactive") }}
                </span>
                <span class="font-medium text-gray-800">{{ lic.name }}</span>
              </div>
              <a
                v-if="lic.target"
                :href="lic.target"
                target="_blank"
                rel="noopener noreferrer"
                class="mt-0.5 block truncate text-xs text-blue-600 hover:underline"
              >
                {{ lic.target }}
              </a>
            </div>
            <div class="ml-4 flex flex-shrink-0 items-center gap-1">
              <button
                class="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                @click="toggleLicenseActive(lic.id, lic.is_active)"
              >
                {{ lic.is_active ? t("licenses.inactive") : t("licenses.active") }}
              </button>
              <button
                class="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                @click="startEditLicense(lic.id, lic.name, lic.target)"
              >
                {{ t("licenses.edit") }}
              </button>
              <button
                class="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                @click="deleteLicense(lic.id)"
              >
                {{ t("licenses.delete") }}
              </button>
            </div>
          </div>

          <!-- Edit row -->
          <div v-else class="space-y-2 px-4 py-3">
            <input
              v-model="licenseDraft.name"
              type="text"
              class="w-full rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
            <input
              v-model="licenseDraft.target"
              type="url"
              :placeholder="t('licenses.target_placeholder')"
              class="w-full rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
            <p v-if="saveLicenseError[lic.id]" class="text-xs text-red-600">
              {{ saveLicenseError[lic.id] }}
            </p>
            <div class="flex gap-2">
              <button
                :disabled="savingLicense[lic.id] || !licenseDraft.name.trim()"
                class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
                @click="saveEditLicense(lic.id)"
              >
                {{ t("licenses.save") }}
              </button>
              <button
                class="rounded border px-3 py-1 text-xs hover:bg-gray-50"
                @click="cancelEditLicense"
              >
                {{ t("licenses.cancel") }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
