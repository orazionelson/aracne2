<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import {
  useCollectionStore,
  type ZipUploadResult,
  type DocumentMeta,
  type WorkflowHistoryEntry,
} from "@/stores/collections";
import { useBodyTemplateStore } from "@/stores/body_templates";
import { useSchemaStore } from "@/stores/schemas";
import { useLicenseStore } from "@/stores/licenses";
import { useCollectionValidationStore } from "@/stores/collection_validation";
import { useAiStore } from "@/stores/ai";
import { useSettingStore } from "@/stores/settings";
import { useZenodoStore, type DepositStatus } from "@/stores/zenodo";
import {
  useInternetArchiveStore,
  type ArchiveStatus as IaStatus,
} from "@/stores/internet_archive";
import { useCodebergStore } from "@/stores/codeberg";
import { useGithubStore } from "@/stores/github";
import { useGitlabStore } from "@/stores/gitlab";
import { usePluginStore } from "@/stores/plugins";
import ForgeCollectionSection from "@/components/ui/ForgeCollectionSection.vue";
import DataverseCollectionSection from "@/components/ui/DataverseCollectionSection.vue";
import WorkflowTimeline from "@/components/ui/WorkflowTimeline.vue";
import ZoteroImportModal from "@/components/ui/ZoteroImportModal.vue";
import AiPanel from "@/components/AiPanel.vue";
import {
  EyeIcon,
  PencilSquareIcon,
  ArrowDownTrayIcon,
  TrashIcon,
} from "@heroicons/vue/24/outline";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const licenseStore = useLicenseStore();
const bodyTemplateStore = useBodyTemplateStore();
const validationStore = useCollectionValidationStore();
const aiStore = useAiStore();
const settingStore = useSettingStore();
const zenodoStore = useZenodoStore();
const iaStore = useInternetArchiveStore();
const codebergStore = useCodebergStore();
const githubStore = useGithubStore();
const gitlabStore = useGitlabStore();
const pluginStore = usePluginStore();

// Zotero import modal visibility + last-run summary.
const showZoteroModal = ref(false);
const zoteroJustImportedMsg = ref<string | null>(null);
const zoteroImportActive = computed(() =>
  pluginStore.plugins.some(
    (p) => p.name === "zotero_import" && p.status === "active",
  ),
);

const zenodoStatus = ref<DepositStatus | null>(null);
const isForcingDeposit = ref(false);
const zenodoDepositError = ref<string | null>(null);

// Internet Archive — same pattern as Zenodo: status fetched for EiC+ on
// mount, manual archive + refresh buttons live in the same footer row.
const iaStatus = ref<IaStatus | null>(null);
const isArchiving = ref(false);
const iaError = ref<string | null>(null);

// Per-forge plugin-active flags — gate the matching <ForgeCollectionSection>.
// All other state (link, edit draft, push/init results, error) is owned by
// the section component itself; the parent only needs to know which plugins
// are active and to reload its document list when one of them runs Initialize.
const codebergPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "codeberg_integration" && p.status === "active"),
);
const githubPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "github_integration" && p.status === "active"),
);
const gitlabPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "gitlab_integration" && p.status === "active"),
);
const dataversePluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "dataverse_integration" && p.status === "active"),
);

async function onForgeInitialized(): Promise<void> {
  // Initialize populated eXist with the imported XML files; reload the
  // document list so the rest of the page reflects the new state.
  await store.fetchDocuments(slug);
}

// Per-collection Zenodo resource_type override. Empty string → "use default"
// (sent as an empty string, mapped to NULL on the backend).
const zenodoResourceTypeDraft = ref<string>("");
const zenodoUploadAsZipDraft = ref<boolean>(false);
const isSavingZenodoResourceType = ref(false);
const zenodoResourceTypeError = ref<string | null>(null);
const zenodoResourceTypeSaved = ref(false);

// ── AI panel per-document ─────────────────────────────────────────────────────
const aiDocFilename = ref<string | null>(null);
const aiEnabled = computed(() => aiStore.config !== null && aiStore.config.provider !== "disabled");

function buildAiValidationContext(docFilename: string): Record<string, string> {
  const doc = validationStore.currentRun?.results?.documents?.find(
    (d) => d.filename === docFilename,
  );
  return {
    filename: docFilename,
    schema: store.current?.schema_id ?? "",
    errors: JSON.stringify(doc?.errors ?? []),
  };
}

function openAiForDoc(docFilename: string): void {
  aiStore.clearResponse();
  aiDocFilename.value = docFilename;
}

// ── Validation report expand state ────────────────────────────────────────────
const validationExpandedDoc = ref<string | null>(null);

function toggleValidationDoc(filename: string): void {
  validationExpandedDoc.value = validationExpandedDoc.value === filename ? null : filename;
}

async function handleValidateAll(): Promise<void> {
  if (!window.confirm(t("collections.validate_all_confirm"))) return;
  await validationStore.startRun(slug);
}

async function handleCancelValidation(): Promise<void> {
  if (!validationStore.currentRun) return;
  await validationStore.cancelRun(slug, validationStore.currentRun.id);
}

onUnmounted(() => { validationStore.reset(); });

const slug = route.params.slug as string;
const isLoading = ref(true);
const error = ref<string | null>(null);

// ── Workflow ──────────────────────────────────────────────────────────────────
const workflowNote = ref("");
const workflowError = ref<string | null>(null);
const isActing = ref(false);
const showRequestRevisionsForm = ref(false);
const revisionNote = ref("");

const isEiC = computed(() => auth.hasMinRole("EditorInChief"));
const isAdmin = computed(() => auth.hasMinRole("Admin"));

// ── Workflow history (EiC+) ───────────────────────────────────────────────
// Powers the timeline stepper, the inline "latest revision request" note,
// and the SLA "stuck for N days" badge. One fetch feeds all three surfaces.
const workflowHistory = ref<WorkflowHistoryEntry[]>([]);

async function loadWorkflowHistory(): Promise<void> {
  if (!auth.hasMinRole("EditorInChief") || !store.current) return;
  try {
    workflowHistory.value = await store.fetchCollectionHistory(store.current.id);
  } catch {
    workflowHistory.value = [];
  }
}

// The most recent ``collection.rejected`` entry — only surfaced as a
// prominent "revisions requested" card when the collection is back in
// ``assigned`` and the rejection is more recent than the last submit
// (otherwise the editor already addressed it).
const lastRevisionRequest = computed<WorkflowHistoryEntry | null>(() => {
  if (store.current?.status !== "assigned") return null;
  const history = workflowHistory.value;
  for (let i = history.length - 1; i >= 0; i--) {
    const e = history[i];
    if (e.action === "collection.submitted") return null;
    if (e.action === "collection.rejected") return e;
  }
  return null;
});

