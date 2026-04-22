<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useWebsiteStore, type WebsiteCreate } from "@/stores/websites";
import { useCollectionStore } from "@/stores/collections";
import WysiwygEditor from "@/components/ui/WysiwygEditor.vue";

const { t } = useI18n();
const router = useRouter();
const authStore = useAuthStore();
const store = useWebsiteStore();
const collectionStore = useCollectionStore();

// ── Filter state ──────────────────────────────────────────────────────────────

const filterName = ref("");
const filterType = ref<"" | "STATIC" | "DYNAMIC" | "HYBRID">("");
const filterStatus = ref<"" | "published" | "unpublished" | "built" | "failed">("");

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

// ── Create form ───────────────────────────────────────────────────────────────

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
  theme_config: {
    primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff",
    doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "",
    home_layout: "single", col_left: "", col_center: "", col_right: "",
    font_family: 'Georgia,"Times New Roman",serif',
    footer_bg: "#ffffff", footer_text: "#9ca3af", hide_header: false as unknown as string, fixed_header: false as unknown as string,
  },
});

const publishedCollections = computed(() =>
  collectionStore.collections.filter((c) => c.status === "published"),
);

async function createWebsite(): Promise<void> {
  isCreating.value = true;
  createError.value = null;
  try {
    await store.createWebsite({ ...newWebsite.value });
    showCreate.value = false;
    newWebsite.value = {
      slug: "", title: "", description: null, collection_id: null,
      rendering_mode: "STATIC", is_published: false, show_in_public_home: false,
      theme_config: {
        primary_color: "#1e293b", text_color: "#1e293b", bg_color: "#ffffff",
        doc_banner_bg: "#1e293b", doc_banner_text: "#ffffff", logo_url: "",
        home_layout: "single", col_left: "", col_center: "", col_right: "",
        font_family: 'Georgia,"Times New Roman",serif',
        footer_bg: "#ffffff", footer_text: "#9ca3af", hide_header: false as unknown as string, fixed_header: false as unknown as string,
      },
    };
  } catch (err: unknown) {
    createError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isCreating.value = false;
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

const confirmDeleteSlug = ref<string | null>(null);

async function deleteWebsite(slug: string): Promise<void> {
  try {
    await store.deleteWebsite(slug);
    confirmDeleteSlug.value = null;
  } catch {
    // handled by store
  }
}

// ── Build / cache ─────────────────────────────────────────────────────────────

const buildingSlug = ref<string | null>(null);
const buildPollInterval = ref<ReturnType<typeof setInterval> | null>(null);
const clearingCacheSlug = ref<string | null>(null);

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
    idle: "text-gray-500", pending: "text-amber-500",
    building: "text-blue-500", done: "text-green-600", failed: "text-red-600",
  };
  return map[status] ?? "text-gray-500";
}

// ── Site URL / preview modal ──────────────────────────────────────────────────

function siteUrl(slug: string, isPublished: boolean): string {
  const base = `/api/v1/sites/${slug}/`;
  if (isPublished) return base;
  const token = authStore.accessToken;
  return token ? `${base}?_preview=${encodeURIComponent(token)}` : base;
}

const showPreviewModal = ref(false);
const previewModalUrl = ref("");

function openSitePreview(slug: string, isPublished: boolean): void {
  const url = siteUrl(slug, isPublished);
  if (isPublished) { window.open(url, "_blank", "noopener"); return; }
  previewModalUrl.value = url;
  showPreviewModal.value = true;
}

function closePreviewModal(): void {
  showPreviewModal.value = false;
  previewModalUrl.value = "";
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([
    store.fetchWebsites(),
    collectionStore.fetchCollections(),
  ]);
});
</script>

