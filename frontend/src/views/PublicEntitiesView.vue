<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUiConfigStore } from "@/stores/ui_config";
import { apiClient } from "@/services/api";
import { usePublicCustomCss } from "@/composables/usePublicCustomCss";

const { t } = useI18n();
const route = useRoute();
const uiConfig = useUiConfigStore();
usePublicCustomCss();

const slug = route.params.slug as string;

// ── Types ─────────────────────────────────────────────────────────────────────

type EntityType = "person" | "place" | "org";

interface NamedEntity {
  id: string;
  type: EntityType;
  canonical_form: string;
  authority_ref: string | null;
  occurrence_count: number;
}

interface Occurrence {
  id: string;
  entity_id: string;
  collection_id: string;
  collection_slug: string;
  collection_title: string;
  filename: string;
  raw_form: string;
  context: string | null;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

// ── State — entity list ───────────────────────────────────────────────────────

const entities = ref<NamedEntity[]>([]);
const pagination = ref<Pagination>({ page: 1, per_page: 30, total: 0, total_pages: 1 });
const isLoading = ref(false);
const error = ref<string | null>(null);
const filterType = ref<EntityType | "">("");
const filterQ = ref("");

// ── State — occurrences panel ─────────────────────────────────────────────────

const selectedEntity = ref<NamedEntity | null>(null);
const occurrences = ref<Occurrence[]>([]);
const occurrencesPagination = ref<Pagination>({ page: 1, per_page: 20, total: 0, total_pages: 1 });
const isLoadingOccurrences = ref(false);

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchEntities(page = 1): Promise<void> {
  isLoading.value = true;
  error.value = null;
  try {
    const params: Record<string, string | number> = {
      page,
      per_page: 30,
      collection_slug: slug,
    };
    if (filterType.value) params["type"] = filterType.value;
    if (filterQ.value.trim()) params["q"] = filterQ.value.trim();

    const res = await apiClient.getPaginated<NamedEntity>("/entities", { params });
    entities.value = res.data as NamedEntity[];
    pagination.value = res.pagination as Pagination;
    selectedEntity.value = null;
    occurrences.value = [];
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
}

async function fetchOccurrences(entityId: string, page = 1): Promise<void> {
  isLoadingOccurrences.value = true;
  try {
    const res = await apiClient.getPaginated<Occurrence>(
      `/entities/${entityId}/occurrences`,
      { params: { page, per_page: 20, collection: slug } },
    );
    occurrences.value = res.data as Occurrence[];
    occurrencesPagination.value = res.pagination as Pagination;
  } catch {
    occurrences.value = [];
  } finally {
    isLoadingOccurrences.value = false;
  }
}

onMounted(() => {
  uiConfig.fetchConfig().catch(() => { /* non-fatal */ });
  fetchEntities();
});

watch(filterType, () => fetchEntities(1));

function onSearchKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter") fetchEntities(1);
}

// ── Occurrences panel ─────────────────────────────────────────────────────────

function openOccurrences(entity: NamedEntity): void {
  if (selectedEntity.value?.id === entity.id) {
    selectedEntity.value = null;
    return;
  }
  selectedEntity.value = entity;
  occurrences.value = [];
  fetchOccurrences(entity.id, 1);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function typeBadgeClass(type: EntityType): string {
  return (
    {
      person: "bg-indigo-100 text-indigo-700",
      place: "bg-emerald-100 text-emerald-700",
      org: "bg-amber-100 text-amber-700",
    }[type] ?? "bg-gray-100 text-gray-600"
  );
}

function typeLabel(type: EntityType): string {
  return t(`entities.type_${type}`);
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Public header (same as PublicBibliographyView) -->
    <header
      class="flex h-14 items-center gap-3 px-6 text-white shadow"
      :style="{ backgroundColor: uiConfig.config.navbar_bg_color }"
    >
      <router-link to="/" class="flex items-center gap-2 text-lg font-bold hover:opacity-80">
        <img
          v-if="uiConfig.config.platform_logo_url"
          :src="uiConfig.config.platform_logo_url"
          alt="Logo"
          class="h-8 w-auto object-contain"
        />
        <span>{{ uiConfig.config.platform_name }}</span>
      </router-link>
      <span class="ml-auto text-sm opacity-80">
        <router-link to="/login" class="hover:underline">
          {{ t("auth.sign_in") }}
        </router-link>
      </span>
    </header>

    <main class="mx-auto max-w-4xl px-4 py-8">
      <!-- Back link -->
      <router-link
        :to="{ name: 'public-collection', params: { slug } }"
        class="mb-4 inline-block text-sm text-indigo-600 hover:underline"
      >
        {{ t("public.entities_back") }}
      </router-link>

      <!-- Page title -->
      <div class="mb-6">
        <h1 class="text-2xl font-bold text-gray-900">{{ t("public.entities_page_title") }}</h1>
        <p class="mt-1 text-sm text-gray-500">{{ t("public.entities_page_subtitle") }}</p>
      </div>

      <!-- Filters -->
      <div class="mb-5 flex flex-wrap items-center gap-3">
        <select
          v-model="filterType"
          class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
        >
          <option value="">{{ t("entities.type_all") }}</option>
          <option value="person">{{ t("entities.type_person") }}</option>
          <option value="place">{{ t("entities.type_place") }}</option>
          <option value="org">{{ t("entities.type_org") }}</option>
        </select>
        <input
          v-model="filterQ"
          type="text"
          :placeholder="t('entities.search_placeholder')"
          class="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          @keydown="onSearchKeydown"
        />
        <button
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          @click="fetchEntities(1)"
        >
          {{ t("collections.search_button") }}
        </button>
      </div>

      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>
      <p v-if="isLoading" class="text-sm text-gray-400">{{ t("common.loading") }}</p>

      <!-- Entity list -->
      <div v-if="!isLoading" class="space-y-2">
        <p v-if="entities.length === 0" class="text-sm text-gray-500">
          {{ t("entities.empty") }}
        </p>

        <template v-for="entity in entities" :key="entity.id">
          <!-- Entity row -->
          <div
            class="flex cursor-pointer items-center justify-between gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm transition-colors hover:border-violet-200 hover:bg-violet-50/30"
            :class="selectedEntity?.id === entity.id ? 'border-violet-300 ring-1 ring-violet-200' : ''"
            @click="openOccurrences(entity)"
          >
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium"
                  :class="typeBadgeClass(entity.type)"
                >
                  {{ typeLabel(entity.type) }}
                </span>
                <span class="truncate font-medium text-gray-900">{{ entity.canonical_form }}</span>
                <span class="shrink-0 text-xs text-gray-400">
                  {{ t("entities.occurrences", { n: entity.occurrence_count }) }}
                </span>
              </div>
              <div
                v-if="entity.authority_ref"
                class="mt-0.5 truncate font-mono text-xs text-indigo-600"
              >
                <a
                  :href="entity.authority_ref"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="hover:underline"
                  @click.stop
                >
                  {{ entity.authority_ref }}
                </a>
              </div>
            </div>
            <span class="shrink-0 text-xs text-gray-400">
              {{ selectedEntity?.id === entity.id ? "▲" : "▼" }}
            </span>
          </div>

          <!-- Inline occurrences panel -->
          <div
            v-if="selectedEntity?.id === entity.id"
            class="rounded-xl border border-violet-200 bg-violet-50 p-4"
          >
            <h2 class="mb-3 text-sm font-semibold text-violet-800">
              {{ t("entities.occurrences_title") }} —
              <span class="font-normal">{{ entity.canonical_form }}</span>
            </h2>

            <p v-if="isLoadingOccurrences" class="text-xs text-gray-500">
              {{ t("common.loading") }}
            </p>
            <p v-else-if="occurrences.length === 0" class="text-xs text-gray-500">
              {{ t("entities.occurrences_empty") }}
            </p>

            <div v-else class="space-y-2">
              <div
                v-for="occ in occurrences"
                :key="occ.id"
                class="rounded border border-violet-100 bg-white p-3 text-xs"
              >
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <span class="font-medium text-violet-700">{{ occ.raw_form }}</span>
                    <span class="ml-2 text-gray-400">
                      {{
                        t("entities.occurrences_in", {
                          collection: occ.collection_title,
                          filename: occ.filename,
                        })
                      }}
                    </span>
                  </div>
                  <router-link
                    :to="{
                      name: 'public-document',
                      params: { slug: occ.collection_slug, filename: occ.filename },
                    }"
                    class="shrink-0 text-indigo-600 hover:underline"
                    target="_blank"
                  >
                    {{ t("entities.view_in_doc") }}
                  </router-link>
                </div>
                <p v-if="occ.context" class="mt-1 italic text-gray-500">"{{ occ.context }}"</p>
              </div>

              <!-- Occurrences pagination -->
              <div
                v-if="occurrencesPagination.total_pages > 1"
                class="flex items-center justify-center gap-3 pt-1 text-xs"
              >
                <button
                  :disabled="occurrencesPagination.page <= 1"
                  class="rounded border px-2 py-0.5 disabled:opacity-40"
                  @click.stop="fetchOccurrences(entity.id, occurrencesPagination.page - 1)"
                >
                  ←
                </button>
                <span>{{ occurrencesPagination.page }} / {{ occurrencesPagination.total_pages }}</span>
                <button
                  :disabled="occurrencesPagination.page >= occurrencesPagination.total_pages"
                  class="rounded border px-2 py-0.5 disabled:opacity-40"
                  @click.stop="fetchOccurrences(entity.id, occurrencesPagination.page + 1)"
                >
                  →
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- Entity list pagination -->
        <div
          v-if="pagination.total_pages > 1"
          class="mt-4 flex items-center justify-center gap-3 text-sm"
        >
          <button
            :disabled="pagination.page <= 1"
            class="rounded border px-3 py-1 disabled:opacity-40"
            @click="fetchEntities(pagination.page - 1)"
          >
            ←
          </button>
          <span class="text-gray-600">{{ pagination.page }} / {{ pagination.total_pages }}</span>
          <button
            :disabled="pagination.page >= pagination.total_pages"
            class="rounded border px-3 py-1 disabled:opacity-40"
            @click="fetchEntities(pagination.page + 1)"
          >
            →
          </button>
        </div>
      </div>
    </main>
  </div>
</template>