// "Stuck for X days": days elapsed since the last transition for
// collections sitting in ``review`` or ``assigned``. Over the threshold,
// the workflow panel shows an amber nudge.
const STUCK_THRESHOLD_DAYS = 14;

const stuckDays = computed<number | null>(() => {
  const status = store.current?.status;
  if (status !== "review" && status !== "assigned") return null;
  const history = workflowHistory.value;
  if (history.length === 0) return null;
  const last = history[history.length - 1];
  const ms = Date.now() - new Date(last.occurred_at).getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
});

const isStuck = computed(
  () => stuckDays.value !== null && stuckDays.value >= STUCK_THRESHOLD_DAYS,
);

// Target publish date (set in the edit view). When present we render a
// small countdown chip in the workflow header: neutral while there is
// time, amber once the date has passed. Does nothing if the collection
// is already published — the date has served its purpose.
const targetDaysLeft = computed<number | null>(() => {
  const iso = store.current?.target_publish_date;
  if (!iso) return null;
  if (store.current?.status === "published") return null;
  const target = new Date(iso + "T00:00:00Z").getTime();
  const today = Date.now();
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24));
});

const isTargetOverdue = computed(
  () => targetDaysLeft.value !== null && targetDaysLeft.value < 0,
);

// ── Saved bibliographies panel ────────────────────────────────────────────────
const biblioOpen = ref(false);
const expandedBiblioVersion = ref<number | null>(null);
const biblioDeleteError = ref<string | null>(null);
const biblioPublicError = ref<string | null>(null);

function toggleBiblioRow(version: number): void {
  expandedBiblioVersion.value = expandedBiblioVersion.value === version ? null : version;
}

async function handleDeleteBiblio(version: number): Promise<void> {
  if (!store.current) return;
  if (!window.confirm(t("bibliobuilder.delete_version_confirm", { version }))) return;
  biblioDeleteError.value = null;
  try {
    await store.deleteBibliography(store.current.id, version);
  } catch (err) {
    biblioDeleteError.value = err instanceof Error ? err.message : t("common.error");
  }
}

async function handleSetPublic(version: number, isPublic: boolean): Promise<void> {
  if (!store.current) return;
  biblioPublicError.value = null;
  try {
    await store.setBibliographyPublic(store.current.id, version, isPublic);
  } catch (err) {
    biblioPublicError.value = err instanceof Error ? err.message : t("common.error");
  }
}

async function copyBiblio(content: string): Promise<void> {
  await navigator.clipboard.writeText(content);
}
const evtPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "evt" && p.status === "active"),
);
const evtEnabled = computed(
  () =>
    evtPluginActive.value &&
    settingStore.getSetting("evt_enabled") === "true" &&
    store.current?.is_public === true &&
    store.current?.status === "published" &&
    store.documents.length === 1 &&
    store.current?.evt_enabled === true,
);
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
    await loadWorkflowHistory();
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
  await loadWorkflowHistory();
}

async function handleRequestRevisions(): Promise<void> {
  if (!revisionNote.value.trim()) return;
  // Note: ``rejectCollection`` is the historical frontend store method
  // name; kept for API path consistency (POST /collections/{id}/reject).
  // User-facing terminology is "Request revisions".
  await doWorkflow(() => store.rejectCollection(slug, revisionNote.value.trim()));
  showRequestRevisionsForm.value = false;
  revisionNote.value = "";
  await loadWorkflowHistory();
}

async function handlePublish(): Promise<void> {
  await doWorkflow(() => store.publishCollection(slug, workflowNote.value.trim() || undefined));
  workflowNote.value = "";
  await loadWorkflowHistory();
}

async function handleUnpublish(): Promise<void> {
  if (!confirm(t("collections.confirm_unpublish"))) return;
  await doWorkflow(() => store.unpublishCollection(slug));
  await loadWorkflowHistory();
}

async function handleDirectPublish(): Promise<void> {
  if (!confirm(t("collections.direct_publish_confirm"))) return;
  await doWorkflow(() => store.directPublishCollection(slug, workflowNote.value.trim() || undefined));
  workflowNote.value = "";
  await loadWorkflowHistory();
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
    store.current?.status !== "published" &&
    (isEiC.value ||
      (isAssignedEditor.value && store.current?.status === "assigned")),
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
      settingStore.fetchSettings().catch(() => { /* non-fatal */ }),
    ];
    // The editors list (GET /users) requires EditorInChief or above.
    // Editors and Users must not call it — they cannot assign editors anyway.
    if (auth.hasMinRole("EditorInChief")) {
      tasks.push(store.fetchEditors());
      tasks.push(validationStore.fetchLatest(slug));
      tasks.push(aiStore.fetchConfig().catch(() => { /* non-fatal */ }));
      tasks.push(store.listBibliographies(slug).catch(() => { /* non-fatal */ }));
      tasks.push(loadZenodoStatus());
      // Populates the dropdown used by the per-collection override below.
      // Silent failure — the plugin may simply not be active yet.
      tasks.push(zenodoStore.fetchResourceTypes().catch(() => undefined));
      tasks.push(loadInternetArchiveStatus());
      // Needed to decide whether to render the "Import from Zotero" button
      // and to gate the Codeberg / git-forge sections.
      tasks.push(
        pluginStore.plugins.length === 0
          ? pluginStore.fetchPlugins().catch(() => undefined)
          : Promise.resolve(),
      );
    }
    await Promise.all(tasks);
    // Forge sections (Codeberg / GitHub / GitLab) load their own links
    // on mount — no parent-side fetch needed any more.
    // Seed the override draft from the loaded collection (runs after
    // fetchCollection has populated store.current).
    zenodoResourceTypeDraft.value = store.current?.zenodo_resource_type ?? "";
    zenodoUploadAsZipDraft.value = store.current?.zenodo_upload_as_zip ?? false;
    // Workflow history fetched after store.current is populated because the
    // endpoint is keyed on the UUID, not the slug.
    await loadWorkflowHistory();
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});

// Zenodo deposit status — only fetched for EiC+ since it mutates plugin_data
// and is not relevant to read-only users. Errors are silent: a 404 just means
// the plugin is not installed or the collection was never deposited.
async function loadZenodoStatus(): Promise<void> {
  try {
    zenodoStatus.value = await zenodoStore.fetchStatus(slug);
  } catch {
    zenodoStatus.value = null;
  }
}

