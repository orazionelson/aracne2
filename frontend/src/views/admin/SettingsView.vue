<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useSettingStore } from "@/stores/settings";
import { useSchemaStore } from "@/stores/schemas";
import { useLicenseStore } from "@/stores/licenses";
import { useBodyTemplateStore } from "@/stores/body_templates";
import { useUiConfigStore } from "@/stores/ui_config";
import { useAiStore } from "@/stores/ai";
import { useXsltTemplateStore, type XsltTemplateSummary } from "@/stores/xslt_templates";
import type { TeiSchema } from "@/stores/schemas";
import type { AiPrompt } from "@/stores/ai";

const { t, te, availableLocales, locale } = useI18n();
const settingStore = useSettingStore();
const schemaStore = useSchemaStore();
const licenseStore = useLicenseStore();
const bodyTemplateStore = useBodyTemplateStore();
const uiConfigStore = useUiConfigStore();
const aiStore = useAiStore();
const xsltStore = useXsltTemplateStore();

// ── Tab ───────────────────────────────────────────────────────────────────────
const activeTab = ref<"settings" | "schemas" | "licenses" | "body_templates" | "ai" | "design">("settings");

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
  ai_provider: ["disabled", "anthropic", "openai", "gemini", "ollama"],
};

// Static per-key hint shown under the key code. Used as a fallback when the
// DB row has no `description`. Looked up via i18n so it stays translated.
function settingHint(key: string): string {
  const k = `settings.hint_${key}`;
  return te(k) ? t(k) : "";
}

// AI-related settings are shown under the AI tab (in a collapsible panel).
// Homepage/branding settings are managed via dedicated switches and pickers
// under the Homepage tab. Both are hidden from the generic System Settings
// table to avoid redundant controls.
const HIDDEN_FROM_SYSTEM_TABLE = new Set<string>([
  "public_home_enabled",
  "home_propagate_css",
  "home_show_collections",
  "home_show_login_button",
  "home_show_search",
  "navbar_bg_color",
  "platform_logo_url",
  "public_registration",
  "default_language",
  "platform_name",
  "sitemap_include_search_engines",
]);
const systemSettings = computed(() =>
  settingStore.settings.filter(
    (s) => !s.key.startsWith("ai_") && !HIDDEN_FROM_SYSTEM_TABLE.has(s.key),
  ),
);
const aiSettings = computed(() =>
  settingStore.settings.filter((s) => s.key.startsWith("ai_")),
);

const aiSettingsPanelOpen = ref(false);

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

// ── Body Templates ────────────────────────────────────────────────────────────
const bodyTemplateError = ref<string | null>(null);
const newTplLabel = ref("");
const newTplSnippet = ref("");
const isCreatingTpl = ref(false);
const createTplError = ref<string | null>(null);
const editingTpl = ref<string | null>(null);
const tplDraft = ref<{ label: string; snippet: string }>({ label: "", snippet: "" });
const savingTpl = ref<Record<string, boolean>>({});
const saveTplError = ref<Record<string, string>>({});

async function loadBodyTemplates(): Promise<void> {
  bodyTemplateError.value = null;
  try {
    await bodyTemplateStore.fetchTemplates();
  } catch {
    bodyTemplateError.value = t("common.error");
  }
}

async function createBodyTemplate(): Promise<void> {
  if (!newTplLabel.value.trim() || !newTplSnippet.value.trim()) return;
  createTplError.value = null;
  isCreatingTpl.value = true;
  try {
    await bodyTemplateStore.createTemplate(
      newTplLabel.value.trim(),
      newTplSnippet.value.trim(),
    );
    newTplLabel.value = "";
    newTplSnippet.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    createTplError.value = msg ?? t("common.error");
  } finally {
    isCreatingTpl.value = false;
  }
}

function startEditTpl(id: string, label: string, snippet: string): void {
  editingTpl.value = id;
  tplDraft.value = { label, snippet };
  saveTplError.value[id] = "";
}

function cancelEditTpl(): void {
  editingTpl.value = null;
}

async function saveEditTpl(id: string): Promise<void> {
  savingTpl.value[id] = true;
  saveTplError.value[id] = "";
  try {
    await bodyTemplateStore.patchTemplate(id, {
      label: tplDraft.value.label.trim(),
      snippet: tplDraft.value.snippet.trim(),
    });
    editingTpl.value = null;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveTplError.value[id] = msg ?? t("common.error");
  } finally {
    savingTpl.value[id] = false;
  }
}

async function deleteBodyTemplate(id: string): Promise<void> {
  if (!confirm(t("body_templates.confirm_delete"))) return;
  await bodyTemplateStore.deleteTemplate(id);
}


const publicRegistration = computed(
  () => settingStore.getSetting("public_registration") === "true",
);
const defaultLanguage = computed(
  () => settingStore.getSetting("default_language") || "",
);
const savingDefaultLanguage = ref(false);

const currentPlatformName = computed(
  () => settingStore.getSetting("platform_name") ?? "",
);
const platformNameDraft = ref("");
const isSavingPlatformName = ref(false);
const platformNameError = ref("");

