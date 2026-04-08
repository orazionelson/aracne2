<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useViafAutocomplete } from "@/composables/useViafAutocomplete";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useCollectionStore, type ZipUploadResult, type DocumentMeta } from "@/stores/collections";
import { useBodyTemplateStore } from "@/stores/body_templates";
import { useSchemaStore } from "@/stores/schemas";
import { useLicenseStore } from "@/stores/licenses";
import { useCollectionValidationStore } from "@/stores/collection_validation";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const licenseStore = useLicenseStore();
const bodyTemplateStore = useBodyTemplateStore();
const validationStore = useCollectionValidationStore();

// ── Validation report expand state ────────────────────────────────────────────
const validationExpandedDoc = ref<string | null>(null);

function toggleValidationDoc(filename: string): void {
  validationExpandedDoc.value = validationExpandedDoc.value === filename ? null : filename;
}

async function handleValidateAll(): Promise<void> {
  await validationStore.startRun(slug);
}

onUnmounted(() => { validationStore.reset(); });

const slug = route.params.slug as string;
const isLoading = ref(true);
const error = ref<string | null>(null);

// ── Edit form ─────────────────────────────────────────────────────────────────
const editing = ref(false);
const editTitle = ref("");
const editDesc = ref("");
const editPublic = ref(false);
const editSchemaId = ref<string | null>(null);
const editPublisher = ref("");
const editPubPlace = ref("");
const editPubYear = ref<number | null>(null);
const editLicenseId = ref<string | null>(null);
const editHasSingleAuthor = ref(false);
const editAuthor = ref("");
const viaf = useViafAutocomplete();
const viafOpen = ref(false);
// Top-level computed so Vue auto-unwraps in template (avoids nested .value issues)
const viafResults = computed(() => viaf.results.value);
const viafLoading = computed(() => viaf.isLoading.value);

function onAuthorInput(e: Event): void {
  const val = (e.target as HTMLInputElement).value;
  editAuthor.value = val;
  viaf.search(val);
  viafOpen.value = true;
}

function selectViafName(name: string): void {
  editAuthor.value = name;
  viaf.clear();
  viafOpen.value = false;
}

function closeViafDropdown(): void {
  setTimeout(() => { viafOpen.value = false; }, 150);
}
const editHasSingleSource = ref(false);
const editMainSource = ref("");
const editHasMsIdentifier = ref(false);
const editMsIdentifier = ref("");
const editHasObjectDescForm = ref(false);
const editObjectDescForm = ref("");
const editBodyTemplateId = ref<string | null>(null);

const OBJECTDESC_FORMS = [
  "codex", "leaf", "roll", "tablet", "sheet", "fascicle", "fragment", "other",
] as const;
const editRespStmts = ref<{ resp: string; name: string }[]>([]);
// per-row autocomplete open state
const respNameOpen = ref<boolean[]>([]);

function filteredRespNamesFor(i: number): { id: string; label: string }[] {
  const q = (editRespStmts.value[i]?.name ?? "").toLowerCase();
  return store.editors
    .filter((e) => {
      const label = (e.display_name ?? e.username).toLowerCase();
      return !q || label.includes(q);
    })
    .map((e) => ({ id: e.id, label: e.display_name ?? e.username }));
}

function addRespStmt(): void {
  editRespStmts.value.push({ resp: "", name: "" });
  respNameOpen.value.push(false);
}

function removeRespStmt(i: number): void {
  editRespStmts.value.splice(i, 1);
  respNameOpen.value.splice(i, 1);
}

function closeRespNameDropdown(i: number): void {
  setTimeout(() => { respNameOpen.value[i] = false; }, 150);
}

function selectRespName(i: number, label: string): void {
  editRespStmts.value[i].name = label;
  respNameOpen.value[i] = false;
}
const isSaving = ref(false);
const saveError = ref<string | null>(null);

