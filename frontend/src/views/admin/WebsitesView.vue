<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useWebsiteStore, type Website, type WebsitePage, type WebsiteCreate, type WebsitePageCreate, type WebsitePageUpdate, type MetaSuggestions } from "@/stores/websites";
import { useCollectionStore } from "@/stores/collections";
import WysiwygEditor from "@/components/ui/WysiwygEditor.vue";

const { t } = useI18n();
const store = useWebsiteStore();
const collectionStore = useCollectionStore();

// ── State ────────────────────────────────────────────────────────────────────

const editingSlug = ref<string | null>(null);
const editTab = ref<"general" | "theme" | "pages">("general");
const showMetaPanel = ref(false);

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
  theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "" },
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

// ── Computed ─────────────────────────────────────────────────────────────────

const publishedCollections = computed(() =>
  collectionStore.collections.filter((c) => c.status === "published"),
);

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([store.fetchWebsites(), collectionStore.fetchCollections()]);
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

async function startEdit(website: Website): Promise<void> {
  editingSlug.value = website.slug;
  editTab.value = "general";
  showMetaPanel.value = false;
  editForm.value = {
    title: website.title,
    description: website.description,
    collection_id: website.collection_id,
    rendering_mode: website.rendering_mode,
    is_published: website.is_published,
    theme_config: { ...website.theme_config },
    meta_config: normaliseMeta({ ...DEFAULT_META_CONFIG, ...(website.meta_config ?? {}) }),
  };
  editError.value = null;

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
      is_published: editForm.value.is_published,
      theme_config: editForm.value.theme_config as Record<string, string>,
      meta_config: editForm.value.meta_config as Record<string, string | string[]>,
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
      theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "" },
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

// ── Build ─────────────────────────────────────────────────────────────────────

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

function siteUrl(slug: string): string {
  return `/api/v1/sites/${slug}/`;
}

// ── Pages ─────────────────────────────────────────────────────────────────────

function openPageForm(websiteSlug: string): void {
  showPageForm.value = websiteSlug;
  newPage.value = { slug: "", title: "", content_md: "", sort_order: 0, is_hidden: false };
  pageError.value = null;
}

function startEditPage(websiteSlug: string, page: { slug: string; title: string; content_md: string | null; sort_order: number; is_hidden: boolean }): void {
  editingPage.value = page.slug;
  showPageForm.value = websiteSlug;
  pageEditForm.value = { title: page.title, content_md: page.content_md ?? "", sort_order: page.sort_order, is_hidden: page.is_hidden };
  pageError.value = null;
}

async function togglePageHidden(websiteSlug: string, page: { slug: string; is_hidden: boolean }): Promise<void> {
  await store.updatePage(websiteSlug, page.slug, { is_hidden: !page.is_hidden });
}

async function movePage(websiteSlug: string, pages: WebsitePage[], fromIdx: number, toIdx: number): Promise<void> {
  if (toIdx < 0 || toIdx >= pages.length) return;
  // Assign array-position as new sort_order for both swapped pages so the
  // ordering is always normalized regardless of existing sort_order values.
  await Promise.all([
    store.updatePage(websiteSlug, pages[fromIdx].slug, { sort_order: toIdx }),
    store.updatePage(websiteSlug, pages[toIdx].slug, { sort_order: fromIdx }),
  ]);
  // Re-sort the local array to reflect the new order immediately.
  const site = store.websites.find((w) => w.slug === websiteSlug);
  if (site) site.pages.sort((a, b) => a.sort_order - b.sort_order);
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
  } catch (err: unknown) {
    pageError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSubmittingPage.value = false;
  }
}

