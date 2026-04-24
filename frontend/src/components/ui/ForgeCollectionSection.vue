<script setup lang="ts">
/**
 * Generic "Deposit on <forge>" section for the Collection detail page.
 *
 * Replaces the inline blocks that used to live in
 * ``CollectionDetailView.vue`` once for Codeberg, once for GitHub,
 * once for GitLab. The three forge stores already share an
 * identical method surface (``getLink`` / ``writeLink`` /
 * ``deleteLink`` / ``pushCollection`` / ``initializeCollection``)
 * and an identical ``Link`` shape, so this component is generic
 * over the store: the parent passes the concrete store instance
 * and a few labels (the i18n key prefix, the default base URL).
 *
 * Initialize bookkeeping is owned here. After a successful import
 * the parent is told via ``@initialized`` so it can reload its own
 * document list — eXist was just populated.
 */

import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

// ── Generic forge contracts ────────────────────────────────────────────

export interface ForgeLink {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  pat_override_set: boolean;
  last_push_sha: string | null;
  last_push_at: string | null;
  initialized_at: string | null;
  initialized_from_sha: string | null;
  html_url: string;
}

export interface ForgePushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export interface ForgeInitializeResponse {
  file_count: number;
  head_sha: string;
  initialized_at: string;
}

export interface ForgeLinkCreate {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  /**
   * ``undefined`` → leave the existing per-link override alone.
   * ``""`` → clear the override (use the global PAT).
   * any string → encrypt and store as the new override.
   */
  pat_override?: string | null;
}

export interface ForgeStore {
  isPushing: boolean;
  isInitializing: boolean;
  getLink(slug: string): Promise<ForgeLink | null>;
  writeLink(slug: string, body: ForgeLinkCreate): Promise<ForgeLink>;
  deleteLink(slug: string): Promise<void>;
  pushCollection(slug: string): Promise<ForgePushResponse>;
  initializeCollection(slug: string): Promise<ForgeInitializeResponse>;
}

// ── Props / emits ──────────────────────────────────────────────────────

const props = defineProps<{
  /** Collection slug — used by the store calls. */
  slug: string;
  /** Number of TEI documents in the collection — gates Initialize. */
  documentCount: number;
  /** True when the corresponding forge plugin row is ``status=active``. */
  isPluginActive: boolean;
  /** Pinia store instance (any of the three forge stores satisfies this shape). */
  store: ForgeStore;
  /** ``"codeberg"`` / ``"github"`` / ``"gitlab"`` — i18n key namespace. */
  i18nPrefix: string;
  /** Default URL written into a fresh edit-draft (``https://codeberg.org`` etc.). */
  defaultBaseUrl: string;
}>();

const emit = defineEmits<{
  /** Emitted after Initialize so the parent can reload the document list. */
  (e: "initialized"): void;
}>();

const { t } = useI18n();

// Localised label helper — saves ``t(`${prefix}.foo`)`` everywhere.
function l(key: string, params?: Record<string, unknown>): string {
  const k = `${props.i18nPrefix}.${key}`;
  return params ? t(k, params as Record<string, unknown>) : t(k);
}

// ── State ──────────────────────────────────────────────────────────────

const link = ref<ForgeLink | null>(null);
const pushResult = ref<ForgePushResponse | null>(null);
const initResult = ref<ForgeInitializeResponse | null>(null);
const error = ref<string | null>(null);

const editing = ref(false);
const confirmingInit = ref(false);
const editDraft = ref({
  base_url: props.defaultBaseUrl,
  repo_owner: "",
  repo_name: "",
  branch: "main",
  pat_override: "",
  use_override: false,
});

const canInitialize = computed(
  () => link.value !== null
    && link.value.initialized_at === null
    && props.documentCount === 0,
);

// ── Lifecycle ──────────────────────────────────────────────────────────

async function load(): Promise<void> {
  if (!props.isPluginActive) { link.value = null; return; }
  try {
    link.value = await props.store.getLink(props.slug);
  } catch {
    link.value = null;
  }
}

onMounted(load);
// If the admin toggles the plugin while the page is open, refresh.
watch(() => props.isPluginActive, () => { void load(); });

// ── Handlers ───────────────────────────────────────────────────────────

function openEdit(): void {
  editing.value = true;
  error.value = null;
  pushResult.value = null;
  if (link.value) {
    editDraft.value = {
      base_url: link.value.base_url,
      repo_owner: link.value.repo_owner,
      repo_name: link.value.repo_name,
      branch: link.value.branch,
      pat_override: "",
      use_override: link.value.pat_override_set,
    };
  } else {
    editDraft.value = {
      base_url: props.defaultBaseUrl,
      repo_owner: "",
      repo_name: "",
      branch: "main",
      pat_override: "",
      use_override: false,
    };
  }
}