function initPlatformNameDraft(): void {
  platformNameDraft.value = currentPlatformName.value;
}

async function savePlatformName(): Promise<void> {
  const trimmed = platformNameDraft.value.trim();
  if (!trimmed) {
    platformNameError.value = t("settings.system_platform_name_required");
    return;
  }
  isSavingPlatformName.value = true;
  platformNameError.value = "";
  try {
    await settingStore.updateSetting("platform_name", trimmed);
    await uiConfigStore.fetchConfig();
    platformNameDraft.value = trimmed;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    platformNameError.value = msg ?? t("common.error");
  } finally {
    isSavingPlatformName.value = false;
  }
}

// Human-readable locale label, translated to the UI's current locale.
// Falls back to the raw code when Intl.DisplayNames is unavailable.
function localeLabel(code: string): string {
  try {
    const dn = new Intl.DisplayNames([locale.value], { type: "language" });
    const name = dn.of(code);
    return name ? `${name} (${code})` : code;
  } catch {
    return code;
  }
}

async function onDefaultLanguageChange(event: Event): Promise<void> {
  const target = event.target as HTMLSelectElement;
  const newValue = target.value;
  savingDefaultLanguage.value = true;
  try {
    await settingStore.updateSetting("default_language", newValue);
  } finally {
    savingDefaultLanguage.value = false;
  }
}

const togglingHomeSetting = ref<Record<string, boolean>>({});

async function toggleHomeSetting(key: string, current: boolean): Promise<void> {
  togglingHomeSetting.value[key] = true;
  try {
    await settingStore.updateSetting(key, current ? "false" : "true");
    await uiConfigStore.fetchConfig();
  } finally {
    togglingHomeSetting.value[key] = false;
  }
}



// ── AI ────────────────────────────────────────────────────────────────────────

const aiError = ref<string | null>(null);
const editingPrompt = ref<string | null>(null);
const promptDraft = ref<{ label: string; template: string }>({ label: "", template: "" });
const savingPrompt = ref<Record<string, boolean>>({});
const savePromptError = ref<Record<string, string>>({});
const isDeletingPrompt = ref<Record<string, boolean>>({});

// Create prompt form
const showCreatePrompt = ref(false);
const newPrompt = ref({ slug: "", label: "", description: "", template: "" });
const isCreatingPrompt = ref(false);
const createPromptError = ref<string | null>(null);

async function loadAiPrompts(): Promise<void> {
  aiError.value = null;
  try {
    await aiStore.fetchPrompts();
    await aiStore.fetchConfig();
  } catch {
    aiError.value = t("common.error");
  }
}

function startEditPrompt(prompt: AiPrompt): void {
  editingPrompt.value = prompt.slug;
  promptDraft.value = { label: prompt.label, template: prompt.template };
  savePromptError.value[prompt.slug] = "";
}

function cancelEditPrompt(): void {
  editingPrompt.value = null;
}

async function saveEditPrompt(slug: string): Promise<void> {
  savingPrompt.value[slug] = true;
  savePromptError.value[slug] = "";
  try {
    await aiStore.updatePrompt(slug, {
      label: promptDraft.value.label.trim(),
      template: promptDraft.value.template.trim(),
    });
    editingPrompt.value = null;
  } catch (err) {
    savePromptError.value[slug] = (err as Error).message ?? t("common.error");
  } finally {
    savingPrompt.value[slug] = false;
  }
}

async function deleteAiPrompt(slug: string): Promise<void> {
  if (!confirm(t("ai.confirm_delete_prompt"))) return;
  isDeletingPrompt.value[slug] = true;
  try {
    await aiStore.deletePrompt(slug);
    if (selectedPromptSlug.value === slug) selectedPromptSlug.value = null;
  } finally {
    isDeletingPrompt.value[slug] = false;
  }
}

// ── Split-panel browse: search box + alphabetical list + detail ──────────
//
// The library was a vertical scroll of cards — fine with 9 native prompts,
// painful as soon as a deployment adds custom ones. Split panel mirrors the
// pattern used elsewhere in the admin (Plugins / Webhooks): scrollable list
// on the left, single detail on the right. Auto-selects the first prompt
// once the catalogue loads.

const promptSearch = ref("");
const selectedPromptSlug = ref<string | null>(null);

const filteredPrompts = computed<AiPrompt[]>(() => {
  const q = promptSearch.value.trim().toLowerCase();
  const sorted = [...aiStore.prompts].sort((a, b) =>
    a.label.localeCompare(b.label, undefined, { sensitivity: "base" }),
  );
  if (!q) return sorted;
  return sorted.filter((p) =>
    p.label.toLowerCase().includes(q)
    || p.slug.toLowerCase().includes(q)
    || (p.description ?? "").toLowerCase().includes(q),
  );
});

const selectedPrompt = computed<AiPrompt | null>(
  () => aiStore.prompts.find((p) => p.slug === selectedPromptSlug.value) ?? null,
);

