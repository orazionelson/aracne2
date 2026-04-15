<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick, type ComponentPublicInstance } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { useCodeMirror } from "@/composables/useCodeMirror";
import AiPanel from "@/components/AiPanel.vue";
import { useAiStore } from "@/stores/ai";
import {
  useWebsiteStore,
  type Website,
  type WebsitePage,
  type WebsiteIndex,
  type WebsiteIndexCreate,
  type WebsiteIndexUpdate,
  type WebsitePageCreate,
  type WebsitePageUpdate,
  type MetaSuggestions,
  type AracnePageConfig,
  type XsltConfig,
  type ImageRenderingConfig,
  type NoteRenderingConfig,
} from "@/stores/websites";
import { useXsltTemplateStore } from "@/stores/xslt_templates";
import { useCollectionStore } from "@/stores/collections";
import WysiwygEditor from "@/components/ui/WysiwygEditor.vue";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useWebsiteStore();
const collectionStore = useCollectionStore();
const xsltStore = useXsltTemplateStore();
const aiStore = useAiStore();

// ── Route param ───────────────────────────────────────────────────────────────

const slug = computed(() => route.params.slug as string);

/** The website record from the store (server-side truth for read-only fields). */
const website = computed<Website | null>(
  () => store.websites.find((w) => w.slug === slug.value) ?? null,
);

// ── Tab state ─────────────────────────────────────────────────────────────────

const editTab = ref<"general" | "theme" | "pages" | "document" | "xslt_edit" | "indices" | "cssjs">("general");
const showMetaPanel = ref(true);

// ── XSLT AI panel ─────────────────────────────────────────────────────────────

const aiEnabled = computed(
  () => aiStore.config !== null && aiStore.config.provider !== "disabled",
);

const XSLT_PANEL_MIN = 240;
const XSLT_PANEL_MAX = 720;
const xsltAiOpen = ref(false);
const xsltAiMode = ref<"debug" | "discuss" | null>(null);
const xsltAiPanelWidth = ref(384);
const xsltIsDragging = ref(false);
const xsltDragStartX = ref(0);
const xsltDragStartW = ref(0);
const xsltDebugError = ref("");
const xsltDiscussContext = ref<Record<string, string> | null>(null);

function startXsltDrag(e: MouseEvent): void {
  xsltIsDragging.value = true;
  xsltDragStartX.value = e.clientX;
  xsltDragStartW.value = xsltAiPanelWidth.value;
  e.preventDefault();
}

function onXsltDragMove(e: MouseEvent): void {
  if (!xsltIsDragging.value) return;
  const delta = xsltDragStartX.value - e.clientX;
  xsltAiPanelWidth.value = Math.max(
    XSLT_PANEL_MIN,
    Math.min(XSLT_PANEL_MAX, xsltDragStartW.value + delta),
  );
}

function onXsltDragEnd(): void {
  xsltIsDragging.value = false;
}

function openXsltAiPanel(): void {
  xsltAiOpen.value = true;
  if (!xsltAiMode.value) xsltAiMode.value = "debug";
}

function closeXsltAiPanel(): void {
  aiStore.resetChat();
  xsltAiOpen.value = false;
  xsltAiMode.value = null;
  xsltDiscussContext.value = null;
}

async function runXsltDebug(): Promise<void> {
  xsltAiMode.value = "debug";
  aiStore.clearResponse();
  await aiStore.startStream("xslt_debug", {
    error_msg: xsltDebugError.value,
    xslt_source: xsltCm.getValue(),
  });
}

function runXsltDiscuss(): void {
  aiStore.resetChat();
  xsltDiscussContext.value = { xslt_source: xsltCm.getValue() };
  xsltAiMode.value = "discuss";
}

// ── Constants ─────────────────────────────────────────────────────────────────

const REPEATABLE_META_FIELDS = new Set([
  "subject", "author", "designer", "dc_creator", "dc_publisher", "dc_contributor", "dc_subject",
]);

const DEFAULT_META_CONFIG: Record<string, string | string[]> = {
  keywords: "", description: "", subject: [] as string[], copyright: "",
  author: [] as string[], designer: [] as string[], url: "",
  dc_title: "", dc_creator: [] as string[], dc_subject: [] as string[], dc_description: "",
  dc_publisher: [] as string[], dc_contributor: [] as string[], dc_date: "", dc_type: "",
  dc_format: "", dc_identifier: "",
};

// ── Edit form ─────────────────────────────────────────────────────────────────

const editForm = ref<Partial<Website>>({});
const isEditing = ref(false);
const editError = ref<string | null>(null);
const isLoading = ref(true);

// ── Page form ─────────────────────────────────────────────────────────────────

const showPageForm = ref(false);
const editingPage = ref<string | null>(null);
const newPage = ref<WebsitePageCreate>({ slug: "", title: "", content_md: "", sort_order: 0, is_hidden: false });
const pageEditForm = ref<WebsitePageUpdate>({});
const isSubmittingPage = ref(false);
const pageError = ref<string | null>(null);

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

// ── XSLT upload + inline CM5 ──────────────────────────────────────────────────

const xsltFileName = ref<string>("");

function resetXsltFileInput(): void {
  const el = document.getElementById("xslt-file-input") as HTMLInputElement | null;
  if (el) el.value = "";
}

const xsltEditorContainer = ref<HTMLElement | null>(null);

function onXsltEditorRef(el: Element | ComponentPublicInstance | null): void {
  xsltEditorContainer.value = el instanceof HTMLElement ? el : null;
}