async function save(): Promise<void> {
  error.value = null;
  const d = editDraft.value;
  let patOverride: string | null | undefined;
  if (!d.use_override) {
    patOverride = "";
  } else if (d.pat_override.trim()) {
    patOverride = d.pat_override.trim();
  } else {
    patOverride = undefined;
  }
  try {
    link.value = await props.store.writeLink(props.slug, {
      base_url: d.base_url.trim(),
      repo_owner: d.repo_owner.trim(),
      repo_name: d.repo_name.trim(),
      branch: d.branch.trim() || "main",
      pat_override: patOverride,
    });
    editing.value = false;
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function disconnect(): Promise<void> {
  error.value = null;
  try {
    await props.store.deleteLink(props.slug);
    link.value = null;
    editing.value = false;
    pushResult.value = null;
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function push(): Promise<void> {
  error.value = null;
  pushResult.value = null;
  try {
    pushResult.value = await props.store.pushCollection(props.slug);
    link.value = await props.store.getLink(props.slug);
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function initialize(): Promise<void> {
  error.value = null;
  initResult.value = null;
  try {
    initResult.value = await props.store.initializeCollection(props.slug);
    link.value = await props.store.getLink(props.slug);
    confirmingInit.value = false;
    emit("initialized");
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
    confirmingInit.value = false;
  }
}
</script>

<template>
  <section
    v-if="isPluginActive"
    class="mb-6 rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"
  >
    <div class="mb-3 flex items-start justify-between">
      <div>
        <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {{ l("section_title") }}
        </h2>
        <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {{ l("section_hint") }}
        </p>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </p>

    <!-- Not linked → connect -->
    <div v-if="!link && !editing">
      <button
        type="button"
        class="rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200"
        @click="openEdit"
      >
        {{ l("connect_btn") }}
      </button>
    </div>

    <!-- Edit form (also used for initial connect) -->
    <div v-else-if="editing" class="space-y-3">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ l("field_base_url") }}</span>
          <input v-model="editDraft.base_url" type="url" class="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ l("field_branch") }}</span>
          <input v-model="editDraft.branch" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ l("field_owner") }}</span>
          <input v-model="editDraft.repo_owner" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ l("field_repo") }}</span>
          <input v-model="editDraft.repo_name" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
      </div>
      <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
        <input v-model="editDraft.use_override" type="checkbox" />
        <span>{{ l("use_per_link_pat") }}</span>
      </label>
      <input
        v-if="editDraft.use_override"
        v-model="editDraft.pat_override"
        type="password"
        autocomplete="off"
        class="w-full rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        :placeholder="link?.pat_override_set ? l('override_replace_hint') : l('field_pat_placeholder')"
      />
      <div class="flex gap-2 pt-2">
        <button type="button" class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700" @click="save">
          {{ t("common.save") }}
        </button>
        <button type="button" class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700" @click="editing = false">
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>

    <!-- Linked summary + push / initialize / disconnect -->
    <div v-else-if="link" class="space-y-3 text-sm">
      <p class="font-mono text-gray-700 dark:text-gray-200">
        <a :href="link.html_url" target="_blank" rel="noopener" class="hover:underline">
          {{ link.repo_owner }}/{{ link.repo_name }}
        </a>
        <span class="text-xs text-gray-500 dark:text-gray-400">
          · {{ link.branch }} · {{ link.base_url }}
        </span>
      </p>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        <span v-if="link.last_push_sha">
          {{ l("last_push") }}:
          <code class="font-mono">{{ link.last_push_sha.slice(0, 10) }}</code>
          <span v-if="link.last_push_at"> ({{ new Date(link.last_push_at).toLocaleString() }})</span>
        </span>
        <span v-else>{{ l("never_pushed") }}</span>
        <span v-if="link.pat_override_set" class="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
          {{ l("pat_override_badge") }}
        </span>
      </p>

      <p v-if="pushResult" class="text-xs text-green-700 dark:text-green-400">
        {{ l("push_success", { n: pushResult.file_count, sha: pushResult.sha.slice(0, 10) }) }}
        <a v-if="pushResult.html_url" :href="pushResult.html_url" target="_blank" rel="noopener" class="underline">
          {{ l("view_commit") }}
        </a>
      </p>
      <p v-if="initResult" class="text-xs text-green-700 dark:text-green-400">
        {{ l("initialize_success", { n: initResult.file_count, sha: initResult.head_sha.slice(0, 10) }) }}
      </p>

      <div v-if="canInitialize" class="rounded border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-900/20">
        <p class="text-xs text-amber-800 dark:text-amber-200">
          {{ l("initialize_available_hint") }}
        </p>
        <div v-if="!confirmingInit" class="mt-2">
          <button type="button" class="rounded border border-amber-400 bg-white px-3 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:bg-gray-800 dark:text-amber-200 dark:hover:bg-amber-900/40" @click="confirmingInit = true">
            {{ l("initialize_btn") }}
          </button>
        </div>
        <div v-else class="mt-2 space-y-2">
          <p class="text-xs font-medium text-amber-900 dark:text-amber-100">
            {{ l("initialize_confirm") }}
          </p>
          <div class="flex gap-2">
            <button type="button" :disabled="store.isInitializing" class="rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50" @click="initialize">
              {{ store.isInitializing ? t("common.loading") : l("initialize_confirm_btn") }}
            </button>
            <button type="button" :disabled="store.isInitializing" class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700" @click="confirmingInit = false">
              {{ t("common.cancel") }}
            </button>
          </div>
        </div>
      </div>

      <div class="flex gap-2">
        <button type="button" :disabled="store.isPushing" class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50" @click="push">
          {{ store.isPushing ? t("common.loading") : l("push_btn") }}
        </button>
        <button type="button" class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700" @click="openEdit">
          {{ l("edit_btn") }}
        </button>
        <button type="button" class="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/40" @click="disconnect">
          {{ l("disconnect_btn") }}
        </button>
      </div>
    </div>
  </section>
</template>