watch(
  () => aiStore.prompts,
  (rows) => {
    if (rows.length === 0) {
      selectedPromptSlug.value = null;
      return;
    }
    if (selectedPromptSlug.value && rows.some((p) => p.slug === selectedPromptSlug.value)) {
      return;
    }
    const sorted = [...rows].sort((a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: "base" }),
    );
    selectedPromptSlug.value = sorted[0]?.slug ?? null;
  },
  { immediate: true, deep: true },
);

function selectPrompt(slug: string): void {
  selectedPromptSlug.value = slug;
  // Cancel any in-progress edit when switching rows.
  if (editingPrompt.value && editingPrompt.value !== slug) {
    editingPrompt.value = null;
  }
}

async function createAiPrompt(): Promise<void> {
  createPromptError.value = null;
  if (!newPrompt.value.slug.trim() || !newPrompt.value.label.trim() || !newPrompt.value.template.trim()) {
    createPromptError.value = t("common.error");
    return;
  }
  isCreatingPrompt.value = true;
  try {
    await aiStore.createPrompt({
      slug: newPrompt.value.slug.trim(),
      label: newPrompt.value.label.trim(),
      description: newPrompt.value.description.trim() || undefined,
      template: newPrompt.value.template.trim(),
    });
    newPrompt.value = { slug: "", label: "", description: "", template: "" };
    showCreatePrompt.value = false;
  } catch (err) {
    createPromptError.value = (err as Error).message ?? t("common.error");
  } finally {
    isCreatingPrompt.value = false;
  }
}

// ── Design tab (XSLT catalog) ──────────────────────────────────────────────────
const xsltError = ref<string | null>(null);

// New template form
const newXsltName = ref("");
const newXsltDescription = ref("");
const newXsltContent = ref("");
const newXsltProcessor = ref("lxml");
const newXsltTags = ref("");
const isCreatingXslt = ref(false);
const createXsltError = ref<string | null>(null);

// Edit template state (inline)
const editingXsltId = ref<string | null>(null);
const xsltEditDraft = ref<{ name: string; description: string; content: string; processor: string; tags: string }>({ name: "", description: "", content: "", processor: "lxml", tags: "" });
const isSavingXslt = ref(false);
const saveXsltError = ref<string | null>(null);

async function loadXsltTemplates(): Promise<void> {
  xsltError.value = null;
  try {
    await xsltStore.fetchTemplates();
  } catch {
    xsltError.value = t("common.error");
  }
}

function tagsFromString(s: string): string[] {
  return s.split(",").map((t) => t.trim()).filter(Boolean);
}

async function createXsltTemplate(): Promise<void> {
  if (!newXsltName.value.trim() || !newXsltContent.value.trim()) return;
  isCreatingXslt.value = true;
  createXsltError.value = null;
  try {
    await xsltStore.createTemplate({
      name: newXsltName.value.trim(),
      description: newXsltDescription.value.trim() || null,
      content: newXsltContent.value.trim(),
      processor: newXsltProcessor.value,
      tags: tagsFromString(newXsltTags.value),
    });
    newXsltName.value = "";
    newXsltDescription.value = "";
    newXsltContent.value = "";
    newXsltProcessor.value = "lxml";
    newXsltTags.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message;
    createXsltError.value = msg ?? t("common.error");
  } finally {
    isCreatingXslt.value = false;
  }
}

function startEditXslt(tpl: XsltTemplateSummary & { content?: string }): void {
  editingXsltId.value = tpl.id;
  xsltEditDraft.value = {
    name: tpl.name,
    description: tpl.description ?? "",
    content: tpl.content ?? "",
    processor: tpl.processor,
    tags: tpl.tags.join(", "),
  };
  saveXsltError.value = null;
  // Load full content if not yet available
  if (!tpl.content) {
    xsltStore.getTemplate(tpl.id).then((full) => {
      xsltEditDraft.value.content = full.content;
    });
  }
}

function cancelEditXslt(): void {
  editingXsltId.value = null;
  saveXsltError.value = null;
}

async function saveXsltTemplate(id: string): Promise<void> {
  isSavingXslt.value = true;
  saveXsltError.value = null;
  try {
    await xsltStore.patchTemplate(id, {
      name: xsltEditDraft.value.name.trim(),
      description: xsltEditDraft.value.description.trim() || null,
      content: xsltEditDraft.value.content.trim(),
      processor: xsltEditDraft.value.processor,
      tags: tagsFromString(xsltEditDraft.value.tags),
    });
    editingXsltId.value = null;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message;
    saveXsltError.value = msg ?? t("common.error");
  } finally {
    isSavingXslt.value = false;
  }
}

async function deleteXsltTemplate(id: string): Promise<void> {
  if (!confirm(t("settings.xslt_templates_confirm_delete"))) return;
  await xsltStore.deleteTemplate(id);
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadSchemas(), loadLicenses(), loadBodyTemplates(), loadAiPrompts(), loadXsltTemplates()]);
  initPlatformNameDraft();
});
</script>

