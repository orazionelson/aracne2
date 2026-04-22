<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { apiClient } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const isAdmin = auth.hasMinRole("Admin");

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
    const params: Record<string, string | number> = { page, per_page: 30 };
    if (filterType.value) params["type"] = filterType.value;
    if (filterQ.value.trim()) params["q"] = filterQ.value.trim();

    const res = await apiClient.getPaginated<NamedEntity>("/entities", { params });
    entities.value = res.data as NamedEntity[];
    pagination.value = res.pagination as Pagination;
    // Close panel when results change
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
      { params: { page, per_page: 20 } }
    );
    occurrences.value = res.data as Occurrence[];
    occurrencesPagination.value = res.pagination as Pagination;
  } catch {
    occurrences.value = [];
  } finally {
    isLoadingOccurrences.value = false;
  }
}

onMounted(() => fetchEntities());

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
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("entities.title") }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t("entities.subtitle") }}</p>
      </div>
      <button
        v-if="isAdmin"
        class="shrink-0 rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        @click="router.push({ name: 'admin-entities' })"
      >
        {{ t("entities.admin_panel_btn") }}
      </button>
    </div>

    <!-- Filters -->
    <div class="mb-5 flex flex-wrap items-center gap-3">
      <select
        v-model="filterType"
        class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
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
        class="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
        @keydown="onSearchKeydown"
      />
      <button
        class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        @click="fetchEntities(1)"
      >
        {{ t("collections.search_button") }}
      </button>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-if="isLoading" class="text-sm text-gray-400 dark:text-gray-500">{{ t("common.loading") }}</p>

    <!-- Entity list -->
    <div v-if="!isLoading" class="space-y-2">
      <p v-if="entities.length === 0" class="text-sm text-gray-500 dark:text-gray-400">{{ t("entities.empty") }}</p>

      <template v-for="entity in entities" :key="entity.id">
        <!-- Entity row -->
        <div
          class="flex cursor-pointer items-center justify-between gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm transition-colors hover:border-indigo-200 hover:bg-indigo-50/30 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/20"
          :class="selectedEntity?.id === entity.id ? 'border-indigo-300 ring-1 ring-indigo-200 dark:border-indigo-600 dark:ring-indigo-700' : ''"
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
              <span class="truncate font-medium text-gray-900 dark:text-gray-100">{{ entity.canonical_form }}</span>
              <span class="shrink-0 text-xs text-gray-400 dark:text-gray-500">
                {{ t("entities.occurrences", { n: entity.occurrence_count }) }}
              </span>
            </div>
            <div
              v-if="entity.authority_ref"
              class="mt-0.5 truncate font-mono text-xs text-indigo-600 dark:text-indigo-400"
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
          <span class="shrink-0 text-xs text-gray-400 dark:text-gray-500">
            {{ selectedEntity?.id === entity.id ? "▲" : "▼" }}
          </span>
        </div>

        <!-- Inline occurrences panel (shown below the selected entity) -->
        <div
          v-if="selectedEntity?.id === entity.id"
          class="rounded-xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-800 dark:bg-indigo-900/30"
        >
          <h2 class="mb-3 text-sm font-semibold text-indigo-800 dark:text-indigo-200">
            {{ t("entities.occurrences_title") }} —
            <span class="font-normal">{{ entity.canonical_form }}</span>
          </h2>

          <p v-if="isLoadingOccurrences" class="text-xs text-gray-500 dark:text-gray-400">
            {{ t("common.loading") }}
          </p>
          <p v-else-if="occurrences.length === 0" class="text-xs text-gray-500 dark:text-gray-400">
            {{ t("entities.occurrences_empty") }}
          </p>

          <div v-else class="space-y-2">
            <div
              v-for="occ in occurrences"
              :key="occ.id"
              class="rounded border border-indigo-100 bg-white p-3 text-xs dark:border-indigo-800 dark:bg-gray-800"
            >
              <div class="flex items-start justify-between gap-2">
                <div>
                  <span class="font-medium text-indigo-700 dark:text-indigo-300">{{ occ.raw_form }}</span>
                  <span class="ml-2 text-gray-400 dark:text-gray-500">
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
                  class="shrink-0 text-indigo-600 hover:underline dark:text-indigo-400"
                  target="_blank"
                >
                  {{ t("entities.view_in_doc") }}
                </router-link>
              </div>
              <p v-if="occ.context" class="mt-1 italic text-gray-500 dark:text-gray-400">"{{ occ.context }}"</p>
            </div>

            <!-- Occurrences pagination -->
            <div
              v-if="occurrencesPagination.total_pages > 1"
              class="flex items-center justify-center gap-3 pt-1 text-xs"
            >
              <button
                :disabled="occurrencesPagination.page <= 1"
                class="rounded border border-gray-300 px-2 py-0.5 disabled:opacity-40 dark:border-gray-700"
                @click.stop="fetchOccurrences(entity.id, occurrencesPagination.page - 1)"
              >
                ←
              </button>
              <span>{{ occurrencesPagination.page }} / {{ occurrencesPagination.total_pages }}</span>
              <button
                :disabled="occurrencesPagination.page >= occurrencesPagination.total_pages"
                class="rounded border border-gray-300 px-2 py-0.5 disabled:opacity-40 dark:border-gray-700"
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
          class="rounded border border-gray-300 px-3 py-1 text-gray-700 disabled:opacity-40 dark:border-gray-700 dark:text-gray-200"
          @click="fetchEntities(pagination.page - 1)"
        >
          ←
        </button>
        <span class="text-gray-600 dark:text-gray-300">{{ pagination.page }} / {{ pagination.total_pages }}</span>
        <button
          :disabled="pagination.page >= pagination.total_pages"
          class="rounded border border-gray-300 px-3 py-1 text-gray-700 disabled:opacity-40 dark:border-gray-700 dark:text-gray-200"
          @click="fetchEntities(pagination.page + 1)"
        >
          →
        </button>
      </div>
    </div>
  </div>
</template>
