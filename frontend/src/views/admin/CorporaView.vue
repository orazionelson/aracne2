<script setup lang="ts">
/**
 * Corpora — admin view that groups public collections under thematic
 * labels and issues per-corpus MCP tokens. The MCP plugin is the only
 * consumer today (see help: 03-advanced/07-mcp-server.md), but the
 * primitive is intentionally generic.
 *
 * Layout:
 *   - left column: list of corpora with collection count + active token count
 *   - right column: detail card for the selected (or new) corpus, with
 *     editable name/description + collection multi-select + token table
 *
 * The plaintext value of an issued token is shown only once, in a
 * modal, with a copy-paste Claude Desktop snippet pre-filled with the
 * platform's URL.
 */
import { onMounted, ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useCorpusStore, type Corpus, type McpToken, type McpTokenCreated } from "@/stores/corpora";
import { apiClient } from "@/services/api";

const { t } = useI18n();
const store = useCorpusStore();

interface CollectionLite {
  id: string;
  slug: string;
  title: string;
  is_public: boolean;
  status: string;
}

const allCollections = ref<CollectionLite[]>([]);
const isLoadingCollections = ref(false);

// ── Selection / draft state ───────────────────────────────────────────────
const selectedId = ref<string | null>(null);
const isCreating = ref(false);
const draftName = ref("");
const draftDescription = ref("");
const draftCollectionIds = ref<Set<string>>(new Set());
const draftError = ref<string | null>(null);
const isSaving = ref(false);

// ── Token modal state ─────────────────────────────────────────────────────
const newTokenLabel = ref("");
const issuingTokenInCorpus = ref<string | null>(null);
const justIssued = ref<McpTokenCreated | null>(null);
const tokenError = ref<string | null>(null);

const selected = computed<Corpus | null>(() =>
  selectedId.value ? store.corpora.find((c) => c.id === selectedId.value) ?? null : null,
);

const tokens = computed<McpToken[]>(() =>
  selectedId.value ? store.tokensByCorpus[selectedId.value] ?? [] : [],
);

// Collections eligible for membership: public + published.
const eligibleCollections = computed(() =>
  allCollections.value.filter((c) => c.is_public && c.status === "published"),
);

onMounted(async () => {
  await store.fetchAll();
  await loadAllCollections();
});

async function loadAllCollections(): Promise<void> {
  isLoadingCollections.value = true;
  try {
    // The /collections endpoint paginates; pull a generous page so the
    // multi-select can render without further round-trips. Admin will
    // iterate rarely and the page sizes are small (typically dozens).
    const res = await apiClient.getPaginated<CollectionLite>("/collections", {
      params: { page: 1, per_page: 200 },
    });
    allCollections.value = res.data as CollectionLite[];
  } finally {
    isLoadingCollections.value = false;
  }
}

function startCreate(): void {
  isCreating.value = true;
  selectedId.value = null;
  draftName.value = "";
  draftDescription.value = "";
  draftCollectionIds.value = new Set();
  draftError.value = null;
}

async function selectCorpus(c: Corpus): Promise<void> {
  isCreating.value = false;
  selectedId.value = c.id;
  draftName.value = c.name;
  draftDescription.value = c.description ?? "";
  draftCollectionIds.value = new Set(c.collections.map((x) => x.id));
  draftError.value = null;
  await store.fetchTokens(c.id);
}

function toggleCollection(id: string): void {
  if (draftCollectionIds.value.has(id)) draftCollectionIds.value.delete(id);
  else draftCollectionIds.value.add(id);
  // Re-assign so reactivity triggers.
  draftCollectionIds.value = new Set(draftCollectionIds.value);
}

