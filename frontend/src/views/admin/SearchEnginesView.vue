<template>
  <div class="mx-auto max-w-5xl px-4 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900">{{ t("search_engines.title") }}</h1>
      <button
        class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="openCreate"
      >
        + {{ t("search_engines.new") }}
      </button>
    </div>

    <!-- Filter toolbar -->
    <div class="mb-4 flex items-center gap-3">
      <input
        v-model="filterName"
        type="search"
        :placeholder="t('search_engines.filter_placeholder')"
        class="w-64 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
      />
      <span class="text-xs text-gray-400">
        {{ filteredEngines.length }} / {{ store.engines.length }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="py-12 text-center text-sm text-gray-400">
      {{ t("common.loading") }}
    </div>

    <!-- Empty state — no engines at all -->
    <div
      v-else-if="store.engines.length === 0"
      class="rounded border border-dashed border-gray-300 py-16 text-center text-sm text-gray-400"
    >
      {{ t("search_engines.empty") }}
    </div>

    <!-- Empty state — filter no match -->
    <div
      v-else-if="filteredEngines.length === 0"
      class="rounded border border-dashed border-gray-300 py-12 text-center text-sm text-gray-400"
    >
      {{ t("search_engines.no_results") }}
    </div>

    <!-- Engine list -->
    <div v-else class="divide-y divide-gray-200 rounded border border-gray-200 bg-white">
      <div
        v-for="engine in filteredEngines"
        :key="engine.slug"
        class="flex items-center gap-4 px-4 py-3"
      >
        <!-- Info -->
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="font-medium text-gray-900">{{ engine.title }}</span>
            <code class="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              {{ engine.slug }}
            </code>
            <!-- Build status badge -->
            <span
              v-if="engine.build_status !== 'idle'"
              :class="buildBadgeClass(engine.build_status)"
              class="rounded-full px-2 py-0.5 text-xs font-medium"
            >
              {{ t(`search_engines.build_status_${engine.build_status}`) }}
            </span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
            <span>
              {{
                engine.collections.length === 0
                  ? t("search_engines.no_collections_assigned")
                  : t("search_engines.collections_count", { n: engine.collections.length })
              }}
            </span>
            <span v-if="engine.xslt_template_id" class="italic">
              {{ t("search_engines.xslt_assigned") }}
            </span>
            <span v-if="engine.last_build_at" class="text-gray-400">
              {{ t("search_engines.built_at") }}: {{ formatDate(engine.last_build_at) }}
            </span>
            <span v-if="engine.build_error" class="text-red-500" :title="engine.build_error">
              {{ t("search_engines.build_error_short") }}
            </span>
          </div>
        </div>

        <!-- Build -->
        <button
          :disabled="engine.build_status === 'building' || engine.build_status === 'pending'"
          class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="triggerBuild(engine.slug)"
        >
          {{ t("search_engines.build") }}
        </button>

        <!-- Open built page -->
        <a
          v-if="engine.build_status === 'done'"
          :href="`/api/v1/search-pages/${engine.slug}/`"
          target="_blank"
          rel="noopener"
          class="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          {{ t("search_engines.open") }}
        </a>

        <!-- Clear cache -->
        <button
          v-if="engine.cache_ttl_minutes > 0"
          class="rounded bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-200"
          @click="handleClearCache(engine.slug)"
        >
          {{ t("search_engines.clear_cache") }}
        </button>

        <!-- Edit -->
        <button
          class="rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800"
          @click="openEdit(engine.slug)"
        >
          {{ t("search_engines.edit") }}
        </button>

        <!-- Delete -->
        <button
          class="rounded bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200"
          @click="confirmDelete(engine.slug, engine.title)"
        >
          {{ t("search_engines.delete") }}
        </button>
      </div>
    </div>
  </div>

  <!-- ── Full-screen modal ──────────────────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="modalOpen"
      class="fixed inset-0 z-50 flex flex-col bg-white"
      role="dialog"
      aria-modal="true"
    >
      <!-- Modal header -->
      <div class="flex shrink-0 items-center justify-between border-b border-gray-200 px-6 py-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">
            {{ isCreating ? t("search_engines.modal_create_title") : t("search_engines.modal_edit_title") }}
          </h2>
          <p v-if="!isCreating" class="mt-0.5 text-xs text-gray-400">
            {{ editingSlug }}
          </p>
        </div>
        <button
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          @click="closeModal"
        >
          <span class="sr-only">Close</span>
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fill-rule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clip-rule="evenodd"
            />
          </svg>
        </button>
      </div>

      <!-- Modal content -->
      <div class="flex-1 overflow-y-auto px-6 py-6">
        <form class="mx-auto max-w-xl space-y-5" @submit.prevent="saveForm">
          <!-- Slug (create only) -->
          <div v-if="isCreating">
            <label class="mb-1 block text-xs font-medium text-gray-700">
              {{ t("search_engines.slug_label") }}
            </label>
            <input
              v-model="form.slug"
              type="text"
              required
              pattern="^[a-z0-9_-]+$"
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
              :placeholder="t('search_engines.slug_placeholder')"
            />
            <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.slug_hint") }}</p>
          </div>

          <!-- Title -->
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700">
              {{ t("search_engines.title_label") }}
            </label>
            <input
              v-model="form.title"
              type="text"
              required
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
            />
          </div>

          <!-- XSLT template -->
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700">
              {{ t("search_engines.xslt_label") }}
            </label>
            <select
              v-model="form.xslt_template_id"
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
            >
              <option :value="null">{{ t("search_engines.xslt_none") }}</option>
              <option
                v-for="tpl in xsltStore.templates"
                :key="tpl.id"
                :value="tpl.id"
              >
                {{ tpl.name }}
              </option>
            </select>
            <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.xslt_hint") }}</p>
          </div>

          <!-- Collections multiselect -->
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700">
              {{ t("search_engines.collections_label") }}
            </label>
            <div
              v-if="store.publicCollections.length === 0"
              class="rounded border border-dashed border-gray-300 py-6 text-center text-xs text-gray-400"
            >
              {{ t("search_engines.no_public_collections") }}
            </div>
            <div
              v-else
              class="max-h-56 overflow-y-auto rounded border border-gray-200"
            >
              <label
                v-for="col in store.publicCollections"
                :key="col.id"
                class="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  :value="col.id"
                  v-model="form.collection_ids"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                <span class="text-sm text-gray-800">{{ col.title }}</span>
                <code class="ml-auto text-xs text-gray-400">{{ col.slug }}</code>
              </label>
            </div>
            <p class="mt-1 text-xs text-gray-400">
              {{ t("search_engines.collections_hint") }}
            </p>
          </div>

          <!-- Cache TTL -->
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700">
              {{ t("search_engines.cache_ttl_label") }}
            </label>
            <input
              v-model.number="form.cache_ttl_minutes"
              type="number"
              min="0"
              max="10080"
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
            />
            <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.cache_ttl_hint") }}</p>
          </div>

          <!-- Advanced search toggle -->
          <div>
            <label class="flex cursor-pointer items-center gap-2">
              <input
                v-model="form.advanced_search_enabled"
                type="checkbox"
                class="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <span class="text-sm font-medium text-gray-700">
                {{ t("search_engines.advanced_search_toggle") }}
              </span>
            </label>
            <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.advanced_search_hint") }}</p>
          </div>

          <!-- Advanced search config panel (visible only when enabled) -->
          <div
            v-if="form.advanced_search_enabled"
            class="rounded border border-indigo-100 bg-indigo-50 px-4 py-4 space-y-5"
          >
            <!-- Datalists for autocomplete -->
            <datalist id="dl-elements">
              <option v-for="name in availableElementNames" :key="name" :value="name" />
            </datalist>
            <datalist id="dl-attrs">
              <option v-for="attr in availableAttrNames" :key="attr" :value="attr" />
            </datalist>

            <!-- Tags refresh bar -->
            <div class="flex items-center gap-2 text-xs text-gray-500">
              <span v-if="tagsLoading">{{ t("search_engines.advanced_tags_loading") }}</span>
              <span v-else-if="availableElementNames.length > 0">
                {{ t("search_engines.advanced_tags_loaded", { n: availableElementNames.length }) }}
              </span>
              <span v-else>{{ t("search_engines.advanced_tags_empty") }}</span>
              <button
                type="button"
                :disabled="tagsLoading"
                class="ml-auto rounded bg-white px-2 py-1 text-xs text-indigo-600 border border-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
                @click="loadAvailableTags"
              >
                {{ t("search_engines.advanced_tags_refresh") }}
              </button>
            </div>

            <!-- Named entity tags -->
            <div>
              <div class="mb-1.5 flex items-center justify-between">
                <label class="text-xs font-semibold text-gray-700">
                  {{ t("search_engines.advanced_named_tags_label") }}
                </label>
                <button
                  type="button"
                  class="text-xs text-indigo-600 hover:underline"
                  @click="addTag"
                >
                  + {{ t("search_engines.advanced_add_tag") }}
                </button>
              </div>
              <p class="mb-2 text-xs text-gray-400">{{ t("search_engines.advanced_named_tags_hint") }}</p>
              <div
                v-for="(tag, idx) in form.advanced_search_config.named_tags"
                :key="idx"
                class="mb-1.5 flex items-center gap-2"
              >
                <input
                  v-model="tag.label"
                  type="text"
                  :placeholder="t('search_engines.advanced_tag_label_placeholder')"
                  class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                />
                <input
                  v-model="tag.element"
                  type="text"
                  list="dl-elements"
                  :placeholder="t('search_engines.advanced_tag_element_placeholder')"
                  class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                />
                <button
                  type="button"
                  class="text-xs text-red-500 hover:text-red-700"
                  @click="removeTag(idx)"
                >
                  {{ t("search_engines.advanced_remove") }}
                </button>
              </div>
              <p v-if="form.advanced_search_config.named_tags.length === 0" class="text-xs text-gray-400 italic">
                {{ t("search_engines.advanced_named_tags_hint") }}
              </p>
            </div>

            <!-- Attribute filters -->
            <div>
              <div class="mb-1.5 flex items-center justify-between">
                <label class="text-xs font-semibold text-gray-700">
                  {{ t("search_engines.advanced_attr_filters_label") }}
                </label>
                <button
                  type="button"
                  class="text-xs text-indigo-600 hover:underline"
                  @click="addAttrFilter"
                >
                  + {{ t("search_engines.advanced_add_filter") }}
                </button>
              </div>
              <p class="mb-2 text-xs text-gray-400">{{ t("search_engines.advanced_attr_filters_hint") }}</p>
              <div
                v-for="(filter, idx) in form.advanced_search_config.attribute_filters"
                :key="idx"
                class="mb-1.5 flex items-center gap-2"
              >
                <input
                  v-model="filter.label"
                  type="text"
                  :placeholder="t('search_engines.advanced_attr_label_placeholder')"
                  class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                />
                <input
                  v-model="filter.attribute"
                  type="text"
                  list="dl-attrs"
                  :placeholder="t('search_engines.advanced_attr_attribute_placeholder')"
                  class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                />
                <button
                  type="button"
                  class="text-xs text-red-500 hover:text-red-700"
                  @click="removeAttrFilter(idx)"
                >
                  {{ t("search_engines.advanced_remove") }}
                </button>
              </div>
            </div>
          </div>

          <!-- Error -->
          <div v-if="formError" class="rounded bg-red-50 px-3 py-2 text-xs text-red-700">
            {{ formError }}
          </div>
        </form>
      </div>

      <!-- Modal action bar -->
      <div class="flex shrink-0 items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
        <button
          type="button"
          class="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          @click="closeModal"
        >
          {{ t("search_engines.cancel") }}
        </button>
        <button
          type="button"
          :disabled="saving"
          class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="saveForm"
        >
          {{ saving ? t("common.saving") : t("search_engines.save") }}
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  useSearchEngineStore,
  type AdvancedSearchConfig,
  type SearchEngineBuildStatus,
} from "@/stores/search_engines";
import { useXsltTemplateStore } from "@/stores/xslt_templates";