function startEdit(): void {
  if (!store.current) return;
  editTitle.value = store.current.title;
  editDesc.value = store.current.description ?? "";
  editPublic.value = store.current.is_public;
  editSchemaId.value = store.current.schema_id;
  editPublisher.value = store.current.publisher ?? "";
  editPubPlace.value = store.current.pub_place ?? "";
  editPubYear.value = store.current.pub_year ?? null;
  editLicenseId.value = store.current.license_id ?? null;
  editHasSingleAuthor.value = !!store.current.author;
  editAuthor.value = store.current.author ?? "";
  editHasSingleSource.value = !!store.current.listbibl_bibl_main;
  editMainSource.value = store.current.listbibl_bibl_main ?? "";
  editHasMsIdentifier.value = !!store.current.msidentifier_idno;
  editMsIdentifier.value = store.current.msidentifier_idno ?? "";
  editHasObjectDescForm.value = !!store.current.objectdesc_form;
  editObjectDescForm.value = store.current.objectdesc_form ?? "";
  editBodyTemplateId.value = store.current.body_template_id ?? null;
  editRespStmts.value = store.current.resp_stmts
    ? store.current.resp_stmts.map((r) => ({ ...r }))
    : [];
  respNameOpen.value = editRespStmts.value.map(() => false);
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
      schema_id: editSchemaId.value,
      publisher: editPublisher.value.trim() || null,
      pub_place: editPubPlace.value.trim() || null,
      pub_year: editPubYear.value,
      license_id: editLicenseId.value,
      resp_stmts: editRespStmts.value.length > 0
        ? editRespStmts.value.filter((r) => r.resp.trim() || r.name.trim())
        : null,
      author: editHasSingleAuthor.value ? (editAuthor.value.trim() || null) : null,
      listbibl_bibl_main: editHasSingleSource.value ? (editMainSource.value.trim() || null) : null,
      msidentifier_idno: editHasMsIdentifier.value ? (editMsIdentifier.value.trim() || null) : null,
      objectdesc_form: editHasObjectDescForm.value ? (editObjectDescForm.value || null) : null,
      body_template_id: editBodyTemplateId.value,
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

// ── New document ──────────────────────────────────────────────────────────────
const showNewDocForm = ref(false);
const newDocFilename = ref("");
const isCreatingDoc = ref(false);
const newDocError = ref<string | null>(null);

async function handleCreateDocument(): Promise<void> {
  const name = newDocFilename.value.trim();
  if (!name) return;
  const filename = name.endsWith(".xml") ? name : `${name}.xml`;
  newDocError.value = null;
  isCreatingDoc.value = true;
  try {
    const col = store.current;
    const lic = col?.license_id
      ? licenseStore.licenses.find((l) => l.id === col.license_id) ?? null
      : null;
    const meta: DocumentMeta = {
      publisher: col?.publisher,
      pub_place: col?.pub_place,
      pub_year: col?.pub_year,
      license_name: lic?.name ?? null,
      license_url: lic?.target ?? null,
      resp_stmts: col?.resp_stmts,
      author: col?.author,
      listbibl_bibl_main: col?.listbibl_bibl_main,
      msidentifier_idno: col?.msidentifier_idno,
      objectdesc_form: col?.objectdesc_form,
      body_snippet: col?.body_template_id
        ? (bodyTemplateStore.templates.find((t) => t.id === col.body_template_id)?.snippet ?? null)
        : null,
    };
    const doc = await store.createDocument(slug, filename, meta);
    showNewDocForm.value = false;
    newDocFilename.value = "";
    router.push({ name: "document-edit", params: { slug, filename: doc.filename } });
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    newDocError.value = msg ?? t("common.error");
  } finally {
    isCreatingDoc.value = false;
  }
}

// ── Pagination ────────────────────────────────────────────────────────────────
const PAGE_SIZES = [10, 25, 50, 100] as const;
const pageSize = ref<number>(25);
const currentPage = ref(1);

const totalPages = computed(() =>
  Math.max(1, Math.ceil(store.documents.length / pageSize.value)),
);
const paginatedDocuments = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return store.documents.slice(start, start + pageSize.value);
});

watch(pageSize, () => {
  currentPage.value = 1;
  selectedFilenames.value = [];
});

// ── Multi-select ──────────────────────────────────────────────────────────────
const selectedFilenames = ref<string[]>([]);
const isDeleting = ref(false);

const allPageSelected = computed(
  () =>
    paginatedDocuments.value.length > 0 &&
    paginatedDocuments.value.every((d) => selectedFilenames.value.includes(d.filename)),
);

