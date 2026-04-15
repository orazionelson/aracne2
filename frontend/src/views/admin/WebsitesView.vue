<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick, type ComponentPublicInstance } from "vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useWebsiteStore, type Website, type WebsitePage, type WebsiteIndex, type WebsiteIndexCreate, type WebsiteIndexUpdate, type WebsiteCreate, type WebsitePageCreate, type WebsitePageUpdate, type MetaSuggestions, type AracnePageConfig, type XsltConfig, type ImageRenderingConfig, type NoteRenderingConfig } from "@/stores/websites";
import { useXsltTemplateStore } from "@/stores/xslt_templates";
import { useCollectionStore } from "@/stores/collections";
import WysiwygEditor from "@/components/ui/WysiwygEditor.vue";
import { useCodeMirror } from "@/composables/useCodeMirror";

const { t } = useI18n();
const authStore = useAuthStore();
const store = useWebsiteStore();
const collectionStore = useCollectionStore();
const xsltStore = useXsltTemplateStore();

// ── State ────────────────────────────────────────────────────────────────────

const editingSlug = ref<string | null>(null);
const editTab = ref<"general" | "theme" | "pages" | "document" | "indices" | "cssjs">("general");
const showMetaPanel = ref(true);

// ── Filter state ─────────────────────────────────────────────────────────────
const filterName = ref("");
const filterType = ref<"" | "STATIC" | "DYNAMIC" | "HYBRID">("");
const filterStatus = ref<"" | "published" | "unpublished" | "built" | "failed">("");

const REPEATABLE_META_FIELDS = new Set(["subject", "author", "designer", "dc_creator", "dc_publisher", "dc_contributor", "dc_subject"]);

const DEFAULT_META_CONFIG: Record<string, string | string[]> = {
  keywords: "", description: "", subject: [] as string[], copyright: "",
  author: [] as string[], designer: [] as string[], url: "",
  dc_title: "", dc_creator: [] as string[], dc_subject: [] as string[], dc_description: "",
  dc_publisher: [] as string[], dc_contributor: [] as string[], dc_date: "", dc_type: "",
  dc_format: "", dc_identifier: "",
};
const confirmDeleteSlug = ref<string | null>(null);
const buildingSlug = ref<string | null>(null);
const buildPollInterval = ref<ReturnType<typeof setInterval> | null>(null);
const clearingCacheSlug = ref<string | null>(null);

// Create website form
const showCreate = ref(false);
const isCreating = ref(false);
const createError = ref<string | null>(null);
const newWebsite = ref<WebsiteCreate>({
  slug: "",
  title: "",
  description: null,
  collection_id: null,
  rendering_mode: "STATIC",
  is_published: false,
  show_in_public_home: false,
  theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "", font_family: 'Georgia,"Times New Roman",serif', footer_bg: "#ffffff", footer_text: "#9ca3af", hide_header: false, fixed_header: false },
});

// Edit website form
const editForm = ref<Partial<Website>>({});
const isEditing = ref(false);
const editError = ref<string | null>(null);

// Page form
const showPageForm = ref<string | null>(null); // website slug for which page form is open
const editingPage = ref<string | null>(null); // page slug being edited
const newPage = ref<WebsitePageCreate>({ slug: "", title: "", content_md: "", sort_order: 0, is_hidden: false });
const pageEditForm = ref<WebsitePageUpdate>({});
const isSubmittingPage = ref(false);
const pageError = ref<string | null>(null);

// Unified pages list (system + free, merged and sorted for the Pages tab)
interface UnifiedPageEntry {
  kind: "system" | "free";
  systemId?: "home" | "browse" | "search" | "indices";
  page?: WebsitePage;
  title: string;
  is_hidden: boolean;
  sort_order: number;
}
const unifiedPages = ref<UnifiedPageEntry[]>([]);
const isSavingPages = ref(false);
const pagesError = ref<string | null>(null);

// Document tab — XSLT upload state
const xsltFileName = ref<string>("");
/** Reset the hidden file input programmatically (avoids reactive-ref issues with native DOM). */
function resetXsltFileInput(): void {
  const el = document.getElementById("xslt-file-input") as HTMLInputElement | null;
  if (el) el.value = "";
}

// Document tab — CodeMirror editor for custom XSLT source
const xsltEditorContainer = ref<HTMLElement | null>(null);
const xsltEditorInitialContent = ref<string>("");
const showXsltModal = ref<boolean>(false);

function openXsltModal(): void {
  showXsltModal.value = true;
  nextTick(() => xsltCm.refresh());
}

function closeXsltModal(): void {
  showXsltModal.value = false;
}

/**
 * Callback ref for the CM5 container div. Vue does not reliably update a
 * plain Ref<HTMLElement> when the element lives inside a v-for + nested
 * v-if/v-show chain. A named callback ref is called directly by Vue at
 * mount/unmount time, bypassing the v-for ref-collection behaviour.
 */
function onXsltEditorRef(el: Element | ComponentPublicInstance | null): void {
  xsltEditorContainer.value = el instanceof HTMLElement ? el : null;
}

const xsltCm = useCodeMirror(xsltEditorContainer, {
  get initialValue() { return xsltEditorInitialContent.value; },
  onChange: (value: string) => {
    if (editForm.value.xslt_config) {
      (editForm.value.xslt_config as XsltConfig).content = value || null;
    }
  },
});

// Document tab — preview state
const previewDocFilename = ref<string>("");
const isPreviewing = ref<boolean>(false);
const previewError = ref<string | null>(null);
const previewBlobUrl = ref<string | null>(null);

function onXsltFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  xsltFileName.value = file.name;
  const reader = new FileReader();
  reader.onload = (e) => {
    const content = e.target?.result as string;
    if (editForm.value.xslt_config) {
      (editForm.value.xslt_config as XsltConfig).content = content;
      // Keep initialValue in sync so initializeEditor (deferred via rAF)
      // picks up the uploaded content even if it runs after this callback.
      xsltEditorInitialContent.value = content;
      xsltCm.setValue(content);
    }
  };
  reader.readAsText(file);
}

function clearXsltFile(): void {
  xsltFileName.value = "";
  resetXsltFileInput();
  if (editForm.value.xslt_config) {
    (editForm.value.xslt_config as XsltConfig).content = null;
    xsltCm.setValue("");
  }
}

async function previewDocument(websiteSlug: string): Promise<void> {
  if (!previewDocFilename.value) return;
  isPreviewing.value = true;
  previewError.value = null;
  try {
    const xsltConfig = editForm.value.xslt_config as XsltConfig | undefined;
    const html = await store.previewDocument(websiteSlug, previewDocFilename.value, xsltConfig);
    if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value);
    previewBlobUrl.value = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  } catch (err: unknown) {
    previewError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isPreviewing.value = false;
  }
}

// ── Indices tab ───────────────────────────────────────────────────────────────

const isRefreshingTags = ref(false);
const indexError = ref<string | null>(null);
const isRebuildingAll = ref(false);
const rebuildingIndexId = ref<string | null>(null);
const showIndexForm = ref(false);   // true = "add new index" form open
const editingIndexId = ref<string | null>(null);  // non-null = editing existing
const indexForm = ref<WebsiteIndexCreate>({ label: "", title: "", tag: "", key_attribute: null, subkey_attribute: null });
const isDeletingIndexId = ref<string | null>(null);

// Combobox state for the tag field in the index form
const indexTagQuery = ref<string>("");
const showTagDropdown = ref(false);
const filteredTags = computed<string[]>(() => {
  const q = indexTagQuery.value.toLowerCase().replace(/^<|>$/g, "");
  if (!q) return availableTags.value;
  return availableTags.value.filter((t) => t.toLowerCase().includes(q));
});

function selectTag(tag: string): void {
  indexForm.value.tag = tag;
  indexTagQuery.value = tag;
  showTagDropdown.value = false;
  indexForm.value.key_attribute = null;
  indexForm.value.subkey_attribute = null;
}

function onTagInput(): void {
  indexForm.value.tag = indexTagQuery.value;
  indexForm.value.key_attribute = null;
  indexForm.value.subkey_attribute = null;
  showTagDropdown.value = true;
}

function onTagBlur(): void {
  // Delay so a mousedown on a dropdown item fires before the dropdown closes.
  setTimeout(() => { showTagDropdown.value = false; }, 150);
}

/** The website currently open in the edit modal. */
const editingWebsite = computed<Website | null>(() =>
  store.websites.find((w) => w.slug === editingSlug.value) ?? null
);

/** Websites filtered by the toolbar controls. */
const filteredWebsites = computed(() =>
  store.websites.filter((w) => {
    if (filterName.value) {
      const q = filterName.value.toLowerCase();
      if (!w.title.toLowerCase().includes(q) && !w.slug.toLowerCase().includes(q)) return false;
    }
    if (filterType.value && w.rendering_mode !== filterType.value) return false;
    if (filterStatus.value) {
      if (filterStatus.value === "published" && !w.is_published) return false;
      if (filterStatus.value === "unpublished" && w.is_published) return false;
      if (filterStatus.value === "built" && w.build_status !== "done") return false;
      if (filterStatus.value === "failed" && w.build_status !== "failed") return false;
    }
    return true;
  })
);

/** Tags available in the current website's collection (from distinct_tags cache). */
const availableTags = computed<string[]>(() => {
  if (!editingWebsite.value?.distinct_tags) return [];
  return Object.keys(editingWebsite.value.distinct_tags).sort();
});

/** Attributes available for the currently selected tag in the index form. */
const availableAttrsForTag = computed<string[]>(() => {
  if (!editingWebsite.value?.distinct_tags || !indexForm.value.tag) return [];
  return (editingWebsite.value.distinct_tags[indexForm.value.tag] ?? []).sort();
});

