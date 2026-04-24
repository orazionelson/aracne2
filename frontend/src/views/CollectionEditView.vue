<script setup lang="ts">
/**
 * Collection edit view — dedicated page at
 * ``/collections/:slug/edit``. Replaces the inline edit form that
 * used to toggle open in CollectionDetailView: the form is large and
 * noisy enough that a full page is the right container for it.
 *
 * All metadata fields editable here (title, description, schema,
 * body template, single-author and single-source toggles, manuscript
 * identifier, physical form, publication metadata, persistent
 * identifier, respStmt rows) live on the collection itself; the page
 * simply seeds draft refs from ``store.current`` on mount, lets the
 * editor mutate them, and writes them back via
 * ``store.updateCollection`` on Save. Save navigates back to the
 * detail view; Cancel does the same without writing.
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useViafAutocomplete } from "@/composables/useViafAutocomplete";
import { useGeonamesAutocomplete } from "@/composables/useGeonamesAutocomplete";
import { useCollectionStore } from "@/stores/collections";
import { useSchemaStore } from "@/stores/schemas";
import { useLicenseStore } from "@/stores/licenses";
import { useBodyTemplateStore } from "@/stores/body_templates";
import { usePluginStore } from "@/stores/plugins";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const store = useCollectionStore();
const schemaStore = useSchemaStore();
const licenseStore = useLicenseStore();
const bodyTemplateStore = useBodyTemplateStore();
const pluginStore = usePluginStore();

const slug = route.params.slug as string;

const isLoading = ref(true);
const loadError = ref<string | null>(null);

// ── Edit form state ──────────────────────────────────────────────────────
const editTitle = ref("");
const editDesc = ref("");
const editPublic = ref(false);
const editEvtEnabled = ref(false);
const editTargetPublishDate = ref<string>("");  // "YYYY-MM-DD" or ""
const editSchemaId = ref<string | null>(null);
const editPublisher = ref("");
const editPubPlace = ref("");
const editPubYear = ref<number | null>(null);
const editLicenseId = ref<string | null>(null);
const editHasSingleAuthor = ref(false);
const editAuthor = ref("");
const editHasSingleSource = ref(false);
const editMainSource = ref("");
const editHasMsIdentifier = ref(false);
const editMsIdentifier = ref("");
const editHasObjectDescForm = ref(false);
const editObjectDescForm = ref("");
const editIdentifierUrl = ref("");
const editBodyTemplateId = ref<string | null>(null);
const editRespStmts = ref<{ resp: string; name: string }[]>([]);
const respNameOpen = ref<boolean[]>([]);

const isSaving = ref(false);
const saveError = ref<string | null>(null);

const OBJECTDESC_FORMS = [
  "codex", "leaf", "roll", "tablet", "sheet", "fascicle", "fragment", "other",
] as const;

// ── Autocomplete composables ─────────────────────────────────────────────
const viaf = useViafAutocomplete();
const viafOpen = ref(false);
const viafResults = computed(() => viaf.results.value);
const viafLoading = computed(() => viaf.isLoading.value);

const geonames = useGeonamesAutocomplete();
const geonamesOpen = ref(false);
const geonamesResults = computed(() => geonames.results.value);
const geonamesLoading = computed(() => geonames.isLoading.value);

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

function onPubPlaceInput(e: Event): void {
  const val = (e.target as HTMLInputElement).value;
  editPubPlace.value = val;
  geonames.search(val);
  geonamesOpen.value = true;
}

function selectGeonamesPlace(name: string): void {
  editPubPlace.value = name;
  geonames.clear();
  geonamesOpen.value = false;
}

function closeGeonamesDropdown(): void {
  setTimeout(() => { geonamesOpen.value = false; }, 150);
}

// ── respStmt autocomplete ────────────────────────────────────────────────
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

// ── Seed draft from current collection ───────────────────────────────────
function seedFromCurrent(): void {
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
  editIdentifierUrl.value = store.current.identifier_url ?? "";
  editBodyTemplateId.value = store.current.body_template_id ?? null;
  editEvtEnabled.value = store.current.evt_enabled;
  editTargetPublishDate.value = store.current.target_publish_date ?? "";
  editRespStmts.value = store.current.resp_stmts
    ? store.current.resp_stmts.map((r) => ({ ...r }))
    : [];
  respNameOpen.value = editRespStmts.value.map(() => false);
}

const evtPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "evt" && p.status === "active"),
);

onMounted(async () => {
  try {
    await Promise.all([
      store.fetchCollection(slug),
      schemaStore.fetchSchemas(),
      licenseStore.fetchLicenses(),
      bodyTemplateStore.fetchTemplates(),
      store.fetchEditors(),
      pluginStore.plugins.length === 0
        ? pluginStore.fetchPlugins().catch(() => undefined)
        : Promise.resolve(),
    ]);
    seedFromCurrent();
  } catch {
    loadError.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
});

async function submitEdit(): Promise<void> {
  if (!store.current) return;
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
      identifier_url: editIdentifierUrl.value.trim() || null,
      body_template_id: editBodyTemplateId.value,
      evt_enabled: editEvtEnabled.value,
      target_publish_date: editTargetPublishDate.value || null,
    });
    router.push({ name: "collection-detail", params: { slug } });
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

function cancel(): void {
  router.push({ name: "collection-detail", params: { slug } });
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-6 py-8">
    <!-- Back -->
    <RouterLink
      :to="{ name: 'collection-detail', params: { slug } }"
      class="mb-4 inline-block text-sm text-indigo-600 hover:underline dark:text-indigo-400"
    >
      ← {{ store.current ? store.current.title : t("collections.back_to_collection") }}
    </RouterLink>

    <h1 class="mb-4 text-xl font-semibold text-gray-800 dark:text-gray-100">
      {{ t("collections.edit") }}
    </h1>

    <p v-if="isLoading" class="text-sm text-gray-400 dark:text-gray-500">
      {{ t("common.loading") }}
    </p>
    <p v-else-if="loadError" class="text-sm text-red-600 dark:text-red-400">
      {{ loadError }}
    </p>

    <section
      v-else-if="store.current"
      class="rounded border border-gray-200 bg-gray-50 p-5 dark:border-gray-700 dark:bg-gray-800/50"
    >
      <form class="space-y-3" @submit.prevent="submitEdit">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
            {{ t("collections.title_label") }}
          </label>
          <input
            v-model="editTitle"
            required
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
            {{ t("collections.description") }}
          </label>
          <textarea
            v-model="editDesc"
            rows="2"
            class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
        <div class="flex items-center gap-2">
          <input id="edit-public" v-model="editPublic" type="checkbox" />
          <label for="edit-public" class="text-sm text-gray-700 dark:text-gray-200">
            {{ t("collections.is_public") }}
          </label>
        </div>
        <div v-if="evtPluginActive" class="flex items-center gap-2">
          <input id="edit-evt-enabled" v-model="editEvtEnabled" type="checkbox" />
          <label for="edit-evt-enabled" class="text-sm text-gray-700 dark:text-gray-200">
            {{ t("collections.evt_enabled_label") }}
          </label>
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ t("collections.evt_enabled_hint") }}</span>
        </div>
        <div class="flex flex-col gap-1">
          <label for="edit-target-publish-date" class="text-xs font-medium text-gray-600 dark:text-gray-300">
            {{ t("collections.target_publish_date_label") }}
          </label>
          <input
            id="edit-target-publish-date"
            v-model="editTargetPublishDate"
            type="date"
            class="w-48 rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500">
            {{ t("collections.target_publish_date_hint") }}
          </p>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">
            {{ t("collections.schema_label") }}
          </label>
          <select
            v-model="editSchemaId"
            class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
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
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">
            {{ t("collections.body_template_label") }}
          </label>
          <select
            v-model="editBodyTemplateId"
            class="rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
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
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-300">
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
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("collections.author_label") }}
            </label>
            <div class="relative">
              <input
                :value="editAuthor"
                type="text"
                autocomplete="off"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                @input="onAuthorInput"
                @focus="viafOpen = true"
                @blur="closeViafDropdown"
              />
              <span
                v-if="viafLoading"
                class="absolute right-2 top-1.5 text-xs text-gray-400 dark:text-gray-500"
              >…</span>
            </div>
            <ul
              v-if="viafOpen && viafResults.length > 0"
              class="absolute z-30 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-56 overflow-y-auto dark:border-gray-700 dark:bg-gray-800"
            >
              <li
                v-for="name in viafResults"
                :key="name"
                class="cursor-pointer px-3 py-2 text-sm text-gray-900 hover:bg-indigo-50 dark:text-gray-100 dark:hover:bg-indigo-900/30"
                @mousedown.prevent="selectViafName(name)"
              >
                {{ name }}
              </li>
            </ul>
          </div>
        </div>
        <!-- Single primary source -->
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-300">
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
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("collections.main_source_label") }}
            </label>
            <input
              v-model="editMainSource"
              type="text"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
          </div>
        </div>
        <!-- Manuscript identifier -->
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-300">
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
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("collections.ms_identifier_label") }}
            </label>
            <input
              v-model="editMsIdentifier"
              type="text"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
          </div>
        </div>
        <!-- Physical form (objectDesc) -->
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-300">
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
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("collections.objectdesc_form_label") }}
            </label>
            <select
              v-model="editObjectDescForm"
              class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            >
              <option value="">—</option>
              <option v-for="f in OBJECTDESC_FORMS" :key="f" :value="f">{{ f }}</option>
            </select>
          </div>
        </div>
        <!-- Publication metadata -->
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
            publicationStmt
          </p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.publisher_label") }}
              </label>
              <input
                v-model="editPublisher"
                type="text"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              />
            </div>
            <div class="relative">
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.pub_place_label") }}
              </label>
              <div class="relative">
                <input
                  :value="editPubPlace"
                  type="text"
                  autocomplete="off"
                  class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                  @input="onPubPlaceInput"
                  @focus="geonamesOpen = true"
                  @blur="closeGeonamesDropdown"
                />
                <span v-if="geonamesLoading" class="absolute right-2 top-1.5 text-xs text-gray-400 dark:text-gray-500">…</span>
              </div>
              <ul
                v-if="geonamesOpen && geonamesResults.length > 0"
                class="absolute z-30 mt-1 w-full overflow-y-auto rounded border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
                style="max-height: 14rem;"
              >
                <li
                  v-for="place in geonamesResults"
                  :key="place.geonames_id"
                  class="cursor-pointer px-3 py-2 text-sm text-gray-900 hover:bg-indigo-50 dark:text-gray-100 dark:hover:bg-indigo-900/30"
                  @mousedown.prevent="selectGeonamesPlace(place.name)"
                >
                  <span class="font-medium">{{ place.name }}</span>
                  <span v-if="place.region || place.country" class="ml-1 text-xs text-gray-400 dark:text-gray-500">
                    {{ [place.region, place.country].filter(Boolean).join(", ") }}
                  </span>
                </li>
              </ul>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.pub_year_label") }}
              </label>
              <input
                v-model.number="editPubYear"
                type="number"
                min="1000"
                max="9999"
                placeholder="YYYY"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.availability_label") }}
              </label>
              <select
                v-model="editLicenseId"
                class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
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
          <div class="col-span-2 mt-1">
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("collections.identifier_url_label") }}
            </label>
            <input
              v-model="editIdentifierUrl"
              type="url"
              placeholder="https://doi.org/… or https://hdl.handle.net/…"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <p class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{{ t("collections.identifier_url_hint") }}</p>
          </div>
        </div>
        <!-- respStmt — one row per responsible party -->
        <div class="border-t border-gray-200 pt-3 dark:border-gray-700">
          <div class="mb-2 flex items-center justify-between">
            <p class="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">respStmt</p>
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
            class="mb-2 grid grid-cols-2 gap-3 rounded border border-gray-100 bg-white p-2 dark:border-gray-800 dark:bg-gray-800"
          >
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.resp_label") }}
              </label>
              <input
                v-model="row.resp"
                type="text"
                list="resp-datalist"
                autocomplete="off"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
              />
            </div>
            <div class="relative">
              <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
                {{ t("collections.resp_name_label") }}
              </label>
              <input
                v-model="row.name"
                type="text"
                autocomplete="off"
                class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                @focus="respNameOpen[i] = true"
                @blur="closeRespNameDropdown(i)"
                @input="respNameOpen[i] = true"
              />
              <ul
                v-if="respNameOpen[i] && filteredRespNamesFor(i).length > 0"
                class="absolute z-20 mt-1 w-full rounded border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto dark:border-gray-700 dark:bg-gray-800"
              >
                <li
                  v-for="opt in filteredRespNamesFor(i)"
                  :key="opt.id"
                  class="cursor-pointer px-3 py-2 text-sm text-gray-900 hover:bg-indigo-50 dark:text-gray-100 dark:hover:bg-indigo-900/30"
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
            class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
            @click="cancel"
          >
            {{ t("common.cancel") }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
