<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";

const { t } = useI18n();

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

// ── Tab ───────────────────────────────────────────────────────────────────────

type Tab = "browse" | "admin" | "reindex";
const activeTab = ref<Tab>("admin");

// ── State — entity list ───────────────────────────────────────────────────────

const entities = ref<NamedEntity[]>([]);
const pagination = ref<Pagination>({ page: 1, per_page: 30, total: 0, total_pages: 1 });
const isLoading = ref(false);
const error = ref<string | null>(null);
const filterType = ref<EntityType | "">("");
const filterQ = ref("");
const filterUnlinked = ref(false);

// ── State — occurrences panel ─────────────────────────────────────────────────

const selectedEntity = ref<NamedEntity | null>(null);
const occurrences = ref<Occurrence[]>([]);
const occurrencesPagination = ref<Pagination>({ page: 1, per_page: 20, total: 0, total_pages: 1 });
const isLoadingOccurrences = ref(false);

// ── State — edit modal ────────────────────────────────────────────────────────

const editingEntity = ref<NamedEntity | null>(null);
const editCanonicalForm = ref("");
const editAuthorityRef = ref("");
const isSaving = ref(false);
const editError = ref<string | null>(null);

// ── State — merge modal ───────────────────────────────────────────────────────

const showMerge = ref(false);
const mergeSourceId = ref("");
const mergeTargetId = ref("");
const isMerging = ref(false);
const mergeError = ref<string | null>(null);

// ── State — re-index ──────────────────────────────────────────────────────────

const reindexSlug = ref("");
const isReindexing = ref(false);
const reindexResult = ref<string | null>(null);
const reindexError = ref<string | null>(null);

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchEntities(page = 1): Promise<void> {
  isLoading.value = true;
  error.value = null;
  try {
    const params: Record<string, string | number | boolean> = { page, per_page: 30 };
    if (filterType.value) params["type"] = filterType.value;
    if (filterQ.value.trim()) params["q"] = filterQ.value.trim();
    if (filterUnlinked.value) params["unlinked"] = true;

    const res = await apiClient.get<{ data: NamedEntity[]; pagination: Pagination }>(
      "/entities/admin",
      { params }
    );
    entities.value = res.data;
    pagination.value = res.pagination;
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
}

async function fetchOccurrences(entityId: string, page = 1): Promise<void> {
  isLoadingOccurrences.value = true;
  try {
    const res = await apiClient.get<{ data: Occurrence[]; pagination: Pagination }>(
      `/entities/${entityId}/occurrences`,
      { params: { page, per_page: 20 } }
    );
    occurrences.value = res.data;
    occurrencesPagination.value = res.pagination;
  } catch {
    occurrences.value = [];
  } finally {
    isLoadingOccurrences.value = false;
  }
}

onMounted(() => fetchEntities());

watch([filterType, filterUnlinked], () => fetchEntities(1));

function onSearchKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter") fetchEntities(1);
}

// ── Occurrences panel ─────────────────────────────────────────────────────────

function openOccurrences(entity: NamedEntity): void {
  selectedEntity.value = entity;
  occurrences.value = [];
  fetchOccurrences(entity.id, 1);
}

function closeOccurrences(): void {
  selectedEntity.value = null;
}

// ── Edit modal ────────────────────────────────────────────────────────────────

function openEdit(entity: NamedEntity): void {
  editingEntity.value = entity;
  editCanonicalForm.value = entity.canonical_form;
  editAuthorityRef.value = entity.authority_ref ?? "";
  editError.value = null;
}

function closeEdit(): void {
  editingEntity.value = null;
}