function openAddIndexForm(): void {
  editingIndexId.value = null;
  indexForm.value = { label: "", title: "", tag: "", key_attribute: null, subkey_attribute: null };
  indexTagQuery.value = "";
  showIndexForm.value = true;
  indexError.value = null;
}

function openEditIndexForm(idx: WebsiteIndex): void {
  editingIndexId.value = idx.id;
  indexForm.value = {
    label: idx.label,
    title: idx.title,
    tag: idx.tag,
    key_attribute: idx.key_attribute,
    subkey_attribute: idx.subkey_attribute,
  };
  indexTagQuery.value = idx.tag;
  showIndexForm.value = true;
  indexError.value = null;
}

function cancelIndexForm(): void {
  showIndexForm.value = false;
  editingIndexId.value = null;
  indexError.value = null;
}

async function saveIndexForm(websiteSlug: string): Promise<void> {
  indexError.value = null;
  try {
    if (editingIndexId.value) {
      const upd: WebsiteIndexUpdate = {
        label: indexForm.value.label,
        title: indexForm.value.title,
        tag: indexForm.value.tag,
        key_attribute: indexForm.value.key_attribute,
        subkey_attribute: indexForm.value.subkey_attribute,
      };
      await store.updateIndex(websiteSlug, editingIndexId.value, upd);
    } else {
      await store.createIndex(websiteSlug, indexForm.value);
    }
    showIndexForm.value = false;
    editingIndexId.value = null;
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  }
}

async function deleteIndex(websiteSlug: string, indexId: string): Promise<void> {
  if (isDeletingIndexId.value === indexId) {
    // Second click confirms deletion.
    try {
      await store.deleteIndex(websiteSlug, indexId);
    } catch (err: unknown) {
      indexError.value = err instanceof Error ? err.message : t("common.error");
    } finally {
      isDeletingIndexId.value = null;
    }
  } else {
    isDeletingIndexId.value = indexId;
  }
}

async function rebuildIndex(websiteSlug: string, indexId: string): Promise<void> {
  rebuildingIndexId.value = indexId;
  indexError.value = null;
  try {
    await store.rebuildIndex(websiteSlug, indexId);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    rebuildingIndexId.value = null;
  }
}

async function rebuildAllIndices(websiteSlug: string): Promise<void> {
  isRebuildingAll.value = true;
  indexError.value = null;
  try {
    await store.rebuildAllIndices(websiteSlug);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isRebuildingAll.value = false;
  }
}

async function refreshTags(websiteSlug: string): Promise<void> {
  isRefreshingTags.value = true;
  indexError.value = null;
  try {
    await store.refreshTags(websiteSlug);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isRefreshingTags.value = false;
  }
}

// ── Computed ─────────────────────────────────────────────────────────────────

const publishedCollections = computed(() =>
  collectionStore.collections.filter((c) => c.status === "published"),
);

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([
    store.fetchWebsites(),
    collectionStore.fetchCollections(),
    xsltStore.fetchTemplates().catch(() => { /* non-blocking for non-Designer roles */ }),
  ]);
});

// When the user opens the Document tab, fetch the linked collection's document
// list so the preview selector is populated.
watch(editTab, async (tab) => {
  if (tab !== "document") return;
  const site = store.websites.find((w) => w.slug === editingSlug.value);
  if (site?.collection_id) {
    collectionStore.fetchDocuments(site.collection_id).catch(() => {});
  }
});

// ── Website CRUD ──────────────────────────────────────────────────────────────

/** Ensure repeatable fields are always arrays after loading from the API. */
function normaliseMeta(cfg: Record<string, string | string[]>): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = { ...cfg };
  for (const key of REPEATABLE_META_FIELDS) {
    const val = out[key];
    if (val === undefined || val === null) {
      out[key] = [];
    } else if (typeof val === "string") {
      out[key] = val === "" ? [] : [val];
    }
  }
  return out;
}

function getMetaArray(field: string): string[] {
  const cfg = editForm.value.meta_config as Record<string, string | string[]>;
  const val = cfg[field];
  if (Array.isArray(val)) return val;
  return val ? [val as string] : [];
}

function addMetaArrayItem(field: string): void {
  const cfg = editForm.value.meta_config as Record<string, string | string[]>;
  cfg[field] = [...getMetaArray(field), ""];
}

function removeMetaArrayItem(field: string, idx: number): void {
  const cfg = editForm.value.meta_config as Record<string, string | string[]>;
  cfg[field] = getMetaArray(field).filter((_, i) => i !== idx);
}

function updateMetaArrayItem(field: string, idx: number, value: string): void {
  const cfg = editForm.value.meta_config as Record<string, string | string[]>;
  const arr = [...getMetaArray(field)];
  arr[idx] = value;
  cfg[field] = arr;
}

// ── Unified pages list (system + free) ───────────────────────────────────────

const _DEFAULT_ARACNE_PAGES: AracnePageConfig[] = [
  { id: "home",    sort_order: 0, is_hidden: false },
  { id: "browse",  sort_order: 1, is_hidden: false },
  { id: "search",  sort_order: 2, is_hidden: false },
  { id: "indices", sort_order: 3, is_hidden: false },
];

function normaliseNavConfig(raw: AracnePageConfig[]): AracnePageConfig[] {
  return _DEFAULT_ARACNE_PAGES.map((def) => {
    const saved = raw.find((p) => p.id === def.id);
    return saved ? { ...def, ...saved } : { ...def };
  });
}

/** Build a single sorted list merging system pages (from nav_config) and free pages. */
function buildUnifiedList(website: Website): UnifiedPageEntry[] {
  const navCfg = normaliseNavConfig((website.nav_config ?? []) as AracnePageConfig[]);
  const _labels: Record<string, string> = { home: "Home", browse: "Browse", search: "Search", indices: t("websites.page_indices") };
  const system: UnifiedPageEntry[] = navCfg.map((ap) => ({
    kind: "system",
    systemId: ap.id,
    title: _labels[ap.id] ?? ap.id,
    is_hidden: ap.is_hidden,
    sort_order: ap.sort_order,
  }));
  const free: UnifiedPageEntry[] = website.pages.map((page) => ({
    kind: "free",
    page,
    title: page.title,
    is_hidden: page.is_hidden,
    sort_order: page.sort_order,
  }));
  return [...system, ...free].sort((a, b) => a.sort_order - b.sort_order);
}

function rebuildUnifiedList(websiteSlug: string): void {
  const site = store.websites.find((w) => w.slug === websiteSlug);
  if (site) unifiedPages.value = buildUnifiedList(site);
}

function moveUnifiedPage(fromIdx: number, toIdx: number): void {
  if (toIdx < 0 || toIdx >= unifiedPages.value.length) return;
  const arr = [...unifiedPages.value];
  [arr[fromIdx], arr[toIdx]] = [arr[toIdx], arr[fromIdx]];
  unifiedPages.value = arr;
}

function toggleUnifiedPageHidden(idx: number): void {
  const entry = unifiedPages.value[idx];
  if (entry) entry.is_hidden = !entry.is_hidden;
}

async function savePages(websiteSlug: string): Promise<void> {
  isSavingPages.value = true;
  pagesError.value = null;
  try {
    const newNavConfig: AracnePageConfig[] = [];
    const pageUpdates: Array<{ slug: string; sort_order: number; is_hidden: boolean }> = [];

    unifiedPages.value.forEach((entry, idx) => {
      if (entry.kind === "system") {
        newNavConfig.push({ id: entry.systemId!, sort_order: idx, is_hidden: entry.is_hidden });
      } else if (entry.kind === "free" && entry.page) {
        pageUpdates.push({ slug: entry.page.slug, sort_order: idx, is_hidden: entry.is_hidden });
      }
    });

    await store.updateWebsite(websiteSlug, { nav_config: newNavConfig });
    await Promise.all(
      pageUpdates.map(({ slug, sort_order, is_hidden }) =>
        store.updatePage(websiteSlug, slug, { sort_order, is_hidden }),
      ),
    );
    rebuildUnifiedList(websiteSlug);
  } catch (err: unknown) {
    pagesError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSavingPages.value = false;
  }
}

async function startEdit(website: Website): Promise<void> {
  editingSlug.value = website.slug;
  editTab.value = "general";
  showMetaPanel.value = true;
  editForm.value = {
    title: website.title,
    description: website.description,
    collection_id: website.collection_id,
    rendering_mode: website.rendering_mode,
    website_url: website.website_url,
    is_published: website.is_published,
    show_in_public_home: website.show_in_public_home,
    theme_config: {
      font_family: 'Georgia,"Times New Roman",serif',
      footer_bg: "#ffffff",
      footer_text: "#9ca3af",
      hide_header: false,
      fixed_header: false,
      ...website.theme_config,
    },
    xslt_config: (() => {
      const ex = (website.xslt_config ?? {}) as Partial<XsltConfig>;
      const exIR = ex.image_rendering;
      const ir: ImageRenderingConfig = {
        enabled: exIR?.enabled ?? false,
        figure: { size: exIR?.figure?.size ?? "full", layout: exIR?.figure?.layout ?? "inline" },
        pb: { show: exIR?.pb?.show ?? true, size: exIR?.pb?.size ?? "thumbnail", layout: exIR?.pb?.layout ?? "inline" },
        facsimile_gallery: exIR?.facsimile_gallery ?? false,
        column_connectors: exIR?.column_connectors ?? false,
      };
      const exNR = ex.note_rendering;
      const nr: NoteRenderingConfig = {
        enabled: exNR?.enabled ?? false,
        mode: exNR?.mode ?? "end-of-text",
      };
      const defaults: XsltConfig = { source: "default", content: null, url: null, catalog_id: null, processor: "lxml", image_rendering: ir, note_rendering: nr };
      return { ...defaults, ...ex, image_rendering: ir, note_rendering: nr };
    })(),
    meta_config: normaliseMeta({ ...DEFAULT_META_CONFIG, ...(website.meta_config ?? {}) }),
    custom_css: website.custom_css ?? "",
    custom_js: website.custom_js ?? "",
    include_jquery: website.include_jquery ?? false,
  };
  unifiedPages.value = buildUnifiedList(website);
  pagesError.value = null;
  editError.value = null;
  xsltFileName.value = "";
  resetXsltFileInput();
  xsltEditorInitialContent.value = (website.xslt_config as XsltConfig)?.content ?? "";
  // Reset preview state for the new website being edited.
  previewDocFilename.value = "";
  previewError.value = null;
  if (previewBlobUrl.value) { URL.revokeObjectURL(previewBlobUrl.value); previewBlobUrl.value = null; }

  // Asynchronously apply server-side suggestions to any fields still empty.
  // Fires after the form is already open so the user is not blocked.
  try {
    const s: MetaSuggestions = await store.fetchMetaSuggestions(website.slug);
    const m = editForm.value.meta_config as Record<string, string | string[]>;
    if ((m.author as string[]).length === 0 && s.author.length > 0) m.author = s.author;
    if ((m.dc_creator as string[]).length === 0 && s.dc_creator.length > 0) m.dc_creator = s.dc_creator;
    if ((m.designer as string[]).length === 0 && s.designer.length > 0) m.designer = s.designer;
    if (!(m.copyright as string) && s.copyright) m.copyright = s.copyright;
    if ((m.dc_publisher as string[]).length === 0 && s.dc_publisher.length > 0) m.dc_publisher = s.dc_publisher;
    if (!(m.dc_format as string) && s.dc_format) m.dc_format = s.dc_format;
    if (!(m.dc_identifier as string) && s.dc_identifier) m.dc_identifier = s.dc_identifier;
  } catch {
    // suggestions are best-effort — proceed without them if the request fails
  }
}