async function forceZenodoDeposit(): Promise<void> {
  zenodoDepositError.value = null;
  isForcingDeposit.value = true;
  try {
    zenodoStatus.value = await zenodoStore.forceDeposit(slug);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    zenodoDepositError.value = msg ?? t("common.error");
  } finally {
    isForcingDeposit.value = false;
  }
}

// ── Internet Archive controls ────────────────────────────────────────────
async function loadInternetArchiveStatus(): Promise<void> {
  try {
    iaStatus.value = await iaStore.fetchStatus(slug);
  } catch {
    iaStatus.value = null;
  }
}

async function forceArchive(): Promise<void> {
  iaError.value = null;
  isArchiving.value = true;
  try {
    iaStatus.value = await iaStore.forceArchive(slug);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    iaError.value = msg ?? t("common.error");
  } finally {
    isArchiving.value = false;
  }
}


async function onZoteroImported(payload: { imported: number; version: number }): Promise<void> {
  zoteroJustImportedMsg.value = t("zotero_import.success_toast", {
    n: payload.imported,
    version: payload.version,
  });
  // Refresh the bibliographies list so the new version appears without a reload.
  if (store.current) {
    await store.listBibliographies(store.current.slug).catch(() => undefined);
  }
  setTimeout(() => {
    zoteroJustImportedMsg.value = null;
  }, 5000);
}

async function refreshArchive(): Promise<void> {
  iaError.value = null;
  isArchiving.value = true;
  try {
    iaStatus.value = await iaStore.refreshArchive(slug);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    iaError.value = msg ?? t("common.error");
  } finally {
    isArchiving.value = false;
  }
}

// Group Zenodo's resource_type vocabulary into {group, options[]} buckets
// so the UI can render a single <select> with <optgroup> sub-lists.
const zenodoGroupedResourceTypes = computed(() => {
  const groups = new Map<string, { id: string; label: string }[]>();
  for (const opt of zenodoStore.resourceTypes) {
    const bucket = groups.get(opt.group);
    if (bucket) bucket.push({ id: opt.id, label: opt.label });
    else groups.set(opt.group, [{ id: opt.id, label: opt.label }]);
  }
  return Array.from(groups, ([group, options]) => ({ group, options }));
});

const zenodoSectionDirty = computed(() => {
  if (!store.current) return false;
  const currentType = store.current.zenodo_resource_type ?? "";
  const currentZip = store.current.zenodo_upload_as_zip ?? false;
  return (
    zenodoResourceTypeDraft.value !== currentType ||
    zenodoUploadAsZipDraft.value !== currentZip
  );
});