async function saveEdit(): Promise<void> {
  if (!editingEntity.value) return;
  if (!editCanonicalForm.value.trim()) {
    editError.value = t("entities.field_canonical_form") + " required";
    return;
  }
  isSaving.value = true;
  editError.value = null;
  try {
    await apiClient.put(`/entities/admin/${editingEntity.value.id}`, {
      canonical_form: editCanonicalForm.value.trim(),
      authority_ref: editAuthorityRef.value.trim() || null,
    });
    closeEdit();
    await fetchEntities(pagination.value.page);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    editError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function deleteEntity(entity: NamedEntity): Promise<void> {
  if (!confirm(t("entities.confirm_delete"))) return;
  try {
    await apiClient.delete(`/entities/admin/${entity.id}`);
    await fetchEntities(pagination.value.page);
    if (selectedEntity.value?.id === entity.id) closeOccurrences();
  } catch {
    error.value = t("common.error");
  }
}

// ── Merge ─────────────────────────────────────────────────────────────────────

function openMerge(): void {
  showMerge.value = true;
  mergeSourceId.value = "";
  mergeTargetId.value = "";
  mergeError.value = null;
}

function closeMerge(): void {
  showMerge.value = false;
}

async function submitMerge(): Promise<void> {
  if (!mergeSourceId.value.trim() || !mergeTargetId.value.trim()) {
    mergeError.value = "Both IDs are required.";
    return;
  }
  if (mergeSourceId.value.trim() === mergeTargetId.value.trim()) {
    mergeError.value = "Source and target must be different.";
    return;
  }
  isMerging.value = true;
  mergeError.value = null;
  try {
    await apiClient.post("/entities/admin/merge", {
      source_id: mergeSourceId.value.trim(),
      target_id: mergeTargetId.value.trim(),
    });
    closeMerge();
    await fetchEntities(1);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    mergeError.value = msg ?? t("common.error");
  } finally {
    isMerging.value = false;
  }
}

// ── Re-index ──────────────────────────────────────────────────────────────────

async function submitReindex(): Promise<void> {
  if (!reindexSlug.value.trim()) return;
  isReindexing.value = true;
  reindexResult.value = null;
  reindexError.value = null;
  try {
    const res = await apiClient.post<{ data: { occurrences_indexed: number } }>(
      `/entities/admin/reindex/${reindexSlug.value.trim()}`
    );
    reindexResult.value = t("entities.reindex_success", { n: res.data.occurrences_indexed });
    await fetchEntities(1);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    reindexError.value = msg ?? t("common.error");
  } finally {
    isReindexing.value = false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function typeBadgeClass(type: EntityType): string {
  return {
    person: "bg-indigo-100 text-indigo-700",
    place:  "bg-emerald-100 text-emerald-700",
    org:    "bg-amber-100 text-amber-700",
  }[type] ?? "bg-gray-100 text-gray-600";
}

function typeLabel(type: EntityType): string {
  return t(`entities.type_${type}`);
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-xl font-bold text-gray-900">{{ t("entities.admin_title") }}</h1>
      <p class="mt-1 text-sm text-gray-500">{{ t("entities.admin_subtitle") }}</p>
    </div>

    <!-- Tabs -->
    <div class="mb-6 flex gap-4 border-b border-gray-200">
      <button
        v-for="tab in (['admin', 'reindex'] as Tab[])"
        :key="tab"
        class="pb-2 text-sm font-medium transition-colors"
        :class="activeTab === tab
          ? 'border-b-2 border-indigo-600 text-indigo-600'
          : 'text-gray-500 hover:text-gray-700'"
        @click="activeTab = tab"
      >
        {{ t(`entities.tab_${tab}`) }}
      </button>
    </div>

    <!-- ── Admin tab ─────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'admin'">
      <!-- Filters -->
      <div class="mb-4 flex flex-wrap items-center gap-3">
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
        <label class="flex items-center gap-1.5 text-sm text-gray-600">
          <input v-model="filterUnlinked" type="checkbox" />
          {{ t("entities.unlinked_only") }}
        </label>
        <button
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          @click="fetchEntities(1)"
        >
          {{ t("entities.search_placeholder").replace("...", "") }}
        </button>
        <button
          class="ml-auto rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          @click="openMerge"
        >
          {{ t("entities.merge_title") }}
        </button>
      </div>

      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>
      <p v-if="isLoading" class="text-sm text-gray-400">{{ t("common.loading") }}</p>

      <!-- Entity table -->
      <div v-if="!isLoading" class="space-y-2">
        <p v-if="entities.length === 0" class="text-sm text-gray-500">{{ t("entities.empty") }}</p>

        <div
          v-for="entity in entities"
          :key="entity.id"
          class="flex items-center justify-between gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm"
          :class="selectedEntity?.id === entity.id ? 'border-indigo-300 ring-1 ring-indigo-200' : ''"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
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
            <div v-if="entity.authority_ref" class="mt-0.5 truncate font-mono text-xs text-indigo-600">
              {{ entity.authority_ref }}
            </div>
            <div v-else class="mt-0.5 text-xs text-gray-400">{{ t("entities.no_authority") }}</div>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
              @click="openOccurrences(entity)"
            >
              {{ t("entities.occurrences_title") }}
            </button>
            <button
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
              @click="openEdit(entity)"
            >
              {{ t("entities.edit") }}
            </button>
            <button
              class="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
              @click="deleteEntity(entity)"
            >
              {{ t("entities.delete") }}
            </button>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="pagination.total_pages > 1" class="mt-4 flex items-center justify-center gap-3 text-sm">
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

      <!-- Occurrences panel (slide-in below selected entity) -->
      <div
        v-if="selectedEntity"
        class="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 p-4"
      >
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-indigo-800">
            {{ t("entities.occurrences_title") }} —
            <span class="font-normal">{{ selectedEntity.canonical_form }}</span>
          </h2>
          <button class="text-xs text-gray-500 hover:text-gray-700" @click="closeOccurrences">
            {{ t("entities.occurrences_close") }}
          </button>
        </div>
        <p v-if="isLoadingOccurrences" class="text-xs text-gray-500">{{ t("common.loading") }}</p>
        <p v-else-if="occurrences.length === 0" class="text-xs text-gray-500">
          {{ t("entities.occurrences_empty") }}
        </p>
        <div v-else class="space-y-2">
          <div
            v-for="occ in occurrences"
            :key="occ.id"
            class="rounded border border-indigo-100 bg-white p-3 text-xs"
          >
            <div class="flex items-start justify-between gap-2">
              <div>
                <span class="font-medium text-indigo-700">{{ occ.raw_form }}</span>
                <span class="ml-2 text-gray-400">
                  {{ t("entities.occurrences_in", {
                    collection: occ.collection_title,
                    filename: occ.filename
                  }) }}
                </span>
              </div>
              <router-link
                :to="{ name: 'document-view', params: { slug: occ.collection_slug, filename: occ.filename } }"
                class="shrink-0 text-indigo-600 hover:underline"
                target="_blank"
              >
                {{ t("entities.view_in_doc") }}
              </router-link>
            </div>
            <p v-if="occ.context" class="mt-1 text-gray-500 italic">
              "{{ occ.context }}"
            </p>
          </div>
          <!-- Occurrences pagination -->
          <div
            v-if="occurrencesPagination.total_pages > 1"
            class="flex items-center justify-center gap-3 pt-1 text-xs"
          >
            <button
              :disabled="occurrencesPagination.page <= 1"
              class="rounded border px-2 py-0.5 disabled:opacity-40"
              @click="fetchOccurrences(selectedEntity!.id, occurrencesPagination.page - 1)"
            >←</button>
            <span>{{ occurrencesPagination.page }} / {{ occurrencesPagination.total_pages }}</span>
            <button
              :disabled="occurrencesPagination.page >= occurrencesPagination.total_pages"
              class="rounded border px-2 py-0.5 disabled:opacity-40"
              @click="fetchOccurrences(selectedEntity!.id, occurrencesPagination.page + 1)"
            >→</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Re-index tab ───────────────────────────────────────────────────── -->
    <div v-else-if="activeTab === 'reindex'" class="max-w-md">
      <h2 class="mb-4 text-base font-semibold text-gray-900">{{ t("entities.reindex_title") }}</h2>
      <p class="mb-4 text-sm text-gray-500">
        Wipes all existing entity occurrences for the collection and rebuilds the
        index by re-running the XQuery extractor on every document.
      </p>
      <div class="space-y-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-600">
            {{ t("entities.reindex_collection_label") }}
          </label>
          <input
            v-model="reindexSlug"
            :placeholder="t('entities.reindex_collection_placeholder')"
            class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <p v-if="reindexError" class="text-sm text-red-600">{{ reindexError }}</p>
        <p v-if="reindexResult" class="text-sm text-green-700">{{ reindexResult }}</p>
        <button
          :disabled="isReindexing || !reindexSlug.trim()"
          class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="submitReindex"
        >
          {{ isReindexing ? t("common.loading") : t("entities.reindex_submit") }}
        </button>
      </div>
    </div>

    <!-- ── Edit modal ─────────────────────────────────────────────────────── -->
    <div
      v-if="editingEntity"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="closeEdit"
    >
      <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-4 text-base font-semibold text-gray-900">{{ t("entities.edit_title") }}</h2>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("entities.field_canonical_form") }}
            </label>
            <input
              v-model="editCanonicalForm"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("entities.field_authority_ref") }}
              <span class="font-normal text-gray-400">
                ({{ t("entities.field_authority_ref_hint") }})
              </span>
            </label>
            <input
              v-model="editAuthorityRef"
              placeholder="https://viaf.org/viaf/..."
              class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
        <p v-if="editError" class="mt-3 text-xs text-red-600">{{ editError }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <button
            class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            @click="closeEdit"
          >
            {{ t("common.cancel") }}
          </button>
          <button
            :disabled="isSaving"
            class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            @click="saveEdit"
          >
            {{ isSaving ? t("common.loading") : t("common.save") }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── Merge modal ────────────────────────────────────────────────────── -->
    <div
      v-if="showMerge"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="closeMerge"
    >
      <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-2 text-base font-semibold text-gray-900">{{ t("entities.merge_title") }}</h2>
        <p class="mb-4 text-xs text-gray-500">{{ t("entities.merge_confirm") }}</p>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("entities.merge_source_label") }}
            </label>
            <input
              v-model="mergeSourceId"
              placeholder="UUID of source entity"
              class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("entities.merge_target_label") }}
            </label>
            <input
              v-model="mergeTargetId"
              placeholder="UUID of target entity"
              class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
        <p v-if="mergeError" class="mt-3 text-xs text-red-600">{{ mergeError }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <button
            class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            @click="closeMerge"
          >
            {{ t("common.cancel") }}
          </button>
          <button
            :disabled="isMerging"
            class="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            @click="submitMerge"
          >
            {{ isMerging ? t("common.loading") : t("entities.merge_submit") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