const xsltCm = useCodeMirror(xsltEditorContainer, {
  get initialValue() {
    return (editForm.value.xslt_config as XsltConfig | undefined)?.content ?? "";
  },
  onChange: (value: string) => {
    if (editForm.value.xslt_config) {
      (editForm.value.xslt_config as XsltConfig).content = value || null;
    }
  },
});

const xsltHasContent = computed<boolean>(
  () => !!((editForm.value.xslt_config as XsltConfig | undefined)?.content),
);

watch(
  () => (editForm.value.xslt_config as XsltConfig | undefined)?.source,
  (src) => {
    if (src === "custom") {
      nextTick(() => xsltCm.refresh());
    } else if (editTab.value === "xslt_edit") {
      editTab.value = "document";
    }
  },
);

const isCustomSource = computed(
  () => (editForm.value.xslt_config as XsltConfig | undefined)?.source === "custom",
);

function onXsltFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  xsltFileName.value = file.name;
  sessionStorage.setItem(`xslt_filename_${slug.value}`, file.name);
  const reader = new FileReader();
  reader.onload = (e) => {
    const content = e.target?.result as string;
    if (editForm.value.xslt_config) {
      (editForm.value.xslt_config as XsltConfig).content = content;
      xsltCm.setValue(content);
    }
  };
  reader.readAsText(file);
}

function clearXsltFile(): void {
  xsltFileName.value = "";
  sessionStorage.removeItem(`xslt_filename_${slug.value}`);
  resetXsltFileInput();
  if (editForm.value.xslt_config) {
    (editForm.value.xslt_config as XsltConfig).content = null;
    xsltCm.setValue("");
  }
}

// ── Document preview ──────────────────────────────────────────────────────────

const previewDocFilename = ref<string>("");
const isPreviewing = ref<boolean>(false);
const previewError = ref<string | null>(null);
const previewBlobUrl = ref<string | null>(null);

async function previewDocument(): Promise<void> {
  if (!previewDocFilename.value || !slug.value) return;
  isPreviewing.value = true;
  previewError.value = null;
  try {
    const xsltConfig = editForm.value.xslt_config as XsltConfig | undefined;
    const html = await store.previewDocument(slug.value, previewDocFilename.value, xsltConfig);
    if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value);
    previewBlobUrl.value = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  } catch (err: unknown) {
    previewError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isPreviewing.value = false;
  }
}

// ── Indices ───────────────────────────────────────────────────────────────────

const isRefreshingTags = ref(false);
const indexError = ref<string | null>(null);
const isRebuildingAll = ref(false);
const rebuildingIndexId = ref<string | null>(null);
const showIndexForm = ref(false);
const editingIndexId = ref<string | null>(null);
const indexForm = ref<WebsiteIndexCreate>({
  label: "", title: "", tag: "", key_attribute: null, subkey_attribute: null,
});
const isDeletingIndexId = ref<string | null>(null);

const indexTagQuery = ref<string>("");
const showTagDropdown = ref(false);

const availableTags = computed<string[]>(() => {
  if (!website.value?.distinct_tags) return [];
  return Object.keys(website.value.distinct_tags).sort();
});

const filteredTags = computed<string[]>(() => {
  const q = indexTagQuery.value.toLowerCase().replace(/^<|>$/g, "");
  if (!q) return availableTags.value;
  return availableTags.value.filter((tag) => tag.toLowerCase().includes(q));
});