async function save(): Promise<void> {
  draftError.value = null;
  isSaving.value = true;
  try {
    const payload = {
      name: draftName.value.trim(),
      description: draftDescription.value.trim() || null,
      collection_ids: Array.from(draftCollectionIds.value),
    };
    if (isCreating.value) {
      const created = await store.create(payload);
      isCreating.value = false;
      selectedId.value = created.id;
    } else if (selectedId.value) {
      await store.update(selectedId.value, payload);
    }
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    draftError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

async function deleteSelected(): Promise<void> {
  if (!selectedId.value) return;
  if (!window.confirm(t("corpora.confirm_delete"))) return;
  await store.remove(selectedId.value);
  selectedId.value = null;
  isCreating.value = false;
}

async function issueToken(): Promise<void> {
  if (!selectedId.value) return;
  tokenError.value = null;
  if (!newTokenLabel.value.trim()) {
    tokenError.value = t("corpora.token_label_required");
    return;
  }
  issuingTokenInCorpus.value = selectedId.value;
  try {
    justIssued.value = await store.issueToken(selectedId.value, newTokenLabel.value.trim());
    newTokenLabel.value = "";
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    tokenError.value = msg ?? t("common.error");
  } finally {
    issuingTokenInCorpus.value = null;
  }
}

async function revokeToken(tokenId: string): Promise<void> {
  if (!selectedId.value) return;
  if (!window.confirm(t("corpora.confirm_revoke_token"))) return;
  await store.revokeToken(selectedId.value, tokenId);
}

async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // ignore; the user can still select the snippet manually.
  }
}

function dismissJustIssued(): void {
  justIssued.value = null;
}
</script>

