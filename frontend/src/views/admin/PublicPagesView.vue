<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";
import { contrastingTextColor } from "@/utils/color";
import { useSettingStore } from "@/stores/settings";
import { useUiConfigStore } from "@/stores/ui_config";
import WysiwygEditor from "@/components/ui/WysiwygEditor.vue";
import { usePluginStore } from "@/stores/plugins";

const { t } = useI18n();
const settingStore = useSettingStore();
const uiConfigStore = useUiConfigStore();
const pluginStore = usePluginStore();

// ── Tabs ─────────────────────────────────────────────────────────────────────
type TabKey = "aspetto" | "homepage" | "pagine" | "documento";
const activeTab = ref<TabKey>("aspetto");

onMounted(async () => {
  // The store already caches by key, so this is a no-op when SettingsView
  // has already loaded — but a direct deep-link to /admin/public-pages
  // needs the settings before any draft can render.
  if (!settingStore.settings.length) await settingStore.fetchSettings();
  if (!pluginStore.plugins.length) await pluginStore.fetchPlugins();
  initAppearanceDraft();
});

// ── Plugin-declared public links (public_navigation capability) ──────────────

const pluginsWithPublicNav = computed(() =>
  pluginStore.plugins
    .filter(
      (p) =>
        p.status === "active"
        && p.ui_descriptor != null
        && typeof p.ui_descriptor === "object"
        && "public_navigation" in p.ui_descriptor,
    )
    .sort((a, b) => a.display_name.localeCompare(b.display_name)),
);

function publicLinkSettingKey(pluginName: string): string {
  return `public_link_${pluginName}_enabled`;
}

function isPublicLinkEnabled(pluginName: string): boolean {
  return settingStore.getSetting(publicLinkSettingKey(pluginName)) === "true";
}

function publicLinkSection(pluginName: string): string {
  const plugin = pluginStore.plugins.find((p) => p.name === pluginName);
  const desc = plugin?.ui_descriptor as { public_navigation?: { section?: string } } | null;
  return desc?.public_navigation?.section ?? "";
}

// ── Appearance ───────────────────────────────────────────────────────────────

const COLOR_PRESETS: Array<{ label: string; value: string }> = [
  { label: "Gray", value: "#111827" },
  { label: "Blue", value: "#1e40af" },
  { label: "Indigo", value: "#3730a3" },
  { label: "Navy", value: "#1e3a5f" },
  { label: "Green", value: "#166534" },
  { label: "Red", value: "#991b1b" },
  { label: "Purple", value: "#6b21a8" },
  { label: "Slate", value: "#1e293b" },
];

const logoUrlDraft = ref("");
const isSavingLogoUrl = ref(false);
const logoUrlError = ref("");
const isUploadingLogo = ref(false);
const uploadLogoError = ref("");

const currentLogoUrl = computed(() => settingStore.getSetting("platform_logo_url") ?? "");
const currentNavbarColor = computed(() => settingStore.getSetting("navbar_bg_color") ?? "#1e40af");
const previewTextColor = computed(() => contrastingTextColor(currentNavbarColor.value));

const navbarColorDraft = ref("#1e40af");
const isSavingNavbarColor = ref(false);
const navbarColorError = ref("");
const hexPattern = /^#[0-9a-fA-F]{6}$/;
const isNavbarColorValid = computed(() => hexPattern.test(navbarColorDraft.value));

function initAppearanceDraft(): void {
  logoUrlDraft.value = currentLogoUrl.value;
  navbarColorDraft.value = currentNavbarColor.value;
}

async function saveLogoUrl(): Promise<void> {
  isSavingLogoUrl.value = true;
  logoUrlError.value = "";
  try {
    await settingStore.updateSetting("platform_logo_url", logoUrlDraft.value.trim());
    await uiConfigStore.fetchConfig();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    logoUrlError.value = msg ?? t("common.error");
  } finally {
    isSavingLogoUrl.value = false;
  }
}

async function handleLogoUpload(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  isUploadingLogo.value = true;
  uploadLogoError.value = "";
  try {
    const url = await settingStore.uploadLogo(file);
    logoUrlDraft.value = url;
    await uiConfigStore.fetchConfig();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    uploadLogoError.value = msg ?? t("common.error");
  } finally {
    isUploadingLogo.value = false;
    (event.target as HTMLInputElement).value = "";
  }
}

const DEFAULT_LOGO_URL = "/aracne-icons/lockup/aracne-lockup-vertical-512.png";

async function restoreDefaultLogo(): Promise<void> {
  logoUrlError.value = "";
  try {
    await settingStore.updateSetting("platform_logo_url", DEFAULT_LOGO_URL);
    logoUrlDraft.value = DEFAULT_LOGO_URL;
    await uiConfigStore.fetchConfig();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    logoUrlError.value = msg ?? t("common.error");
  }
}

async function selectNavbarColor(color: string): Promise<void> {
  navbarColorDraft.value = color;
  await saveNavbarColor();
}