function toggleSelectAll(): void {
  const pageNames = paginatedDocuments.value.map((d) => d.filename);
  if (allPageSelected.value) {
    selectedFilenames.value = selectedFilenames.value.filter((f) => !pageNames.includes(f));
  } else {
    selectedFilenames.value = [...new Set([...selectedFilenames.value, ...pageNames])];
  }
}

function goToPage(page: number): void {
  currentPage.value = page;
  selectedFilenames.value = [];
}

async function handleDeleteSelected(): Promise<void> {
  if (selectedFilenames.value.length === 0) return;
  if (!confirm(t("collections.confirm_delete_selected", { n: selectedFilenames.value.length }))) return;
  docError.value = null;
  isDeleting.value = true;
  const toDelete = [...selectedFilenames.value];
  const errors: string[] = [];
  for (const filename of toDelete) {
    try {
      await store.deleteDocument(slug, filename);
      selectedFilenames.value = selectedFilenames.value.filter((f) => f !== filename);
    } catch {
      errors.push(filename);
    }
  }
  isDeleting.value = false;
  if (errors.length > 0) docError.value = `${t("common.error")}: ${errors.join(", ")}`;
  // Clamp current page after deletions
  if (currentPage.value > totalPages.value) currentPage.value = totalPages.value;
}

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