function cancelEdit(): void {
  editingSlug.value = null;
  editError.value = null;
  unifiedPages.value = [];
  if (previewBlobUrl.value) { URL.revokeObjectURL(previewBlobUrl.value); previewBlobUrl.value = null; }
  previewDocFilename.value = "";
  previewError.value = null;
}

async function saveEdit(slug: string): Promise<void> {
  isEditing.value = true;
  editError.value = null;
  try {
    await store.updateWebsite(slug, {
      title: editForm.value.title,
      description: editForm.value.description,
      collection_id: editForm.value.collection_id ?? null,
      rendering_mode: editForm.value.rendering_mode,
      website_url: (editForm.value.website_url as string) || null,
      is_published: editForm.value.is_published,
      show_in_public_home: editForm.value.show_in_public_home as boolean,
      theme_config: editForm.value.theme_config as Record<string, string>,
      meta_config: editForm.value.meta_config as Record<string, string | string[]>,
      nav_config: editForm.value.nav_config as AracnePageConfig[],
      xslt_config: editForm.value.xslt_config as XsltConfig,
      custom_css: (editForm.value.custom_css as string) || null,
      custom_js: (editForm.value.custom_js as string) || null,
      include_jquery: editForm.value.include_jquery as boolean,
    });
    editingSlug.value = null;
  } catch (err: unknown) {
    editError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isEditing.value = false;
  }
}

async function createWebsite(): Promise<void> {
  isCreating.value = true;
  createError.value = null;
  try {
    await store.createWebsite({ ...newWebsite.value });
    showCreate.value = false;
    newWebsite.value = {
      slug: "",
      title: "",
      description: null,
      collection_id: null,
      rendering_mode: "STATIC",
      is_published: false,
      show_in_public_home: false,
      theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "", font_family: 'Georgia,"Times New Roman",serif', footer_bg: "#ffffff", footer_text: "#9ca3af", hide_header: false, fixed_header: false },
    };
  } catch (err: unknown) {
    createError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isCreating.value = false;
  }
}

async function deleteWebsite(slug: string): Promise<void> {
  try {
    await store.deleteWebsite(slug);
    confirmDeleteSlug.value = null;
  } catch {
    // handled by store
  }
}

// ── Build / Cache ──────────────────────────────────────────────────────────────

async function clearSiteCache(slug: string): Promise<void> {
  clearingCacheSlug.value = slug;
  try {
    await store.clearCache(slug);
  } finally {
    clearingCacheSlug.value = null;
  }
}

async function downloadSite(slug: string): Promise<void> {
  await store.downloadSite(slug);
}

async function triggerBuild(slug: string): Promise<void> {
  buildingSlug.value = slug;
  try {
    await store.triggerBuild(slug);
    // Poll until the build finishes or fails.
    if (buildPollInterval.value) clearInterval(buildPollInterval.value);
    buildPollInterval.value = setInterval(async () => {
      const status = await store.pollBuildStatus(slug);
      if (status === "done" || status === "failed") {
        clearInterval(buildPollInterval.value!);
        buildPollInterval.value = null;
        buildingSlug.value = null;
      }
    }, 2000);
  } catch {
    buildingSlug.value = null;
  }
}

function buildStatusClass(status: string): string {
  const map: Record<string, string> = {
    idle: "text-gray-500",
    pending: "text-amber-500",
    building: "text-blue-500",
    done: "text-green-600",
    failed: "text-red-600",
  };
  return map[status] ?? "text-gray-500";
}

function siteUrl(slug: string, isPublished: boolean): string {
  const base = `/api/v1/sites/${slug}/`;
  if (isPublished) return base;
  // Unpublished: pass the access token as ?_preview= so the browser tab / iframe
  // (which cannot send an Authorization header) is accepted by the backend.
  const token = authStore.accessToken;
  return token ? `${base}?_preview=${encodeURIComponent(token)}` : base;
}

// ── Site preview modal (unpublished sites) ────────────────────────────────────

const showPreviewModal = ref(false);
const previewModalUrl = ref("");

function openSitePreview(slug: string, isPublished: boolean): void {
  const url = siteUrl(slug, isPublished);
  if (isPublished) {
    window.open(url, "_blank", "noopener");
    return;
  }
  previewModalUrl.value = url;
  showPreviewModal.value = true;
}

function closePreviewModal(): void {
  showPreviewModal.value = false;
  previewModalUrl.value = "";
}

// ── Pages ─────────────────────────────────────────────────────────────────────

function openPageForm(websiteSlug: string): void {
  showPageForm.value = websiteSlug;
  // New page gets a global sort_order at the end of the current unified list.
  newPage.value = { slug: "", title: "", content_md: "", sort_order: unifiedPages.value.length, is_hidden: false };
  pageError.value = null;
}

function startEditPage(websiteSlug: string, page: WebsitePage): void {
  editingPage.value = page.slug;
  showPageForm.value = websiteSlug;
  pageEditForm.value = { title: page.title, content_md: page.content_md ?? "", sort_order: page.sort_order, is_hidden: page.is_hidden };
  pageError.value = null;
}

function onWidgetDragStart(event: DragEvent, widgetType: string): void {
  if (!event.dataTransfer) return;
  event.dataTransfer.setData("widget-type", widgetType);
  event.dataTransfer.effectAllowed = "copy";
}

function cancelPageForm(): void {
  showPageForm.value = null;
  editingPage.value = null;
  pageError.value = null;
}

async function submitPage(websiteSlug: string): Promise<void> {
  isSubmittingPage.value = true;
  pageError.value = null;
  try {
    if (editingPage.value) {
      await store.updatePage(websiteSlug, editingPage.value, pageEditForm.value);
    } else {
      await store.createPage(websiteSlug, { ...newPage.value });
    }
    cancelPageForm();
    rebuildUnifiedList(websiteSlug);
  } catch (err: unknown) {
    pageError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSubmittingPage.value = false;
  }
}

async function deletePage(websiteSlug: string, pageSlug: string): Promise<void> {
  if (!confirm(t("websites.confirm_delete_page"))) return;
  await store.deletePage(websiteSlug, pageSlug);
  rebuildUnifiedList(websiteSlug);
}
</script>