<template>
  <div class="mx-auto max-w-screen-xl px-6 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("websites.title") }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t("websites.subtitle") }}</p>
      </div>
      <button
        class="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="showCreate = !showCreate"
      >
        + {{ t("websites.create") }}
      </button>
    </div>

    <!-- Create form -->
    <div v-if="showCreate" class="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 p-5">
      <h2 class="mb-4 text-sm font-semibold text-indigo-800">{{ t("websites.create_title") }}</h2>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_slug") }}</label>
          <input v-model="newWebsite.slug" type="text" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.field_slug_hint')" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_title") }}</label>
          <input v-model="newWebsite.title" type="text" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm" />
        </div>
        <div class="sm:col-span-2">
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_description") }}</label>
          <input v-model="newWebsite.description" type="text" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_collection") }}</label>
          <select v-model="newWebsite.collection_id" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option :value="null">{{ t("websites.no_collection") }}</option>
            <option v-for="col in publishedCollections" :key="col.id" :value="col.id">{{ col.title }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700">{{ t("websites.field_rendering_mode") }}</label>
          <select v-model="newWebsite.rendering_mode" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option value="STATIC">{{ t("websites.mode_static") }}</option>
            <option value="DYNAMIC">{{ t("websites.mode_dynamic") }}</option>
            <option value="HYBRID">{{ t("websites.mode_hybrid") }}</option>
          </select>
        </div>
        <!-- Theme colours -->
        <div class="sm:col-span-2">
          <p class="mb-2 text-xs font-medium text-gray-700">{{ t("websites.field_theme") }}</p>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_primary") }}<input v-model="newWebsite.theme_config!.primary_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_text") }}<input v-model="newWebsite.theme_config!.text_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_bg") }}<input v-model="newWebsite.theme_config!.bg_color" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_doc_banner_bg") }}<input v-model="(newWebsite.theme_config as Record<string, string>).doc_banner_bg" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
            <label class="flex items-center gap-2 text-xs text-gray-600">{{ t("websites.theme_doc_banner_text") }}<input v-model="(newWebsite.theme_config as Record<string, string>).doc_banner_text" type="color" class="h-7 w-10 cursor-pointer rounded border border-gray-300" /></label>
          </div>
          <div class="mt-2">
            <label class="block text-xs font-medium text-gray-700">{{ t("websites.theme_logo") }}</label>
            <input v-model="newWebsite.theme_config!.logo_url" type="text" class="mt-1 block w-full rounded border border-gray-300 px-3 py-1.5 text-sm" :placeholder="t('websites.theme_logo_hint')" />
          </div>
        </div>
        <!-- Home layout -->
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
        <button class="rounded px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-100" @click="showCreate = false">
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>

    <!-- Filter toolbar -->
    <div v-if="!store.isLoading && store.websites.length > 0" class="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
      <input v-model="filterName" type="search" :placeholder="t('websites.filter_placeholder')" class="flex-1 min-w-36 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none" />
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
    <div v-if="store.isLoading" class="py-12 text-center text-sm text-gray-500">{{ t("common.loading") }}</div>
    <div v-else-if="store.websites.length === 0" class="py-12 text-center text-sm text-gray-500">{{ t("websites.empty") }}</div>
    <div v-else-if="filteredWebsites.length === 0" class="py-12 text-center text-sm text-gray-500">{{ t("websites.filter_no_results") }}</div>

    <!-- Websites list -->
    <div v-else class="space-y-2">
      <div v-for="website in filteredWebsites" :key="website.slug" class="rounded-lg border border-gray-200 bg-white">
        <!-- Website row header -->
        <div class="flex items-center gap-3 px-4 py-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900">{{ website.title }}</span>
              <span class="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-500">{{ website.slug }}</span>
              <span v-if="website.is_published" class="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">{{ t("websites.published") }}</span>
              <span class="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">{{ t(`websites.mode_${website.rendering_mode.toLowerCase()}`) }}</span>
            </div>
            <div class="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
              <span :class="buildStatusClass(website.build_status)">{{ t(`websites.build_${website.build_status}`) }}</span>
              <span v-if="website.last_build_at">· {{ new Date(website.last_build_at).toLocaleString() }}</span>
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
              <a v-if="website.is_published" :href="siteUrl(website.slug, true)" target="_blank" rel="noopener" class="rounded bg-green-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-green-700">{{ t("websites.open") }}</a>
              <button v-else class="rounded bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-200" @click="openSitePreview(website.slug, false)">{{ t("websites.preview") }}</button>
            </template>
            <!-- Download ZIP (STATIC only, when built) -->
            <button v-if="website.rendering_mode === 'STATIC' && website.build_status === 'done'" class="rounded bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-800 hover:bg-sky-200" @click="downloadSite(website.slug)">
              {{ t("websites.download_site") }}
            </button>
            <!-- Edit → navigate to dedicated edit page -->
            <button
              class="rounded bg-gray-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-gray-800"
              @click="router.push(`/admin/websites/${website.slug}/edit`)"
            >
              {{ t("common.edit") }}
            </button>
            <!-- Delete -->
            <button class="rounded bg-red-100 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-200" @click="confirmDeleteSlug = website.slug">
              {{ t("common.delete") }}
            </button>
          </div>
        </div>

        <!-- Build error -->
        <div v-if="website.build_error && website.build_status === 'failed'" class="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">
          {{ website.build_error }}
        </div>

        <!-- Delete confirmation -->
        <div v-if="confirmDeleteSlug === website.slug" class="border-t border-red-100 bg-red-50 px-4 py-3 text-sm">
          <p class="text-red-700">{{ t("websites.confirm_delete") }}</p>
          <div class="mt-2 flex gap-2">
            <button class="rounded bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-700" @click="deleteWebsite(website.slug)">{{ t("common.delete") }}</button>
            <button class="rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100" @click="confirmDeleteSlug = null">{{ t("common.cancel") }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Site preview modal (unpublished sites only) -->
  <Teleport to="body">
    <div v-if="showPreviewModal" class="fixed inset-0 z-50 flex flex-col bg-black/80" @keydown.esc="closePreviewModal">
      <div class="flex items-center justify-between bg-gray-900 px-4 py-2 text-white">
        <span class="text-sm font-medium">{{ t("websites.preview_title") }}</span>
        <button class="rounded px-3 py-1 text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white" @click="closePreviewModal">{{ t("websites.preview_close") }} ✕</button>
      </div>
      <iframe v-if="previewModalUrl" :src="previewModalUrl" class="flex-1 w-full border-0 bg-white" :title="t('websites.preview_title')" />
    </div>
  </Teleport>
</template>