const availableAttrsForTag = computed<string[]>(() => {
  if (!website.value?.distinct_tags || !indexForm.value.tag) return [];
  return (website.value.distinct_tags[indexForm.value.tag] ?? []).sort();
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
  setTimeout(() => { showTagDropdown.value = false; }, 150);
}

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
    label: idx.label, title: idx.title, tag: idx.tag,
    key_attribute: idx.key_attribute, subkey_attribute: idx.subkey_attribute,
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

async function saveIndexForm(): Promise<void> {
  indexError.value = null;
  try {
    if (editingIndexId.value) {
      const upd: WebsiteIndexUpdate = {
        label: indexForm.value.label, title: indexForm.value.title,
        tag: indexForm.value.tag, key_attribute: indexForm.value.key_attribute,
        subkey_attribute: indexForm.value.subkey_attribute,
      };
      await store.updateIndex(slug.value, editingIndexId.value, upd);
    } else {
      await store.createIndex(slug.value, indexForm.value);
    }
    showIndexForm.value = false;
    editingIndexId.value = null;
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  }
}

async function deleteIndex(indexId: string): Promise<void> {
  if (isDeletingIndexId.value === indexId) {
    try {
      await store.deleteIndex(slug.value, indexId);
    } catch (err: unknown) {
      indexError.value = err instanceof Error ? err.message : t("common.error");
    } finally {
      isDeletingIndexId.value = null;
    }
  } else {
    isDeletingIndexId.value = indexId;
  }
}

async function rebuildIndex(indexId: string): Promise<void> {
  rebuildingIndexId.value = indexId;
  indexError.value = null;
  try {
    await store.rebuildIndex(slug.value, indexId);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    rebuildingIndexId.value = null;
  }
}

async function rebuildAllIndices(): Promise<void> {
  isRebuildingAll.value = true;
  indexError.value = null;
  try {
    await store.rebuildAllIndices(slug.value);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isRebuildingAll.value = false;
  }
}

async function refreshTags(): Promise<void> {
  isRefreshingTags.value = true;
  indexError.value = null;
  try {
    await store.refreshTags(slug.value);
  } catch (err: unknown) {
    indexError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isRefreshingTags.value = false;
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────

const publishedCollections = computed(() =>
  collectionStore.collections.filter((c) => c.status === "published"),
);

// ── Meta helpers ──────────────────────────────────────────────────────────────

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

// ── Unified pages list ────────────────────────────────────────────────────────

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

function buildUnifiedList(site: Website): UnifiedPageEntry[] {
  const navCfg = normaliseNavConfig((site.nav_config ?? []) as AracnePageConfig[]);
  const _labels: Record<string, string> = {
    home: "Home", browse: "Browse", search: "Search", indices: t("websites.page_indices"),
  };
  const system: UnifiedPageEntry[] = navCfg.map((ap) => ({
    kind: "system", systemId: ap.id, title: _labels[ap.id] ?? ap.id,
    is_hidden: ap.is_hidden, sort_order: ap.sort_order,
  }));
  const free: UnifiedPageEntry[] = site.pages.map((page) => ({
    kind: "free", page, title: page.title, is_hidden: page.is_hidden, sort_order: page.sort_order,
  }));
  return [...system, ...free].sort((a, b) => a.sort_order - b.sort_order);
}

function rebuildUnifiedList(): void {
  if (website.value) unifiedPages.value = buildUnifiedList(website.value);
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

async function savePages(): Promise<void> {
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
    await store.updateWebsite(slug.value, { nav_config: newNavConfig });
    await Promise.all(
      pageUpdates.map(({ slug: pSlug, sort_order, is_hidden }) =>
        store.updatePage(slug.value, pSlug, { sort_order, is_hidden }),
      ),
    );
    rebuildUnifiedList();
  } catch (err: unknown) {
    pagesError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSavingPages.value = false;
  }
}

// ── Page form ─────────────────────────────────────────────────────────────────

function openPageForm(): void {
  showPageForm.value = true;
  newPage.value = { slug: "", title: "", content_md: "", sort_order: unifiedPages.value.length, is_hidden: false };
  pageError.value = null;
}

function startEditPage(page: WebsitePage): void {
  editingPage.value = page.slug;
  showPageForm.value = true;
  pageEditForm.value = { title: page.title, content_md: page.content_md ?? "", sort_order: page.sort_order, is_hidden: page.is_hidden };
  pageError.value = null;
}

function cancelPageForm(): void {
  showPageForm.value = false;
  editingPage.value = null;
  pageError.value = null;
}

async function submitPage(): Promise<void> {
  isSubmittingPage.value = true;
  pageError.value = null;
  try {
    if (editingPage.value) {
      await store.updatePage(slug.value, editingPage.value, pageEditForm.value);
    } else {
      await store.createPage(slug.value, { ...newPage.value });
    }
    cancelPageForm();
    rebuildUnifiedList();
  } catch (err: unknown) {
    pageError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSubmittingPage.value = false;
  }
}

async function deletePage(pageSlug: string): Promise<void> {
  if (!confirm(t("websites.confirm_delete_page"))) return;
  await store.deletePage(slug.value, pageSlug);
  rebuildUnifiedList();
}

function onWidgetDragStart(event: DragEvent, widgetType: string): void {
  if (!event.dataTransfer) return;
  event.dataTransfer.setData("widget-type", widgetType);
  event.dataTransfer.effectAllowed = "copy";
}

// ── Form init ─────────────────────────────────────────────────────────────────

function initForm(site: Website): void {
  editForm.value = {
    title: site.title,
    description: site.description,
    collection_id: site.collection_id,
    rendering_mode: site.rendering_mode,
    website_url: site.website_url,
    is_published: site.is_published,
    show_in_public_home: site.show_in_public_home,
    theme_config: {
      font_family: 'Georgia,"Times New Roman",serif',
      footer_bg: "#ffffff",
      footer_text: "#9ca3af",
      hide_header: false as unknown as string,
      fixed_header: false as unknown as string,
      ...site.theme_config,
    },
    xslt_config: (() => {
      const ex = (site.xslt_config ?? {}) as Partial<XsltConfig>;
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
      const defaults: XsltConfig = {
        source: "default", content: null, url: null, catalog_id: null,
        processor: "lxml", image_rendering: ir, note_rendering: nr,
      };
      return { ...defaults, ...ex, image_rendering: ir, note_rendering: nr };
    })(),
    meta_config: normaliseMeta({ ...DEFAULT_META_CONFIG, ...(site.meta_config ?? {}) }),
    custom_css: site.custom_css ?? "",
    custom_js: site.custom_js ?? "",
    include_jquery: site.include_jquery ?? false,
  };
  unifiedPages.value = buildUnifiedList(site);
  xsltFileName.value = sessionStorage.getItem(`xslt_filename_${site.slug}`) ?? "";
  resetXsltFileInput();
  xsltCm.setValue((site.xslt_config as XsltConfig)?.content ?? "");
  previewDocFilename.value = "";
  previewError.value = null;
  if (previewBlobUrl.value) { URL.revokeObjectURL(previewBlobUrl.value); previewBlobUrl.value = null; }

  // Apply server-side meta suggestions to empty fields asynchronously.
  store.fetchMetaSuggestions(site.slug).then((s: MetaSuggestions) => {
    const m = editForm.value.meta_config as Record<string, string | string[]>;
    if ((m.author as string[]).length === 0 && s.author.length > 0) m.author = s.author;
    if ((m.dc_creator as string[]).length === 0 && s.dc_creator.length > 0) m.dc_creator = s.dc_creator;
    if ((m.designer as string[]).length === 0 && s.designer.length > 0) m.designer = s.designer;
    if (!(m.copyright as string) && s.copyright) m.copyright = s.copyright;
    if ((m.dc_publisher as string[]).length === 0 && s.dc_publisher.length > 0) m.dc_publisher = s.dc_publisher;
    if (!(m.dc_format as string) && s.dc_format) m.dc_format = s.dc_format;
    if (!(m.dc_identifier as string) && s.dc_identifier) m.dc_identifier = s.dc_identifier;
  }).catch(() => { /* suggestions are best-effort */ });
}

// ── Save / cancel ─────────────────────────────────────────────────────────────

async function saveEdit(): Promise<void> {
  isEditing.value = true;
  editError.value = null;
  try {
    await store.updateWebsite(slug.value, {
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
    router.push("/admin/websites");
  } catch (err: unknown) {
    editError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isEditing.value = false;
  }
}

function goBack(): void {
  if (previewBlobUrl.value) { URL.revokeObjectURL(previewBlobUrl.value); previewBlobUrl.value = null; }
  router.push("/admin/websites");
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

// When the user opens the Document tab, fetch the linked collection's document
// list so the preview selector is populated.
watch(editTab, async (tab) => {
  if (tab !== "document") return;
  const collId = website.value?.collection_id;
  if (collId) collectionStore.fetchDocuments(collId).catch(() => {});
});

onMounted(async () => {
  document.addEventListener("mousemove", onXsltDragMove);
  document.addEventListener("mouseup", onXsltDragEnd);
  await Promise.all([
    store.fetchWebsites(),
    collectionStore.fetchCollections(),
    xsltStore.fetchTemplates().catch(() => { /* non-blocking for non-Designer roles */ }),
    aiStore.fetchConfig().catch(() => { /* non-fatal if AI is not configured */ }),
  ]);
  const site = store.websites.find((w) => w.slug === slug.value);
  if (!site) {
    router.push("/admin/websites");
    return;
  }
  initForm(site);
  isLoading.value = false;
});

onBeforeUnmount(() => {
  document.removeEventListener("mousemove", onXsltDragMove);
  document.removeEventListener("mouseup", onXsltDragEnd);
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value);
});
</script>

<template>
  <div v-if="isLoading" class="flex h-screen items-center justify-center text-sm text-gray-500">
    {{ t("common.loading") }}
  </div>

  <div v-else-if="!website" class="flex h-screen items-center justify-center text-sm text-gray-500">
    {{ t("common.error") }}
  </div>

  <div v-else class="flex h-screen flex-col bg-white">

    <!-- Page header -->
    <div class="flex shrink-0 items-center gap-4 border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
      <button
        class="shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        :title="t('websites.back_to_list')"
        @click="goBack"
      >
        ← {{ t("websites.back_to_list") }}
      </button>
      <div class="min-w-0">
        <h1 class="truncate text-base font-semibold text-gray-900">{{ website.title }}</h1>
        <p class="font-mono text-xs text-gray-400">{{ website.slug }}</p>
      </div>
    </div>

    <!-- Tab bar -->
    <div class="flex shrink-0 overflow-x-auto border-b border-gray-200 bg-white px-4">
      <button
        v-for="tab in (['general', 'theme', 'pages', 'document', 'xslt_edit', 'indices', 'cssjs'] as const)"
        :key="tab"
        :disabled="tab === 'xslt_edit' && !isCustomSource"
        class="-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors"
        :class="[
          editTab === tab
            ? 'border-indigo-600 text-indigo-700'
            : 'border-transparent text-gray-500 hover:text-gray-700',
          tab === 'xslt_edit' && !isCustomSource ? 'cursor-not-allowed opacity-40' : '',
        ]"
        @click="editTab = tab"
      >
        {{ t(`websites.tab_${tab}`) }}
      </button>
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
              <input :id="`edit-pub-${website.slug}`" v-model="editForm.is_published" type="checkbox" class="rounded border-gray-300" />
              <label :for="`edit-pub-${website.slug}`" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
            </div>
            <div class="flex items-center gap-2">
              <input :id="`edit-sph-${website.slug}`" v-model="editForm.show_in_public_home" type="checkbox" class="rounded border-gray-300" />
              <label :for="`edit-sph-${website.slug}`" class="text-xs text-gray-700">{{ t("websites.field_show_in_public_home") }}</label>
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
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_primary") }}<input v-model="(editForm.theme_config as Record<string, string>).primary_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_text") }}<input v-model="(editForm.theme_config as Record<string, string>).text_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_bg") }}<input v-model="(editForm.theme_config as Record<string, string>).bg_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_doc_banner_bg") }}<input v-model="(editForm.theme_config as Record<string, string>).doc_banner_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_doc_banner_text") }}<input v-model="(editForm.theme_config as Record<string, string>).doc_banner_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
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
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_footer_bg") }}<input v-model="(editForm.theme_config as Record<string, string>).footer_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_footer_text") }}<input v-model="(editForm.theme_config as Record<string, string>).footer_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
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
          <!-- Widget palette -->
          <div class="mb-2 flex items-center gap-2">
            <span class="text-xs text-gray-400">{{ t("websites.theme_widgets") }}:</span>
            <div draggable="true" class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing" @dragstart="onWidgetDragStart($event, 'search-bar')">&#128269; {{ t("websites.widget_search_bar") }}</div>
            <div draggable="true" class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing" @dragstart="onWidgetDragStart($event, 'page-menu')">&#128196; {{ t("websites.widget_page_menu") }}</div>
            <div draggable="true" class="cursor-grab select-none rounded border border-dashed border-indigo-300 bg-white px-2.5 py-1 text-xs text-indigo-600 hover:bg-indigo-50 active:cursor-grabbing" @dragstart="onWidgetDragStart($event, 'index-list')">&#128203; {{ t("websites.widget_index_list") }}</div>
          </div>
          <div class="grid gap-3" :class="(editForm.theme_config as Record<string,string>).home_layout === 'single' ? 'grid-cols-1' : (editForm.theme_config as Record<string,string>).home_layout === 'three' ? 'grid-cols-3' : 'grid-cols-2'">
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

      <!-- Tab: Pages -->
      <div v-if="editTab === 'pages'" class="bg-gray-50 p-4">
        <div class="mb-3 flex items-center justify-between">
          <p class="text-xs font-semibold text-gray-700">{{ t("websites.pages_title") }}</p>
          <button class="rounded px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-100" @click="openPageForm">
            {{ t("websites.page_add") }}
          </button>
        </div>

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
              <span class="flex flex-col">
                <button class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20" :disabled="idx === 0" @click="moveUnifiedPage(idx, idx - 1)">▲</button>
                <button class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20" :disabled="idx === unifiedPages.length - 1" @click="moveUnifiedPage(idx, idx + 1)">▼</button>
              </span>
              <span v-if="entry.kind === 'system'" class="rounded bg-indigo-100 px-1 py-0.5 text-xs font-medium text-indigo-500">sys</span>
              <span :class="entry.is_hidden ? 'text-gray-400 line-through' : 'font-medium text-gray-800'">{{ entry.title }}</span>
              <span v-if="entry.kind === 'free'" class="font-mono text-xs text-gray-400">{{ entry.page?.slug }}</span>
              <span v-if="entry.is_hidden" class="rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-500">{{ t("websites.page_hidden") }}</span>
            </div>
            <div class="flex gap-1">
              <button
                v-if="entry.systemId !== 'home'"
                class="rounded px-1.5 py-0.5 text-xs hover:bg-gray-100"
                :class="entry.is_hidden ? 'text-amber-600' : 'text-gray-500'"
                @click="toggleUnifiedPageHidden(idx)"
              >{{ entry.is_hidden ? t("websites.page_show") : t("websites.page_hide") }}</button>
              <button v-if="entry.kind === 'free'" class="rounded px-1.5 py-0.5 text-xs text-gray-600 hover:bg-gray-100" @click="startEditPage(entry.page!)">{{ t("common.edit") }}</button>
              <button v-if="entry.kind === 'free'" class="rounded px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50" @click="deletePage(entry.page!.slug)">{{ t("common.delete") }}</button>
            </div>
          </li>
        </ul>

        <!-- Free page create / edit form -->
        <div v-if="showPageForm" class="rounded border border-indigo-200 bg-white p-3">
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
              <WysiwygEditor :model-value="newPage.content_md ?? ''" @update:model-value="newPage.content_md = $event" />
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
            <button :disabled="isSubmittingPage" class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50" @click="submitPage">
              {{ isSubmittingPage ? t("common.loading") : t("common.save") }}
            </button>
            <button class="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100" @click="cancelPageForm">{{ t("common.cancel") }}</button>
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

          <!-- Catalog -->
          <div v-if="(editForm.xslt_config as XsltConfig).source === 'catalog'" class="mt-3">
            <div class="flex items-center gap-2">
              <select v-model="(editForm.xslt_config as XsltConfig).catalog_id" class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm">
                <option :value="null">{{ t("websites.doc_xslt_catalog_placeholder") }}</option>
                <option v-for="tpl in xsltStore.templates" :key="tpl.id" :value="tpl.id">
                  {{ tpl.name }}<template v-if="tpl.processor !== 'lxml'"> ({{ tpl.processor }})</template>
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
            <p v-if="xsltStore.templates.length === 0" class="mt-1 text-xs text-gray-400">{{ t("settings.xslt_templates_empty") }}</p>
          </div>

          <!-- URL -->
          <div v-if="(editForm.xslt_config as XsltConfig).source === 'url'" class="mt-3">
            <input v-model="(editForm.xslt_config as XsltConfig).url" type="url" class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.doc_xslt_url_placeholder')" />
          </div>
        </div>

        <!-- Processor -->
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.doc_xslt_processor") }}</label>
          <select v-model="(editForm.xslt_config as XsltConfig).processor" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option value="lxml">{{ t("websites.doc_xslt_processor_lxml") }}</option>
            <option value="saxon" disabled>{{ t("websites.doc_xslt_processor_saxon") }}</option>
          </select>
        </div>

        <!-- Image Rendering -->
        <div class="border-t border-indigo-100 pt-4">
          <div class="mb-3 flex items-center justify-between">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.doc_img_section") }}</p>
            <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
              <input type="checkbox" class="rounded text-indigo-600" v-model="(editForm.xslt_config as XsltConfig).image_rendering!.enabled" />
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
                  <select v-model="(editForm.xslt_config as XsltConfig).image_rendering!.figure.size" class="w-full rounded border border-gray-300 px-2 py-1 text-xs">
                    <option value="full">{{ t("websites.doc_img_size_full") }}</option>
                    <option value="thumbnail">{{ t("websites.doc_img_size_thumb") }}</option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_layout") }}</label>
                  <select v-model="(editForm.xslt_config as XsltConfig).image_rendering!.figure.layout" class="w-full rounded border border-gray-300 px-2 py-1 text-xs">
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
                  <input type="checkbox" class="rounded text-teal-600" v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.show" />
                  {{ t("websites.doc_img_pb_show") }}
                </label>
              </div>
              <template v-if="(editForm.xslt_config as XsltConfig).image_rendering?.pb.show">
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_size") }}</label>
                    <select v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.size" class="w-full rounded border border-gray-300 px-2 py-1 text-xs">
                      <option value="full">{{ t("websites.doc_img_size_full") }}</option>
                      <option value="thumbnail">{{ t("websites.doc_img_size_thumb") }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="mb-1 block text-xs text-gray-500">{{ t("websites.doc_img_layout") }}</label>
                    <select v-model="(editForm.xslt_config as XsltConfig).image_rendering!.pb.layout" class="w-full rounded border border-gray-300 px-2 py-1 text-xs">
                      <option value="inline">{{ t("websites.doc_img_layout_inline") }}</option>
                      <option value="left">{{ t("websites.doc_img_layout_left") }}</option>
                      <option value="right">{{ t("websites.doc_img_layout_right") }}</option>
                      <option value="column-left">{{ t("websites.doc_img_layout_col_left") }}</option>
                      <option value="column-right">{{ t("websites.doc_img_layout_col_right") }}</option>
                      <option value="modal">{{ t("websites.doc_img_layout_modal") }}</option>
                      <option value="one-to-one">{{ t("websites.doc_img_layout_oto") }}</option>
                    </select>
                    <p v-if="(editForm.xslt_config as XsltConfig).image_rendering!.pb.layout === 'one-to-one'" class="mt-1 text-xs text-indigo-600">{{ t("websites.doc_img_layout_oto_hint") }}</p>
                  </div>
                </div>
              </template>
            </div>
            <!-- facsimile gallery -->
            <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
              <input type="checkbox" class="rounded text-indigo-600" v-model="(editForm.xslt_config as XsltConfig).image_rendering!.facsimile_gallery" />
              {{ t("websites.doc_img_gallery") }}
            </label>
            <p class="mt-0.5 pl-5 text-xs text-gray-400">{{ t("websites.doc_img_gallery_hint") }}</p>
            <!-- column connectors -->
            <template v-if="['column-left','column-right'].includes((editForm.xslt_config as XsltConfig).image_rendering!.figure.layout) || ['column-left','column-right'].includes((editForm.xslt_config as XsltConfig).image_rendering!.pb.layout)">
              <label class="flex cursor-pointer items-center gap-2 text-xs text-gray-600">
                <input type="checkbox" class="rounded text-indigo-600" v-model="(editForm.xslt_config as XsltConfig).image_rendering!.column_connectors" />
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
              <input type="checkbox" class="rounded text-indigo-600" v-model="(editForm.xslt_config as XsltConfig).note_rendering!.enabled" />
              {{ t("websites.doc_note_enabled") }}
            </label>
          </div>
          <p class="mb-3 text-xs text-gray-400">{{ t("websites.doc_note_enabled_hint") }}</p>
          <template v-if="(editForm.xslt_config as XsltConfig).note_rendering!.enabled">
            <p class="mb-2 text-xs font-medium text-gray-600">{{ t("websites.doc_note_mode") }}</p>
            <div class="space-y-2">
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input type="radio" class="mt-0.5 text-indigo-600" value="end-of-text" v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode" />
                <span><span class="font-medium">{{ t("websites.doc_note_mode_end_of_text") }}</span><br /><span class="text-gray-400">{{ t("websites.doc_note_mode_end_of_text_hint") }}</span></span>
              </label>
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input type="radio" class="mt-0.5 text-indigo-600" value="tooltip" v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode" />
                <span><span class="font-medium">{{ t("websites.doc_note_mode_tooltip") }}</span><br /><span class="text-gray-400">{{ t("websites.doc_note_mode_tooltip_hint") }}</span></span>
              </label>
              <label class="flex cursor-pointer items-start gap-2 text-xs text-gray-600">
                <input type="radio" class="mt-0.5 text-indigo-600" value="frame" v-model="(editForm.xslt_config as XsltConfig).note_rendering!.mode" />
                <span><span class="font-medium">{{ t("websites.doc_note_mode_frame") }}</span><br /><span class="text-gray-400">{{ t("websites.doc_note_mode_frame_hint") }}</span></span>
              </label>
            </div>
          </template>
        </div>

        <!-- Preview -->
        <div class="border-t border-indigo-100 pt-4">
          <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.doc_preview_section") }}</p>
          <div v-if="!website.collection_id" class="text-xs text-gray-400">{{ t("websites.doc_preview_no_collection") }}</div>
          <div v-else class="space-y-2">
            <div class="flex items-center gap-2">
              <select v-model="previewDocFilename" class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm">
                <option value="">{{ t("websites.doc_preview_select_doc") }}</option>
                <option v-for="doc in collectionStore.documents" :key="doc.filename" :value="doc.filename">{{ doc.filename }}</option>
              </select>
              <button :disabled="!previewDocFilename || isPreviewing" class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50" @click="previewDocument">
                {{ isPreviewing ? t("common.loading") : t("websites.doc_preview_button") }}
              </button>
            </div>
            <p v-if="previewError" class="text-xs text-red-600">{{ previewError }}</p>
            <iframe v-if="previewBlobUrl" :src="previewBlobUrl" class="w-full rounded border border-gray-200 bg-white" style="height: 420px;" sandbox="allow-same-origin" title="Document preview" />
          </div>
        </div>
      </div>

      <!-- Tab: XSLT Edit (active only when source=custom).
           v-show keeps CM5 alive across tab switches. The outer div is a flex
           row: editor pane on the left, optional AI side panel on the right. -->
      <div v-show="editTab === 'xslt_edit'" class="flex h-full" :class="xsltIsDragging ? 'select-none' : ''">

        <!-- Editor pane -->
        <div class="flex min-w-0 flex-1 flex-col bg-indigo-50 p-4">
          <input id="xslt-file-input" type="file" accept=".xsl,.xslt,.xml" class="hidden" @change="onXsltFileChange" />
          <div class="flex shrink-0 items-center gap-2 pb-2">
            <label for="xslt-file-input" class="cursor-pointer rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">
              {{ t("websites.doc_xslt_filename") }}…
            </label>
            <span class="text-xs text-gray-500">
              {{ xsltHasContent ? t("websites.doc_xslt_saved") : t("websites.doc_xslt_no_file") }}
              <span v-if="xsltFileName" class="ml-1 font-mono">{{ xsltFileName }}</span>
            </span>
            <button v-if="xsltHasContent" type="button" class="text-xs text-red-500 hover:text-red-700" @click="clearXsltFile">
              {{ t("websites.doc_xslt_clear") }}
            </button>
            <!-- AI button -->
            <button
              v-if="aiEnabled"
              class="ml-auto inline-flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs font-medium transition-colors"
              :class="xsltAiOpen
                ? 'border-violet-300 bg-violet-50 text-violet-700'
                : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100'"
              @click="xsltAiOpen ? closeXsltAiPanel() : openXsltAiPanel()"
            >
              <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z"/>
              </svg>
              {{ t("ai.button_editor") }}
            </button>
          </div>

          <div class="flex min-h-0 flex-1 flex-col">
            <div
              :ref="onXsltEditorRef"
              class="min-h-0 flex-1 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
            />
          </div>
        </div>

        <!-- Resize handle -->
        <div
          v-if="xsltAiOpen"
          class="group relative z-10 flex w-[5px] shrink-0 cursor-col-resize select-none items-center justify-center transition-colors"
          :class="xsltIsDragging ? 'bg-indigo-400' : 'bg-gray-200 hover:bg-indigo-400'"
          @mousedown="startXsltDrag"
        >
          <div class="pointer-events-none flex flex-col gap-[3px]">
            <span v-for="i in 5" :key="i" class="h-[3px] w-[3px] rounded-full transition-colors" :class="xsltIsDragging ? 'bg-white' : 'bg-gray-400 group-hover:bg-white'" />
          </div>
        </div>

        <!-- AI side panel -->
        <div
          v-if="xsltAiOpen"
          class="flex shrink-0 flex-col border-l border-gray-200 bg-white"
          :style="{ width: xsltAiPanelWidth + 'px' }"
        >
          <!-- Discuss mode: AiPanel component handles full sidebar -->
          <AiPanel
            v-if="xsltAiMode === 'discuss' && xsltDiscussContext"
            prompt-slug="xslt_discuss"
            :context="xsltDiscussContext"
            :title="t('ai.panel_xslt_discuss_title')"
            :chat="true"
            :show-apply="false"
            :sidebar="true"
            @close="closeXsltAiPanel"
          />

          <!-- Debug mode: one-shot custom panel -->
          <template v-else>
            <!-- Header: Debug / Discuss buttons + close -->
            <div class="flex shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
              <div class="flex gap-1.5">
                <button
                  :disabled="aiStore.isStreaming"
                  class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
                  @click="runXsltDebug"
                >
                  {{ t("websites.xslt_debug") }}
                </button>
                <button
                  :disabled="aiStore.isStreaming"
                  class="inline-flex items-center gap-1.5 rounded border border-violet-300 bg-violet-50 px-2 py-1 text-xs font-medium text-violet-700 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-40"
                  @click="runXsltDiscuss"
                >
                  <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  {{ t("ai.discuss") }}
                </button>
              </div>
              <button class="text-gray-400 hover:text-gray-700" @click="closeXsltAiPanel">✕</button>
            </div>

            <!-- Error message textarea (optional context for Debug) -->
            <div class="shrink-0 border-b border-gray-100 px-3 py-2">
              <label class="mb-1 block text-xs font-medium text-gray-500">{{ t("websites.xslt_debug_error_label") }}</label>
              <textarea
                v-model="xsltDebugError"
                :placeholder="t('websites.xslt_debug_error_placeholder')"
                rows="3"
                class="w-full resize-none rounded border border-gray-200 px-2 py-1.5 text-xs text-gray-700 focus:border-indigo-400 focus:outline-none"
              />
            </div>

            <!-- Response area -->
            <div class="min-h-0 flex-1 overflow-y-auto">
              <span v-if="!aiStore.response && !aiStore.streamError && !aiStore.isStreaming" class="block px-4 py-3 text-xs text-gray-400">
                {{ t("ai.idle_hint") }}
              </span>
              <span v-else-if="!aiStore.response && aiStore.isStreaming" class="block animate-pulse px-4 py-3 text-gray-400">
                {{ t("ai.thinking") }}
              </span>
              <span v-else-if="aiStore.streamError" class="block px-4 py-3 font-mono text-sm text-red-600">{{ aiStore.streamError }}</span>
              <span v-else class="block whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800">{{ aiStore.response }}</span>
            </div>

            <!-- Footer -->
            <div class="flex items-center border-t border-gray-100 px-4 py-2">
              <button
                v-if="aiStore.isStreaming"
                class="rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50"
                @click="aiStore.stopStream()"
              >
                {{ t("ai.stop") }}
              </button>
              <span v-else class="text-xs text-gray-400">{{ aiStore.config?.provider ?? "" }}</span>
            </div>
          </template>
        </div>

      </div>

      <!-- Tab: Indices -->
      <div v-if="editTab === 'indices'" class="bg-gray-50 p-4 space-y-4">
        <!-- Tags section -->
        <div class="rounded border border-gray-200 bg-white p-3">
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.indices_tags_title") }}</p>
            <button :disabled="isRefreshingTags || !website.collection_id" class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50" @click="refreshTags">
              {{ isRefreshingTags ? t("common.loading") : t("websites.indices_refresh_tags") }}
            </button>
          </div>
          <p v-if="!website.collection_id" class="text-xs text-gray-400">{{ t("websites.indices_no_collection") }}</p>
          <p v-else-if="!website.distinct_tags" class="text-xs text-gray-400">{{ t("websites.indices_tags_empty") }}</p>
          <div v-else class="flex flex-wrap gap-1">
            <span v-for="tag in availableTags" :key="tag" class="rounded bg-indigo-50 px-2 py-0.5 text-xs font-mono text-indigo-700">&lt;{{ tag }}&gt;</span>
          </div>
          <p v-if="website.tags_refreshed_at" class="mt-1.5 text-xs text-gray-400">
            {{ t("websites.indices_tags_updated") }}: {{ new Date(website.tags_refreshed_at).toLocaleString() }}
          </p>
        </div>

        <!-- Index list header -->
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold text-gray-700">{{ t("websites.indices_list_title") }}</p>
          <div class="flex gap-2">
            <button :disabled="isRebuildingAll || website.indices.length === 0" class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50" @click="rebuildAllIndices">
              {{ isRebuildingAll ? t("common.loading") : t("websites.indices_rebuild_all") }}
            </button>
            <button class="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700" @click="openAddIndexForm">{{ t("websites.indices_add") }}</button>
          </div>
        </div>

        <p v-if="indexError" class="text-xs text-red-600">{{ indexError }}</p>

        <!-- Add / edit form -->
        <div v-if="showIndexForm" class="rounded border border-indigo-200 bg-indigo-50 p-3 space-y-3">
          <p class="text-xs font-semibold text-gray-700">{{ editingIndexId ? t("websites.indices_edit") : t("websites.indices_new") }}</p>
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
                <input v-model="indexTagQuery" type="text" :placeholder="t('websites.indices_select_tag')" class="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono" autocomplete="off" @input="onTagInput" @focus="showTagDropdown = filteredTags.length > 0" @blur="onTagBlur" />
                <ul v-if="showTagDropdown && filteredTags.length > 0" class="absolute z-20 mt-0.5 max-h-48 w-full overflow-y-auto rounded border border-gray-200 bg-white shadow-md">
                  <li v-for="tag in filteredTags" :key="tag" class="cursor-pointer px-2 py-1 text-xs font-mono hover:bg-indigo-50" @mousedown.prevent="selectTag(tag)">&lt;{{ tag }}&gt;</li>
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
                <option v-for="attr in availableAttrsForTag.filter(a => a !== indexForm.key_attribute)" :key="attr" :value="attr">@{{ attr }}</option>
              </select>
            </div>
          </div>
          <div class="flex gap-2">
            <button class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700" @click="saveIndexForm">{{ t("common.save") }}</button>
            <button class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50" @click="cancelIndexForm">{{ t("common.cancel") }}</button>
          </div>
        </div>

        <!-- Indices list -->
        <div v-if="website.indices.length === 0 && !showIndexForm" class="text-xs text-gray-400">{{ t("websites.indices_empty") }}</div>
        <div v-else class="space-y-2">
          <div v-for="idx in website.indices" :key="idx.id" class="rounded border border-gray-200 bg-white p-3">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="text-sm font-medium text-gray-800">{{ idx.title }}</p>
                <p class="text-xs text-gray-500 font-mono">
                  /index/{{ idx.label }}/ · &lt;{{ idx.tag }}&gt;
                  <template v-if="idx.key_attribute"> · @{{ idx.key_attribute }}</template>
                  <template v-if="idx.subkey_attribute"> / @{{ idx.subkey_attribute }}</template>
                </p>
                <p class="mt-0.5 text-xs text-gray-400">
                  <template v-if="idx.last_built_at">{{ t("websites.indices_built_at") }}: {{ new Date(idx.last_built_at).toLocaleString() }}</template>
                  <template v-else><span class="text-amber-600">{{ t("websites.indices_not_built") }}</span></template>
                </p>
              </div>
              <div class="flex shrink-0 gap-1">
                <button :disabled="rebuildingIndexId === idx.id" class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50" @click="rebuildIndex(idx.id)">{{ rebuildingIndexId === idx.id ? t("common.loading") : t("websites.indices_rebuild") }}</button>
                <button class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50" @click="openEditIndexForm(idx)">{{ t("common.edit") }}</button>
                <button :class="isDeletingIndexId === idx.id ? 'rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700' : 'rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-50'" @click="deleteIndex(idx.id)">{{ isDeletingIndexId === idx.id ? t("common.confirm") : t("common.delete") }}</button>
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
          <textarea v-model="(editForm.custom_css as string)" rows="12" spellcheck="false" class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-gray-700">{{ t("websites.cssjs_custom_js") }}</label>
          <p class="mb-1 text-xs text-gray-500">{{ t("websites.cssjs_js_hint") }}</p>
          <label class="mb-3 flex items-center gap-2 cursor-pointer">
            <input type="checkbox" v-model="(editForm.include_jquery as boolean)" class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
            <span class="text-xs text-gray-700">{{ t("websites.cssjs_include_jquery") }}</span>
          </label>
          <textarea v-model="(editForm.custom_js as string)" rows="12" spellcheck="false" class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none" />
        </div>
      </div>

    </div>

    <!-- Action bar -->
    <div class="shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-2">
      <template v-if="editTab !== 'pages' && editTab !== 'indices'">
        <p v-if="editError" class="mr-auto text-xs text-red-600">{{ editError }}</p>
        <button :disabled="isEditing" class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50" @click="saveEdit">
          {{ isEditing ? t("common.saving") : t("common.save") }}
        </button>
      </template>
      <template v-else-if="editTab === 'pages'">
        <p v-if="pagesError" class="mr-auto text-xs text-red-600">{{ pagesError }}</p>
        <button :disabled="isSavingPages" class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50" @click="savePages">
          {{ isSavingPages ? t("common.saving") : t("websites.pages_save") }}
        </button>
      </template>
      <button class="ml-auto rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="goBack">
        {{ t("common.cancel") }}
      </button>
    </div>

  </div>
</template>