<template>
  <div class="mx-auto max-w-screen-xl px-6 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ t("websites.title") }}</h1>
        <p class="mt-1 text-sm text-gray-500">{{ t("websites.subtitle") }}</p>
      </div>
      <button
        class="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="showCreate = !showCreate"
      >
        {{ t("websites.create") }}
      </button>
    </div>

    <!-- Create form -->
    <div v-if="showCreate" class="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 p-5">
      <h2 class="mb-4 text-sm font-semibold text-indigo-800">{{ t("websites.create_title") }}</h2>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_slug") }}</label>
          <input
            v-model="newWebsite.slug"
            type="text"
            class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            :placeholder="t('websites.field_slug_hint')"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_title") }}</label>
          <input
            v-model="newWebsite.title"
            type="text"
            class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div class="sm:col-span-2">
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_description") }}</label>
          <input
            v-model="newWebsite.description"
            type="text"
            class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_collection") }}</label>
          <select
            v-model="newWebsite.collection_id"
            class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option :value="null">{{ t("websites.no_collection") }}</option>
            <option v-for="col in publishedCollections" :key="col.id" :value="col.id">
              {{ col.title }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_rendering_mode") }}</label>
          <select
            v-model="newWebsite.rendering_mode"
            class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="STATIC">{{ t("websites.mode_static") }}</option>
            <option value="DYNAMIC">{{ t("websites.mode_dynamic") }}</option>
            <option value="HYBRID">{{ t("websites.mode_hybrid") }}</option>
          </select>
        </div>
        <!-- Theme colours -->
        <div class="sm:col-span-2">
          <p class="mb-2 text-xs font-medium text-gray-700">{{ t("websites.field_theme") }}</p>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_primary") }}
              <input v-model="newWebsite.theme_config!.primary_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_text") }}
              <input v-model="newWebsite.theme_config!.text_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_bg") }}
              <input v-model="newWebsite.theme_config!.bg_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_doc_banner_bg") }}
              <input v-model="(newWebsite.theme_config as Record<string, string>).doc_banner_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_doc_banner_text") }}
              <input v-model="(newWebsite.theme_config as Record<string, string>).doc_banner_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
          </div>
          <div class="mt-2">
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.theme_logo") }}</label>
            <input v-model="newWebsite.theme_config!.logo_url" type="text" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.theme_logo_hint')" />
          </div>
        </div>

        <!-- Home page layout + column content -->
        <div class="sm:col-span-2 border-t border-indigo-100 pt-4">
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.home_content_title") }}</p>
          <div class="mb-3">
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.home_layout") }}</label>
            <select v-model="newWebsite.theme_config!.home_layout" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
              <option value="single">{{ t("websites.layout_single") }}</option>
              <option value="two_left">{{ t("websites.layout_two_left") }}</option>
              <option value="two_right">{{ t("websites.layout_two_right") }}</option>
              <option value="three">{{ t("websites.layout_three") }}</option>
            </select>
          </div>
          <div class="grid gap-3" :class="newWebsite.theme_config!.home_layout === 'single' ? 'grid-cols-1' : newWebsite.theme_config!.home_layout === 'three' ? 'grid-cols-3' : 'grid-cols-2'">
            <div v-if="newWebsite.theme_config!.home_layout === 'two_left' || newWebsite.theme_config!.home_layout === 'three'">
              <label class="mb-1 block text-xs font-medium text-gray-700">{{ t("websites.col_left") }}</label>
              <WysiwygEditor v-model="newWebsite.theme_config!.col_left" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-700">{{ t("websites.col_center") }}</label>
              <WysiwygEditor v-model="newWebsite.theme_config!.col_center" />
            </div>
            <div v-if="newWebsite.theme_config!.home_layout === 'two_right' || newWebsite.theme_config!.home_layout === 'three'">
              <label class="mb-1 block text-xs font-medium text-gray-700">{{ t("websites.col_right") }}</label>
              <WysiwygEditor v-model="newWebsite.theme_config!.col_right" />
            </div>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <div class="flex items-center gap-2">
            <input id="create-published" v-model="newWebsite.is_published" type="checkbox" class="rounded border-gray-300" />
            <label for="create-published" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
          </div>
          <div class="flex items-center gap-2">
            <input id="create-sph" v-model="newWebsite.show_in_public_home" type="checkbox" class="rounded border-gray-300" />
            <label for="create-sph" class="text-xs text-gray-700">{{ t("websites.field_show_in_public_home") }}</label>
          </div>
        </div>
      </div>
      <p v-if="createError" class="mt-3 text-xs text-red-600">{{ createError }}</p>
      <div class="mt-4 flex gap-2">
        <button
          :disabled="isCreating || !newWebsite.slug || !newWebsite.title"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="createWebsite"
        >
          {{ isCreating ? t("common.loading") : t("websites.create_submit") }}
        </button>
        <button
          class="rounded px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
          @click="showCreate = false"
        >
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>

    <!-- Filter toolbar -->
    <div v-if="!store.isLoading && store.websites.length > 0" class="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
      <input
        v-model="filterName"
        type="search"
        :placeholder="t('websites.filter_placeholder')"
        class="flex-1 min-w-36 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
      />
      <select v-model="filterType" class="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-400 focus:outline-none">
        <option value="">{{ t("websites.filter_type_all") }}</option>
        <option value="STATIC">{{ t("websites.mode_static") }}</option>
        <option value="DYNAMIC">{{ t("websites.mode_dynamic") }}</option>
        <option value="HYBRID">{{ t("websites.mode_hybrid") }}</option>
      </select>
      <select v-model="filterStatus" class="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-400 focus:outline-none">
        <option value="">{{ t("websites.filter_status_all") }}</option>
        <option value="published">{{ t("websites.published") }}</option>
        <option value="unpublished">{{ t("websites.filter_unpublished") }}</option>
        <option value="built">{{ t("websites.build_done") }}</option>
        <option value="failed">{{ t("websites.build_failed") }}</option>
      </select>
      <span class="text-xs text-gray-400">{{ filteredWebsites.length }} / {{ store.websites.length }}</span>
    </div>

    <!-- Loading / empty -->
    <div v-if="store.isLoading" class="py-12 text-center text-sm text-gray-500">
      {{ t("common.loading") }}
    </div>
    <div v-else-if="store.websites.length === 0" class="py-12 text-center text-sm text-gray-500">
      {{ t("websites.empty") }}
    </div>
    <div v-else-if="filteredWebsites.length === 0" class="py-12 text-center text-sm text-gray-500">
      {{ t("websites.filter_no_results") }}
    </div>

    <!-- Websites list -->
    <div v-else class="space-y-2">
      <div
        v-for="website in filteredWebsites"
        :key="website.slug"
        class="rounded-lg border border-gray-200 bg-white"
      >
        <!-- Website row header -->
        <div class="flex items-center gap-3 px-4 py-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900">{{ website.title }}</span>
              <span class="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-500">{{ website.slug }}</span>
              <span
                v-if="website.is_published"
                class="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700"
              >
                {{ t("websites.published") }}
              </span>
              <span class="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">
                {{ t(`websites.mode_${website.rendering_mode.toLowerCase()}`) }}
              </span>
            </div>
            <div class="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
              <span :class="buildStatusClass(website.build_status)">
                {{ t(`websites.build_${website.build_status}`) }}
              </span>
              <span v-if="website.last_build_at">
                · {{ new Date(website.last_build_at).toLocaleString() }}
              </span>
            </div>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-1.5" @click.stop>
            <!-- Build (STATIC and HYBRID only) -->
            <button
              v-if="website.rendering_mode === 'STATIC' || website.rendering_mode === 'HYBRID'"
              :disabled="buildingSlug === website.slug || website.build_status === 'building' || website.build_status === 'pending'"
              class="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
              @click="triggerBuild(website.slug)"
            >
              {{ buildingSlug === website.slug ? t("websites.building") : t("websites.build") }}
            </button>
            <!-- Clear cache (DYNAMIC and HYBRID) -->
            <button
              v-if="website.rendering_mode === 'DYNAMIC' || website.rendering_mode === 'HYBRID'"
              :disabled="clearingCacheSlug === website.slug"
              class="rounded bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-200 disabled:opacity-40"
              @click="clearSiteCache(website.slug)"
            >
              {{ clearingCacheSlug === website.slug ? t("websites.clearing_cache") : t("websites.clear_cache") }}
            </button>
            <!-- Open / Preview -->
            <template v-if="(website.rendering_mode === 'DYNAMIC') || (website.build_status === 'done' && (website.rendering_mode === 'STATIC' || website.rendering_mode === 'HYBRID'))">
              <a
                v-if="website.is_published"
                :href="siteUrl(website.slug, true)"
                target="_blank"
                rel="noopener"
                class="rounded bg-green-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-green-700"
              >{{ t("websites.open") }}</a>
              <button
                v-else
                class="rounded bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-200"
                @click="openSitePreview(website.slug, false)"
              >{{ t("websites.preview") }}</button>
            </template>
            <!-- Download ZIP (STATIC only, when built) -->
            <button
              v-if="website.rendering_mode === 'STATIC' && website.build_status === 'done'"
              class="rounded bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-800 hover:bg-sky-200"
              @click="downloadSite(website.slug)"
            >
              {{ t("websites.download_site") }}
            </button>
            <!-- Edit -->
            <button
              class="rounded bg-gray-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-gray-800"
              @click="startEdit(website)"
            >
              {{ t("common.edit") }}
            </button>
            <!-- Delete -->
            <button
              class="rounded bg-red-100 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-200"
              @click="confirmDeleteSlug = website.slug"
            >
              {{ t("common.delete") }}
            </button>
          </div>
        </div>

        <!-- Build error -->
        <div
          v-if="website.build_error && website.build_status === 'failed'"
          class="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700"
        >
          {{ website.build_error }}
        </div>

        <!-- (edit form moved to full-screen modal below) -->

        <!-- Delete confirmation -->
        <div
          v-if="confirmDeleteSlug === website.slug"
          class="border-t border-red-100 bg-red-50 px-4 py-3 text-sm"
        >
          <p class="text-red-700">{{ t("websites.confirm_delete") }}</p>
          <div class="mt-2 flex gap-2">
            <button
              class="rounded bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-700"
              @click="deleteWebsite(website.slug)"
            >
              {{ t("common.delete") }}
            </button>
            <button
              class="rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100"
              @click="confirmDeleteSlug = null"
            >
              {{ t("common.cancel") }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Site preview modal (unpublished sites only) ──────────────────────── -->
  <Teleport to="body">
    <div
      v-if="showPreviewModal"
      class="fixed inset-0 z-50 flex flex-col bg-black/80"
      @keydown.esc="closePreviewModal"
    >
      <!-- Toolbar -->
      <div class="flex items-center justify-between bg-gray-900 px-4 py-2 text-white">
        <span class="text-sm font-medium">{{ t("websites.preview_title") }}</span>
        <button
          class="rounded px-3 py-1 text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white"
          @click="closePreviewModal"
        >{{ t("websites.preview_close") }} ✕</button>
      </div>
      <!-- iframe -->
      <iframe
        v-if="previewModalUrl"
        :src="previewModalUrl"
        class="flex-1 w-full border-0 bg-white"
        :title="t('websites.preview_title')"
      />
    </div>
  </Teleport>
  <!-- ── Edit modal (full-screen) ─────────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="editingWebsite"
      class="fixed inset-0 z-40 flex flex-col bg-white"
      @keydown.esc="cancelEdit"
    >
      <!-- Modal header -->
      <div class="flex shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div class="min-w-0">
          <h2 class="truncate text-base font-semibold text-gray-900">{{ editingWebsite.title }}</h2>
          <p class="font-mono text-xs text-gray-400">{{ editingWebsite.slug }}</p>
        </div>
        <button
          class="ml-4 shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          @click="cancelEdit"
          :title="t('common.cancel')"
        >✕</button>
      </div>
      <!-- Tab bar -->
      <div class="flex shrink-0 overflow-x-auto border-b border-gray-200 bg-white px-4">
      <!-- Tab bar -->
      <div class="flex border-b border-gray-200 bg-white px-4">
        <button
          v-for="tab in (['general', 'theme', 'pages', 'document', 'indices', 'cssjs'] as const)"
          :key="tab"
          class="-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors"
          :class="editTab === tab
            ? 'border-indigo-600 text-indigo-700'
            : 'border-transparent text-gray-500 hover:text-gray-700'"
          @click="editTab = tab"
        >
          {{ t(`websites.tab_${tab}`) }}
        </button>
      </div>
      </div>
      <!-- Tab panels (scrollable) -->
      <div class="flex-1 overflow-y-auto">

      <!-- Tab: General -->
      <div v-if="editTab === 'general'" class="bg-indigo-50 p-4">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_title") }}</label>
            <input v-model="editForm.title" type="text" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_collection") }}</label>
            <select v-model="editForm.collection_id" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
              <option :value="null">{{ t("websites.no_collection") }}</option>
              <option v-for="col in publishedCollections" :key="col.id" :value="col.id">{{ col.title }}</option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_description") }}</label>
            <input v-model="editForm.description" type="text" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm" />
          </div>
          <div class="sm:col-span-2">
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_website_url") }}</label>
            <input
              v-model="editForm.website_url"
              type="url"
              :placeholder="t('websites.field_website_url_placeholder')"
              class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            />
            <p class="mt-0.5 text-xs text-gray-400">{{ t("websites.field_website_url_hint") }}</p>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_rendering_mode") }}</label>
            <select v-model="editForm.rendering_mode" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
              <option value="STATIC">{{ t("websites.mode_static") }}</option>
              <option value="DYNAMIC">{{ t("websites.mode_dynamic") }}</option>
              <option value="HYBRID">{{ t("websites.mode_hybrid") }}</option>
            </select>
          </div>
          <div class="flex flex-col gap-2 pt-5">
            <div class="flex items-center gap-2">
              <input :id="`edit-pub-${editingWebsite!.slug}`" v-model="editForm.is_published" type="checkbox" class="rounded border-gray-300" />
              <label :for="`edit-pub-${editingWebsite!.slug}`" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
            </div>
            <div class="flex items-center gap-2">
              <input :id="`edit-sph-${editingWebsite!.slug}`" v-model="editForm.show_in_public_home" type="checkbox" class="rounded border-gray-300" />
              <label :for="`edit-sph-${editingWebsite!.slug}`" class="text-xs text-gray-700">{{ t("websites.field_show_in_public_home") }}</label>
            </div>
            <p class="text-xs text-gray-400">{{ t("websites.field_show_in_public_home_hint") }}</p>
          </div>

          <!-- Metadata foldable panel -->
          <div class="sm:col-span-2">
            <button
              type="button"
              class="flex w-full items-center justify-between rounded border border-gray-300 bg-white px-3 py-2 text-left text-xs font-semibold text-gray-700 hover:bg-gray-50"
              :class="showMetaPanel ? 'rounded-b-none' : ''"
              @click="showMetaPanel = !showMetaPanel"
            >
              <span>{{ t("websites.meta_section") }}</span>
              <span class="text-gray-400">{{ showMetaPanel ? '▲' : '▼' }}</span>
            </button>
            <div v-show="showMetaPanel" class="rounded-b border border-t-0 border-gray-300 bg-white p-3 space-y-5">

              <!-- Standard HTML meta -->
              <div>
                <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{{ t("websites.meta_html_section") }}</p>
                <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div class="sm:col-span-2">
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_description") }}</label>
                    <textarea v-model="(editForm.meta_config as Record<string,string>).description" rows="2" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs resize-none" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_keywords") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).keywords" type="text" placeholder="keyword1, keyword2" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_subject") }}</label>
                    <div v-for="(_, idx) in getMetaArray('subject')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('subject')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('subject', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('subject', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('subject')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_author") }}</label>
                    <div v-for="(_, idx) in getMetaArray('author')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('author')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('author', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('author', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('author')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_copyright") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).copyright" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_designer") }}</label>
                    <div v-for="(_, idx) in getMetaArray('designer')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('designer')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('designer', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('designer', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('designer')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_url") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).url" type="url" placeholder="https://www.example.com" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                </div>
              </div>

              <!-- Dublin Core meta -->
              <div>
                <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Dublin Core</p>
                <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_title") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).dc_title" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_creator") }}</label>
                    <div v-for="(_, idx) in getMetaArray('dc_creator')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('dc_creator')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('dc_creator', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('dc_creator', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('dc_creator')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_publisher") }}</label>
                    <div v-for="(_, idx) in getMetaArray('dc_publisher')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('dc_publisher')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('dc_publisher', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('dc_publisher', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('dc_publisher')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_contributor") }}</label>
                    <div v-for="(_, idx) in getMetaArray('dc_contributor')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('dc_contributor')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('dc_contributor', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('dc_contributor', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('dc_contributor')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_subject") }}</label>
                    <div v-for="(_, idx) in getMetaArray('dc_subject')" :key="idx" class="mt-0.5 flex gap-1">
                      <input :value="getMetaArray('dc_subject')[idx]" type="text" class="w-full rounded border border-gray-300 px-2 py-1 text-xs" @input="updateMetaArrayItem('dc_subject', idx, ($event.target as HTMLInputElement).value)" />
                      <button type="button" class="px-1 text-xs text-red-500 hover:text-red-700" @click="removeMetaArrayItem('dc_subject', idx)">✕</button>
                    </div>
                    <button type="button" class="mt-1 text-xs text-indigo-600 hover:text-indigo-800" @click="addMetaArrayItem('dc_subject')">+ {{ t("websites.meta_add_item") }}</button>
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_date") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).dc_date" type="text" placeholder="YYYY-MM-DD" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div class="sm:col-span-2">
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_description") }}</label>
                    <textarea v-model="(editForm.meta_config as Record<string,string>).dc_description" rows="2" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs resize-none" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_type") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).dc_type" type="text" placeholder="e.g. Text, Dataset" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_format") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).dc_format" type="text" placeholder="e.g. text/html" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                  <div>
                    <label class="block text-xs text-gray-600">{{ t("websites.meta_dc_identifier") }}</label>
                    <input v-model="(editForm.meta_config as Record<string,string>).dc_identifier" type="text" placeholder="URI or URL" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Theme -->
      <div v-if="editTab === 'theme'" class="bg-indigo-50 p-4 space-y-5">
        <!-- Colours -->
        <div>
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.field_theme") }}</p>
          <div class="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_primary") }}
              <input v-model="(editForm.theme_config as Record<string, string>).primary_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_text") }}
              <input v-model="(editForm.theme_config as Record<string, string>).text_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_bg") }}
              <input v-model="(editForm.theme_config as Record<string, string>).bg_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_doc_banner_bg") }}
              <input v-model="(editForm.theme_config as Record<string, string>).doc_banner_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_doc_banner_text") }}
              <input v-model="(editForm.theme_config as Record<string, string>).doc_banner_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
          </div>
        </div>
        <!-- Font family -->
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.theme_font") }}</label>
          <select v-model="(editForm.theme_config as Record<string, string>).font_family" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option value='Georgia,"Times New Roman",serif'>Georgia (serif)</option>
            <option value='"Palatino Linotype",Palatino,serif'>Palatino (serif)</option>
            <option value='"Times New Roman",Times,serif'>Times New Roman (serif)</option>
            <option value='Arial,Helvetica,sans-serif'>Arial (sans-serif)</option>
            <option value='"Helvetica Neue",Helvetica,Arial,sans-serif'>Helvetica (sans-serif)</option>
            <option value='Verdana,Geneva,sans-serif'>Verdana (sans-serif)</option>
            <option value='"Trebuchet MS",Tahoma,Geneva,sans-serif'>Trebuchet MS (sans-serif)</option>
            <option value='system-ui,-apple-system,BlinkMacSystemFont,sans-serif'>System UI</option>
            <option value='"Courier New",Courier,monospace'>Courier New (monospace)</option>
          </select>
        </div>
        <!-- Footer -->
        <div>
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.theme_footer_section") }}</p>
          <div class="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_footer_bg") }}
              <input v-model="(editForm.theme_config as Record<string, string>).footer_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              {{ t("websites.theme_footer_text") }}
              <input v-model="(editForm.theme_config as Record<string, string>).footer_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
            </label>
          </div>
        </div>
        <!-- Header -->
        <div>
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.theme_header_section") }}</p>
          <label class="flex items-center gap-2 text-xs text-gray-600">
            <input type="checkbox" v-model="(editForm.theme_config as Record<string, unknown>).hide_header" class="rounded border-gray-300 text-indigo-600" />
            {{ t("websites.theme_hide_header") }}
          </label>
          <label class="mt-1.5 flex items-center gap-2 text-xs text-gray-600">
            <input type="checkbox" v-model="(editForm.theme_config as Record<string, unknown>).fixed_header" class="rounded border-gray-300 text-indigo-600" />
            {{ t("websites.theme_fixed_header") }}
          </label>
          <p class="mt-0.5 pl-5 text-xs text-gray-400">{{ t("websites.theme_fixed_header_hint") }}</p>
          <div class="mt-2">
            <label class="block text-xs text-gray-700">{{ t("websites.theme_logo") }}</label>
            <input v-model="(editForm.theme_config as Record<string, string>).logo_url" type="text" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.theme_logo_hint')" />
          </div>
        </div>
        <!-- Home layout -->
        <div>
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.home_content_title") }}</p>
          <div class="mb-3">
            <label class="block text-xs text-gray-700">{{ t("websites.home_layout") }}</label>
            <select v-model="(editForm.theme_config as Record<string, string>).home_layout" class="mt-1 w-64 rounded border border-gray-300 px-3 py-1.5 text-sm">
              <option value="single">{{ t("websites.layout_single") }}</option>
              <option value="two_left">{{ t("websites.layout_two_left") }}</option>
              <option value="two_right">{{ t("websites.layout_two_right") }}</option>
              <option value="three">{{ t("websites.layout_three") }}</option>
            </select>
          </div>
          <!-- Widget palette — drag chips into a column editor below -->
          <div class="mb-2 flex items-center gap-2">
            <span class="text-xs text-gray-400">{{ t("websites.theme_widgets") }}:</span>
            <div
              draggable="true"
              class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing"
              @dragstart="onWidgetDragStart($event, 'search-bar')"
            >
              &#128269; {{ t("websites.widget_search_bar") }}
            </div>
            <div
              draggable="true"
              class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing"
              @dragstart="onWidgetDragStart($event, 'page-menu')"
            >
              &#128196; {{ t("websites.widget_page_menu") }}
            </div>
            <div
              draggable="true"
              class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing"
              @dragstart="onWidgetDragStart($event, 'index-list')"
            >
              &#128203; {{ t("websites.widget_index_list") }}
            </div>
          </div>

          <div
            class="grid gap-3"
            :class="(editForm.theme_config as Record<string,string>).home_layout === 'single'
              ? 'grid-cols-1'
              : (editForm.theme_config as Record<string,string>).home_layout === 'three'
                ? 'grid-cols-3'
                : 'grid-cols-2'"
          >
            <div v-if="(editForm.theme_config as Record<string,string>).home_layout === 'two_left' || (editForm.theme_config as Record<string,string>).home_layout === 'three'">
              <label class="mb-1 block text-xs text-gray-700">{{ t("websites.col_left") }}</label>
              <WysiwygEditor v-model="(editForm.theme_config as Record<string, string>).col_left" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-gray-700">{{ t("websites.col_center") }}</label>
              <WysiwygEditor v-model="(editForm.theme_config as Record<string, string>).col_center" />
            </div>
            <div v-if="(editForm.theme_config as Record<string,string>).home_layout === 'two_right' || (editForm.theme_config as Record<string,string>).home_layout === 'three'">
              <label class="mb-1 block text-xs text-gray-700">{{ t("websites.col_right") }}</label>
              <WysiwygEditor v-model="(editForm.theme_config as Record<string, string>).col_right" />
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Pages — single unified ordered list -->
      <div v-if="editTab === 'pages'" class="bg-gray-50 p-4">
        <div class="mb-3 flex items-center justify-between">
          <p class="text-xs font-semibold text-gray-700">{{ t("websites.pages_title") }}</p>
          <button
            class="rounded px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-100"
            @click="openPageForm(editingWebsite!.slug)"
          >
            {{ t("websites.page_add") }}
          </button>
        </div>

        <!-- Unified list: system pages + free pages, sorted by global sort_order -->
        <ul class="mb-3 space-y-1">
          <li
            v-for="(entry, idx) in unifiedPages"
            :key="entry.kind + '-' + (entry.systemId ?? entry.page?.slug)"
            class="flex items-center justify-between rounded px-3 py-1.5 text-sm shadow-sm"
            :class="[
              entry.is_hidden ? 'opacity-60' : '',
              entry.kind === 'system' ? 'bg-indigo-50' : (entry.is_hidden ? 'bg-gray-100' : 'bg-white'),
            ]"
          >
            <div class="flex items-center gap-2">
              <!-- ▲▼ reorder -->
              <span class="flex flex-col">
                <button
                  class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20"
                  :disabled="idx === 0"
                  @click="moveUnifiedPage(idx, idx - 1)"
                >▲</button>
                <button
                  class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20"
                  :disabled="idx === unifiedPages.length - 1"
                  @click="moveUnifiedPage(idx, idx + 1)"
                >▼</button>
              </span>
              <!-- system badge -->
              <span v-if="entry.kind === 'system'" class="rounded bg-indigo-100 px-1 py-0.5 text-xs font-medium text-indigo-500">sys</span>
              <!-- title -->
              <span :class="entry.is_hidden ? 'text-gray-400 line-through' : 'font-medium text-gray-800'">
                {{ entry.title }}
              </span>
              <!-- slug (free pages only) -->
              <span v-if="entry.kind === 'free'" class="font-mono text-xs text-gray-400">{{ entry.page?.slug }}</span>
              <!-- hidden badge -->
              <span v-if="entry.is_hidden" class="rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-500">
                {{ t("websites.page_hidden") }}
              </span>
            </div>
            <div class="flex gap-1">
              <!-- Hide/Show: Browse, Search, free pages (not Home) -->
              <button
                v-if="entry.systemId !== 'home'"
                class="rounded px-1.5 py-0.5 text-xs hover:bg-gray-100"
                :class="entry.is_hidden ? 'text-amber-600' : 'text-gray-500'"
                @click="toggleUnifiedPageHidden(idx)"
              >
                {{ entry.is_hidden ? t("websites.page_show") : t("websites.page_hide") }}
              </button>
              <!-- Edit / Delete: free pages only -->
              <button
                v-if="entry.kind === 'free'"
                class="rounded px-1.5 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
                @click="startEditPage(editingWebsite!.slug, entry.page!)"
              >
                {{ t("common.edit") }}
              </button>
              <button
                v-if="entry.kind === 'free'"
                class="rounded px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50"
                @click="deletePage(editingWebsite!.slug, entry.page!.slug)"
              >
                {{ t("common.delete") }}
              </button>
            </div>
          </li>
        </ul>

        <!-- Free page create / edit form -->
        <div v-if="showPageForm === editingWebsite!.slug" class="rounded border border-indigo-200 bg-white p-3">
          <p class="mb-2 text-xs font-semibold text-indigo-800">
            {{ editingPage ? t("websites.page_edit_title") : t("websites.page_create_title") }}
          </p>
          <div v-if="!editingPage" class="mb-2 space-y-2">
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.field_slug") }}</label>
                <input v-model="newPage.slug" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" :placeholder="t('websites.field_slug_hint')" />
              </div>
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.field_title") }}</label>
                <input v-model="newPage.title" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs text-gray-700">{{ t("websites.page_content") }}</label>
              <WysiwygEditor v-model="newPage.content_md" />
            </div>
          </div>
          <div v-else class="mb-2 space-y-2">
            <div>
              <label class="block text-xs text-gray-700">{{ t("websites.field_title") }}</label>
              <input v-model="pageEditForm.title" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-gray-700">{{ t("websites.page_content") }}</label>
              <WysiwygEditor :model-value="pageEditForm.content_md ?? ''" @update:model-value="pageEditForm.content_md = $event" />
            </div>
          </div>
          <p v-if="pageError" class="mb-1 text-xs text-red-600">{{ pageError }}</p>
          <div class="flex gap-2">
            <button
              :disabled="isSubmittingPage"
              class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
              @click="submitPage(editingWebsite!.slug)"
            >
              {{ isSubmittingPage ? t("common.loading") : t("common.save") }}
            </button>
            <button class="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100" @click="cancelPageForm">
              {{ t("common.cancel") }}
            </button>
          </div>
        </div>
      </div>

      <!-- Tab: Document -->
      <div v-if="editTab === 'document'" class="bg-indigo-50 p-4 space-y-5">
        <!-- XSLT source -->
        <div>
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.doc_xslt_section") }}</p>
          <div class="space-y-2">
            <label class="flex items-center gap-2 text-xs text-gray-600">
              <input type="radio" v-model="(editForm.xslt_config as XsltConfig).source" value="default" class="text-indigo-600" />
              {{ t("websites.doc_xslt_source_default") }}
              <button
                type="button"
                class="ml-1 inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 hover:underline"
                :title="t('websites.doc_xslt_default_download')"
                @click.prevent="store.downloadDefaultXslt()"
              >
                <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {{ t("websites.doc_xslt_default_download") }}
              </button>
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              <input type="radio" v-model="(editForm.xslt_config as XsltConfig).source" value="custom" class="text-indigo-600" />
              {{ t("websites.doc_xslt_source_custom") }}
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              <input type="radio" v-model="(editForm.xslt_config as XsltConfig).source" value="url" class="text-indigo-600" />
              {{ t("websites.doc_xslt_source_url") }}
            </label>
            <label class="flex items-center gap-2 text-xs text-gray-600">
              <input type="radio" v-model="(editForm.xslt_config as XsltConfig).source" value="catalog" class="text-indigo-600" />
              {{ t("websites.doc_xslt_source_catalog") }}
            </label>
          </div>

          <!-- Upload section for custom XSLT (file picker + Edit button). -->
          <div v-show="(editForm.xslt_config as XsltConfig).source === 'custom'" class="mt-3 space-y-2">
            <input
              id="xslt-file-input"
              type="file"
              accept=".xsl,.xslt,.xml"
              class="hidden"
              @change="onXsltFileChange"
            />
            <div class="flex items-center gap-2">
              <label
                for="xslt-file-input"
                class="cursor-pointer rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
              >
                {{ t("websites.doc_xslt_filename") }}…
              </label>
              <span class="text-xs text-gray-500">
                {{ xsltFileName || t("websites.doc_xslt_no_file") }}
              </span>
              <button
                v-if="xsltFileName"
                type="button"
                class="text-xs text-red-500 hover:text-red-700"
                @click="clearXsltFile"
              >
                {{ t("websites.doc_xslt_clear") }}
              </button>
              <button
                v-if="xsltFileName"
                type="button"
                class="ml-auto inline-flex items-center gap-1.5 rounded border border-indigo-300 bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700 hover:bg-indigo-100"
                @click="openXsltModal"
              >
                <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t("websites.doc_xslt_edit_file") }}
              </button>
            </div>
          </div>

          <!-- Full-screen XSLT editor modal.
               v-show (not v-if) keeps the CM5 container in the DOM so the
               editor stays initialised between opens. autoRefresh:true handles
               the display:none → visible transition automatically; openXsltModal
               also calls refresh() after the next tick for an instant repaint. -->
          <div
            v-show="showXsltModal"
            class="fixed inset-0 z-50 flex flex-col bg-white"
            role="dialog"
            :aria-label="t('websites.doc_xslt_modal_title')"
          >
            <!-- Modal header -->
            <div class="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <span class="font-medium text-sm text-gray-800">
                {{ t("websites.doc_xslt_modal_title") }}
                <span v-if="xsltFileName" class="ml-2 font-mono text-xs text-gray-500">{{ xsltFileName }}</span>
              </span>
              <button
                type="button"
                class="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
                :aria-label="t('websites.doc_xslt_modal_close')"
                @click="closeXsltModal"
              >
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <!-- CodeMirror fills all available space -->
            <div
              :ref="onXsltEditorRef"
              class="min-h-0 flex-1 overflow-hidden [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
            />
            <!-- Modal footer -->
            <div class="flex items-center justify-end border-t border-gray-200 px-4 py-3">
              <button
                type="button"
                class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700"
                @click="closeXsltModal"
              >
                {{ t("websites.doc_xslt_modal_close") }}
              </button>
            </div>
          </div>

          <!-- Catalog -->
          <div v-if="(editForm.xslt_config as XsltConfig).source === 'catalog'" class="mt-3">
            <div class="flex items-center gap-2">
              <select
                v-model="(editForm.xslt_config as XsltConfig).catalog_id"
                class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
              >
                <option :value="null">{{ t("websites.doc_xslt_catalog_placeholder") }}</option>
                <option v-for="tpl in xsltStore.templates" :key="tpl.id" :value="tpl.id">
                  {{ tpl.name }}
                  <template v-if="tpl.processor !== 'lxml'"> ({{ tpl.processor }})</template>
                </option>
              </select>
              <button
                type="button"
                :disabled="!(editForm.xslt_config as XsltConfig).catalog_id"
                class="inline-flex items-center gap-1 rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:border-indigo-400 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40"
                :title="t('websites.doc_xslt_catalog_download')"
                @click="xsltStore.downloadTemplate((editForm.xslt_config as XsltConfig).catalog_id!)"
              >
                <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {{ t("websites.doc_xslt_catalog_download") }}
              </button>
            </div>
            <p v-if="xsltStore.templates.length === 0" class="mt-1 text-xs text-gray-400">
              {{ t("settings.xslt_templates_empty") }}
            </p>
          </div>

          <!-- URL -->
          <div v-if="(editForm.xslt_config as XsltConfig).source === 'url'" class="mt-3">
            <input
              v-model="(editForm.xslt_config as XsltConfig).url"
              type="url"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
              :placeholder="t('websites.doc_xslt_url_placeholder')"
            />
          </div>
        </div>

        <!-- Processor -->
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.doc_xslt_processor") }}</label>
          <select
            v-model="(editForm.xslt_config as XsltConfig).processor"
            class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="lxml">{{ t("websites.doc_xslt_processor_lxml") }}</option>
            <option value="saxon" disabled>{{ t("websites.doc_xslt_processor_saxon") }}</option>
          </select>
        </div>

        <!-- Image Rendering -->
        <div class="border-t border-indigo-100 pt-4">
          <div class="mb-3 flex items-center justify-between">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.doc_img_section") }}</p>
            <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                class="rounded text-indigo-600"
                v-model="(editForm.xslt_config as XsltConfig).image_rendering!.enabled"
              />
              {{ t("websites.doc_img_enabled") }}
            </label>
          </div>

          <template v-if="(editForm.xslt_config as XsltConfig).image_rendering?.enabled">
            <!-- figure -->
            <div class="mb-4 rounded border border-indigo-100 bg-white p-3">
              <p class="mb-2 text-xs font-semibold text-gray-600">{{ t("websites.doc_img_figure_title") }}</p>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_size") }}</label>
                  <select
                    v-model="(editForm.xslt_config as XsltConfig).image_rendering!.figure.size"
                    class="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                  >
                    <option value="full">{{ t("websites.doc_img_size_full") }}</option>
                    <option value="thumbnail">{{ t("websites.doc_img_size_thumb") }}</option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_layout") }}</label>
                  <select
                    v-model="(editForm.xslt_config as XsltConfig).image_rendering!.figure.layout"
                    class="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                  >
                    <option value="inline">{{ t("websites.doc_img_layout_inline") }}</option>
                    <option value="left">{{ t("websites.doc_img_layout_left") }}</option>
                    <option value="right">{{ t("websites.doc_img_layout_right") }}</option>
                    <option value="column-left">{{ t("websites.doc_img_layout_col_left") }}</option>
                    <option value="column-right">{{ t("websites.doc_img_layout_col_right") }}</option>
                    <option value="modal">{{ t("websites.doc_img_layout_modal") }}</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- pb facsimile -->
            <div class="mb-4 rounded border border-indigo-100 bg-white p-3">
              <div class="mb-2 flex items-center justify-between">
                <p class="text-xs font-semibold text-gray-600">{{ t("websites.doc_img_pb_title") }}</p>
                <label class="flex cursor-pointer items-center gap-1.5 text-xs text-gray-500">
                  <input
                    type="checkbox"
                    class="rounded text-teal-600"
                    v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.show"
                  />
                  {{ t("websites.doc_img_pb_show") }}
                </label>
              </div>
              <template v-if="(editForm.xslt_config as XsltConfig).image_rendering?.pb.show">
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_size") }}</label>
                    <select
                      v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.size"
                      class="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                    >
                      <option value="full">{{ t("websites.doc_img_size_full") }}</option>
                      <option value="thumbnail">{{ t("websites.doc_img_size_thumb") }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_layout") }}</label>
                    <select
                      v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.layout"
                      class="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                    >
                      <option value="inline">{{ t("websites.doc_img_layout_inline") }}</option>
                      <option value="left">{{ t("websites.doc_img_layout_left") }}</option>
                      <option value="right">{{ t("websites.doc_img_layout_right") }}</option>
                      <option value="column-left">{{ t("websites.doc_img_layout_col_left") }}</option>
                      <option value="column-right">{{ t("websites.doc_img_layout_col_right") }}</option>
                      <option value="modal">{{ t("websites.doc_img_layout_modal") }}</option>
                      <option value="one-to-one">{{ t("websites.doc_img_layout_oto") }}</option>
                    </select>
                    <p
                      v-if="(editForm.xslt_config as XsltConfig).image_rendering!.pb.layout === 'one-to-one'"
                      class="mt-1 text-xs text-indigo-600"
                    >{{ t("websites.doc_img_layout_oto_hint") }}</p>
                  </div>
                </div>
              </template>
            </div>

            <!-- facsimile gallery -->
            <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                class="rounded text-indigo-600"
                v-model="(editForm.xslt_config as XsltConfig).image_rendering!.facsimile_gallery"
              />
              {{ t("websites.doc_img_gallery") }}
            </label>
            <p class="mt-0.5 pl-5 text-xs text-gray-400">{{ t("websites.doc_img_gallery_hint") }}</p>

            <!-- column connectors — only relevant when column layout is active -->
            <template
              v-if="
                ['column-left','column-right'].includes((editForm.xslt_config as XsltConfig).image_rendering!.figure.layout) ||
                ['column-left','column-right'].includes((editForm.xslt_config as XsltConfig).image_rendering!.pb.layout)
              "
            >
              <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  class="rounded text-indigo-600"
                  v-model="(editForm.xslt_config as XsltConfig).image_rendering!.column_connectors"
                />
                {{ t("websites.doc_img_connectors") }}
              </label>
              <p class="mt-0.5 pl-5 text-xs text-gray-400">{{ t("websites.doc_img_connectors_hint") }}</p>
            </template>
          </template>
        </div>

        <!-- Note Rendering -->
        <div class="border-t border-indigo-100 pt-4">
          <div class="mb-3 flex items-center justify-between">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.doc_note_section") }}</p>
            <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                class="rounded text-indigo-600"
                v-model="(editForm.xslt_config as XsltConfig).note_rendering!.enabled"
              />
              {{ t("websites.doc_note_enabled") }}
            </label>
          </div>
          <p class="mb-3 text-xs text-gray-400">{{ t("websites.doc_note_enabled_hint") }}</p>

          <template v-if="(editForm.xslt_config as XsltConfig).note_rendering!.enabled">
            <p class="mb-2 text-xs font-medium text-gray-600">{{ t("websites.doc_note_mode") }}</p>
            <div class="space-y-2">
              <!-- end-of-text -->
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input
                  type="radio"
                  class="mt-0.5 text-indigo-600"
                  value="end-of-text"
                  v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode"
                />
                <span>
                  <span class="font-medium">{{ t("websites.doc_note_mode_end_of_text") }}</span>
                  <br />
                  <span class="text-gray-400">{{ t("websites.doc_note_mode_end_of_text_hint") }}</span>
                </span>
              </label>
              <!-- tooltip -->
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input
                  type="radio"
                  class="mt-0.5 text-indigo-600"
                  value="tooltip"
                  v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode"
                />
                <span>
                  <span class="font-medium">{{ t("websites.doc_note_mode_tooltip") }}</span>
                  <br />
                  <span class="text-gray-400">{{ t("websites.doc_note_mode_tooltip_hint") }}</span>
                </span>
              </label>
              <!-- frame -->
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input
                  type="radio"
                  class="mt-0.5 text-indigo-600"
                  value="frame"
                  v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode"
                />
                <span>
                  <span class="font-medium">{{ t("websites.doc_note_mode_frame") }}</span>
                  <br />
                  <span class="text-gray-400">{{ t("websites.doc_note_mode_frame_hint") }}</span>
                </span>
              </label>
            </div>
          </template>
        </div>

        <!-- Preview -->
        <div class="border-t border-indigo-100 pt-4">
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.doc_preview_section") }}</p>
          <div v-if="!editingWebsite!.collection_id" class="text-xs text-gray-400">
            {{ t("websites.doc_preview_no_collection") }}
          </div>
          <div v-else class="space-y-2">
            <div class="flex items-center gap-2">
              <select
                v-model="previewDocFilename"
                class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
              >
                <option value="">{{ t("websites.doc_preview_select_doc") }}</option>
                <option
                  v-for="doc in collectionStore.documents"
                  :key="doc.filename"
                  :value="doc.filename"
                >
                  {{ doc.filename }}
                </option>
              </select>
              <button
                :disabled="!previewDocFilename || isPreviewing"
                class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                @click="previewDocument(editingWebsite!.slug)"
              >
                {{ isPreviewing ? t("common.loading") : t("websites.doc_preview_button") }}
              </button>
            </div>
            <p v-if="previewError" class="text-xs text-red-600">{{ previewError }}</p>
            <iframe
              v-if="previewBlobUrl"
              :src="previewBlobUrl"
              class="w-full rounded border border-gray-200 bg-white"
              style="height: 420px;"
              sandbox="allow-same-origin"
              title="Document preview"
            />
          </div>
        </div>
      </div>

      <!-- Tab: Indices -->
      <div v-if="editTab === 'indices'" class="bg-gray-50 p-4 space-y-4">
        <!-- Tags section -->
        <div class="rounded border border-gray-200 bg-white p-3">
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.indices_tags_title") }}</p>
            <button
              :disabled="isRefreshingTags || !editingWebsite!.collection_id"
              class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              @click="refreshTags(editingWebsite!.slug)"
            >
              {{ isRefreshingTags ? t("common.loading") : t("websites.indices_refresh_tags") }}
            </button>
          </div>
          <p v-if="!editingWebsite!.collection_id" class="text-xs text-gray-400">{{ t("websites.indices_no_collection") }}</p>
          <p v-else-if="!editingWebsite!.distinct_tags" class="text-xs text-gray-400">{{ t("websites.indices_tags_empty") }}</p>
          <div v-else class="flex flex-wrap gap-1">
            <span
              v-for="tag in availableTags"
              :key="tag"
              class="rounded bg-indigo-50 px-2 py-0.5 text-xs font-mono text-indigo-700"
            >&lt;{{ tag }}&gt;</span>
          </div>
          <p v-if="editingWebsite!.tags_refreshed_at" class="mt-1.5 text-xs text-gray-400">
            {{ t("websites.indices_tags_updated") }}: {{ new Date(editingWebsite!.tags_refreshed_at).toLocaleString() }}
          </p>
        </div>

        <!-- Index list -->
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold text-gray-700">{{ t("websites.indices_list_title") }}</p>
          <div class="flex gap-2">
            <button
              :disabled="isRebuildingAll || editingWebsite!.indices.length === 0"
              class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              @click="rebuildAllIndices(editingWebsite!.slug)"
            >
              {{ isRebuildingAll ? t("common.loading") : t("websites.indices_rebuild_all") }}
            </button>
            <button
              class="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
              @click="openAddIndexForm"
            >
              {{ t("websites.indices_add") }}
            </button>
          </div>
        </div>

        <p v-if="indexError" class="text-xs text-red-600">{{ indexError }}</p>

        <!-- Add / edit form -->
        <div v-if="showIndexForm" class="rounded border border-indigo-200 bg-indigo-50 p-3 space-y-3">
          <p class="text-xs font-semibold text-gray-700">
            {{ editingIndexId ? t("websites.indices_edit") : t("websites.indices_new") }}
          </p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.indices_field_label") }}</label>
              <input v-model="indexForm.label" type="text" placeholder="persons" class="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.indices_field_title") }}</label>
              <input v-model="indexForm.title" type="text" :placeholder="t('websites.indices_field_title_placeholder')" class="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.indices_field_tag") }}</label>
              <div class="relative mt-1">
                <input
                  v-model="indexTagQuery"
                  type="text"
                  :placeholder="t('websites.indices_select_tag')"
                  class="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                  autocomplete="off"
                  @input="onTagInput"
                  @focus="showTagDropdown = filteredTags.length > 0"
                  @blur="onTagBlur"
                />
                <ul
                  v-if="showTagDropdown && filteredTags.length > 0"
                  class="absolute z-20 mt-0.5 max-h-48 w-full overflow-y-auto rounded border border-gray-200 bg-white shadow-md"
                >
                  <li
                    v-for="tag in filteredTags"
                    :key="tag"
                    class="cursor-pointer px-2 py-1 text-xs font-mono hover:bg-indigo-50"
                    @mousedown.prevent="selectTag(tag)"
                  >&lt;{{ tag }}&gt;</li>
                </ul>
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.indices_field_key_attr") }}</label>
              <select v-model="indexForm.key_attribute" class="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs">
                <option :value="null">{{ t("websites.indices_none_use_text") }}</option>
                <option v-for="attr in availableAttrsForTag" :key="attr" :value="attr">@{{ attr }}</option>
              </select>
            </div>
            <div class="col-span-2">
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.indices_field_subkey_attr") }}</label>
              <select v-model="indexForm.subkey_attribute" class="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs">
                <option :value="null">{{ t("websites.indices_none") }}</option>
                <option
                  v-for="attr in availableAttrsForTag.filter(a => a !== indexForm.key_attribute)"
                  :key="attr"
                  :value="attr"
                >@{{ attr }}</option>
              </select>
            </div>
          </div>
          <div class="flex gap-2">
            <button
              class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700"
              @click="saveIndexForm(editingWebsite!.slug)"
            >{{ t("common.save") }}</button>
            <button
              class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
              @click="cancelIndexForm"
            >{{ t("common.cancel") }}</button>
          </div>
        </div>

        <!-- Indices list -->
        <div v-if="editingWebsite!.indices.length === 0 && !showIndexForm" class="text-xs text-gray-400">
          {{ t("websites.indices_empty") }}
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="idx in editingWebsite!.indices"
            :key="idx.id"
            class="rounded border border-gray-200 bg-white p-3"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="text-sm font-medium text-gray-800">{{ idx.title }}</p>
                <p class="text-xs text-gray-500 font-mono">
                  /index/{{ idx.label }}/ · &lt;{{ idx.tag }}&gt;
                  <template v-if="idx.key_attribute"> · @{{ idx.key_attribute }}</template>
                  <template v-if="idx.subkey_attribute"> / @{{ idx.subkey_attribute }}</template>
                </p>
                <p class="mt-0.5 text-xs text-gray-400">
                  <template v-if="idx.last_built_at">
                    {{ t("websites.indices_built_at") }}: {{ new Date(idx.last_built_at).toLocaleString() }}
                  </template>
                  <template v-else>
                    <span class="text-amber-600">{{ t("websites.indices_not_built") }}</span>
                  </template>
                </p>
              </div>
              <div class="flex shrink-0 gap-1">
                <button
                  :disabled="rebuildingIndexId === idx.id"
                  class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  @click="rebuildIndex(editingWebsite!.slug, idx.id)"
                >
                  {{ rebuildingIndexId === idx.id ? t("common.loading") : t("websites.indices_rebuild") }}
                </button>
                <button
                  class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                  @click="openEditIndexForm(idx)"
                >{{ t("common.edit") }}</button>
                <button
                  :class="isDeletingIndexId === idx.id
                    ? 'rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700'
                    : 'rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50'"
                  @click="deleteIndex(editingWebsite!.slug, idx.id)"
                >
                  {{ isDeletingIndexId === idx.id ? t("common.confirm") : t("common.delete") }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: CSS/JS -->
      <div v-if="editTab === 'cssjs'" class="bg-indigo-50 p-4 space-y-5">
        <div>
          <label class="mb-1 block text-xs font-semibold text-gray-700">{{ t("websites.cssjs_custom_css") }}</label>
          <p class="mb-1 text-xs text-gray-500">{{ t("websites.cssjs_css_hint") }}</p>
          <textarea
            v-model="(editForm.custom_css as string)"
            rows="12"
            spellcheck="false"
            class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-gray-700">{{ t("websites.cssjs_custom_js") }}</label>
          <p class="mb-1 text-xs text-gray-500">{{ t("websites.cssjs_js_hint") }}</p>
          <label class="mb-3 flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="(editForm.include_jquery as boolean)"
              class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span class="text-xs text-gray-700">{{ t("websites.cssjs_include_jquery") }}</span>
          </label>
          <textarea
            v-model="(editForm.custom_js as string)"
            rows="12"
            spellcheck="false"
            class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none"
          />
        </div>
      </div>

      </div>
      <!-- Action bar -->
      <div class="border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-2">
        <template v-if="editTab !== 'pages' && editTab !== 'indices'">
          <p v-if="editError" class="mr-auto text-xs text-red-600">{{ editError }}</p>
          <button
            :disabled="isEditing"
            class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
            @click="saveEdit(editingWebsite!.slug)"
          >
            {{ t("common.save") }}
          </button>
        </template>
        <template v-else-if="editTab === 'pages'">
          <p v-if="pagesError" class="mr-auto text-xs text-red-600">{{ pagesError }}</p>
          <button
            :disabled="isSavingPages"
            class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
            @click="savePages(editingWebsite!.slug)"
          >
            {{ t("websites.pages_save") }}
          </button>
        </template>
        <button class="ml-auto rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="cancelEdit">
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>
  </Teleport>

</template>