async function deletePage(websiteSlug: string, pageSlug: string): Promise<void> {
  if (!confirm(t("websites.confirm_delete_page"))) return;
  await store.deletePage(websiteSlug, pageSlug);
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

        <div class="flex items-center gap-2">
          <input id="create-published" v-model="newWebsite.is_published" type="checkbox" class="rounded border-gray-300" />
          <label for="create-published" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
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

    <!-- Loading / empty -->
    <div v-if="store.isLoading" class="py-12 text-center text-sm text-gray-500">
      {{ t("common.loading") }}
    </div>
    <div v-else-if="store.websites.length === 0" class="py-12 text-center text-sm text-gray-500">
      {{ t("websites.empty") }}
    </div>

    <!-- Websites list -->
    <div v-else class="space-y-3">
      <div
        v-for="website in store.websites"
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
          <div class="flex shrink-0 items-center gap-1" @click.stop>
            <!-- Build button (STATIC only) -->
            <button
              v-if="website.rendering_mode === 'STATIC'"
              :disabled="buildingSlug === website.slug || website.build_status === 'building' || website.build_status === 'pending'"
              class="rounded px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-40"
              @click="triggerBuild(website.slug)"
            >
              {{ buildingSlug === website.slug ? t("websites.building") : t("websites.build") }}
            </button>
            <!-- Open site link -->
            <a
              v-if="website.build_status === 'done' && website.rendering_mode === 'STATIC'"
              :href="siteUrl(website.slug)"
              target="_blank"
              rel="noopener"
              class="rounded px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50"
            >
              {{ t("websites.open") }}
            </a>
            <button
              class="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
              @click="startEdit(website)"
            >
              {{ t("common.edit") }}
            </button>
            <button
              class="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
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

        <!-- Edit form with tabs -->
        <div v-if="editingSlug === website.slug" class="border-t border-indigo-100">
          <!-- Tab bar -->
          <div class="flex border-b border-gray-200 bg-white px-4">
            <button
              v-for="tab in (['general', 'theme', 'pages'] as const)"
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
              <div>
                <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_rendering_mode") }}</label>
                <select v-model="editForm.rendering_mode" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
                  <option value="STATIC">{{ t("websites.mode_static") }}</option>
                  <option value="DYNAMIC">{{ t("websites.mode_dynamic") }}</option>
                  <option value="HYBRID">{{ t("websites.mode_hybrid") }}</option>
                </select>
              </div>
              <div class="flex items-center gap-2 pt-5">
                <input :id="`edit-pub-${website.slug}`" v-model="editForm.is_published" type="checkbox" class="rounded border-gray-300" />
                <label :for="`edit-pub-${website.slug}`" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
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
            <!-- Logo -->
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.theme_logo") }}</label>
              <input v-model="(editForm.theme_config as Record<string, string>).logo_url" type="text" class="mt-1 w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.theme_logo_hint')" />
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

          <!-- Tab: Pages -->
          <div v-if="editTab === 'pages'" class="bg-gray-50 p-4">
            <div class="mb-3 flex items-center justify-between">
              <p class="text-xs font-semibold text-gray-700">{{ t("websites.pages_title") }}</p>
              <button
                class="rounded px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-100"
                @click="openPageForm(website.slug)"
              >
                {{ t("websites.page_add") }}
              </button>
            </div>
            <div v-if="website.pages.length === 0 && showPageForm !== website.slug" class="py-2 text-xs text-gray-400">
              {{ t("websites.pages_empty") }}
            </div>
            <ul v-else-if="website.pages.length > 0" class="mb-3 space-y-1">
              <li
                v-for="(page, idx) in website.pages"
                :key="page.slug"
                class="flex items-center justify-between rounded px-3 py-1.5 text-sm shadow-sm"
                :class="page.is_hidden ? 'bg-gray-100' : 'bg-white'"
              >
                <div class="flex items-center gap-2">
                  <!-- Reorder arrows -->
                  <span class="flex flex-col">
                    <button
                      class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20"
                      :disabled="idx === 0"
                      @click="movePage(website.slug, website.pages, idx, idx - 1)"
                    >▲</button>
                    <button
                      class="leading-none text-gray-400 hover:text-gray-700 disabled:opacity-20"
                      :disabled="idx === website.pages.length - 1"
                      @click="movePage(website.slug, website.pages, idx, idx + 1)"
                    >▼</button>
                  </span>
                  <span :class="page.is_hidden ? 'font-medium text-gray-400 line-through' : 'font-medium text-gray-800'">{{ page.title }}</span>
                  <span class="font-mono text-xs text-gray-400">{{ page.slug }}</span>
                  <span v-if="page.is_hidden" class="rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-500">{{ t("websites.page_hidden") }}</span>
                </div>
                <div class="flex gap-1">
                  <button
                    class="rounded px-1.5 py-0.5 text-xs hover:bg-gray-100"
                    :class="page.is_hidden ? 'text-amber-600' : 'text-gray-500'"
                    :title="page.is_hidden ? t('websites.page_show') : t('websites.page_hide')"
                    @click="togglePageHidden(website.slug, page)"
                  >
                    {{ page.is_hidden ? t("websites.page_show") : t("websites.page_hide") }}
                  </button>
                  <button
                    class="rounded px-1.5 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
                    @click="startEditPage(website.slug, page)"
                  >
                    {{ t("common.edit") }}
                  </button>
                  <button
                    class="rounded px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50"
                    @click="deletePage(website.slug, page.slug)"
                  >
                    {{ t("common.delete") }}
                  </button>
                </div>
              </li>
            </ul>
            <!-- Page create / edit form -->
            <div v-if="showPageForm === website.slug" class="rounded border border-indigo-200 bg-white p-3">
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
                <label class="flex items-center gap-2 text-xs text-gray-600">
                  <input v-model="newPage.is_hidden" type="checkbox" class="rounded border-gray-300" />
                  {{ t("websites.page_is_hidden") }}
                </label>
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
                <label class="flex items-center gap-2 text-xs text-gray-600">
                  <input v-model="pageEditForm.is_hidden" type="checkbox" class="rounded border-gray-300" />
                  {{ t("websites.page_is_hidden") }}
                </label>
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
                  @click="submitPage(website.slug)"
                >
                  {{ isSubmittingPage ? t("common.loading") : t("common.save") }}
                </button>
                <button class="rounded px-3 py-1 text-xs text-gray-600 hover:bg-gray-100" @click="cancelPageForm">
                  {{ t("common.cancel") }}
                </button>
              </div>
            </div>
          </div>

          <!-- Action bar -->
          <div class="border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-2">
            <template v-if="editTab !== 'pages'">
              <p v-if="editError" class="mr-auto text-xs text-red-600">{{ editError }}</p>
              <button
                :disabled="isEditing"
                class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                @click="saveEdit(website.slug)"
              >
                {{ t("common.save") }}
              </button>
            </template>
            <button class="ml-auto rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="cancelEdit">
              {{ t("common.cancel") }}
            </button>
          </div>
        </div>

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
</template>