<template>
  <div class="p-6">
    <!-- Tab bar -->
    <div class="mb-6 flex gap-4 border-b border-gray-200 dark:border-gray-700">
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'settings'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'settings'"
      >
        {{ t("settings.tab_settings") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'schemas'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'schemas'"
      >
        {{ t("settings.tab_schemas") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'licenses'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'licenses'"
      >
        {{ t("settings.tab_licenses") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'body_templates'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'body_templates'"
      >
        {{ t("settings.tab_body_templates") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'ai'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'ai'"
      >
        {{ t("settings.tab_ai") }}
      </button>
      <button
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === 'design'
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = 'design'"
      >
        {{ t("settings.tab_design") }}
      </button>
    </div>

    <!-- ── System Settings tab ── -->
    <template v-if="activeTab === 'settings'">
      <h1 class="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("settings.title") }}</h1>
      <p v-if="error" class="mb-4 text-red-600 dark:text-red-400">{{ error }}</p>

      <!-- System-wide controls shown above the generic settings table. -->
      <div class="mb-6 space-y-3">
        <!-- platform_name — free-text input with commit button -->
        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <div class="mr-4 flex-1">
            <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
              {{ t("settings.system_platform_name") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {{ t("settings.system_platform_name_hint") }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <input
              v-model="platformNameDraft"
              type="text"
              maxlength="80"
              class="w-56 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-40 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              :disabled="isSavingPlatformName"
            />
            <button
              :disabled="isSavingPlatformName || !platformNameDraft.trim() || platformNameDraft.trim() === currentPlatformName"
              class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
              @click="savePlatformName"
            >
              {{ t("common.save") }}
            </button>
          </div>
        </div>
        <p v-if="platformNameError" class="text-xs text-red-600 dark:text-red-400">{{ platformNameError }}</p>

        <!-- default_language — select driven by installed i18n locales -->
        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <div class="mr-4">
            <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
              {{ t("settings.system_default_language") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {{ t("settings.system_default_language_hint") }}
            </p>
          </div>
          <select
            :value="defaultLanguage"
            :disabled="savingDefaultLanguage"
            class="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-40 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            @change="onDefaultLanguageChange"
          >
            <option
              v-for="code in availableLocales"
              :key="code"
              :value="code"
            >{{ localeLabel(code) }}</option>
          </select>
        </div>

        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <div class="mr-4">
            <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
              {{ t("settings.system_public_registration") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {{ t("settings.system_public_registration_hint") }}
            </p>
          </div>
          <button
            :disabled="togglingHomeSetting['public_registration']"
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
            :class="publicRegistration ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
            @click="toggleHomeSetting('public_registration', publicRegistration)"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="publicRegistration ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>
      </div>

      <p v-if="settingStore.isLoading" class="text-gray-500 dark:text-gray-400">{{ t("common.loading") }}</p>
      <div v-else-if="systemSettings.length > 0" class="overflow-x-auto rounded border border-gray-200 dark:border-gray-700">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-gray-100 text-left text-gray-700 dark:bg-gray-800 dark:text-gray-200">
              <th class="w-56 px-4 py-2 font-semibold">{{ t("settings.key") }}</th>
              <th class="px-4 py-2 font-semibold">{{ t("settings.value") }}</th>
              <th class="w-16 px-4 py-2 font-semibold">{{ t("settings.type") }}</th>
              <th class="px-4 py-2 font-semibold"></th>
            </tr>
          </thead>
          <tbody class="bg-white dark:bg-gray-900">
            <tr
              v-for="s in systemSettings"
              :key="s.key"
              class="border-t border-gray-100 align-top hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
            >
              <td class="px-4 py-3">
                <code class="text-xs text-gray-700 dark:text-gray-200">{{ s.key }}</code>
                <p v-if="s.description || settingHint(s.key)" class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                  {{ s.description || settingHint(s.key) }}
                </p>
              </td>
              <td class="px-4 py-3">
                <template v-if="isEditing(s.key)">
                  <div class="flex flex-col gap-1">
                    <template v-if="SETTING_OPTIONS[s.key]">
                      <select v-model="drafts[s.key]" class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
                        <option
                          v-for="opt in SETTING_OPTIONS[s.key]"
                          :key="opt"
                          :value="opt"
                        >{{ opt }}</option>
                      </select>
                    </template>
                    <template v-else-if="s.type === 'bool'">
                      <select v-model="drafts[s.key]" class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    </template>
                    <template v-else>
                      <input
                        v-model="drafts[s.key]"
                        :type="s.type === 'int' ? 'number' : 'text'"
                        class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                      />
                    </template>
                    <p v-if="saveError[s.key]" class="text-xs text-red-600 dark:text-red-400">
                      {{ saveError[s.key] }}
                    </p>
                  </div>
                </template>
                <span v-else class="font-mono text-sm text-gray-900 dark:text-gray-100">{{ s.value }}</span>
              </td>
              <td class="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">{{ s.type }}</td>
              <td class="px-4 py-3">
                <template v-if="isEditing(s.key)">
                  <div class="flex gap-2">
                    <button
                      :disabled="saving[s.key]"
                      class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40 dark:bg-indigo-600 dark:hover:bg-indigo-700"
                      @click="save(s.key)"
                    >
                      {{ t("common.save") }}
                    </button>
                    <button
                      class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                      @click="cancelEdit(s.key)"
                    >
                      {{ t("common.cancel") }}
                    </button>
                  </div>
                </template>
                <button
                  v-else
                  class="text-xs text-blue-600 hover:underline dark:text-blue-400"
                  @click="startEdit(s.key, s.value)"
                >
                  {{ t("settings.edit") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-4 text-gray-500 dark:text-gray-400">{{ t("settings.empty") }}</p>
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

    <!-- ── Body Templates tab ── -->
    <template v-if="activeTab === 'body_templates'">
      <h1 class="mb-6 text-2xl font-bold">{{ t("body_templates.title") }}</h1>
      <p v-if="bodyTemplateError" class="mb-4 text-red-600">{{ bodyTemplateError }}</p>

      <!-- Add form -->
      <div class="mb-6 rounded border border-gray-200 bg-gray-50 p-4">
        <p class="mb-3 text-sm font-medium text-gray-700">{{ t("body_templates.add") }}</p>
        <div class="space-y-2">
          <input
            v-model="newTplLabel"
            type="text"
            :placeholder="t('body_templates.label_placeholder')"
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
          <textarea
            v-model="newTplSnippet"
            rows="6"
            :placeholder="t('body_templates.snippet_placeholder')"
            class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <p v-if="createTplError" class="mt-1 text-xs text-red-600">{{ createTplError }}</p>
        <button
          :disabled="isCreatingTpl || !newTplLabel.trim() || !newTplSnippet.trim()"
          class="mt-2 rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="createBodyTemplate"
        >
          {{ t("body_templates.add") }}
        </button>
      </div>

      <!-- Template list -->
      <p v-if="bodyTemplateStore.templates.length === 0" class="text-sm text-gray-500">
        {{ t("body_templates.no_templates") }}
      </p>
      <div v-else class="space-y-3">
        <div
          v-for="tpl in bodyTemplateStore.templates"
          :key="tpl.id"
          class="rounded border border-gray-200 bg-white p-4"
        >
          <!-- View mode -->
          <template v-if="editingTpl !== tpl.id">
            <div class="mb-2 flex items-center gap-2">
              <span class="font-medium text-gray-800">{{ tpl.label }}</span>
              <span
                v-if="tpl.is_native"
                class="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500"
              >
                {{ t("body_templates.native_badge") }}
              </span>
            </div>
            <pre class="mb-3 overflow-x-auto rounded bg-gray-50 p-3 text-xs text-gray-700">{{ tpl.snippet }}</pre>
            <div class="flex gap-2">
              <button
                class="text-xs text-indigo-600 hover:text-indigo-800"
                @click="startEditTpl(tpl.id, tpl.label, tpl.snippet)"
              >
                {{ t("body_templates.edit") }}
              </button>
              <button
                class="text-xs text-red-500 hover:text-red-700"
                @click="deleteBodyTemplate(tpl.id)"
              >
                {{ t("body_templates.delete") }}
              </button>
            </div>
          </template>

          <!-- Edit mode -->
          <template v-else>
            <div class="space-y-2">
              <input
                v-model="tplDraft.label"
                type="text"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
              <textarea
                v-model="tplDraft.snippet"
                rows="8"
                class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <p v-if="saveTplError[tpl.id]" class="mt-1 text-xs text-red-600">
              {{ saveTplError[tpl.id] }}
            </p>
            <div class="mt-2 flex gap-2">
              <button
                :disabled="savingTpl[tpl.id] || !tplDraft.label.trim() || !tplDraft.snippet.trim()"
                class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
                @click="saveEditTpl(tpl.id)"
              >
                {{ t("body_templates.save") }}
              </button>
              <button
                class="rounded border px-3 py-1 text-xs hover:bg-gray-50"
                @click="cancelEditTpl"
              >
                {{ t("body_templates.cancel") }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </template>

    <!-- ── AI tab ── -->
    <template v-if="activeTab === 'ai'">
      <h1 class="mb-2 text-2xl font-bold">{{ t("settings.ai_title") }}</h1>
      <p class="mb-6 text-sm text-gray-500">
        {{ t("settings.ai_subtitle") }}
      </p>

      <!-- Provider & API keys accordion -->
      <div class="mb-6 rounded border border-gray-200 dark:border-gray-700">
        <button
          type="button"
          class="flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
          :aria-expanded="aiSettingsPanelOpen"
          @click="aiSettingsPanelOpen = !aiSettingsPanelOpen"
        >
          <svg
            class="h-3 w-3 shrink-0 transition-transform text-gray-500 dark:text-gray-400"
            :class="aiSettingsPanelOpen ? 'rotate-90' : ''"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4 2l5 4-5 4V2z" />
          </svg>
          <span class="font-medium text-gray-700 dark:text-gray-200">{{ t("settings.ai_provider_panel_title") }}</span>
          <template v-if="aiStore.config">
            <span
              :class="[
                'ml-3 rounded px-2 py-0.5 text-xs font-medium',
                aiStore.config.provider === 'disabled'
                  ? 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                  : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
              ]"
            >
              {{ aiStore.config.provider }}
            </span>
            <span v-if="aiStore.config.provider !== 'disabled'" class="ml-2 text-gray-500 dark:text-gray-400">
              {{ aiStore.config.model }}
            </span>
            <span class="ml-auto text-xs text-gray-400 dark:text-gray-500">
              {{ t("settings.ai_rate_limit_label", { n: aiStore.config.rate_limit }) }}
            </span>
          </template>
        </button>

        <div v-if="aiSettingsPanelOpen" class="border-t border-gray-200 dark:border-gray-700">
          <p v-if="error" class="px-4 pt-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
          <div v-if="aiSettings.length > 0" class="overflow-x-auto">
            <table class="w-full border-collapse text-sm">
              <thead class="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                <tr>
                  <th class="w-64 px-4 py-2 font-semibold">{{ t("settings.key") }}</th>
                  <th class="px-4 py-2 font-semibold">{{ t("settings.value") }}</th>
                  <th class="w-16 px-4 py-2 font-semibold">{{ t("settings.type") }}</th>
                  <th class="px-4 py-2 font-semibold"></th>
                </tr>
              </thead>
              <tbody class="bg-white dark:bg-gray-900">
                <tr
                  v-for="s in aiSettings"
                  :key="s.key"
                  class="border-t border-gray-100 align-top hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
                >
                  <td class="px-4 py-3">
                    <code class="text-xs text-gray-700 dark:text-gray-200">{{ s.key }}</code>
                    <p v-if="s.description || settingHint(s.key)" class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                      {{ s.description || settingHint(s.key) }}
                    </p>
                  </td>
                  <td class="px-4 py-3">
                    <template v-if="isEditing(s.key)">
                      <div class="flex flex-col gap-1">
                        <template v-if="SETTING_OPTIONS[s.key]">
                          <select v-model="drafts[s.key]" class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
                            <option
                              v-for="opt in SETTING_OPTIONS[s.key]"
                              :key="opt"
                              :value="opt"
                            >{{ opt }}</option>
                          </select>
                        </template>
                        <template v-else-if="s.type === 'bool'">
                          <select v-model="drafts[s.key]" class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        </template>
                        <template v-else>
                          <input
                            v-model="drafts[s.key]"
                            :type="s.type === 'int' ? 'number' : 'text'"
                            class="rounded border border-gray-300 px-2 py-1 text-sm bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                          />
                        </template>
                        <p v-if="saveError[s.key]" class="text-xs text-red-600 dark:text-red-400">
                          {{ saveError[s.key] }}
                        </p>
                      </div>
                    </template>
                    <span v-else class="font-mono text-sm text-gray-900 dark:text-gray-100">{{ s.value || "—" }}</span>
                  </td>
                  <td class="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">{{ s.type }}</td>
                  <td class="px-4 py-3">
                    <template v-if="isEditing(s.key)">
                      <div class="flex gap-2">
                        <button
                          :disabled="saving[s.key]"
                          class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40 dark:bg-indigo-600 dark:hover:bg-indigo-700"
                          @click="save(s.key)"
                        >
                          {{ t("common.save") }}
                        </button>
                        <button
                          class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                          @click="cancelEdit(s.key)"
                        >
                          {{ t("common.cancel") }}
                        </button>
                      </div>
                    </template>
                    <button
                      v-else
                      class="text-xs text-blue-600 hover:underline dark:text-blue-400"
                      @click="startEdit(s.key, s.value)"
                    >
                      {{ t("settings.edit") }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Prompt library -->
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-700">{{ t("settings.ai_prompts_title") }}</h2>
        <button
          class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
          @click="showCreatePrompt = !showCreatePrompt"
        >
          {{ t("ai.create_prompt") }}
        </button>
      </div>

      <!-- Create prompt form -->
      <div
        v-if="showCreatePrompt"
        class="mb-5 rounded-lg border border-indigo-200 bg-indigo-50 p-4"
      >
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("ai.field_slug") }}
              </label>
              <input
                v-model="newPrompt.slug"
                type="text"
                placeholder="my_prompt"
                class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
              />
              <p class="mt-0.5 text-xs text-gray-400">{{ t("ai.field_slug_hint") }}</p>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("ai.field_label") }}
              </label>
              <input
                v-model="newPrompt.label"
                type="text"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("ai.field_description") }}
              <span class="font-normal text-gray-400">({{ t("ai.field_description_hint") }})</span>
            </label>
            <input
              v-model="newPrompt.description"
              type="text"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("ai.field_template") }}
            </label>
            <textarea
              v-model="newPrompt.template"
              rows="6"
              placeholder="You are an expert... Use {variable} for context variables."
              class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
        <p v-if="createPromptError" class="mt-2 text-xs text-red-600">{{ createPromptError }}</p>
        <div class="mt-3 flex gap-2">
          <button
            :disabled="isCreatingPrompt"
            class="rounded bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            @click="createAiPrompt"
          >
            {{ isCreatingPrompt ? t("common.loading") : t("ai.create_submit") }}
          </button>
          <button
            class="rounded border border-gray-300 px-4 py-1.5 text-xs text-gray-600 hover:bg-white"
            @click="showCreatePrompt = false; newPrompt = { slug: '', label: '', description: '', template: '' }; createPromptError = null"
          >
            {{ t("common.cancel") }}
          </button>
        </div>
      </div>

      <p v-if="aiError" class="mb-4 text-sm text-red-600">{{ aiError }}</p>
      <p v-if="aiStore.prompts.length === 0" class="text-sm text-gray-400">
        {{ t("settings.ai_no_prompts") }}
      </p>

      <!-- Split panel: search + sorted list on the left, detail on the right -->
      <div v-else class="flex gap-4 rounded border border-gray-200 bg-white">
        <!-- Left: search + list -->
        <aside class="flex w-64 shrink-0 flex-col border-r border-gray-200">
          <div class="border-b border-gray-200 p-2">
            <input
              v-model="promptSearch"
              type="search"
              :placeholder="t('ai.search_placeholder')"
              class="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div class="max-h-[28rem] flex-1 overflow-y-auto">
            <p
              v-if="filteredPrompts.length === 0"
              class="px-3 py-6 text-center text-xs text-gray-400"
            >
              {{ t("ai.no_match") }}
            </p>
            <button
              v-for="prompt in filteredPrompts"
              :key="prompt.slug"
              type="button"
              class="block w-full border-b border-gray-100 px-3 py-2 text-left transition-colors last:border-b-0"
              :class="selectedPromptSlug === prompt.slug
                ? 'bg-indigo-50 text-indigo-900'
                : 'hover:bg-gray-50 text-gray-700'"
              @click="selectPrompt(prompt.slug)"
            >
              <div class="flex items-center gap-1.5">
                <span class="truncate text-sm font-medium">{{ prompt.label }}</span>
                <span
                  v-if="prompt.is_native"
                  class="ml-auto rounded bg-blue-100 px-1 py-0.5 text-[10px] font-medium text-blue-600"
                  :title="t('ai.native_badge')"
                >★</span>
              </div>
              <div class="mt-0.5 truncate font-mono text-[11px] text-gray-400">
                {{ prompt.slug }}
              </div>
            </button>
          </div>
        </aside>

        <!-- Right: detail of the selected prompt -->
        <section class="flex-1 p-4">
          <div v-if="!selectedPrompt" class="text-sm text-gray-400">
            {{ t("ai.select_a_prompt") }}
          </div>
          <template v-else>
            <!-- View mode -->
            <template v-if="editingPrompt !== selectedPrompt.slug">
              <div class="mb-2 flex flex-wrap items-center gap-2">
                <span class="font-medium text-gray-800">{{ selectedPrompt.label }}</span>
                <span class="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-500">
                  {{ selectedPrompt.slug }}
                </span>
                <span
                  v-if="selectedPrompt.is_native"
                  class="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-600"
                >
                  {{ t("ai.native_badge") }}
                </span>
                <span
                  v-if="selectedPrompt.target_context"
                  class="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-600"
                >
                  {{ selectedPrompt.target_context }}
                </span>
              </div>
              <p v-if="selectedPrompt.description" class="mb-2 text-xs text-gray-400">
                {{ selectedPrompt.description }}
              </p>
              <pre class="mb-3 max-h-96 overflow-y-auto rounded bg-gray-50 p-2 text-xs text-gray-700">{{ selectedPrompt.template }}</pre>
              <div class="flex gap-2">
                <button
                  class="text-xs text-indigo-600 hover:text-indigo-800"
                  @click="startEditPrompt(selectedPrompt)"
                >
                  {{ t("ai.edit_prompt") }}
                </button>
                <button
                  v-if="!selectedPrompt.is_native"
                  :disabled="isDeletingPrompt[selectedPrompt.slug]"
                  class="text-xs text-red-500 hover:text-red-700 disabled:opacity-40"
                  @click="deleteAiPrompt(selectedPrompt.slug)"
                >
                  {{ t("ai.delete_prompt") }}
                </button>
              </div>
            </template>

            <!-- Edit mode -->
            <template v-else>
              <div class="space-y-2">
                <input
                  v-model="promptDraft.label"
                  type="text"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                />
                <textarea
                  v-model="promptDraft.template"
                  rows="14"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <p v-if="savePromptError[selectedPrompt.slug]" class="mt-1 text-xs text-red-600">
                {{ savePromptError[selectedPrompt.slug] }}
              </p>
              <div class="mt-2 flex gap-2">
                <button
                  :disabled="savingPrompt[selectedPrompt.slug]"
                  class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
                  @click="saveEditPrompt(selectedPrompt.slug)"
                >
                  {{ t("common.save") }}
                </button>
                <button
                  class="rounded border px-3 py-1 text-xs hover:bg-gray-50"
                  @click="cancelEditPrompt"
                >
                  {{ t("common.cancel") }}
                </button>
              </div>
            </template>
          </template>
        </section>
      </div>
    </template>

    <!-- ── Design tab — XSLT Stylesheets ── -->
    <template v-if="activeTab === 'design'">
      <h1 class="mb-1 text-2xl font-bold">{{ t("settings.xslt_templates_title") }}</h1>
      <p class="mb-6 text-sm text-gray-500">{{ t("settings.xslt_templates_subtitle") }}</p>

      <p v-if="xsltError" class="mb-4 text-sm text-red-600">{{ xsltError }}</p>

      <!-- Add form -->
      <div class="mb-8 rounded border border-gray-200 bg-white p-4 space-y-3">
        <p class="text-sm font-medium text-gray-700">{{ t("settings.xslt_templates_add") }}</p>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_name") }} *</label>
            <input v-model="newXsltName" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" :placeholder="t('settings.xslt_templates_name_placeholder')" />
          </div>
          <div>
            <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_processor") }}</label>
            <select v-model="newXsltProcessor" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm">
              <option value="lxml">lxml (XSLT 1.0)</option>
              <option value="saxon" disabled>Saxon (XSLT 2.0/3.0) — not yet available</option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_description") }}</label>
            <input v-model="newXsltDescription" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" :placeholder="t('settings.xslt_templates_description_placeholder')" />
          </div>
          <div class="sm:col-span-2">
            <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_tags") }}</label>
            <input v-model="newXsltTags" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" :placeholder="t('settings.xslt_templates_tags_placeholder')" />
          </div>
          <div class="sm:col-span-2">
            <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_content") }} *</label>
            <textarea v-model="newXsltContent" rows="8" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" placeholder="<?xml version=&quot;1.0&quot;?>&#10;<xsl:stylesheet ...>" />
            <p class="mt-0.5 text-right text-xs text-gray-400">{{ newXsltContent.length.toLocaleString() }} {{ t("settings.xslt_templates_chars") }}</p>
          </div>
        </div>
        <p v-if="createXsltError" class="text-xs text-red-600">{{ createXsltError }}</p>
        <button
          :disabled="isCreatingXslt || !newXsltName.trim() || !newXsltContent.trim()"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="createXsltTemplate"
        >
          {{ isCreatingXslt ? t("common.loading") : t("common.save") }}
        </button>
      </div>

      <!-- Catalog list -->
      <p v-if="xsltStore.templates.length === 0" class="text-sm text-gray-400 italic">{{ t("settings.xslt_templates_empty") }}</p>
      <div v-else class="space-y-3">
        <div
          v-for="tpl in xsltStore.templates"
          :key="tpl.id"
          class="rounded border border-gray-200 bg-white p-4"
        >
          <!-- View mode -->
          <template v-if="editingXsltId !== tpl.id">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <p class="truncate font-medium text-sm text-gray-800">{{ tpl.name }}</p>
                <p v-if="tpl.description" class="text-xs text-gray-500 mt-0.5">{{ tpl.description }}</p>
                <div class="mt-1 flex flex-wrap gap-1">
                  <span class="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{{ tpl.processor }}</span>
                  <span v-for="tag in tpl.tags" :key="tag" class="rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-600">{{ tag }}</span>
                </div>
              </div>
              <div class="flex shrink-0 gap-3">
                <button class="text-xs text-indigo-600 hover:text-indigo-800" @click="startEditXslt(tpl)">{{ t("common.edit") }}</button>
                <button class="text-xs text-red-500 hover:text-red-700" @click="deleteXsltTemplate(tpl.id)">{{ t("common.delete") }}</button>
              </div>
            </div>
          </template>

          <!-- Edit mode -->
          <template v-else>
            <div class="space-y-3">
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_name") }}</label>
                  <input v-model="xsltEditDraft.name" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
                </div>
                <div>
                  <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_processor") }}</label>
                  <select v-model="xsltEditDraft.processor" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm">
                    <option value="lxml">lxml (XSLT 1.0)</option>
                    <option value="saxon" disabled>Saxon (XSLT 2.0/3.0) — not yet available</option>
                  </select>
                </div>
                <div class="sm:col-span-2">
                  <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_description") }}</label>
                  <input v-model="xsltEditDraft.description" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
                </div>
                <div class="sm:col-span-2">
                  <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_tags") }}</label>
                  <input v-model="xsltEditDraft.tags" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
                </div>
                <div class="sm:col-span-2">
                  <label class="block text-xs text-gray-600">{{ t("settings.xslt_templates_content") }}</label>
                  <textarea v-model="xsltEditDraft.content" rows="10" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" />
                  <p class="mt-0.5 text-right text-xs text-gray-400">{{ xsltEditDraft.content.length.toLocaleString() }} {{ t("settings.xslt_templates_chars") }}</p>
                </div>
              </div>
              <p v-if="saveXsltError" class="text-xs text-red-600">{{ saveXsltError }}</p>
              <div class="flex gap-2">
                <button
                  :disabled="isSavingXslt"
                  class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                  @click="saveXsltTemplate(tpl.id)"
                >
                  {{ isSavingXslt ? t("common.loading") : t("common.save") }}
                </button>
                <button class="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="cancelEditXslt">
                  {{ t("common.cancel") }}
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
