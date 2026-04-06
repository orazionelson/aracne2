<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useCollectionStore, type ZipUploadResult } from "@/stores/collections";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useCollectionStore();

const slug = route.params.slug as string;
const isLoading = ref(true);
const error = ref<string | null>(null);

// ── Edit form ─────────────────────────────────────────────────────────────────
const editing = ref(false);
const editTitle = ref("");
const editDesc = ref("");
const editPublic = ref(false);
const isSaving = ref(false);
const saveError = ref<string | null>(null);

function startEdit(): void {
  if (!store.current) return;
  editTitle.value = store.current.title;
  editDesc.value = store.current.description ?? "";
  editPublic.value = store.current.is_public;
  editing.value = true;
}

async function submitEdit(): Promise<void> {
  saveError.value = null;
  isSaving.value = true;
  try {
    await store.updateCollection(slug, {
      title: editTitle.value.trim(),
      description: editDesc.value.trim() || undefined,
      is_public: editPublic.value,
    });
    editing.value = false;
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

// ── Workflow ──────────────────────────────────────────────────────────────────
const workflowNote = ref("");
const workflowError = ref<string | null>(null);
const isActing = ref(false);
const showRejectForm = ref(false);
const rejectNote = ref("");

const isEiC = computed(() => auth.hasMinRole("EditorInChief"));
const isAdmin = computed(() => auth.hasMinRole("Admin"));
const isAssignedEditor = computed(
  () => !!auth.user && auth.user.id === store.current?.editor_id,
);

// ── Assign ───────────────────────────────────────────────────────────────────
const showAssignForm = ref(false);
const assignUsername = ref("");
const assignNote = ref("");
const isAssigning = ref(false);
const assignError = ref<string | null>(null);
const isEditorDropdownOpen = ref(false);

// Resolve username → UUID from the loaded editors list.
const resolvedEditorId = computed(() => {
  const match = store.editors.find((e) => e.username === assignUsername.value.trim());
  return match?.id ?? null;
});

const filteredEditors = computed(() => {
  const q = assignUsername.value.toLowerCase().trim();
  if (!q) return store.editors;
  return store.editors.filter(
    (e) =>
      e.username.toLowerCase().includes(q) ||
      (e.display_name?.toLowerCase().includes(q) ?? false),
  );
});

function selectEditor(e: { id: string; username: string; display_name: string | null }): void {
  assignUsername.value = e.username;
  isEditorDropdownOpen.value = false;
}

function closeEditorDropdown(): void {
  // Delay so mousedown on an option fires before blur closes the list.
  window.setTimeout(() => { isEditorDropdownOpen.value = false }, 150);
}

watch(showAssignForm, async (open) => {
  if (open && store.editors.length === 0) {
    await store.fetchEditors();
  }
});

async function submitAssign(): Promise<void> {
  assignError.value = null;
  if (!resolvedEditorId.value) {
    assignError.value = t("collections.assign_user_not_found");
    return;
  }
  isAssigning.value = true;
  try {
    await store.assignCollection(slug, resolvedEditorId.value, assignNote.value.trim());
    showAssignForm.value = false;
    assignUsername.value = "";
    assignNote.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    assignError.value = msg ?? t("common.error");
  } finally {
    isAssigning.value = false;
  }
}

async function doWorkflow(
  action: () => Promise<void>,
): Promise<void> {
  workflowError.value = null;
  isActing.value = true;
  try {
    await action();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    workflowError.value = msg ?? t("common.error");
  } finally {
    isActing.value = false;
  }
}

async function handleSubmit(): Promise<void> {
  await doWorkflow(() => store.submitCollection(slug, workflowNote.value.trim() || undefined));
  workflowNote.value = "";
}

async function handleReject(): Promise<void> {
  if (!rejectNote.value.trim()) return;
  await doWorkflow(() => store.rejectCollection(slug, rejectNote.value.trim()));
  showRejectForm.value = false;
  rejectNote.value = "";
}

async function handlePublish(): Promise<void> {
  await doWorkflow(() => store.publishCollection(slug, workflowNote.value.trim() || undefined));
  workflowNote.value = "";
}

async function handleUnpublish(): Promise<void> {
  if (!confirm(t("collections.confirm_unpublish"))) return;
  await doWorkflow(() => store.unpublishCollection(slug));
}

// ── Documents ─────────────────────────────────────────────────────────────────
const docError = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const zipInput = ref<HTMLInputElement | null>(null);
const isUploading = ref(false);
const isUploadingZip = ref(false);
const uploadProgress = ref({ done: 0, total: 0 });
const zipResult = ref<ZipUploadResult | null>(null);

const canWrite = computed(
  () =>
    isEiC.value ||
    (isAssignedEditor.value && store.current?.status === "assigned"),
);

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (files.length === 0) return;
  docError.value = null;
  isUploading.value = true;
  uploadProgress.value = { done: 0, total: files.length };
  const errors: string[] = [];
  for (const file of files) {
    try {
      await store.uploadDocument(slug, file);
    } catch (err) {
      const msg = (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message;
      errors.push(`${file.name}: ${msg ?? t("common.error")}`);
    }
    uploadProgress.value.done += 1;
  }
  isUploading.value = false;
  uploadProgress.value = { done: 0, total: 0 };
  if (fileInput.value) fileInput.value.value = "";
  if (errors.length > 0) docError.value = errors.join(" — ");
}

async function onZipSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  docError.value = null;
  zipResult.value = null;
  isUploadingZip.value = true;
  try {
    zipResult.value = await store.uploadZip(slug, file);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    docError.value = msg ?? t("common.error");
  } finally {
    isUploadingZip.value = false;
    if (zipInput.value) zipInput.value.value = "";
  }
}

async function handleDownload(filename: string): Promise<void> {
  try {
    await store.downloadDocument(slug, filename);
  } catch {
    alert(t("common.error"));
  }
}

async function handleDeleteDoc(filename: string): Promise<void> {
  if (!confirm(t("collections.confirm_delete_document"))) return;
  docError.value = null;
  try {
    await store.deleteDocument(slug, filename);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    docError.value = msg ?? t("common.error");
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
const searchQuery = ref("");
const searchResults = ref<{ filename: string; snippet: string }[]>([]);
const isSearching = ref(false);
const searchError = ref<string | null>(null);
const searchDone = ref(false);

async function handleSearch(): Promise<void> {
  if (!searchQuery.value.trim()) return;
  searchError.value = null;
  isSearching.value = true;
  searchDone.value = false;
  try {
    searchResults.value = await store.searchDocuments(slug, searchQuery.value.trim());
    searchDone.value = true;
  } catch {
    searchError.value = t("common.error");
  } finally {
    isSearching.value = false;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    await Promise.all([store.fetchCollection(slug), store.fetchDocuments(slug)]);
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});

function statusClass(s: string): string {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600",
    assigned: "bg-blue-100 text-blue-700",
    review: "bg-amber-100 text-amber-700",
    published: "bg-green-100 text-green-700",
  };
  return map[s] ?? "bg-gray-100 text-gray-600";
}
</script>

<template>
  <div class="mx-auto max-w-4xl px-4 py-8">
    <!-- Back -->
    <button
      class="mb-6 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800"
      @click="router.push({ name: 'collections' })"
    >
      ← {{ t("collections.title") }}
    </button>

    <p v-if="isLoading" class="text-sm text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <template v-else-if="store.current">
      <!-- Collection header -->
      <div class="mb-6">
        <div class="flex items-start justify-between">
          <div>
            <div class="flex items-center gap-3">
              <h1 class="text-2xl font-bold text-gray-900">{{ store.current.title }}</h1>
              <span
                class="rounded px-2 py-0.5 text-xs font-semibold"
                :class="statusClass(store.current.status)"
              >
                {{ t(`collections.status_${store.current.status}`) }}
              </span>
              <span v-if="store.current.is_public" class="text-xs text-gray-400">
                {{ t("collections.public_badge") }}
              </span>
            </div>
            <p class="mt-1 font-mono text-sm text-gray-500">{{ store.current.slug }}</p>
            <p v-if="store.current.description" class="mt-2 text-sm text-gray-700">
              {{ store.current.description }}
            </p>
            <p class="mt-1 text-xs text-gray-400">
              {{ t("collections.editor_label") }}:
              {{
                store.editors.find((e) => e.id === store.current!.editor_id)?.username
                ?? (store.current.editor_id ? store.current.editor_id : t("collections.unassigned"))
              }}
            </p>
          </div>
          <button
            v-if="isEiC && !editing"
            class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
            @click="startEdit"
          >
            {{ t("collections.edit") }}
          </button>
        </div>
      </div>

      <!-- Edit form -->
      <section v-if="editing" class="mb-6 rounded border border-gray-200 bg-gray-50 p-5">
        <h2 class="mb-4 text-sm font-semibold text-gray-700">{{ t("collections.edit") }}</h2>
        <form class="space-y-3" @submit.prevent="submitEdit">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("collections.title_label") }}
            </label>
            <input
              v-model="editTitle"
              required
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("collections.description") }}
            </label>
            <textarea
              v-model="editDesc"
              rows="2"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div class="flex items-center gap-2">
            <input id="edit-public" v-model="editPublic" type="checkbox" />
            <label for="edit-public" class="text-sm text-gray-700">
              {{ t("collections.is_public") }}
            </label>
          </div>
          <p v-if="saveError" class="text-sm text-red-600">{{ saveError }}</p>
          <div class="flex gap-3">
            <button
              type="submit"
              :disabled="isSaving"
              class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {{ isSaving ? t("common.loading") : t("common.save") }}
            </button>
            <button
              type="button"
              class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
              @click="editing = false"
            >
              {{ t("common.cancel") }}
            </button>
          </div>
        </form>
      </section>

      <!-- Workflow section -->
      <section class="mb-6 rounded border border-gray-200 p-5">
        <h2 class="mb-4 text-sm font-semibold text-gray-700">{{ t("collections.workflow") }}</h2>
        <p v-if="workflowError" class="mb-3 text-sm text-red-600">{{ workflowError }}</p>

        <!-- Assign / Reassign (EiC+, draft or assigned) -->
        <div
          v-if="isEiC && (store.current.status === 'draft' || store.current.status === 'assigned')"
          class="mb-4"
        >
          <button
            class="mb-2 rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
            @click="showAssignForm = !showAssignForm"
          >
            {{ store.current.status === "assigned" ? t("collections.reassign_editor") : t("collections.assign_editor") }}
          </button>
          <form v-if="showAssignForm" class="mt-2 space-y-2" @submit.prevent="submitAssign">
            <div class="relative">
              <input
                v-model="assignUsername"
                required
                autocomplete="off"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                :placeholder="t('collections.assign_username')"
                @focus="isEditorDropdownOpen = true"
                @blur="closeEditorDropdown"
                @input="isEditorDropdownOpen = true"
              />
              <ul
                v-if="isEditorDropdownOpen && filteredEditors.length > 0"
                class="absolute z-20 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto"
              >
                <li
                  v-for="e in filteredEditors"
                  :key="e.id"
                  class="cursor-pointer px-3 py-2 text-sm hover:bg-indigo-50"
                  @mousedown.prevent="selectEditor(e)"
                >
                  <span class="font-medium">{{ e.username }}</span>
                  <span v-if="e.display_name" class="ml-2 text-xs text-gray-500">
                    {{ e.display_name }}
                  </span>
                </li>
              </ul>
            </div>
            <input
              v-model="assignNote"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              :placeholder="t('collections.assign_note')"
            />
            <p v-if="assignError" class="text-sm text-red-600">{{ assignError }}</p>
            <div class="flex gap-2">
              <button
                type="submit"
                :disabled="isAssigning"
                class="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {{ isAssigning ? t("common.loading") : t("collections.assign_submit") }}
              </button>
              <button
                type="button"
                class="text-sm text-gray-500 hover:text-gray-700"
                @click="showAssignForm = false"
              >
                {{ t("common.cancel") }}
              </button>
            </div>
          </form>
        </div>

        <!-- Submit for review (assigned editor only) -->
        <div v-if="isAssignedEditor && store.current.status === 'assigned'" class="mb-4">
          <p class="mb-2 text-sm text-gray-600">{{ t("collections.submit_hint") }}</p>
          <div class="flex items-center gap-2">
            <input
              v-model="workflowNote"
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              :placeholder="t('collections.workflow_note_optional')"
            />
            <button
              :disabled="isActing"
              class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              @click="handleSubmit"
            >
              {{ t("collections.submit_for_review") }}
            </button>
          </div>
        </div>

        <!-- Publish / Reject (EiC+, review) -->
        <div v-if="isEiC && store.current.status === 'review'" class="space-y-3">
          <div class="flex items-center gap-2">
            <input
              v-model="workflowNote"
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              :placeholder="t('collections.workflow_note_optional')"
            />
            <button
              :disabled="isActing"
              class="rounded bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              @click="handlePublish"
            >
              {{ t("collections.publish") }}
            </button>
            <button
              class="rounded border border-red-300 px-4 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
              @click="showRejectForm = !showRejectForm"
            >
              {{ t("collections.reject") }}
            </button>
          </div>
          <div v-if="showRejectForm" class="flex items-center gap-2">
            <input
              v-model="rejectNote"
              required
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              :placeholder="t('collections.reject_note')"
            />
            <button
              :disabled="isActing || !rejectNote.trim()"
              class="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              @click="handleReject"
            >
              {{ t("collections.reject_submit") }}
            </button>
          </div>
        </div>

        <!-- Unpublish (Admin, published) -->
        <div v-if="isAdmin && store.current.status === 'published'">
          <button
            :disabled="isActing"
            class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
            @click="handleUnpublish"
          >
            {{ t("collections.unpublish") }}
          </button>
        </div>

        <!-- Quiescent state messages -->
        <p
          v-if="
            store.current.status === 'published' && !isAdmin &&
            store.current.status === 'draft' && !isEiC
          "
          class="text-sm text-gray-400"
        >
          {{ t("collections.no_actions") }}
        </p>
      </section>

      <!-- Documents section -->
      <section class="rounded border border-gray-200 p-5">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-700">{{ t("collections.documents") }}</h2>
          <div v-if="canWrite" class="flex gap-2">
            <button
              :disabled="isUploading || isUploadingZip"
              class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
              @click="fileInput?.click()"
            >
              <span v-if="isUploading && uploadProgress.total > 1">
                {{ uploadProgress.done }}/{{ uploadProgress.total }}
              </span>
              <span v-else-if="isUploading">{{ t("common.loading") }}</span>
              <span v-else>{{ t("collections.upload") }}</span>
            </button>
            <button
              :disabled="isUploading || isUploadingZip"
              class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
              @click="zipInput?.click()"
            >
              {{ isUploadingZip ? t("common.loading") : t("collections.upload_zip") }}
            </button>
          </div>
          <input
            ref="fileInput"
            type="file"
            accept=".xml,application/xml,text/xml"
            multiple
            class="hidden"
            @change="onFileSelected"
          />
          <input
            ref="zipInput"
            type="file"
            accept=".zip,application/zip"
            class="hidden"
            @change="onZipSelected"
          />
        </div>

        <p v-if="canWrite" class="mb-3 text-xs text-gray-400">
          {{ t("collections.upload_hint") }}
        </p>

        <!-- ZIP upload result summary -->
        <div
          v-if="zipResult"
          class="mb-3 rounded border border-gray-200 bg-gray-50 px-4 py-3 text-sm"
        >
          <p class="font-medium text-gray-700">
            {{ t("collections.zip_result_uploaded", { n: zipResult.uploaded }) }}
            <span v-if="zipResult.skipped.length > 0" class="ml-2 text-gray-400">
              {{ t("collections.zip_result_skipped", { n: zipResult.skipped.length }) }}
            </span>
          </p>
          <ul v-if="zipResult.errors.length > 0" class="mt-2 space-y-0.5">
            <li
              v-for="e in zipResult.errors"
              :key="e.filename"
              class="text-xs text-red-600"
            >
              {{ e.filename }}: {{ e.error }}
            </li>
          </ul>
        </div>

        <p v-if="docError" class="mb-3 text-sm text-red-600">{{ docError }}</p>

        <!-- Search -->
        <div class="mb-4 flex gap-2">
          <input
            v-model="searchQuery"
            class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            :placeholder="t('collections.search_placeholder')"
            @keyup.enter="handleSearch"
          />
          <button
            :disabled="isSearching || !searchQuery.trim()"
            class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
            @click="handleSearch"
          >
            {{ isSearching ? t("common.loading") : t("collections.search_button") }}
          </button>
        </div>

        <!-- Search results -->
        <div v-if="searchDone" class="mb-4">
          <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            {{ t("collections.search_results") }}
          </p>
          <p
            v-if="searchResults.length === 0"
            class="text-sm text-gray-500"
          >
            {{ t("collections.no_results", { q: searchQuery }) }}
          </p>
          <ul v-else class="space-y-2">
            <li
              v-for="hit in searchResults"
              :key="hit.filename"
              class="rounded border border-gray-100 bg-gray-50 px-3 py-2"
            >
              <p class="font-mono text-sm font-medium text-gray-800">{{ hit.filename }}</p>
              <p class="mt-0.5 text-xs text-gray-500">…{{ hit.snippet }}…</p>
            </li>
          </ul>
        </div>
        <p v-if="searchError" class="mb-3 text-sm text-red-600">{{ searchError }}</p>

        <!-- Document list -->
        <div v-if="store.documents.length === 0" class="text-sm text-gray-500">
          {{ t("collections.no_documents") }}
        </div>
        <ul v-else class="divide-y divide-gray-100">
          <li
            v-for="doc in store.documents"
            :key="doc.filename"
            class="flex items-center justify-between py-2"
          >
            <span class="font-mono text-sm text-gray-800">{{ doc.filename }}</span>
            <div class="flex gap-3">
              <button
                class="text-xs text-indigo-600 hover:text-indigo-800"
                @click="handleDownload(doc.filename)"
              >
                {{ t("collections.download") }}
              </button>
              <button
                v-if="canWrite"
                class="text-xs text-red-500 hover:text-red-700"
                @click="handleDeleteDoc(doc.filename)"
              >
                {{ t("collections.delete_document") }}
              </button>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