function handleViewDoc(filename: string): void {
  router.push({ name: "document-view", params: { slug, filename } });
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

function resetSearch(): void {
  searchQuery.value = "";
  searchResults.value = [];
  searchDone.value = false;
  searchError.value = null;
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const tasks = [
      store.fetchCollection(slug),
      store.fetchDocuments(slug),
      schemaStore.fetchSchemas(),
      licenseStore.fetchLicenses(),
      bodyTemplateStore.fetchTemplates(),
    ];
    // The editors list (GET /users) requires EditorInChief or above.
    // Editors and Users must not call it — they cannot assign editors anyway.
    if (auth.hasMinRole("EditorInChief")) {
      tasks.push(store.fetchEditors());
      tasks.push(validationStore.fetchLatest(slug));
    }
    await Promise.all(tasks);
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
                (() => {
                  const ed = store.editors.find((e) => e.id === store.current!.editor_id);
                  return ed
                    ? (ed.display_name ?? ed.username)
                    : (store.current.editor_id ? store.current.editor_id : t("collections.unassigned"));
                })()
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
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-gray-600">
              {{ t("collections.schema_label") }}
            </label>
            <select
              v-model="editSchemaId"
              class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            >
              <option :value="null">{{ t("schemas.none") }}</option>
              <option v-for="s in schemaStore.schemas" :key="s.id" :value="s.id">
                {{ s.name }}
                <template v-if="s.validation_format"> ({{ s.validation_format.toUpperCase() }})</template>
              </option>
            </select>
          </div>
          <!-- Body template -->
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-gray-600">
              {{ t("collections.body_template_label") }}
            </label>
            <select
              v-model="editBodyTemplateId"
              class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            >
              <option :value="null">{{ t("collections.body_template_none") }}</option>
              <option
                v-for="tpl in bodyTemplateStore.templates"
                :key="tpl.id"
                :value="tpl.id"
              >
                {{ tpl.label }}
              </option>
            </select>
          </div>
          <!-- Single author -->
          <div class="border-t border-gray-200 pt-3">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-600">
                {{ t("collections.single_author_question") }}
              </span>
              <button
                type="button"
                class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                :class="editHasSingleAuthor ? 'bg-indigo-600' : 'bg-gray-200'"
                @click="editHasSingleAuthor = !editHasSingleAuthor; if (!editHasSingleAuthor) editAuthor = ''"
              >
                <span
                  class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                  :class="editHasSingleAuthor ? 'translate-x-4' : 'translate-x-0'"
                />
              </button>
            </div>
            <div v-if="editHasSingleAuthor" class="relative mt-2">
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("collections.author_label") }}
              </label>
              <div class="relative">
                <input
                  :value="editAuthor"
                  type="text"
                  autocomplete="off"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                  @input="onAuthorInput"
                  @focus="viafOpen = true"
                  @blur="closeViafDropdown"
                />
                <span
                  v-if="viafLoading"
                  class="absolute right-2 top-1.5 text-xs text-gray-400"
                >…</span>
              </div>
              <ul
                v-if="viafOpen && viafResults.length > 0"
                class="absolute z-30 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-56 overflow-y-auto"
              >
                <li
                  v-for="name in viafResults"
                  :key="name"
                  class="cursor-pointer px-3 py-2 text-sm hover:bg-indigo-50"
                  @mousedown.prevent="selectViafName(name)"
                >
                  {{ name }}
                </li>
              </ul>
            </div>
          </div>
          <!-- Single primary source -->
          <div class="border-t border-gray-200 pt-3">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-600">
                {{ t("collections.single_source_question") }}
              </span>
              <button
                type="button"
                class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                :class="editHasSingleSource ? 'bg-indigo-600' : 'bg-gray-200'"
                @click="editHasSingleSource = !editHasSingleSource; if (!editHasSingleSource) editMainSource = ''"
              >
                <span
                  class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                  :class="editHasSingleSource ? 'translate-x-4' : 'translate-x-0'"
                />
              </button>
            </div>
            <div v-if="editHasSingleSource" class="mt-2">
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("collections.main_source_label") }}
              </label>
              <input
                v-model="editMainSource"
                type="text"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
          <!-- Manuscript identifier -->
          <div class="border-t border-gray-200 pt-3">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-600">
                {{ t("collections.single_ms_question") }}
              </span>
              <button
                type="button"
                class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                :class="editHasMsIdentifier ? 'bg-indigo-600' : 'bg-gray-200'"
                @click="editHasMsIdentifier = !editHasMsIdentifier; if (!editHasMsIdentifier) editMsIdentifier = ''"
              >
                <span
                  class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                  :class="editHasMsIdentifier ? 'translate-x-4' : 'translate-x-0'"
                />
              </button>
            </div>
            <div v-if="editHasMsIdentifier" class="mt-2">
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("collections.ms_identifier_label") }}
              </label>
              <input
                v-model="editMsIdentifier"
                type="text"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
          <!-- Physical form (objectDesc) -->
          <div class="border-t border-gray-200 pt-3">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-600">
                {{ t("collections.objectdesc_form_question") }}
              </span>
              <button
                type="button"
                class="relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                :class="editHasObjectDescForm ? 'bg-indigo-600' : 'bg-gray-200'"
                @click="editHasObjectDescForm = !editHasObjectDescForm; if (!editHasObjectDescForm) editObjectDescForm = ''"
              >
                <span
                  class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                  :class="editHasObjectDescForm ? 'translate-x-4' : 'translate-x-0'"
                />
              </button>
            </div>
            <div v-if="editHasObjectDescForm" class="mt-2">
              <label class="mb-1 block text-xs font-medium text-gray-600">
                {{ t("collections.objectdesc_form_label") }}
              </label>
              <select
                v-model="editObjectDescForm"
                class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              >
                <option value="">—</option>
                <option v-for="f in OBJECTDESC_FORMS" :key="f" :value="f">{{ f }}</option>
              </select>
            </div>
          </div>
          <!-- Publication metadata -->
          <div class="border-t border-gray-200 pt-3">
            <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              publicationStmt
            </p>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.publisher_label") }}
                </label>
                <input
                  v-model="editPublisher"
                  type="text"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.pub_place_label") }}
                </label>
                <input
                  v-model="editPubPlace"
                  type="text"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.pub_year_label") }}
                </label>
                <input
                  v-model.number="editPubYear"
                  type="number"
                  min="1000"
                  max="9999"
                  placeholder="YYYY"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.availability_label") }}
                </label>
                <select
                  v-model="editLicenseId"
                  class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                >
                  <option :value="null">{{ t("collections.no_license") }}</option>
                  <option
                    v-for="lic in licenseStore.licenses.filter(l => l.is_active)"
                    :key="lic.id"
                    :value="lic.id"
                  >
                    {{ lic.name }}
                  </option>
                </select>
              </div>
            </div>
          </div>
          <!-- respStmt — one row per responsible party -->
          <div class="border-t border-gray-200 pt-3">
            <div class="mb-2 flex items-center justify-between">
              <p class="text-xs font-semibold uppercase tracking-wide text-gray-400">respStmt</p>
              <button
                type="button"
                class="text-xs text-indigo-600 hover:text-indigo-800"
                @click="addRespStmt"
              >
                + {{ t("collections.resp_stmts_add") }}
              </button>
            </div>
            <datalist id="resp-datalist">
              <option value="transcription by" />
              <option value="edited by" />
              <option value="mark-up by" />
              <option value="main editor" />
            </datalist>
            <div
              v-for="(row, i) in editRespStmts"
              :key="i"
              class="mb-2 grid grid-cols-2 gap-3 rounded border border-gray-100 bg-white p-2"
            >
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.resp_label") }}
                </label>
                <input
                  v-model="row.resp"
                  type="text"
                  list="resp-datalist"
                  autocomplete="off"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div class="relative">
                <label class="mb-1 block text-xs font-medium text-gray-600">
                  {{ t("collections.resp_name_label") }}
                </label>
                <input
                  v-model="row.name"
                  type="text"
                  autocomplete="off"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
                  @focus="respNameOpen[i] = true"
                  @blur="closeRespNameDropdown(i)"
                  @input="respNameOpen[i] = true"
                />
                <ul
                  v-if="respNameOpen[i] && filteredRespNamesFor(i).length > 0"
                  class="absolute z-20 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto"
                >
                  <li
                    v-for="opt in filteredRespNamesFor(i)"
                    :key="opt.id"
                    class="cursor-pointer px-3 py-2 text-sm hover:bg-indigo-50"
                    @mousedown.prevent="selectRespName(i, opt.label)"
                  >
                    {{ opt.label }}
                  </li>
                </ul>
              </div>
              <div class="col-span-2 flex justify-end">
                <button
                  type="button"
                  class="text-xs text-red-500 hover:text-red-700"
                  @click="removeRespStmt(i)"
                >
                  {{ t("collections.resp_stmts_remove") }}
                </button>
              </div>
            </div>
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
          <h2 class="text-sm font-semibold text-gray-700">
            {{ t("collections.documents") }}
            <span class="ml-1 font-normal text-gray-400">({{ store.documents.length }})</span>
          </h2>
          <div class="flex gap-2">
          <!-- Validate all — EiC+ only, collection must have a schema -->
          <button
            v-if="isEiC && store.current?.schema_id"
            :disabled="validationStore.isStarting || validationStore.currentRun?.status === 'pending' || validationStore.currentRun?.status === 'running'"
            class="rounded border border-violet-300 bg-violet-50 px-3 py-1.5 text-sm text-violet-700 hover:bg-violet-100 disabled:opacity-50"
            @click="handleValidateAll"
          >
            <span v-if="validationStore.currentRun?.status === 'running'">
              {{ t("collections.validate_all_running", { n: validationStore.currentRun.validated_count, total: validationStore.currentRun.doc_count }) }}
            </span>
            <span v-else-if="validationStore.currentRun?.status === 'pending'">
              {{ t("common.loading") }}
            </span>
            <span v-else>{{ t("collections.validate_all") }}</span>
          </button>
          <div v-if="canWrite" class="flex gap-2">
            <!-- New document -->
            <button
              class="rounded border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-700 hover:bg-indigo-100"
              @click="showNewDocForm = !showNewDocForm; newDocError = null"
            >
              {{ t("collections.new_document") }}
            </button>
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
          </div><!-- end outer flex gap-2 -->

          <!-- New document inline form -->
          <div
            v-if="showNewDocForm && canWrite"
            class="mt-3 flex items-center gap-2"
          >
            <input
              v-model="newDocFilename"
              type="text"
              :placeholder="t('collections.new_document_placeholder')"
              class="rounded border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
              @keydown.enter="handleCreateDocument"
              @keydown.esc="showNewDocForm = false"
            />
            <button
              :disabled="isCreatingDoc || !newDocFilename.trim()"
              class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-40"
              @click="handleCreateDocument"
            >
              {{ isCreatingDoc ? t("common.loading") : t("collections.new_document_create") }}
            </button>
            <button
              class="text-sm text-gray-400 hover:text-gray-700"
              @click="showNewDocForm = false"
            >
              {{ t("common.cancel") }}
            </button>
            <span v-if="newDocError" class="text-xs text-red-600">{{ newDocError }}</span>
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
          <div class="mb-2 flex items-center justify-between">
            <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">
              {{ t("collections.search_results") }}
            </p>
            <button
              class="text-xs text-gray-400 hover:text-gray-700"
              @click="resetSearch"
            >
              {{ t("collections.search_reset") }}
            </button>
          </div>
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
              <div class="flex items-center justify-between">
                <p class="font-mono text-sm font-medium text-gray-800">{{ hit.filename }}</p>
                <button
                  class="text-xs text-indigo-500 hover:text-indigo-700"
                  @click="handleViewDoc(hit.filename)"
                >
                  {{ t("collections.view_document") }}
                </button>
              </div>
              <p class="mt-0.5 text-xs text-gray-500">…{{ hit.snippet }}…</p>
            </li>
          </ul>
        </div>
        <p v-if="searchError" class="mb-3 text-sm text-red-600">{{ searchError }}</p>

        <!-- Document list -->
        <div v-if="store.documents.length === 0" class="text-sm text-gray-500">
          {{ t("collections.no_documents") }}
        </div>

        <template v-else>
          <!-- List controls: select-all + page size -->
          <div class="mb-1 flex items-center justify-between border-b border-gray-100 pb-2">
            <label v-if="canWrite" class="flex cursor-pointer items-center gap-2 text-xs text-gray-500">
              <input
                type="checkbox"
                :checked="allPageSelected"
                :indeterminate="selectedFilenames.length > 0 && !allPageSelected"
                class="cursor-pointer"
                @change="toggleSelectAll"
              />
              <span v-if="selectedFilenames.length > 0" class="font-medium text-indigo-600">
                {{ t("collections.selected_count", { n: selectedFilenames.length }) }}
              </span>
              <span v-else>{{ t("collections.select_all") }}</span>
            </label>
            <span v-else />

            <div class="flex items-center gap-2 text-xs text-gray-500">
              <button
                v-if="canWrite && selectedFilenames.length > 0"
                :disabled="isDeleting"
                class="rounded border border-red-300 px-2 py-0.5 text-red-600 hover:bg-red-50 disabled:opacity-50"
                @click="handleDeleteSelected"
              >
                {{ t("collections.delete_selected", { n: selectedFilenames.length }) }}
              </button>
              <select
                v-model.number="pageSize"
                class="rounded border border-gray-200 px-1 py-0.5 text-xs"
              >
                <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option>
              </select>
              <span>{{ t("collections.per_page") }}</span>
            </div>
          </div>

          <ul class="divide-y divide-gray-100">
            <li
              v-for="doc in paginatedDocuments"
              :key="doc.filename"
              class="flex items-center justify-between py-2"
              :class="selectedFilenames.includes(doc.filename) ? 'bg-indigo-50' : ''"
            >
              <div class="flex items-center gap-3">
                <input
                  v-if="canWrite"
                  type="checkbox"
                  :checked="selectedFilenames.includes(doc.filename)"
                  class="cursor-pointer"
                  @change="selectedFilenames.includes(doc.filename)
                    ? selectedFilenames.splice(selectedFilenames.indexOf(doc.filename), 1)
                    : selectedFilenames.push(doc.filename)"
                />
                <span class="font-mono text-sm text-gray-800">{{ doc.filename }}</span>
              </div>
              <div class="flex gap-3">
                <button
                  class="text-xs text-indigo-500 hover:text-indigo-700"
                  @click="handleViewDoc(doc.filename)"
                >
                  {{ t("collections.view_document") }}
                </button>
                <button
                  v-if="canWrite"
                  class="text-xs text-amber-600 hover:text-amber-800"
                  @click="router.push({ name: 'document-edit', params: { slug, filename: doc.filename } })"
                >
                  {{ t("collections.edit_document") }}
                </button>
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

          <!-- Pagination -->
          <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>
              {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, store.documents.length) }}
              / {{ store.documents.length }}
            </span>
            <div class="flex items-center gap-1">
              <button
                :disabled="currentPage === 1"
                class="rounded border px-2 py-0.5 disabled:opacity-40 hover:bg-gray-100"
                @click="goToPage(currentPage - 1)"
              >
                ←
              </button>
              <span class="px-2">{{ currentPage }} / {{ totalPages }}</span>
              <button
                :disabled="currentPage === totalPages"
                class="rounded border px-2 py-0.5 disabled:opacity-40 hover:bg-gray-100"
                @click="goToPage(currentPage + 1)"
              >
                →
              </button>
            </div>
          </div>
        </template>
      </section>

      <!-- Validation report panel — EiC+ only, shown when a run exists -->
      <section
        v-if="isEiC && validationStore.currentRun"
        class="rounded border border-violet-200 bg-violet-50 p-5"
      >
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-violet-800">
            {{ t("collections.validate_all_report") }}
          </h2>
          <!-- Summary badge -->
          <span
            v-if="validationStore.currentRun.status === 'done'"
            :class="[
              'rounded px-2 py-0.5 text-xs font-medium',
              validationStore.currentRun.error_count === 0
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700',
            ]"
          >
            {{
              validationStore.currentRun.error_count === 0
                ? t("collections.validate_all_done_ok", { total: validationStore.currentRun.doc_count })
                : t("collections.validate_all_done_errors", {
                    errors: validationStore.currentRun.error_count,
                    total: validationStore.currentRun.doc_count,
                  })
            }}
          </span>
          <span
            v-else-if="validationStore.currentRun.status === 'running'"
            class="text-xs text-violet-600"
          >
            {{ t("collections.validate_all_running", { n: validationStore.currentRun.validated_count, total: validationStore.currentRun.doc_count }) }}
          </span>
          <span
            v-else-if="validationStore.currentRun.status === 'failed'"
            class="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
          >
            {{ t("collections.validate_all_failed", { msg: validationStore.currentRun.error_message ?? '' }) }}
          </span>
        </div>

        <!-- Progress bar while running -->
        <div
          v-if="validationStore.currentRun.status === 'running' && validationStore.currentRun.doc_count > 0"
          class="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-violet-200"
        >
          <div
            class="h-full rounded-full bg-violet-500 transition-all duration-500"
            :style="{ width: `${(validationStore.currentRun.validated_count / validationStore.currentRun.doc_count) * 100}%` }"
          />
        </div>

        <!-- Per-document results -->
        <div
          v-if="validationStore.currentRun.results?.documents?.length"
          class="space-y-1"
        >
          <div
            v-for="doc in validationStore.currentRun.results.documents"
            :key="doc.filename"
            class="rounded border border-violet-100 bg-white"
          >
            <button
              class="flex w-full items-center justify-between px-3 py-2 text-left"
              @click="toggleValidationDoc(doc.filename)"
            >
              <span class="font-mono text-sm text-gray-700">{{ doc.filename }}</span>
              <span
                :class="[
                  'rounded px-2 py-0.5 text-xs font-medium',
                  doc.valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700',
                ]"
              >
                {{
                  doc.valid
                    ? t("collections.validate_all_valid")
                    : t("collections.validate_all_errors", { n: doc.errors.length })
                }}
              </span>
            </button>
            <!-- Error list (expanded) -->
            <div
              v-if="!doc.valid && validationExpandedDoc === doc.filename"
              class="border-t border-violet-100 px-3 pb-2"
            >
              <table class="w-full text-xs">
                <tbody>
                  <tr
                    v-for="(err, i) in doc.errors"
                    :key="i"
                    class="border-b border-gray-100 last:border-0"
                  >
                    <td class="w-20 whitespace-nowrap py-1 font-mono text-gray-400">
                      {{ err.line }}:{{ err.col }}
                    </td>
                    <td class="py-1 text-red-700">
                      {{ err.message }}
                      <span v-if="err.path" class="ml-1 font-mono text-red-400">({{ err.path }})</span>
                      <a
                        :href="`https://www.google.com/search?q=${encodeURIComponent(err.message + (err.path ? ' ' + err.path : ''))}`"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="ml-2 whitespace-nowrap text-blue-500 underline hover:text-blue-700"
                      >{{ t("documents.search_google") }}</a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