const { t } = useI18n();
const store = useSearchEngineStore();
const xsltStore = useXsltTemplateStore();

// ── Filter ────────────────────────────────────────────────────────────────────

const filterName = ref("");

const filteredEngines = computed(() => {
  if (!filterName.value) return store.engines;
  const q = filterName.value.toLowerCase();
  return store.engines.filter(
    (e) =>
      e.title.toLowerCase().includes(q) || e.slug.toLowerCase().includes(q),
  );
});

// ── Modal state ───────────────────────────────────────────────────────────────

const modalOpen = ref(false);
const isCreating = ref(false);
const editingSlug = ref<string | null>(null);
const saving = ref(false);
const formError = ref<string | null>(null);

interface FormState {
  slug: string;
  title: string;
  xslt_template_id: string | null;
  collection_ids: string[];
  cache_ttl_minutes: number;
  advanced_search_enabled: boolean;
  advanced_search_config: AdvancedSearchConfig;
}

const defaultForm = (): FormState => ({
  slug: "",
  title: "",
  xslt_template_id: null,
  collection_ids: [],
  cache_ttl_minutes: 60,
  advanced_search_enabled: false,
  advanced_search_config: { named_tags: [], attribute_filters: [] },
});

const form = ref<FormState>(defaultForm());

function openCreate(): void {
  isCreating.value = true;
  editingSlug.value = null;
  form.value = defaultForm();
  formError.value = null;
  availableTags.value = {};
  modalOpen.value = true;
}

