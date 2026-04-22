<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useCollectionStore, type CollectionStatus } from "@/stores/collections";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const store = useCollectionStore();

const page = ref(1);
const search = ref("");
const statusFilter = ref<CollectionStatus | "">("");
const error = ref<string | null>(null);

// ── Create panel ──────────────────────────────────────────────────────────────
const showCreate = ref(false);
const newSlug = ref("");
const newTitle = ref("");
const newDesc = ref("");
const newPublic = ref(false);
const isCreating = ref(false);
const createError = ref<string | null>(null);

function statusClass(s: string): string {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    assigned: "bg-blue-100 text-blue-700",
    review: "bg-amber-100 text-amber-700",
    published: "bg-green-100 text-green-700",
  };
  return map[s] ?? "bg-gray-100 text-gray-600";
}

async function load(): Promise<void> {
  error.value = null;
  try {
    await store.fetchCollections(
      page.value,
      statusFilter.value || undefined,
      search.value || undefined,
    );
  } catch {
    error.value = t("common.error");
  }
}

onMounted(load);
watch([page, statusFilter], load);

let searchTimeout: ReturnType<typeof setTimeout>;
function onSearchInput(): void {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    page.value = 1;
    load();
  }, 300);
}

async function submitCreate(): Promise<void> {
  createError.value = null;
  isCreating.value = true;
  try {
    const col = await store.createCollection({
      slug: newSlug.value.trim(),
      title: newTitle.value.trim(),
      description: newDesc.value.trim() || undefined,
      is_public: newPublic.value,
    });
    showCreate.value = false;
    newSlug.value = "";
    newTitle.value = "";
    newDesc.value = "";
    newPublic.value = false;
    router.push({ name: "collection-detail", params: { slug: col.slug } });
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    createError.value = msg ?? t("common.error");
  } finally {
    isCreating.value = false;
  }
}

async function confirmDelete(id: string, title: string): Promise<void> {
  if (!confirm(`${t("collections.confirm_delete")}\n\n"${title}"`)) return;
  try {
    await store.deleteCollection(id);
  } catch {
    alert(t("common.error"));
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-8">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("collections.title") }}</h1>
      <button
        v-if="auth.hasMinRole('EditorInChief')"
        class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="showCreate = !showCreate"
      >
        + {{ t("collections.new") }}
      </button>
    </div>

    <!-- Create panel -->
    <div v-if="showCreate" class="mb-6 rounded border border-gray-200 bg-gray-50 p-5">
      <h2 class="mb-4 text-sm font-semibold text-gray-700">{{ t("collections.create_title") }}</h2>
      <form class="grid grid-cols-2 gap-4" @submit.prevent="submitCreate">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-600">
            {{ t("collections.slug") }}
          </label>
          <input
            v-model="newSlug"
            required
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            placeholder="my-collection"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-600">
            {{ t("collections.title_label") }}
          </label>
          <input
            v-model="newTitle"
            required
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-gray-600">
            {{ t("collections.description") }}
          </label>
          <textarea
            v-model="newDesc"
            rows="2"
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div class="flex items-center gap-2">
          <input id="new-public" v-model="newPublic" type="checkbox" />
          <label for="new-public" class="text-sm text-gray-700">
            {{ t("collections.is_public") }}
          </label>
        </div>
        <div v-if="createError" class="col-span-2 text-sm text-red-600">{{ createError }}</div>
        <div class="col-span-2 flex gap-3">
          <button
            type="submit"
            :disabled="isCreating"
            class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {{ isCreating ? t("common.loading") : t("collections.create_submit") }}
          </button>
          <button
            type="button"
            class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
            @click="showCreate = false"
          >
            {{ t("common.cancel") }}
          </button>
        </div>
      </form>
    </div>

    <!-- Filters -->
    <div class="mb-4 flex gap-3">
      <input
        v-model="search"
        class="w-64 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
        :placeholder="t('collections.search_placeholder')"
        @input="onSearchInput"
      />
      <select
        v-model="statusFilter"
        class="rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
        @change="page = 1"
      >
        <option value="">{{ t("collections.all_statuses") }}</option>
        <option value="draft">{{ t("collections.status_draft") }}</option>
        <option value="assigned">{{ t("collections.status_assigned") }}</option>
        <option value="review">{{ t("collections.status_review") }}</option>
        <option value="published">{{ t("collections.status_published") }}</option>
      </select>
    </div>

    <!-- Error -->
    <p v-if="error" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ error }}</p>

    <!-- Loading -->
    <p v-if="store.isLoading" class="text-sm text-gray-500 dark:text-gray-400">{{ t("common.loading") }}</p>

    <!-- Table -->
    <template v-else>
      <div v-if="store.collections.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
        {{ t("collections.no_collections") }}
      </div>
      <table v-else class="w-full border-collapse text-sm">
        <thead>
          <tr class="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th class="py-2 pr-4">{{ t("collections.title_label") }}</th>
            <th class="py-2 pr-4">{{ t("collections.slug") }}</th>
            <th class="py-2 pr-4">{{ t("collections.status") }}</th>
            <th class="py-2 pr-4">{{ t("collections.is_public") }}</th>
            <th class="py-2 pr-4">{{ t("collections.created_at") }}</th>
            <th class="py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="col in store.collections"
            :key="col.id"
            class="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
          >
            <td class="py-2 pr-4 font-medium text-gray-900 dark:text-gray-100">
              <router-link
                :to="{ name: 'collection-detail', params: { slug: col.slug } }"
                class="hover:text-indigo-600 hover:underline dark:hover:text-indigo-400"
              >
                {{ col.title }}
              </router-link>
            </td>
            <td class="py-2 pr-4 font-mono text-gray-500 dark:text-gray-400">{{ col.slug }}</td>
            <td class="py-2 pr-4">
              <span
                class="rounded px-2 py-0.5 text-xs font-medium"
                :class="statusClass(col.status)"
              >
                {{ t(`collections.status_${col.status}`) }}
              </span>
            </td>
            <td class="py-2 pr-4 text-gray-500 dark:text-gray-400">{{ col.is_public ? "✓" : "—" }}</td>
            <td class="py-2 pr-4 text-gray-500 dark:text-gray-400">
              {{ new Date(col.created_at).toLocaleDateString() }}
            </td>
            <td class="py-2 text-right">
              <button
                v-if="auth.hasMinRole('Admin')"
                class="text-xs text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                @click="confirmDelete(col.id, col.title)"
              >
                {{ t("common.delete") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div
        v-if="store.pagination && store.pagination.total_pages > 1"
        class="mt-4 flex items-center gap-2 text-sm"
      >
        <button
          :disabled="page <= 1"
          class="rounded border border-gray-300 px-3 py-1 text-gray-700 disabled:opacity-40 dark:border-gray-700 dark:text-gray-200"
          @click="page--"
        >
          ‹
        </button>
        <span class="text-gray-600 dark:text-gray-300">
          {{ page }} / {{ store.pagination.total_pages }}
        </span>
        <button
          :disabled="page >= store.pagination.total_pages"
          class="rounded border border-gray-300 px-3 py-1 text-gray-700 disabled:opacity-40 dark:border-gray-700 dark:text-gray-200"
          @click="page++"
        >
          ›
        </button>
      </div>
    </template>
  </div>
</template>