async function saveNavbarColor(): Promise<void> {
  if (!isNavbarColorValid.value) {
    navbarColorError.value = t("settings.appearance_color_invalid");
    return;
  }
  isSavingNavbarColor.value = true;
  navbarColorError.value = "";
  try {
    await settingStore.updateSetting("navbar_bg_color", navbarColorDraft.value);
    await uiConfigStore.fetchConfig();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    navbarColorError.value = msg ?? t("common.error");
  } finally {
    isSavingNavbarColor.value = false;
  }
}

// ── Intro HTML (homepage cover text + media) ─────────────────────────────────
//
// Free-form HTML rendered above the collection list on the public
// homepage. Edited via the standard WysiwygEditor with the
// homepage-media library wired in. Saved via a dedicated PUT
// endpoint (the generic SettingUpdate validator rejects empty
// strings, but the admin must be able to *clear* the intro).

const introDraft = ref<string>("");
const isSavingIntro = ref(false);
const introSaveOk = ref(false);
const introError = ref<string | null>(null);

function syncIntroFromConfig(): void {
  introDraft.value = uiConfigStore.config.home_intro_html || "";
}

watch(() => uiConfigStore.config.home_intro_html, syncIntroFromConfig, { immediate: true });

async function saveIntro(): Promise<void> {
  isSavingIntro.value = true;
  introError.value = null;
  introSaveOk.value = false;
  try {
    await apiClient.put<{ html: string }>("/settings/home-intro", {
      html: introDraft.value,
    });
    await uiConfigStore.fetchConfig();
    introSaveOk.value = true;
    setTimeout(() => { introSaveOk.value = false; }, 1500);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    introError.value = msg ?? t("common.error");
  } finally {
    isSavingIntro.value = false;
  }
}

async function clearIntro(): Promise<void> {
  if (!introDraft.value.trim()) return;
  if (!window.confirm(t("settings.home_intro_confirm_clear"))) return;
  introDraft.value = "";
  await saveIntro();
}

// ── Behaviour toggles ─────────────────────────────────────────────────────────

const publicHomeEnabled = computed(
  () => settingStore.getSetting("public_home_enabled") === "true",
);
const homeShowCollections = computed(
  () => settingStore.getSetting("home_show_collections") === "true",
);
const homeShowSearch = computed(
  () => settingStore.getSetting("home_show_search") === "true",
);
const homeShowLoginButton = computed(
  () => settingStore.getSetting("home_show_login_button") === "true",
);
const homePropagateCss = computed(
  () => settingStore.getSetting("home_propagate_css") === "true",
);
const sitemapIncludeSearchEngines = computed(
  () => settingStore.getSetting("sitemap_include_search_engines") === "true",
);

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

// ── Public Search header link ────────────────────────────────────────────────

interface AdminSearchEngineItem { slug: string; title: string }
const publicSearchEngineEnabled = computed(
  () => settingStore.getSetting("public_search_engine_enabled") === "true",
);
const publicSearchEngineSlug = computed(
  () => settingStore.getSetting("public_search_engine_slug") || "",
);
const searchPanelOpen = ref(false);
const enginesList = ref<AdminSearchEngineItem[]>([]);
const enginesLoading = ref(false);
const enginesError = ref<string | null>(null);
const savingSearchEngine = ref(false);

async function loadAdminEngines(): Promise<void> {
  if (enginesList.value.length > 0 || enginesLoading.value) return;
  enginesLoading.value = true;
  enginesError.value = null;
  try {
    const data = await apiClient.get<AdminSearchEngineItem[]>("/search-engines");
    enginesList.value = data.map((e) => ({ slug: e.slug, title: e.title }));
  } catch {
    enginesError.value = t("common.error");
  } finally {
    enginesLoading.value = false;
  }
}

function toggleSearchPanel(): void {
  searchPanelOpen.value = !searchPanelOpen.value;
  if (searchPanelOpen.value) loadAdminEngines();
}

async function setPublicSearchEngineSlug(newSlug: string): Promise<void> {
  if (!newSlug || newSlug === publicSearchEngineSlug.value) return;
  savingSearchEngine.value = true;
  try {
    await settingStore.updateSetting("public_search_engine_slug", newSlug);
    await uiConfigStore.fetchConfig();
  } finally {
    savingSearchEngine.value = false;
  }
}

async function togglePublicSearchEngine(): Promise<void> {
  const wantOn = !publicSearchEngineEnabled.value;
  if (wantOn && !publicSearchEngineSlug.value) {
    await loadAdminEngines();
    const first = enginesList.value[0];
    if (!first) {
      enginesError.value = t("public_search.no_engines");
      return;
    }
    await setPublicSearchEngineSlug(first.slug);
  }
  savingSearchEngine.value = true;
  try {
    await settingStore.updateSetting(
      "public_search_engine_enabled",
      wantOn ? "true" : "false",
    );
    await uiConfigStore.fetchConfig();
  } finally {
    savingSearchEngine.value = false;
  }
}