async function saveZenodoCollectionSettings(): Promise<void> {
  if (!store.current) return;
  zenodoResourceTypeError.value = null;
  zenodoResourceTypeSaved.value = false;
  isSavingZenodoResourceType.value = true;
  try {
    // Empty string clears the override on the backend (stored as NULL).
    await store.updateCollection(store.current.id, {
      zenodo_resource_type: zenodoResourceTypeDraft.value || null,
      zenodo_upload_as_zip: zenodoUploadAsZipDraft.value,
    });
    zenodoResourceTypeSaved.value = true;
    setTimeout(() => {
      zenodoResourceTypeSaved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    zenodoResourceTypeError.value = msg ?? t("common.error");
  } finally {
    isSavingZenodoResourceType.value = false;
  }
}

// ── Deposit foldable panel ───────────────────────────────────────────────
// Collapses what used to be five stacked card-panels (Zenodo, Internet
// Archive, Codeberg, GitHub, GitLab, Dataverse) into a single foldable
// "Deposita" container with one tab per active external service.
const depositOpen = ref(false);
const activeDepositTab = ref<string>("");

interface DepositTab {
  id: string;
  label: string;
}

const depositTabs = computed<DepositTab[]>(() => {
  const tabs: DepositTab[] = [];
  if (!isEiC.value) return tabs;
  // Zenodo: the per-collection override surface appears only once the
  // vocabulary has loaded (proxy for "Zenodo plugin reachable").
  if (zenodoGroupedResourceTypes.value.length > 0) {
    tabs.push({ id: "zenodo", label: "Zenodo" });
  }
  // Internet Archive appears when the collection is published.
  if (store.current?.status === "published") {
    tabs.push({ id: "internet_archive", label: "Internet Archive" });
  }
  if (codebergPluginActive.value) tabs.push({ id: "codeberg", label: "Codeberg" });
  if (githubPluginActive.value) tabs.push({ id: "github", label: "GitHub" });
  if (gitlabPluginActive.value) tabs.push({ id: "gitlab", label: "GitLab" });
  if (dataversePluginActive.value) tabs.push({ id: "dataverse", label: "Dataverse" });
  return tabs;
});

const hasAnyDepositTab = computed(() => depositTabs.value.length > 0);

// Keep activeDepositTab valid as the list changes (status transitions,
// plugin activation). Default to the first visible tab.
watch(
  depositTabs,
  (tabs) => {
    if (tabs.length === 0) {
      activeDepositTab.value = "";
      return;
    }
    if (!tabs.some((t) => t.id === activeDepositTab.value)) {
      activeDepositTab.value = tabs[0].id;
    }
  },
  { immediate: true },
);

function statusClass(s: string): string {
  const map: Record<string, string> = {
    draft: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
    assigned: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    published: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  };
  return map[s] ?? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300";
}
</script>

<template>
  <div class="p-6">
    <!-- Back -->
    <button
      class="mb-6 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
      @click="router.push({ name: 'collections' })"
    >
      ← {{ t("collections.title") }}
    </button>

    <p v-if="isLoading" class="text-sm text-gray-500 dark:text-gray-400">{{ t("common.loading") }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <template v-else-if="store.current">
      <!-- Collection header -->
      <div class="mb-6">
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ store.current.title }}</h1>
            <span
              class="rounded px-2 py-0.5 text-xs font-semibold"
              :class="statusClass(store.current.status)"
            >
              {{ t(`collections.status_${store.current.status}`) }}
            </span>
            <span v-if="store.current.is_public" class="text-xs text-gray-400 dark:text-gray-500">
              {{ t("collections.public_badge") }}
            </span>
            <!-- Zenodo deposit badge (EiC+ only, shown when a deposit record exists) -->
            <a
              v-if="zenodoStatus && zenodoStatus.status === 'published' && zenodoStatus.record_url"
              :href="zenodoStatus.record_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-green-700 bg-green-50 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50"
              :title="t('zenodo.badge_published_hint')"
            >
              {{ zenodoStatus.doi ? `DOI: ${zenodoStatus.doi}` : t("zenodo.badge_published") }}
            </a>
            <a
              v-else-if="zenodoStatus && zenodoStatus.status === 'draft' && zenodoStatus.record_url"
              :href="zenodoStatus.record_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50"
              :title="t('zenodo.badge_draft_hint')"
            >
              {{ t("zenodo.badge_draft") }}
            </a>
            <span
              v-else-if="zenodoStatus && zenodoStatus.status === 'failed'"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-red-700 bg-red-50 dark:bg-red-900/30 dark:text-red-300"
              :title="zenodoStatus.error ?? t('zenodo.badge_failed_hint')"
            >
              {{ t("zenodo.badge_failed") }}
            </span>

            <!-- Internet Archive badge (EiC+ only, shown when a record exists) -->
            <a
              v-if="iaStatus && iaStatus.status === 'success' && iaStatus.wayback_url"
              :href="iaStatus.wayback_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300 dark:hover:bg-emerald-900/50"
              :title="t('internet_archive.badge_success_hint')"
            >
              {{ t("internet_archive.badge_success") }}
            </a>
            <span
              v-else-if="iaStatus && iaStatus.status === 'pending'"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-amber-700 bg-amber-50 dark:bg-amber-900/30 dark:text-amber-300"
              :title="t('internet_archive.badge_pending_hint')"
            >
              {{ t("internet_archive.badge_pending") }}
            </span>
            <span
              v-else-if="iaStatus && iaStatus.status === 'failed'"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-red-700 bg-red-50 dark:bg-red-900/30 dark:text-red-300"
              :title="iaStatus.error ?? t('internet_archive.badge_failed_hint')"
            >
              {{ t("internet_archive.badge_failed") }}
            </span>
          </div>
          <p class="mt-1 font-mono text-sm text-gray-500 dark:text-gray-400">{{ store.current.slug }}</p>
          <p v-if="store.current.description" class="mt-2 text-sm text-gray-700 dark:text-gray-200">
            {{ store.current.description }}
          </p>
          <p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
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
      </div>

      <!-- Action buttons (EVT viewer + Edit + Bibliobuilder) -->
      <div v-if="evtEnabled || isEiC" class="mb-4 flex gap-2">
        <RouterLink
          v-if="evtEnabled"
          :to="{ name: 'collection-read', params: { slug } }"
          class="rounded border border-indigo-300 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
        >
          {{ t("evt.read_button") }}
        </RouterLink>
        <RouterLink
          v-if="isEiC"
          :to="{ name: 'collection-edit', params: { slug } }"
          class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
        >
          {{ t("collections.edit") }}
        </RouterLink>
        <!-- Bibliobuilder depends on the AI provider being active (it uses
             the bibliobuilder native prompt to normalise <bibl> entries).
             Hide the entry point entirely when the Admin has set
             ai_provider="disabled" — clicking into an unusable screen
             is worse than not seeing the action. -->
        <RouterLink
          v-if="isEiC && aiEnabled"
          :to="{ name: 'collection-bibliobuilder', params: { slug } }"
          class="rounded border border-violet-300 px-3 py-1.5 text-sm text-violet-700 hover:bg-violet-50 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-900/40"
        >
          {{ t("collections.bibliobuilder_btn") }}
        </RouterLink>
      </div>

      <!-- Workflow section — the heart of the page: status, timeline,
           inline revision-note and all editorial actions. A thicker
           indigo accent bar on the left visually separates it from the
           other cards (assign / submit / publish / revisions are the
           high-value actions users come here to do). -->
      <section
        class="mb-6 rounded border border-gray-200 border-l-4 border-l-indigo-500 bg-indigo-50/40 p-5 dark:border-gray-700 dark:border-l-indigo-400 dark:bg-indigo-900/10"
      >
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
            <svg class="h-4 w-4 text-indigo-600 dark:text-indigo-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" y1="9" x2="6" y2="21"/>
            </svg>
            {{ t("collections.workflow") }}
          </h2>
          <div class="flex flex-wrap items-center gap-2">
            <!-- Target publish date countdown. Neutral while there is
                 time, amber once overdue. Published collections suppress
                 the chip since the target has served its purpose. -->
            <span
              v-if="targetDaysLeft !== null"
              class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
              :class="
                isTargetOverdue
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
                  : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200'
              "
              :title="t('collections.target_publish_date_tooltip', { date: store.current.target_publish_date })"
            >
              📅
              <template v-if="isTargetOverdue">
                {{ t("collections.target_overdue_label", { days: Math.abs(targetDaysLeft) }) }}
              </template>
              <template v-else-if="targetDaysLeft === 0">
                {{ t("collections.target_today_label") }}
              </template>
              <template v-else>
                {{ t("collections.target_countdown_label", { days: targetDaysLeft }) }}
              </template>
            </span>
            <!-- SLA "stuck for N days" badge (EiC+, only on review/assigned) -->
            <span
              v-if="isEiC && isStuck"
              class="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
              :title="t('collections.sla_stuck_hint', { days: stuckDays, state: t(`collections.status_${store.current.status}`) })"
            >
              ⏱ {{ t("collections.sla_stuck_label", { days: stuckDays }) }}
            </span>
          </div>
        </div>

        <!-- Inline timeline of past transitions (EiC+). Click any step
             to see who did what and any attached note. -->
        <WorkflowTimeline
          v-if="isEiC && workflowHistory.length > 0"
          :entries="workflowHistory"
          class="mb-4"
        />

        <!-- Prominent revision-request card: only when the collection
             is back in ``assigned`` after an EiC "Request revisions".
             Surfaces the note directly so the editor does not have to
             dig through notifications or audit log. -->
        <div
          v-if="lastRevisionRequest"
          class="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-900/20"
        >
          <p class="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
            <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 9v4"/><path d="M12 17h.01"/><circle cx="12" cy="12" r="10"/>
            </svg>
            {{ t("collections.last_revision_note_title") }}
          </p>
          <p class="mb-1 text-xs text-amber-700 dark:text-amber-300">
            {{ t("collections.last_revision_note_hint", {
              actor: lastRevisionRequest.actor_display_name ?? lastRevisionRequest.actor_username ?? t("collections.history_actor_unknown"),
              when: new Date(lastRevisionRequest.occurred_at).toLocaleString(),
            }) }}
          </p>
          <p class="whitespace-pre-wrap text-amber-900 dark:text-amber-100">
            {{ lastRevisionRequest.note }}
          </p>
        </div>

        <p v-if="workflowError" class="mb-3 text-sm text-red-600">{{ workflowError }}</p>

        <!-- Assign / Reassign (EiC+, draft or assigned). Primary on
             ``draft`` (that is the obvious next step); demoted to
             outlined secondary on ``assigned``. -->
        <div
          v-if="isEiC && (store.current.status === 'draft' || store.current.status === 'assigned')"
          class="mb-4"
        >
          <button
            :class="
              store.current.status === 'draft'
                ? 'mb-2 rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700'
                : 'mb-2 rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700'
            "
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
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                :placeholder="t('collections.assign_username')"
                @focus="isEditorDropdownOpen = true"
                @blur="closeEditorDropdown"
                @input="isEditorDropdownOpen = true"
              />
              <ul
                v-if="isEditorDropdownOpen && filteredEditors.length > 0"
                class="absolute z-20 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto dark:border-gray-700 dark:bg-gray-800"
              >
                <li
                  v-for="e in filteredEditors"
                  :key="e.id"
                  class="cursor-pointer px-3 py-2 text-sm text-gray-900 hover:bg-indigo-50 dark:text-gray-100 dark:hover:bg-indigo-900/30"
                  @mousedown.prevent="selectEditor(e)"
                >
                  <span class="font-medium">{{ e.username }}</span>
                  <span v-if="e.display_name" class="ml-2 text-xs text-gray-500 dark:text-gray-400">
                    {{ e.display_name }}
                  </span>
                </li>
              </ul>
            </div>
            <input
              v-model="assignNote"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
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
                class="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                @click="showAssignForm = false"
              >
                {{ t("common.cancel") }}
              </button>
            </div>
          </form>
        </div>

        <!-- Submit for review (assigned editor only) -->
        <div v-if="isAssignedEditor && store.current.status === 'assigned'" class="mb-4">
          <p class="mb-2 text-sm text-gray-600 dark:text-gray-300">{{ t("collections.submit_hint") }}</p>
          <div class="flex items-center gap-2">
            <input
              v-model="workflowNote"
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
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

        <!-- Publish / Request revisions (EiC+, review) -->
        <div v-if="isEiC && store.current.status === 'review'" class="space-y-3">
          <div class="flex items-center gap-2">
            <input
              v-model="workflowNote"
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
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
              class="rounded border border-amber-300 px-4 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-900/40"
              @click="showRequestRevisionsForm = !showRequestRevisionsForm"
            >
              {{ t("collections.request_revisions") }}
            </button>
          </div>
          <div v-if="showRequestRevisionsForm" class="flex items-center gap-2">
            <input
              v-model="revisionNote"
              required
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              :placeholder="t('collections.request_revisions_note')"
            />
            <button
              :disabled="isActing || !revisionNote.trim()"
              class="rounded bg-amber-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              @click="handleRequestRevisions"
            >
              {{ t("collections.request_revisions_submit") }}
            </button>
          </div>
        </div>

        <!-- Unpublish (Admin, published) -->
        <div v-if="isAdmin && store.current.status === 'published'">
          <button
            :disabled="isActing"
            class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
            @click="handleUnpublish"
          >
            {{ t("collections.unpublish") }}
          </button>
        </div>

        <!-- Direct publish (EiC+, any status except published). Shortcut
             that bypasses the review step — visually muted on purpose so
             the standard workflow is what catches the eye. -->
        <div
          v-if="isEiC && store.current.status !== 'published'"
          class="mt-3 border-t border-dashed border-gray-200 pt-3 dark:border-gray-700"
        >
          <p class="mb-2 text-xs text-gray-400 dark:text-gray-500">{{ t("collections.direct_publish_hint") }}</p>
          <div class="flex items-center gap-2">
            <input
              v-model="workflowNote"
              class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              :placeholder="t('collections.workflow_note_optional')"
            />
            <button
              :disabled="isActing"
              class="rounded border border-emerald-400 px-3 py-1.5 text-sm text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-600 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
              @click="handleDirectPublish"
            >
              {{ t("collections.direct_publish") }}
            </button>
          </div>
        </div>

        <!-- Quiescent state messages -->
        <p
          v-if="
            store.current.status === 'published' && !isAdmin &&
            store.current.status === 'draft' && !isEiC
          "
          class="text-sm text-gray-400 dark:text-gray-500"
        >
          {{ t("collections.no_actions") }}
        </p>
      </section>

      <!-- Deposit foldable panel — consolidates Zenodo, Internet Archive
           and the forge/Dataverse integrations into a single container
           with one tab per active external service. Keeps the collection
           page compact regardless of how many deposit plugins are on. -->
      <section
        v-if="hasAnyDepositTab"
        class="mb-6 rounded border border-gray-200 dark:border-gray-700"
      >
        <button
          class="flex w-full items-center justify-between px-5 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/60"
          @click="depositOpen = !depositOpen"
        >
          <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">
            {{ t("collections.deposit_panel_title") }}
            <span class="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
              {{ depositTabs.length }}
            </span>
          </span>
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ depositOpen ? "▲" : "▼" }}</span>
        </button>

        <div v-show="depositOpen" class="border-t border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <p class="px-5 pt-3 text-xs text-gray-500 dark:text-gray-400">
            {{ t("collections.deposit_panel_hint") }}
          </p>

          <!-- Tab bar -->
          <div class="flex flex-wrap gap-1 border-b border-gray-200 px-5 pt-3 dark:border-gray-700">
            <button
              v-for="tab in depositTabs"
              :key="tab.id"
              class="rounded-t px-3 py-1.5 text-xs font-medium transition-colors"
              :class="
                activeDepositTab === tab.id
                  ? 'border border-b-0 border-gray-200 bg-white text-indigo-700 dark:border-gray-700 dark:bg-gray-900 dark:text-indigo-300'
                  : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'
              "
              @click="activeDepositTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>

          <!-- Tab panels -->
          <div class="px-5 py-4">
            <!-- Zenodo tab -->
            <div v-show="activeDepositTab === 'zenodo'">
              <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
                {{ t("zenodo.collection_section_hint") }}
              </p>

              <p v-if="zenodoResourceTypeError" class="mb-2 text-sm text-red-600 dark:text-red-400">
                {{ zenodoResourceTypeError }}
              </p>
              <p v-if="zenodoResourceTypeSaved" class="mb-2 text-sm text-green-600 dark:text-green-400">
                {{ t("zenodo.collection_section_saved") }}
              </p>

              <div class="space-y-3">
                <!-- Resource type dropdown -->
                <div class="flex flex-wrap items-center gap-2">
                  <select
                    v-model="zenodoResourceTypeDraft"
                    class="min-w-[18rem] rounded border border-gray-300 px-3 py-1.5 text-sm bg-white text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                  >
                    <option value="">{{ t("zenodo.collection_use_default") }}</option>
                    <optgroup
                      v-for="grp in zenodoGroupedResourceTypes"
                      :key="grp.group"
                      :label="grp.group"
                    >
                      <option
                        v-for="opt in grp.options"
                        :key="opt.id"
                        :value="opt.id"
                      >{{ opt.label }}</option>
                    </optgroup>
                  </select>
                </div>

                <!-- ZIP bundle toggle -->
                <div class="flex items-start justify-between rounded border border-gray-200 p-3 dark:border-gray-700">
                  <div class="mr-4">
                    <p class="text-sm font-medium text-gray-800 dark:text-gray-100">
                      {{ t("zenodo.collection_upload_as_zip") }}
                    </p>
                    <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                      {{ t("zenodo.collection_upload_as_zip_hint") }}
                    </p>
                  </div>
                  <button
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none"
                    :class="zenodoUploadAsZipDraft ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-gray-700'"
                    @click="zenodoUploadAsZipDraft = !zenodoUploadAsZipDraft"
                  >
                    <span
                      class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                      :class="zenodoUploadAsZipDraft ? 'translate-x-5' : 'translate-x-0'"
                    />
                  </button>
                </div>

                <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
                  <!-- Left: manual (re-)deposit action, only once the
                       collection is published. -->
                  <div
                    v-if="store.current.status === 'published'"
                    class="flex flex-wrap items-center gap-2"
                  >
                    <button
                      :disabled="isForcingDeposit"
                      class="inline-flex items-center gap-1.5 rounded border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-200 dark:hover:bg-indigo-900/50"
                      @click="forceZenodoDeposit"
                    >
                      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"/>
                      </svg>
                      {{ isForcingDeposit ? t("zenodo.working") : (zenodoStatus ? t("zenodo.redeposit_btn") : t("zenodo.deposit_btn")) }}
                    </button>
                    <span v-if="zenodoDepositError" class="text-xs text-red-600 dark:text-red-400">
                      {{ zenodoDepositError }}
                    </span>
                  </div>
                  <span v-else />

                  <!-- Right: save the per-collection overrides -->
                  <button
                    :disabled="isSavingZenodoResourceType || !zenodoSectionDirty"
                    class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
                    @click="saveZenodoCollectionSettings"
                  >
                    {{ isSavingZenodoResourceType ? t("common.saving") : t("common.save") }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Internet Archive tab -->
            <div v-show="activeDepositTab === 'internet_archive'">
              <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
                {{ t("internet_archive.collection_section_hint") }}
              </p>
              <div
                v-if="store.current.status === 'published'"
                class="flex flex-wrap items-center gap-2"
              >
                <!-- Archive / Re-archive (terminal states) or
                     Refresh (pending state, re-polls the SPN2 job). -->
                <button
                  v-if="!iaStatus || iaStatus.status !== 'pending'"
                  :disabled="isArchiving"
                  class="inline-flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
                  @click="forceArchive"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/>
                  </svg>
                  {{
                    isArchiving
                      ? t('internet_archive.working')
                      : (iaStatus ? t('internet_archive.rearchive_btn') : t('internet_archive.archive_btn'))
                  }}
                </button>
                <button
                  v-else
                  :disabled="isArchiving"
                  class="inline-flex items-center gap-1.5 rounded border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200 dark:hover:bg-amber-900/50"
                  @click="refreshArchive"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 12a9 9 0 1 1-6.22-8.56"/><path d="M21 3v6h-6"/>
                  </svg>
                  {{ isArchiving ? t('internet_archive.working') : t('internet_archive.refresh_btn') }}
                </button>
                <span v-if="iaError" class="text-xs text-red-600 dark:text-red-400">
                  {{ iaError }}
                </span>
              </div>
              <p v-else class="text-sm text-gray-500 dark:text-gray-400">
                {{ t("internet_archive.collection_needs_published") }}
              </p>
            </div>

            <!-- Codeberg tab -->
            <div v-show="activeDepositTab === 'codeberg'">
              <ForgeCollectionSection
                :slug="slug"
                :document-count="store.documents.length"
                :is-plugin-active="codebergPluginActive"
                :store="codebergStore"
                i18n-prefix="codeberg"
                default-base-url="https://codeberg.org"
                bare
                @initialized="onForgeInitialized"
              />
            </div>

            <!-- GitHub tab -->
            <div v-show="activeDepositTab === 'github'">
              <ForgeCollectionSection
                :slug="slug"
                :document-count="store.documents.length"
                :is-plugin-active="githubPluginActive"
                :store="githubStore"
                i18n-prefix="github"
                default-base-url="https://github.com"
                bare
                @initialized="onForgeInitialized"
              />
            </div>

            <!-- GitLab tab -->
            <div v-show="activeDepositTab === 'gitlab'">
              <ForgeCollectionSection
                :slug="slug"
                :document-count="store.documents.length"
                :is-plugin-active="gitlabPluginActive"
                :store="gitlabStore"
                i18n-prefix="gitlab"
                default-base-url="https://gitlab.com"
                bare
                @initialized="onForgeInitialized"
              />
            </div>

            <!-- Dataverse tab -->
            <div v-show="activeDepositTab === 'dataverse'">
              <DataverseCollectionSection :slug="slug" bare />
            </div>
          </div>
        </div>
      </section>

      <!-- Saved bibliographies panel (EiC+) — placed right above the
           Documents section so editors can glance at the bibliography
           versions before drilling into the per-document editor. -->
      <section v-if="isEiC" class="mb-6 rounded border border-gray-200 dark:border-gray-700">
        <button
          class="flex w-full items-center justify-between px-5 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/60"
          @click="biblioOpen = !biblioOpen"
        >
          <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">
            {{ t("bibliobuilder.panel_title") }}
            <span
              v-if="store.bibliographies.length"
              class="ml-2 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
            >{{ store.bibliographies.length }}</span>
          </span>
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ biblioOpen ? "▲" : "▼" }}</span>
        </button>

        <div v-show="biblioOpen" class="border-t border-gray-200 bg-white px-5 py-4 dark:border-gray-700 dark:bg-gray-900">
          <!-- Zotero import — only visible when the plugin is active, its button
               feeds a new CollectionBibliography version so this is the natural
               home for the action. -->
          <div
            v-if="zoteroImportActive"
            class="mb-3 flex flex-wrap items-center justify-between gap-2 rounded border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm dark:border-indigo-800 dark:bg-indigo-900/20"
          >
            <span class="text-gray-700 dark:text-gray-200">
              {{ t("zotero_import.collection_section_hint") }}
            </span>
            <button
              class="inline-flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
              @click="showZoteroModal = true"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              {{ t("zotero_import.import_btn") }}
            </button>
          </div>
          <p v-if="zoteroJustImportedMsg" class="mb-2 text-sm text-green-700 dark:text-green-400">
            {{ zoteroJustImportedMsg }}
          </p>

          <p v-if="biblioDeleteError" class="mb-2 text-sm text-red-600 dark:text-red-400">{{ biblioDeleteError }}</p>
          <p v-if="biblioPublicError" class="mb-2 text-sm text-red-600 dark:text-red-400">{{ biblioPublicError }}</p>

          <p v-if="!store.bibliographies.length" class="text-sm text-gray-400 dark:text-gray-500">
            {{ t("bibliobuilder.panel_empty") }}
          </p>

          <template v-else>
            <!-- Column headers -->
            <div class="mb-1 flex items-center gap-2 px-3 text-xs font-medium text-gray-400 dark:text-gray-500">
              <span class="w-6 text-center">{{ t("bibliobuilder.col_public") }}</span>
              <span class="flex-1">{{ t("bibliobuilder.col_version") }}</span>
              <span class="w-32 text-right">{{ t("bibliobuilder.col_actions") }}</span>
            </div>

            <div class="space-y-1">
              <div
                v-for="bib in store.bibliographies"
                :key="bib.version"
                class="rounded border"
                :class="bib.is_public ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20' : 'border-gray-100 bg-white dark:border-gray-700 dark:bg-gray-800'"
              >
                <!-- Row header -->
                <div class="flex items-center gap-2 px-3 py-2">
                  <!-- Radio button: public selector -->
                  <input
                    type="radio"
                    :name="`bib-public-${store.current?.id}`"
                    :checked="bib.is_public"
                    class="h-4 w-4 cursor-pointer accent-green-600"
                    @change="handleSetPublic(bib.version, true)"
                  />

                  <!-- Version + date (click to expand) -->
                  <button
                    class="flex flex-1 items-center gap-2 text-left"
                    @click="toggleBiblioRow(bib.version)"
                  >
                    <span
                      class="rounded px-2 py-0.5 text-xs font-mono font-medium"
                      :class="bib.is_public ? 'bg-green-200 text-green-800 dark:bg-green-800 dark:text-green-100' : 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'"
                    >
                      v{{ bib.version }}
                    </span>
                    <span v-if="bib.is_public" class="rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                      {{ t("bibliobuilder.is_public_label") }}
                    </span>
                    <span class="text-xs text-gray-500 dark:text-gray-400">
                      {{ new Date(bib.created_at).toLocaleString() }}
                    </span>
                  </button>

                  <!-- Actions -->
                  <div class="flex shrink-0 items-center gap-2">
                    <RouterLink
                      v-if="bib.is_public && store.current"
                      :to="{ name: 'public-bibliography', params: { slug: store.current.slug } }"
                      target="_blank"
                      class="text-xs text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-200"
                    >
                      {{ t("bibliobuilder.view_public") }}
                    </RouterLink>
                    <button
                      class="text-xs text-gray-400 hover:text-indigo-600 dark:text-gray-500 dark:hover:text-indigo-400"
                      @click="copyBiblio(bib.content)"
                    >
                      {{ t("bibliobuilder.copy_btn") }}
                    </button>
                    <button
                      class="text-xs text-gray-400 hover:text-red-600 dark:text-gray-500 dark:hover:text-red-400"
                      @click="handleDeleteBiblio(bib.version)"
                    >
                      {{ t("common.delete") }}
                    </button>
                  </div>
                </div>

                <!-- Expanded content -->
                <div
                  v-if="expandedBiblioVersion === bib.version"
                  class="border-t border-gray-100 px-3 pb-3 pt-2 dark:border-gray-700"
                >
                  <textarea
                    :value="bib.content"
                    readonly
                    rows="10"
                    class="w-full rounded border border-gray-200 bg-gray-50 px-2 py-1.5 font-mono text-xs text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                  />
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- Documents section -->
      <section class="rounded border border-gray-200 p-5 dark:border-gray-700">
        <div class="mb-4 flex items-start justify-between">
          <h2 class="text-sm font-semibold text-gray-700 dark:text-gray-200">
            {{ t("collections.documents") }}
            <span class="ml-1 font-normal text-gray-400 dark:text-gray-500">({{ store.documents.length }})</span>
          </h2>
          <!-- Right column: action buttons + new-doc form stacked vertically -->
          <div class="flex flex-col items-end gap-2">
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
              <template v-if="canWrite">
                <button
                  class="rounded border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-700 hover:bg-indigo-100"
                  @click="showNewDocForm = !showNewDocForm; newDocError = null"
                >
                  {{ t("collections.new_document") }}
                </button>
                <button
                  :disabled="isUploading || isUploadingZip"
                  class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
                  @click="fileInput?.click()"
                >
                  <span v-if="isUploading && uploadProgress.total > 1">{{ uploadProgress.done }}/{{ uploadProgress.total }}</span>
                  <span v-else-if="isUploading">{{ t("common.loading") }}</span>
                  <span v-else>{{ t("collections.upload") }}</span>
                </button>
                <button
                  :disabled="isUploading || isUploadingZip"
                  class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
                  @click="zipInput?.click()"
                >
                  {{ isUploadingZip ? t("common.loading") : t("collections.upload_zip") }}
                </button>
              </template>
            </div>

            <!-- New document form — appears below the buttons row -->
            <div v-if="showNewDocForm && canWrite" class="flex items-center gap-2">
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
              <button class="text-sm text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200" @click="showNewDocForm = false">
                {{ t("common.cancel") }}
              </button>
              <span v-if="newDocError" class="text-xs text-red-600">{{ newDocError }}</span>
            </div>
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

        <p v-if="canWrite" class="mb-3 text-xs text-gray-400 dark:text-gray-500">
          {{ t("collections.upload_hint") }}
        </p>

        <!-- ZIP upload result summary -->
        <div
          v-if="zipResult"
          class="mb-3 rounded border border-gray-200 bg-gray-50 px-4 py-3 text-sm dark:border-gray-700 dark:bg-gray-800/50 dark:text-gray-200"
        >
          <p class="font-medium text-gray-700 dark:text-gray-200">
            {{ t("collections.zip_result_uploaded", { n: zipResult.uploaded }) }}
            <span v-if="zipResult.skipped.length > 0" class="ml-2 text-gray-400 dark:text-gray-500">
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
            class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            :placeholder="t('collections.search_placeholder')"
            @keyup.enter="handleSearch"
          />
          <button
            :disabled="isSearching || !searchQuery.trim()"
            class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
            @click="handleSearch"
          >
            {{ isSearching ? t("common.loading") : t("collections.search_button") }}
          </button>
        </div>

        <!-- Search results -->
        <div v-if="searchDone" class="mb-4">
          <div class="mb-2 flex items-center justify-between">
            <p class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {{ t("collections.search_results") }}
            </p>
            <button
              class="text-xs text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200"
              @click="resetSearch"
            >
              {{ t("collections.search_reset") }}
            </button>
          </div>
          <p
            v-if="searchResults.length === 0"
            class="text-sm text-gray-500 dark:text-gray-400"
          >
            {{ t("collections.no_results", { q: searchQuery }) }}
          </p>
          <ul v-else class="space-y-2">
            <li
              v-for="hit in searchResults"
              :key="hit.filename"
              class="rounded border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50"
            >
              <div class="flex items-center justify-between">
                <p class="font-mono text-sm font-medium text-gray-800 dark:text-gray-100">{{ hit.filename }}</p>
                <button
                  class="text-xs text-indigo-500 hover:text-indigo-700"
                  @click="handleViewDoc(hit.filename)"
                >
                  {{ t("collections.view_document") }}
                </button>
              </div>
              <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">…{{ hit.snippet }}…</p>
            </li>
          </ul>
        </div>
        <p v-if="searchError" class="mb-3 text-sm text-red-600">{{ searchError }}</p>

        <!-- Document list -->
        <div v-if="store.documents.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
          {{ t("collections.no_documents") }}
        </div>

        <template v-else>
          <!-- List controls: select-all + page size -->
          <div class="mb-1 flex items-center justify-between border-b border-gray-100 pb-2 dark:border-gray-700">
            <label v-if="canWrite" class="flex cursor-pointer items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
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

            <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
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
                class="rounded border border-gray-200 px-1 py-0.5 text-xs bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200"
              >
                <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option>
              </select>
              <span>{{ t("collections.per_page") }}</span>
            </div>
          </div>

          <ul class="divide-y divide-gray-100 dark:divide-gray-800">
            <li
              v-for="doc in paginatedDocuments"
              :key="doc.filename"
              class="flex items-center justify-between py-2"
              :class="selectedFilenames.includes(doc.filename) ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''"
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
                <span class="font-mono text-sm text-gray-800 dark:text-gray-100">{{ doc.filename }}</span>
              </div>
              <div class="flex items-center gap-1.5">
                <button
                  class="inline-flex items-center gap-1.5 rounded border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 transition-colors hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50"
                  @click="handleViewDoc(doc.filename)"
                >
                  <EyeIcon class="h-3.5 w-3.5" />
                  {{ t("collections.view_document") }}
                </button>
                <button
                  v-if="canWrite"
                  class="inline-flex items-center gap-1.5 rounded border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50"
                  @click="router.push({ name: 'document-edit', params: { slug, filename: doc.filename } })"
                >
                  <PencilSquareIcon class="h-3.5 w-3.5" />
                  {{ t("collections.edit_document") }}
                </button>
                <button
                  class="inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                  @click="handleDownload(doc.filename)"
                >
                  <ArrowDownTrayIcon class="h-3.5 w-3.5" />
                  {{ t("collections.download") }}
                </button>
                <button
                  v-if="canWrite"
                  class="inline-flex items-center gap-1.5 rounded border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-100 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50"
                  @click="handleDeleteDoc(doc.filename)"
                >
                  <TrashIcon class="h-3.5 w-3.5" />
                  {{ t("collections.delete_document") }}
                </button>
              </div>
            </li>
          </ul>

          <!-- Pagination -->
          <div class="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>
              {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, store.documents.length) }}
              / {{ store.documents.length }}
            </span>
            <div class="flex items-center gap-1">
              <button
                :disabled="currentPage === 1"
                class="rounded border border-gray-300 px-2 py-0.5 text-gray-700 disabled:opacity-40 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                @click="goToPage(currentPage - 1)"
              >
                ←
              </button>
              <span class="px-2">{{ currentPage }} / {{ totalPages }}</span>
              <button
                :disabled="currentPage === totalPages"
                class="rounded border border-gray-300 px-2 py-0.5 text-gray-700 disabled:opacity-40 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
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
            v-else-if="validationStore.currentRun.status === 'cancelled'"
            class="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-200"
          >
            {{ t("collections.validate_all_cancelled", { n: validationStore.currentRun.validated_count, total: validationStore.currentRun.doc_count }) }}
          </span>
          <span
            v-else-if="validationStore.currentRun.status === 'failed'"
            class="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
          >
            {{ t("collections.validate_all_failed", { msg: validationStore.currentRun.error_message ?? '' }) }}
          </span>
          <!-- Stop button — visible while the run is in progress -->
          <button
            v-if="validationStore.currentRun.status === 'pending' || validationStore.currentRun.status === 'running'"
            class="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-700 hover:bg-red-100"
            @click="handleCancelValidation"
          >
            {{ t("collections.validate_all_cancel") }}
          </button>
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
            class="rounded border border-violet-100 bg-white dark:border-violet-900 dark:bg-gray-800"
          >
            <button
              class="flex w-full items-center justify-between px-3 py-2 text-left"
              @click="toggleValidationDoc(doc.filename)"
            >
              <span class="font-mono text-sm text-gray-700 dark:text-gray-200">{{ doc.filename }}</span>
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
                    class="border-b border-gray-100 last:border-0 dark:border-gray-700"
                  >
                    <td class="w-20 whitespace-nowrap py-1 font-mono text-gray-400 dark:text-gray-500">
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

              <!-- AI analysis button -->
              <div v-if="aiEnabled" class="mt-2">
                <button
                  v-if="aiDocFilename !== doc.filename"
                  class="rounded border border-violet-300 bg-violet-50 px-2 py-0.5 text-xs text-violet-700 hover:bg-violet-100"
                  @click="openAiForDoc(doc.filename)"
                >
                  {{ t("ai.button_validation") }}
                </button>
                <AiPanel
                  v-else
                  prompt-slug="validate_errors_explain"
                  :context="buildAiValidationContext(doc.filename)"
                  :title="t('ai.panel_validation_title')"
                  :chat="true"
                  :show-apply="false"
                  @close="aiDocFilename = null"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

    </template>

    <!-- Zotero import modal — teleports to body so it sits above the page. -->
    <Teleport to="body">
      <ZoteroImportModal
        v-if="showZoteroModal && store.current"
        :slug="store.current.slug"
        @close="showZoteroModal = false"
        @imported="onZoteroImported"
      />
    </Teleport>
  </div>
</template>