function openEdit(slug: string): void {
  const engine = store.engines.find((e) => e.slug === slug);
  if (!engine) return;
  isCreating.value = false;
  editingSlug.value = slug;
  availableTags.value = {};
  form.value = {
    slug: engine.slug,
    title: engine.title,
    xslt_template_id: engine.xslt_template_id,
    collection_ids: engine.collections.map((c) => c.id),
    cache_ttl_minutes: engine.cache_ttl_minutes,
    advanced_search_enabled: engine.advanced_search_enabled,
    advanced_search_config: {
      named_tags: engine.advanced_search_config.named_tags.map((t) => ({ ...t })),
      attribute_filters: engine.advanced_search_config.attribute_filters.map((f) => ({ ...f })),
    },
  };
  formError.value = null;
  modalOpen.value = true;
}

function closeModal(): void {
  modalOpen.value = false;
}

async function saveForm(): Promise<void> {
  formError.value = null;
  if (!form.value.title.trim()) {
    formError.value = t("search_engines.error_title_required");
    return;
  }
  if (isCreating.value && !form.value.slug.trim()) {
    formError.value = t("search_engines.error_slug_required");
    return;
  }
  saving.value = true;
  try {
    if (isCreating.value) {
      await store.create({
        slug: form.value.slug,
        title: form.value.title,
        xslt_template_id: form.value.xslt_template_id,
        collection_ids: form.value.collection_ids,
        cache_ttl_minutes: form.value.cache_ttl_minutes,
        advanced_search_enabled: form.value.advanced_search_enabled,
        advanced_search_config: form.value.advanced_search_config,
      });
    } else {
      await store.update(editingSlug.value!, {
        title: form.value.title,
        xslt_template_id: form.value.xslt_template_id,
        collection_ids: form.value.collection_ids,
        cache_ttl_minutes: form.value.cache_ttl_minutes,
        advanced_search_enabled: form.value.advanced_search_enabled,
        advanced_search_config: form.value.advanced_search_config,
      });
    }
    closeModal();
  } catch (err: unknown) {
    const msg =
      err instanceof Error ? err.message : t("search_engines.error_save");
    formError.value = msg;
  } finally {
    saving.value = false;
  }
}