<template>
  <div class="p-6">
    <h1 class="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
      {{ t("corpora.title") }}
    </h1>
    <p class="mb-6 text-sm text-gray-500 dark:text-gray-400">
      {{ t("corpora.subtitle") }}
    </p>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <!-- Left column: list -->
      <div class="lg:col-span-1">
        <button
          class="mb-3 w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          @click="startCreate"
        >
          + {{ t("corpora.new_corpus") }}
        </button>

        <p v-if="store.isLoading" class="text-sm text-gray-500">{{ t("common.loading") }}</p>
        <p v-else-if="store.corpora.length === 0" class="text-sm text-gray-400">
          {{ t("corpora.empty") }}
        </p>
        <ul v-else class="space-y-1">
          <li
            v-for="c in store.corpora"
            :key="c.id"
            class="cursor-pointer rounded border px-3 py-2 text-sm transition-colors"
            :class="
              selectedId === c.id
                ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-900/30'
                : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
            "
            @click="selectCorpus(c)"
          >
            <p class="font-medium text-gray-800 dark:text-gray-100">{{ c.name }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              {{ t("corpora.list_meta", { n: c.collections.length, t: c.token_count }) }}
            </p>
          </li>
        </ul>
      </div>

      <!-- Right column: detail / create form -->
      <div class="lg:col-span-2">
        <div
          v-if="!selected && !isCreating"
          class="rounded border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400 dark:border-gray-700"
        >
          {{ t("corpora.select_or_create") }}
        </div>

        <div
          v-else
          class="space-y-4 rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800"
        >
          <!-- ── Corpus form ─────────────────────────────────────────────── -->
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("corpora.field_name") }}
            </label>
            <input
              v-model="draftName"
              type="text"
              required
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              :placeholder="t('corpora.field_name_hint')"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("corpora.field_description") }}
            </label>
            <textarea
              v-model="draftDescription"
              rows="2"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              :placeholder="t('corpora.field_description_hint')"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("corpora.field_collections") }}
            </label>
            <p class="mb-2 text-xs text-gray-500 dark:text-gray-400">
              {{ t("corpora.field_collections_hint") }}
            </p>
            <div
              class="max-h-64 overflow-y-auto rounded border border-gray-200 dark:border-gray-700"
            >
              <p
                v-if="isLoadingCollections"
                class="p-3 text-xs text-gray-400"
              >{{ t("common.loading") }}</p>
              <p
                v-else-if="eligibleCollections.length === 0"
                class="p-3 text-xs text-gray-400"
              >{{ t("corpora.no_eligible_collections") }}</p>
              <label
                v-for="c in eligibleCollections"
                :key="c.id"
                class="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-3 py-1.5 text-xs hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900/40"
              >
                <input
                  type="checkbox"
                  :checked="draftCollectionIds.has(c.id)"
                  @change="toggleCollection(c.id)"
                />
                <span class="text-gray-800 dark:text-gray-100">{{ c.title }}</span>
                <span class="font-mono text-gray-400">{{ c.slug }}</span>
              </label>
            </div>
          </div>
          <p v-if="draftError" class="text-sm text-red-600">{{ draftError }}</p>
          <div class="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3 dark:border-gray-700">
            <button
              :disabled="isSaving"
              class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
              @click="save"
            >
              {{ isSaving ? t("common.saving") : t("common.save") }}
            </button>
            <button
              v-if="selected"
              class="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:border-red-700 dark:hover:bg-red-900/30"
              @click="deleteSelected"
            >
              {{ t("common.delete") }}
            </button>
          </div>

          <!-- ── Tokens table (existing corpus only) ─────────────────────── -->
          <section v-if="selected" class="border-t border-gray-200 pt-4 dark:border-gray-700">
            <h3 class="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-200">
              {{ t("corpora.tokens_title") }}
            </h3>
            <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
              {{ t("corpora.tokens_hint") }}
            </p>

            <div class="mb-3 flex flex-wrap items-center gap-2">
              <input
                v-model="newTokenLabel"
                type="text"
                class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                :placeholder="t('corpora.token_label_placeholder')"
              />
              <button
                :disabled="issuingTokenInCorpus !== null"
                class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
                @click="issueToken"
              >
                {{ t("corpora.token_issue") }}
              </button>
            </div>
            <p v-if="tokenError" class="mb-2 text-sm text-red-600">{{ tokenError }}</p>

            <table class="w-full text-sm">
              <thead class="text-xs text-gray-500 dark:text-gray-400">
                <tr>
                  <th class="py-1 text-left">{{ t("corpora.token_label") }}</th>
                  <th class="py-1 text-left">{{ t("corpora.token_created_at") }}</th>
                  <th class="py-1 text-left">{{ t("corpora.token_last_used_at") }}</th>
                  <th class="py-1 text-left">{{ t("corpora.token_status") }}</th>
                  <th class="py-1" />
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="tok in tokens"
                  :key="tok.id"
                  class="border-t border-gray-100 dark:border-gray-700"
                >
                  <td class="py-1.5">{{ tok.label }}</td>
                  <td class="py-1.5 text-xs text-gray-500">{{ new Date(tok.created_at).toLocaleString() }}</td>
                  <td class="py-1.5 text-xs text-gray-500">
                    {{ tok.last_used_at ? new Date(tok.last_used_at).toLocaleString() : t("corpora.token_never_used") }}
                  </td>
                  <td class="py-1.5">
                    <span
                      v-if="tok.revoked_at"
                      class="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                    >{{ t("corpora.token_revoked") }}</span>
                    <span
                      v-else
                      class="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                    >{{ t("corpora.token_active") }}</span>
                  </td>
                  <td class="py-1.5 text-right">
                    <button
                      v-if="!tok.revoked_at"
                      class="text-xs text-red-600 hover:underline"
                      @click="revokeToken(tok.id)"
                    >{{ t("corpora.token_revoke") }}</button>
                  </td>
                </tr>
                <tr v-if="tokens.length === 0">
                  <td colspan="5" class="py-3 text-center text-xs text-gray-400">
                    {{ t("corpora.tokens_empty") }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>

    <!-- ── Just-issued token modal (one-shot reveal) ────────────────────── -->
    <div
      v-if="justIssued"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="dismissJustIssued"
    >
      <div class="w-full max-w-2xl rounded-lg bg-white p-5 dark:bg-gray-800">
        <h2 class="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-100">
          {{ t("corpora.token_just_created_title") }}
        </h2>
        <p class="mb-4 text-sm text-amber-700 dark:text-amber-400">
          ⚠ {{ t("corpora.token_just_created_warning") }}
        </p>

        <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
          {{ t("corpora.token_plaintext_label") }}
        </label>
        <div class="mb-3 flex items-center gap-2">
          <code
            class="flex-1 break-all rounded bg-gray-100 px-3 py-2 font-mono text-xs dark:bg-gray-900 dark:text-gray-200"
          >{{ justIssued.plaintext }}</code>
          <button
            class="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-700"
            @click="copyToClipboard(justIssued.plaintext)"
          >{{ t("common.copy") }}</button>
        </div>

        <label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300">
          {{ t("corpora.token_snippet_label") }}
        </label>
        <p class="mb-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t("corpora.token_snippet_hint") }}
        </p>
        <pre
          class="mb-3 max-h-64 overflow-y-auto rounded bg-gray-100 p-3 font-mono text-xs dark:bg-gray-900 dark:text-gray-200"
        >{{ justIssued.claude_desktop_snippet }}</pre>
        <div class="flex justify-end gap-2">
          <button
            class="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-700"
            @click="copyToClipboard(justIssued.claude_desktop_snippet)"
          >{{ t("corpora.token_copy_snippet") }}</button>
          <button
            class="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700"
            @click="dismissJustIssued"
          >{{ t("common.close") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