// ── Document options (public document pages) ─────────────────────────────────

const NOTE_MODES = ["end-of-text", "tooltip", "frame"] as const;
type NoteMode = (typeof NOTE_MODES)[number];

const publicNoteMode = computed<NoteMode>(() => {
  const v = settingStore.getSetting("public_pages_note_mode") || "end-of-text";
  return (NOTE_MODES as readonly string[]).includes(v) ? (v as NoteMode) : "end-of-text";
});
const publicEntityHoverEnabled = computed(
  () => settingStore.getSetting("public_pages_entity_hover_enabled") === "true",
);
const publicDocFrameEnabled = computed(
  () => settingStore.getSetting("public_pages_doc_frame_enabled") === "true",
);
const savingNoteMode = ref(false);

async function setPublicNoteMode(mode: NoteMode): Promise<void> {
  if (publicNoteMode.value === mode) return;
  savingNoteMode.value = true;
  try {
    await settingStore.updateSetting("public_pages_note_mode", mode);
  } finally {
    savingNoteMode.value = false;
  }
}

// ── Custom CSS upload ────────────────────────────────────────────────────────

const cssFileInput = ref<HTMLInputElement | null>(null);
const selectedCssFile = ref<File | null>(null);
const isUploadingCss = ref(false);
const cssUploadError = ref<string | null>(null);
const cssUploadOk = ref(false);

function onCssFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedCssFile.value = input.files?.[0] ?? null;
  cssUploadError.value = null;
  cssUploadOk.value = false;
}

async function uploadCustomCss(): Promise<void> {
  if (!selectedCssFile.value) return;
  isUploadingCss.value = true;
  cssUploadError.value = null;
  cssUploadOk.value = false;
  try {
    const form = new FormData();
    form.append("file", selectedCssFile.value);
    await apiClient.upload<{ url: string }>("/settings/homepage-css", form);
    await uiConfigStore.fetchConfig();
    cssUploadOk.value = true;
    selectedCssFile.value = null;
    if (cssFileInput.value) cssFileInput.value.value = "";
  } catch (err) {
    cssUploadError.value = (err as Error).message ?? t("common.error");
  } finally {
    isUploadingCss.value = false;
  }
}

async function deleteCustomCss(): Promise<void> {
  if (!confirm(t("settings.homepage_css_confirm_delete"))) return;
  try {
    await apiClient.delete("/settings/homepage-css");
    await uiConfigStore.fetchConfig();
    cssUploadOk.value = false;
  } catch (err) {
    cssUploadError.value = (err as Error).message ?? t("common.error");
  }
}