// ── Advanced search: available tags from linked collections ──────────────────

const availableTags = ref<Record<string, string[]>>({});
const tagsLoading = ref(false);

/** Sorted element names from the linked collections. */
const availableElementNames = computed(() => Object.keys(availableTags.value).sort());

/** All distinct attribute names across all elements. */
const availableAttrNames = computed(() =>
  [...new Set(Object.values(availableTags.value).flat())].sort(),
);

async function loadAvailableTags(): Promise<void> {
  const slug = editingSlug.value;
  if (!slug) return;
  tagsLoading.value = true;
  try {
    availableTags.value = await store.fetchAvailableTags(slug);
  } catch {
    availableTags.value = {};
  } finally {
    tagsLoading.value = false;
  }
}

// Auto-fetch when the advanced search panel is first opened during an edit.
watch(
  () => form.value.advanced_search_enabled,
  (enabled) => {
    if (enabled && editingSlug.value && Object.keys(availableTags.value).length === 0) {
      void loadAvailableTags();
    }
  },
);

// ── Advanced search config helpers ───────────────────────────────────────────

function addTag(): void {
  form.value.advanced_search_config.named_tags.push({ label: "", element: "" });
}

function removeTag(idx: number): void {
  form.value.advanced_search_config.named_tags.splice(idx, 1);
}

function addAttrFilter(): void {
  form.value.advanced_search_config.attribute_filters.push({ label: "", attribute: "" });
}

function removeAttrFilter(idx: number): void {
  form.value.advanced_search_config.attribute_filters.splice(idx, 1);
}

// ── Build ─────────────────────────────────────────────────────────────────────

function buildBadgeClass(status: SearchEngineBuildStatus): string {
  switch (status) {
    case "done":     return "bg-green-100 text-green-700";
    case "failed":   return "bg-red-100 text-red-700";
    case "building": return "bg-blue-100 text-blue-700";
    case "pending":  return "bg-yellow-100 text-yellow-700";
    default:         return "bg-gray-100 text-gray-500";
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

async function triggerBuild(slug: string): Promise<void> {
  try {
    await store.build(slug);
    // Poll until done or failed (max ~30 s at 2 s intervals).
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts++;
      await store.fetchAll();
      const engine = store.engines.find((e) => e.slug === slug);
      if (!engine || engine.build_status === "done" || engine.build_status === "failed" || attempts >= 15) {
        clearInterval(poll);
      }
    }, 2000);
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_build"));
  }
}

// ── Cache ─────────────────────────────────────────────────────────────────────

async function handleClearCache(slug: string): Promise<void> {
  try {
    const deleted = await store.clearCache(slug);
    window.alert(t("search_engines.cache_cleared", { n: deleted }));
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_clear_cache"));
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function confirmDelete(slug: string, title: string): Promise<void> {
  if (!window.confirm(t("search_engines.delete_confirm", { title }))) return;
  try {
    await store.remove(slug);
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_delete"));
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([
    store.fetchAll(),
    store.fetchPublicCollections(),
    xsltStore.fetchTemplates(),
  ]);
});
</script>
