<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useWebsiteStore, type Website, type WebsiteCreate, type WebsitePageCreate, type WebsitePageUpdate } from "@/stores/websites";
import { useCollectionStore } from "@/stores/collections";

const { t } = useI18n();
const store = useWebsiteStore();
const collectionStore = useCollectionStore();

// ── State ────────────────────────────────────────────────────────────────────

const expandedSlug = ref<string | null>(null);
const editingSlug = ref<string | null>(null);
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
  theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "" },
});

// Edit website form
const editForm = ref<Partial<Website>>({});
const isEditing = ref(false);
const editError = ref<string | null>(null);

// Page form
const showPageForm = ref<string | null>(null); // website slug for which page form is open
const editingPage = ref<string | null>(null); // page slug being edited
const newPage = ref<WebsitePageCreate>({ slug: "", title: "", content_md: null, sort_order: 0 });
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

function toggleExpand(slug: string): void {
  expandedSlug.value = expandedSlug.value === slug ? null : slug;
}

function startEdit(website: Website): void {
  editingSlug.value = website.slug;
  editForm.value = {
    title: website.title,
    description: website.description,
    collection_id: website.collection_id,
    rendering_mode: website.rendering_mode,
    is_published: website.is_published,
    theme_config: { ...website.theme_config },
  };
  editError.value = null;
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
      theme_config: { primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff", logo_url: "", home_layout: "single", col_left: "", col_center: "", col_right: "" },
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
    if (expandedSlug.value === slug) expandedSlug.value = null;
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
  newPage.value = { slug: "", title: "", content_md: null, sort_order: 0 };
  pageError.value = null;
}

function startEditPage(websiteSlug: string, page: { slug: string; title: string; content_md: string | null; sort_order: number }): void {
  editingPage.value = page.slug;
  showPageForm.value = websiteSlug;
  pageEditForm.value = { title: page.title, content_md: page.content_md, sort_order: page.sort_order };
  pageError.value = null;
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
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.col_left") }}</label>
              <textarea v-model="newWebsite.theme_config!.col_left" rows="6" class="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.col_center") }}</label>
              <textarea v-model="newWebsite.theme_config!.col_center" rows="6" class="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
            </div>
            <div v-if="newWebsite.theme_config!.home_layout === 'two_right' || newWebsite.theme_config!.home_layout === 'three'">
              <label class="block text-xs font-medium text-gray-700">{{ t("websites.col_right") }}</label>
              <textarea v-model="newWebsite.theme_config!.col_right" rows="6" class="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
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
        <div
          class="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-gray-50"
          @click="toggleExpand(website.slug)"
        >
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

        <!-- Edit form (inline, below header) -->
        <div v-if="editingSlug === website.slug" class="border-t border-indigo-100 bg-indigo-50 p-4">
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
            <!-- Theme colours -->
            <div>
              <p class="mb-1 text-xs font-medium text-gray-700">{{ t("websites.field_theme") }}</p>
              <div class="flex flex-wrap gap-3">
                <label class="flex items-center gap-1.5 text-xs text-gray-600">
                  {{ t("websites.theme_primary") }}
                  <input v-model="(editForm.theme_config as Record<string, string>).primary_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
                </label>
                <label class="flex items-center gap-1.5 text-xs text-gray-600">
                  {{ t("websites.theme_text") }}
                  <input v-model="(editForm.theme_config as Record<string, string>).text_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
                </label>
                <label class="flex items-center gap-1.5 text-xs text-gray-600">
                  {{ t("websites.theme_bg") }}
                  <input v-model="(editForm.theme_config as Record<string, string>).bg_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" />
                </label>
              </div>
              <div class="mt-2">
                <label class="block text-xs text-gray-700">{{ t("websites.theme_logo") }}</label>
                <input v-model="(editForm.theme_config as Record<string, string>).logo_url" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" :placeholder="t('websites.theme_logo_hint')" />
              </div>
            </div>

            <!-- Home page layout + column content -->
            <div class="sm:col-span-2 border-t border-indigo-100 pt-3">
              <p class="mb-2 text-xs font-semibold text-gray-700">{{ t("websites.home_content_title") }}</p>
              <div class="mb-2">
                <label class="block text-xs text-gray-700">{{ t("websites.home_layout") }}</label>
                <select v-model="(editForm.theme_config as Record<string, string>).home_layout" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs">
                  <option value="single">{{ t("websites.layout_single") }}</option>
                  <option value="two_left">{{ t("websites.layout_two_left") }}</option>
                  <option value="two_right">{{ t("websites.layout_two_right") }}</option>
                  <option value="three">{{ t("websites.layout_three") }}</option>
                </select>
              </div>
              <div class="grid gap-2" :class="(editForm.theme_config as Record<string,string>).home_layout === 'single' ? 'grid-cols-1' : (editForm.theme_config as Record<string,string>).home_layout === 'three' ? 'grid-cols-3' : 'grid-cols-2'">
                <div v-if="(editForm.theme_config as Record<string,string>).home_layout === 'two_left' || (editForm.theme_config as Record<string,string>).home_layout === 'three'">
                  <label class="block text-xs text-gray-700">{{ t("websites.col_left") }}</label>
                  <textarea v-model="(editForm.theme_config as Record<string, string>).col_left" rows="6" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
                </div>
                <div>
                  <label class="block text-xs text-gray-700">{{ t("websites.col_center") }}</label>
                  <textarea v-model="(editForm.theme_config as Record<string, string>).col_center" rows="6" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
                </div>
                <div v-if="(editForm.theme_config as Record<string,string>).home_layout === 'two_right' || (editForm.theme_config as Record<string,string>).home_layout === 'three'">
                  <label class="block text-xs text-gray-700">{{ t("websites.col_right") }}</label>
                  <textarea v-model="(editForm.theme_config as Record<string, string>).col_right" rows="6" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs" :placeholder="t('websites.col_content_hint')" />
                </div>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <input :id="`edit-pub-${website.slug}`" v-model="editForm.is_published" type="checkbox" class="rounded border-gray-300" />
              <label :for="`edit-pub-${website.slug}`" class="text-xs text-gray-700">{{ t("websites.field_is_published") }}</label>
            </div>
          </div>
          <p v-if="editError" class="mt-2 text-xs text-red-600">{{ editError }}</p>
          <div class="mt-3 flex gap-2">
            <button
              :disabled="isEditing"
              class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
              @click="saveEdit(website.slug)"
            >
              {{ t("common.save") }}
            </button>
            <button class="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="cancelEdit">
              {{ t("common.cancel") }}
            </button>
          </div>
        </div>

        <!-- Expanded: pages panel -->
        <div v-if="expandedSlug === website.slug && editingSlug !== website.slug" class="border-t border-gray-100 bg-gray-50 px-4 py-3">
          <div class="mb-2 flex items-center justify-between">
            <p class="text-xs font-semibold text-gray-700">{{ t("websites.pages_title") }}</p>
            <button
              class="rounded px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-50"
              @click="openPageForm(website.slug)"
            >
              {{ t("websites.page_add") }}
            </button>
          </div>

          <!-- Page list -->
          <div v-if="website.pages.length === 0" class="py-2 text-xs text-gray-400">
            {{ t("websites.pages_empty") }}
          </div>
          <ul v-else class="mb-2 space-y-1">
            <li
              v-for="page in website.pages"
              :key="page.slug"
              class="flex items-center justify-between rounded bg-white px-3 py-1.5 text-sm shadow-sm"
            >
              <div>
                <span class="font-medium text-gray-800">{{ page.title }}</span>
                <span class="ml-2 font-mono text-xs text-gray-400">{{ page.slug }}</span>
              </div>
              <div class="flex gap-1">
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
          <div
            v-if="showPageForm === website.slug"
            class="mt-2 rounded border border-indigo-200 bg-indigo-50 p-3"
          >
            <p class="mb-2 text-xs font-semibold text-indigo-800">
              {{ editingPage ? t("websites.page_edit_title") : t("websites.page_create_title") }}
            </p>
            <div v-if="!editingPage" class="mb-2 grid grid-cols-2 gap-2">
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.field_slug") }}</label>
                <input v-model="newPage.slug" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" :placeholder="t('websites.field_slug_hint')" />
              </div>
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.field_title") }}</label>
                <input v-model="newPage.title" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
              </div>
              <div class="col-span-2">
                <label class="block text-xs text-gray-700">{{ t("websites.page_content") }}</label>
                <textarea
                  v-model="newPage.content_md"
                  rows="4"
                  class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                  :placeholder="t('websites.page_content_hint')"
                />
              </div>
            </div>
            <div v-else class="mb-2 space-y-2">
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.field_title") }}</label>
                <input v-model="pageEditForm.title" type="text" class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
              </div>
              <div>
                <label class="block text-xs text-gray-700">{{ t("websites.page_content") }}</label>
                <textarea
                  v-model="pageEditForm.content_md"
                  rows="4"
                  class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                />
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