function downloadHomepageCss(): void {
  const css = `/* ============================================================
   Aracne2 — Public pages custom stylesheet
   Generated by Aracne2 · docs/reference/PUBLIC_PAGES.md
   ============================================================ */


/* ============================================================
   HOMEPAGE  (PublicHomeSection.vue)
   ============================================================ */

/* ── Page structure ─────────────────────────────────────────── */
.ph-page    {}
.ph-header  {}
.ph-main    {}

/* ── Header ─────────────────────────────────────────────────── */
.ph-logo        {}
.ph-logo-img    {}
.ph-site-name   {}
.ph-login       {}

/* ── Search bar ─────────────────────────────────────────────── */
.ph-search        {}
.ph-search-form   {}
.ph-search-input  {}
.ph-search-btn    {}
.ph-search-reset  {}

/* ── Collection section ─────────────────────────────────────── */
.ph-stats      {}
.ph-loading    {}
.ph-no-results {}
.ph-empty      {}

/* ── Recent additions ("Ultime aggiunte") ───────────────────── */
.last-add        {}
.last-add-title  {}
.last-add-grid   {}
.last-add-card   {}


/* ============================================================
   COLLECTION VIEW  (PublicCollectionView.vue)
   ============================================================ */

/* ── Page structure ─────────────────────────────────────────── */
.pc-page   {}
.pc-header {}
.pc-main   {}

/* ── Header ─────────────────────────────────────────────────── */
.pc-logo      {}
.pc-logo-img  {}
.pc-site-name {}
.pc-login     {}

/* ── Navigation & collection info ───────────────────────────── */
.pc-breadcrumb        {}
.pc-collection-header {}

/* ── Document list ──────────────────────────────────────────── */
.doc-list-heading {}
.doc-list         {}
.doc-item         {}
.doc-title        {}
.doc-author       {}
.doc-view-link    {}


/* ============================================================
   DOCUMENT VIEWER  (PublicDocumentView.vue)
   ============================================================ */

/* ── Page structure ─────────────────────────────────────────── */
.pd-page   {}
.pd-header {}
.pd-main   {}

/* ── Header ─────────────────────────────────────────────────── */
.pd-logo      {}
.pd-logo-img  {}
.pd-site-name {}
.pd-login     {}

/* ── Content ────────────────────────────────────────────────── */
.pd-breadcrumb {}
.doc-frame     {}


/* ============================================================
   NAMED ENTITIES  (PublicEntitiesView.vue)
   ============================================================ */

/* ── Page structure ─────────────────────────────────────────── */
.pe-page   {}
.pe-header {}
.pe-main   {}

/* ── Header ─────────────────────────────────────────────────── */
.pe-logo      {}
.pe-logo-img  {}
.pe-site-name {}
.pe-login     {}

/* ── Navigation & filters ───────────────────────────────────── */
.pe-back-link  {}
.pe-page-title {}
.entity-filters {}
.filter-type    {}
.filter-search  {}
.filter-btn     {}

/* ── Entity list ────────────────────────────────────────────── */
.entity-list      {}
.entity-row       {}
.entity-badge     {}
.entity-name      {}
.entity-count     {}
.entity-authority {}
.entity-pagination {}

/* ── Occurrences panel ──────────────────────────────────────── */
.occurrences-panel    {}
.occurrence-item      {}
.occurrence-form      {}
.occurrence-context   {}
.occurrence-doc-link  {}
.occurrences-pagination {}


/* ============================================================
   BIBLIOGRAPHY  (PublicBibliographyView.vue)
   ============================================================ */

/* ── Page structure ─────────────────────────────────────────── */
.pb-page   {}
.pb-header {}
.pb-main   {}

/* ── Header ─────────────────────────────────────────────────── */
.pb-logo      {}
.pb-logo-img  {}
.pb-site-name {}
.pb-login     {}

/* ── Content ────────────────────────────────────────────────── */
.pb-error      {}
.pb-page-title {}
.pb-back-link  {}
.bibliography-list {}
.bibliography-item {}
`;
  const blob = new Blob([css], { type: "text/css" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "public-pages.css";
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="px-6 py-6">
    <h1 class="mb-1 text-2xl font-bold">{{ t("settings.homepage_title") }}</h1>
    <p class="mb-6 text-sm text-gray-500">{{ t("settings.homepage_subtitle") }}</p>

    <!-- Master toggle: Enable Public Pages (always visible, outside any tab) -->
    <div class="mb-6 flex items-start justify-between rounded border border-gray-200 bg-white p-4">
      <div class="mr-4">
        <p class="text-sm font-medium text-gray-800">
          {{ t("settings.homepage_public_home_enabled") }}
        </p>
        <p class="mt-0.5 text-xs text-gray-500">
          {{ t("settings.homepage_public_home_enabled_hint") }}
        </p>
      </div>
      <button
        :disabled="togglingHomeSetting['public_home_enabled']"
        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
        :class="publicHomeEnabled ? 'bg-indigo-600' : 'bg-gray-200'"
        @click="toggleHomeSetting('public_home_enabled', publicHomeEnabled)"
      >
        <span
          class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
          :class="publicHomeEnabled ? 'translate-x-5' : 'translate-x-0'"
        />
      </button>
    </div>

    <!-- Tab bar -->
    <div class="mb-6 flex gap-4 border-b border-gray-200 dark:border-gray-700">
      <button
        v-for="tab in (['aspetto', 'homepage', 'pagine', 'documento'] as TabKey[])"
        :key="tab"
        :class="[
          'pb-2 text-sm font-medium',
          activeTab === tab
            ? 'border-b-2 border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100',
        ]"
        @click="activeTab = tab"
      >
        {{ t(`settings.public_pages_tab_${tab}`) }}
      </button>
    </div>

    <!-- ── Tab: Aspetto ── -->
    <template v-if="activeTab === 'aspetto'">
      <!-- home_show_login_button -->
      <div class="mb-6 flex items-start justify-between rounded border border-gray-200 bg-white p-4">
        <div class="mr-4">
          <p class="text-sm font-medium text-gray-800">
            {{ t("settings.homepage_show_login_button") }}
          </p>
          <p class="mt-0.5 text-xs text-gray-500">
            {{ t("settings.homepage_show_login_button_hint") }}
          </p>
        </div>
        <button
          :disabled="togglingHomeSetting['home_show_login_button']"
          class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
          :class="homeShowLoginButton ? 'bg-indigo-600' : 'bg-gray-200'"
          @click="toggleHomeSetting('home_show_login_button', homeShowLoginButton)"
        >
          <span
            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
            :class="homeShowLoginButton ? 'translate-x-5' : 'translate-x-0'"
          />
        </button>
      </div>

    <!-- Logo section -->
    <section class="mb-8 rounded border border-gray-200 p-5">
      <h2 class="mb-4 text-sm font-semibold text-gray-800">
        {{ t("settings.appearance_logo_title") }}
      </h2>

      <div class="mb-4 flex items-center gap-4">
        <div class="flex h-16 w-32 items-center justify-center rounded border border-gray-200 bg-gray-50">
          <img
            v-if="currentLogoUrl"
            :src="currentLogoUrl"
            alt="current logo"
            class="max-h-14 max-w-28 object-contain"
          />
          <span v-else class="text-xs text-gray-400">—</span>
        </div>
        <div class="text-xs text-gray-500">
          <p>{{ t("settings.appearance_logo_url_hint") }}</p>
          <p class="mt-1 font-mono">{{ currentLogoUrl || "—" }}</p>
          <button
            v-if="currentLogoUrl && currentLogoUrl !== DEFAULT_LOGO_URL"
            class="mt-2 text-indigo-600 hover:underline"
            @click="restoreDefaultLogo"
          >
            {{ t("settings.appearance_logo_restore_default") }}
          </button>
        </div>
      </div>

      <div class="mb-4">
        <label class="block text-xs font-medium text-gray-700 mb-1">
          {{ t("settings.appearance_logo_upload") }}
        </label>
        <input
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.svg,.webp"
          :disabled="isUploadingLogo"
          class="text-sm text-gray-600 file:mr-3 file:rounded file:border file:border-gray-300 file:bg-white file:px-3 file:py-1 file:text-xs file:text-gray-700 hover:file:bg-gray-50"
          @change="handleLogoUpload"
        />
        <p v-if="uploadLogoError" class="mt-1 text-xs text-red-600">{{ uploadLogoError }}</p>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">
          {{ t("settings.appearance_logo_url_label") }}
        </label>
        <div class="flex gap-2">
          <input
            v-model="logoUrlDraft"
            type="text"
            :placeholder="t('settings.appearance_logo_url_hint')"
            class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
          <button
            :disabled="isSavingLogoUrl || !logoUrlDraft.trim()"
            class="rounded bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
            @click="saveLogoUrl"
          >
            {{ t("settings.appearance_logo_save_url") }}
          </button>
        </div>
        <p v-if="logoUrlError" class="mt-1 text-xs text-red-600">{{ logoUrlError }}</p>
      </div>
    </section>

    <!-- Navbar colour section -->
    <section class="mb-8 rounded border border-gray-200 p-5">
      <h2 class="mb-4 text-sm font-semibold text-gray-800">
        {{ t("settings.appearance_color_title") }}
      </h2>

      <div class="mb-4">
        <label class="block text-xs font-medium text-gray-700 mb-1">
          {{ t("settings.appearance_color_custom_label") }}
        </label>
        <div class="flex items-center gap-2">
          <input
            v-model="navbarColorDraft"
            type="color"
            :aria-label="t('settings.appearance_color_picker_label')"
            class="h-9 w-12 cursor-pointer rounded border border-gray-300 bg-white p-0.5"
          />
          <input
            v-model="navbarColorDraft"
            type="text"
            placeholder="#1e40af"
            maxlength="7"
            class="w-32 rounded border border-gray-300 px-3 py-1.5 font-mono text-sm uppercase focus:border-indigo-500 focus:outline-none"
            :class="isNavbarColorValid ? '' : 'border-red-400'"
          />
          <button
            :disabled="isSavingNavbarColor || !isNavbarColorValid || navbarColorDraft === currentNavbarColor"
            class="rounded bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
            @click="saveNavbarColor"
          >
            {{ t("common.save") }}
          </button>
        </div>
        <p v-if="navbarColorError" class="mt-1 text-xs text-red-600">{{ navbarColorError }}</p>
      </div>

      <div>
        <p class="mb-2 text-xs text-gray-500">{{ t("settings.appearance_color_quick_picks") }}</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="preset in COLOR_PRESETS"
            :key="preset.value"
            :title="`${preset.label} — ${preset.value}`"
            class="h-7 w-7 rounded border-2 shadow-sm transition-all"
            :class="currentNavbarColor === preset.value ? 'border-indigo-500 scale-110' : 'border-transparent hover:border-gray-400'"
            :style="{ backgroundColor: preset.value }"
            @click="selectNavbarColor(preset.value)"
          />
        </div>
      </div>

      <div class="mt-5">
        <p class="mb-2 text-xs text-gray-500">{{ t("settings.appearance_color_preview") }}</p>
        <div
          class="flex h-12 items-center gap-3 rounded px-4"
          :style="{ backgroundColor: currentNavbarColor, color: previewTextColor }"
        >
          <img
            v-if="currentLogoUrl"
            :src="currentLogoUrl"
            alt="logo preview"
            class="h-7 w-auto object-contain"
          />
          <span class="text-sm font-bold">{{ uiConfigStore.config.platform_name }}</span>
          <span class="ml-auto text-xs opacity-70">{{ t("auth.sign_in") }}</span>
        </div>
      </div>
    </section>

      <!-- Custom CSS tools (Aspetto tab) -->
      <div class="mb-6 space-y-3 rounded border border-gray-200 bg-white p-4">
        <p class="text-sm font-semibold text-gray-800">{{ t("settings.homepage_css_title") }}</p>
        <p class="text-xs text-gray-500">{{ t("settings.homepage_css_hint") }}</p>

        <div class="flex items-center gap-2">
          <span
            class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
            :class="uiConfigStore.config.has_custom_homepage_css
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-500'"
          >
            <span
              class="h-1.5 w-1.5 rounded-full"
              :class="uiConfigStore.config.has_custom_homepage_css ? 'bg-green-500' : 'bg-gray-400'"
            />
            {{ uiConfigStore.config.has_custom_homepage_css
                ? t("settings.homepage_css_status_active")
                : t("settings.homepage_css_status_none") }}
          </span>
          <button
            v-if="uiConfigStore.config.has_custom_homepage_css"
            class="text-xs text-red-500 hover:underline"
            @click="deleteCustomCss"
          >
            {{ t("settings.homepage_css_remove") }}
          </button>
        </div>

        <div class="flex items-center gap-2">
          <input
            ref="cssFileInput"
            type="file"
            accept=".css"
            class="flex-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 file:mr-2 file:rounded file:border-0 file:bg-gray-100 file:px-2 file:py-0.5 file:text-xs file:font-medium"
            @change="onCssFileChange"
          />
          <button
            :disabled="!selectedCssFile || isUploadingCss"
            class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            @click="uploadCustomCss"
          >
            {{ isUploadingCss ? t("common.saving") : t("settings.homepage_css_upload_btn") }}
          </button>
        </div>

        <p v-if="cssUploadOk"    class="text-xs text-green-600">{{ t("settings.homepage_css_upload_ok") }}</p>
        <p v-if="cssUploadError" class="text-xs text-red-600">{{ cssUploadError }}</p>

        <div class="flex items-center justify-between border-t border-gray-100 pt-3">
          <p class="text-xs text-gray-500">{{ t("settings.homepage_download_css_hint") }}</p>
          <button
            class="flex items-center gap-1.5 rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            @click="downloadHomepageCss"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {{ t("settings.homepage_download_css_btn") }}
          </button>
        </div>
      </div>

      <!-- home_propagate_css -->
      <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4">
        <div class="mr-4">
          <p class="text-sm font-medium text-gray-800">
            {{ t("settings.homepage_propagate_css") }}
          </p>
          <p class="mt-0.5 text-xs text-gray-500">
            {{ t("settings.homepage_propagate_css_hint") }}
          </p>
        </div>
        <button
          :disabled="togglingHomeSetting['home_propagate_css']"
          class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
          :class="homePropagateCss ? 'bg-indigo-600' : 'bg-gray-200'"
          @click="toggleHomeSetting('home_propagate_css', homePropagateCss)"
        >
          <span
            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
            :class="homePropagateCss ? 'translate-x-5' : 'translate-x-0'"
          />
        </button>
      </div>
    </template>

    <!-- ── Tab: Homepage ── -->
    <template v-if="activeTab === 'homepage'">
    <!-- Intro HTML — free-form cover text rendered above the collection list -->
    <section class="mb-8 rounded border border-gray-200 p-5">
      <h2 class="mb-1 text-sm font-semibold text-gray-800">
        {{ t("settings.home_intro_title") }}
      </h2>
      <p class="mb-3 text-xs text-gray-500">
        {{ t("settings.home_intro_subtitle") }}
      </p>

      <WysiwygEditor v-model="introDraft" homepage-media />

      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          :disabled="isSavingIntro || introDraft === (uiConfigStore.config.home_intro_html || '')"
          class="rounded bg-gray-900 px-3 py-1.5 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
          @click="saveIntro"
        >
          {{ isSavingIntro ? t("common.saving") : t("common.save") }}
        </button>
        <button
          v-if="introDraft.trim()"
          type="button"
          class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
          @click="clearIntro"
        >
          {{ t("settings.home_intro_clear") }}
        </button>
        <span v-if="introSaveOk" class="text-xs text-green-600">{{ t("common.saved") }}</span>
        <span v-if="introError" class="text-xs text-red-600">{{ introError }}</span>
      </div>
    </section>

      <div class="space-y-4">
        <!-- home_show_collections -->
        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4">
          <div class="mr-4">
            <p class="text-sm font-medium text-gray-800">
              {{ t("settings.homepage_show_collections") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500">
              {{ t("settings.homepage_show_collections_hint") }}
            </p>
          </div>
          <button
            :disabled="togglingHomeSetting['home_show_collections']"
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
            :class="homeShowCollections ? 'bg-indigo-600' : 'bg-gray-200'"
            @click="toggleHomeSetting('home_show_collections', homeShowCollections)"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="homeShowCollections ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>

        <!-- home_show_search -->
        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4">
          <div class="mr-4">
            <p class="text-sm font-medium text-gray-800">
              {{ t("settings.homepage_show_search") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500">
              {{ t("settings.homepage_show_search_hint") }}
            </p>
          </div>
          <button
            :disabled="togglingHomeSetting['home_show_search']"
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
            :class="homeShowSearch ? 'bg-indigo-600' : 'bg-gray-200'"
            @click="toggleHomeSetting('home_show_search', homeShowSearch)"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="homeShowSearch ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>
      </div>
    </template>

    <!-- ── Tab: Pagine ── -->
    <template v-if="activeTab === 'pagine'">
      <div class="space-y-4">
        <!-- public_search_engine_enabled — foldable panel -->
        <div class="rounded border border-gray-200 bg-white">
          <button
            type="button"
            class="flex w-full items-start justify-between gap-4 px-4 py-4 text-left"
            @click="toggleSearchPanel"
          >
            <span class="flex items-center gap-2">
              <svg
                class="h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform"
                :class="{ 'rotate-90': searchPanelOpen }"
                viewBox="0 0 20 20" fill="currentColor"
              >
                <path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 0 1 .02-1.06L11.168 10 7.23 6.29a.75.75 0 1 1 1.04-1.08l4.5 4.25a.75.75 0 0 1 0 1.08l-4.5 4.25a.75.75 0 0 1-1.06-.02Z" clip-rule="evenodd" />
              </svg>
              <span class="flex flex-col">
                <span class="text-sm font-medium text-gray-800">
                  {{ t("settings.homepage_public_search_engine_enabled") }}
                </span>
                <span class="mt-0.5 text-xs text-gray-500">
                  {{ t("settings.homepage_public_search_engine_enabled_hint") }}
                </span>
              </span>
            </span>
            <span
              class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
              :class="publicSearchEngineEnabled ? 'bg-indigo-600' : 'bg-gray-200'"
              :aria-disabled="savingSearchEngine"
              @click.stop="togglePublicSearchEngine"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="publicSearchEngineEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </span>
          </button>
          <div v-if="searchPanelOpen" class="border-t border-gray-100 px-4 py-4">
            <p class="mb-2 text-xs font-medium text-gray-700">
              {{ t("public_search.engine_label") }}
            </p>
            <p v-if="enginesLoading" class="text-xs text-gray-400">
              {{ t("public_search.loading_engines") }}
            </p>
            <p v-else-if="enginesError" class="text-xs text-red-600">{{ enginesError }}</p>
            <p v-else-if="enginesList.length === 0" class="text-xs text-gray-400">
              {{ t("public_search.no_engines") }}
            </p>
            <select
              v-else
              :value="publicSearchEngineSlug"
              :disabled="savingSearchEngine"
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none disabled:opacity-50"
              @change="setPublicSearchEngineSlug(($event.target as HTMLSelectElement).value)"
            >
              <option value="" disabled>{{ t("public_search.engine_select_placeholder") }}</option>
              <option v-for="e in enginesList" :key="e.slug" :value="e.slug">
                {{ e.title }} ({{ e.slug }})
              </option>
            </select>
          </div>
        </div>

        <!-- sitemap_include_search_engines -->
        <div class="flex items-start justify-between rounded border border-gray-200 bg-white p-4">
          <div class="mr-4">
            <p class="text-sm font-medium text-gray-800">
              {{ t("settings.homepage_sitemap_include_search_engines") }}
            </p>
            <p class="mt-0.5 text-xs text-gray-500">
              {{ t("settings.homepage_sitemap_include_search_engines_hint") }}
            </p>
          </div>
          <button
            :disabled="togglingHomeSetting['sitemap_include_search_engines']"
            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
            :class="sitemapIncludeSearchEngines ? 'bg-indigo-600' : 'bg-gray-200'"
            @click="toggleHomeSetting('sitemap_include_search_engines', sitemapIncludeSearchEngines)"
          >
            <span
              class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
              :class="sitemapIncludeSearchEngines ? 'translate-x-5' : 'translate-x-0'"
            />
          </button>
        </div>

        <!-- Plugin links — auto-generated per active plugin advertising public_navigation -->
        <div class="rounded border border-gray-200 bg-white p-4">
          <h3 class="text-sm font-semibold text-gray-800">
            {{ t("settings.public_pages_plugin_links_title") }}
          </h3>
          <p class="mt-0.5 text-xs text-gray-500">
            {{ t("settings.public_pages_plugin_links_intro") }}
          </p>

          <p
            v-if="pluginsWithPublicNav.length === 0"
            class="mt-3 text-xs text-gray-400"
          >
            {{ t("settings.public_pages_plugin_links_empty") }}
          </p>

          <ul v-else class="mt-3 space-y-2">
            <li
              v-for="plugin in pluginsWithPublicNav"
              :key="plugin.name"
              class="flex items-start justify-between rounded border border-gray-100 bg-gray-50 p-3"
            >
              <div class="mr-4">
                <p class="text-sm font-medium text-gray-800">
                  {{ plugin.display_name }}
                </p>
                <p class="mt-0.5 text-xs text-gray-500">
                  {{ t("settings.public_pages_plugin_link_section", { section: publicLinkSection(plugin.name) || "—" }) }}
                </p>
              </div>
              <button
                :disabled="togglingHomeSetting[publicLinkSettingKey(plugin.name)]"
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
                :class="isPublicLinkEnabled(plugin.name) ? 'bg-indigo-600' : 'bg-gray-200'"
                @click="toggleHomeSetting(publicLinkSettingKey(plugin.name), isPublicLinkEnabled(plugin.name))"
              >
                <span
                  class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                  :class="isPublicLinkEnabled(plugin.name) ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </li>
          </ul>
        </div>
      </div>
    </template>

    <!-- ── Tab: Documento ── -->
    <template v-if="activeTab === 'documento'">
      <div class="rounded border border-gray-200 bg-white p-5">
        <h3 class="mb-1 text-sm font-semibold text-gray-800">
          {{ t("settings.public_doc_options_title") }}
        </h3>
        <p class="mb-4 text-xs text-gray-500">
          {{ t("settings.public_doc_options_subtitle") }}
        </p>

        <p class="mb-2 text-xs font-medium text-gray-700">
          {{ t("settings.public_doc_note_mode_label") }}
        </p>
        <div class="space-y-1.5 text-xs text-gray-700">
          <label class="flex items-start gap-2">
            <input
              type="radio"
              class="mt-0.5 text-indigo-600"
              value="end-of-text"
              :checked="publicNoteMode === 'end-of-text'"
              :disabled="savingNoteMode"
              @change="setPublicNoteMode('end-of-text')"
            />
            <span>
              <span class="font-medium">{{ t("settings.public_doc_note_mode_end_of_text") }}</span>
              <br />
              <span class="text-gray-400">{{ t("settings.public_doc_note_mode_end_of_text_hint") }}</span>
            </span>
          </label>
          <label class="flex items-start gap-2">
            <input
              type="radio"
              class="mt-0.5 text-indigo-600"
              value="tooltip"
              :checked="publicNoteMode === 'tooltip'"
              :disabled="savingNoteMode"
              @change="setPublicNoteMode('tooltip')"
            />
            <span>
              <span class="font-medium">{{ t("settings.public_doc_note_mode_tooltip") }}</span>
              <br />
              <span class="text-gray-400">{{ t("settings.public_doc_note_mode_tooltip_hint") }}</span>
            </span>
          </label>
          <label class="flex items-start gap-2">
            <input
              type="radio"
              class="mt-0.5 text-indigo-600"
              value="frame"
              :checked="publicNoteMode === 'frame'"
              :disabled="savingNoteMode"
              @change="setPublicNoteMode('frame')"
            />
            <span>
              <span class="font-medium">{{ t("settings.public_doc_note_mode_frame") }}</span>
              <br />
              <span class="text-gray-400">{{ t("settings.public_doc_note_mode_frame_hint") }}</span>
            </span>
          </label>
        </div>

        <div class="mt-5 border-t border-gray-100 pt-4">
          <div class="flex items-start justify-between">
            <div class="mr-4">
              <p class="text-sm font-medium text-gray-800">
                {{ t("settings.public_doc_entity_hover_label") }}
              </p>
              <p class="mt-0.5 text-xs text-gray-500">
                {{ t("settings.public_doc_entity_hover_hint") }}
              </p>
            </div>
            <button
              :disabled="togglingHomeSetting['public_pages_entity_hover_enabled']"
              class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
              :class="publicEntityHoverEnabled ? 'bg-indigo-600' : 'bg-gray-200'"
              @click="toggleHomeSetting('public_pages_entity_hover_enabled', publicEntityHoverEnabled)"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="publicEntityHoverEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
          <p v-if="publicEntityHoverEnabled" class="mt-2 text-xs text-amber-700">
            {{ t("settings.public_doc_entity_hover_privacy") }}
          </p>
        </div>

        <div class="mt-5 border-t border-gray-100 pt-4">
          <div class="flex items-start justify-between">
            <div class="mr-4">
              <p class="text-sm font-medium text-gray-800">
                {{ t("settings.public_doc_frame_enabled_label") }}
              </p>
              <p class="mt-0.5 text-xs text-gray-500">
                {{ t("settings.public_doc_frame_enabled_hint") }}
              </p>
            </div>
            <button
              :disabled="togglingHomeSetting['public_pages_doc_frame_enabled']"
              class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40"
              :class="publicDocFrameEnabled ? 'bg-indigo-600' : 'bg-gray-200'"
              @click="toggleHomeSetting('public_pages_doc_frame_enabled', publicDocFrameEnabled)"
            >
              <span
                class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                :class="publicDocFrameEnabled ? 'translate-x-5' : 'translate-x-0'"
              />
            </button>
          </div>
        </div>
      </div>
    </template>

  </div>
</template>
