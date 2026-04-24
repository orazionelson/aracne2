<script setup lang="ts">
/**
 * Trismegistos ID-resolver panel.
 *
 * Trismegistos has no free-text search API, so the panel's UX is
 * "paste an ID" rather than "type a name". The editor picks a
 * kind (person / place / text); for texts, an optional partner-DB
 * source can be selected to reverse-look-up a foreign ID (e.g.
 * DDBDP ``9`` → TM text ``9``). The result card shows the canonical
 * TM URL plus any partner-DB cross-references; the Apply button
 * writes the URL as ``@ref`` on the enclosing ``<persName>`` or
 * ``<placeName>`` (texts currently render the URL for reference
 * only — the editor copies it manually).
 */

import { ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useTrismegistosStore,
  type TmKind,
  type TmTextSource,
  type TrismegistosHit,
} from "@/stores/trismegistos";

type ApplyOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: "no_enclosing_tag" }
  | { ok: false; reason: "not_entity_tag"; tagName: string };

const props = defineProps<{
  initialKind?: TmKind;
  onApply: (uri: string) => ApplyOutcome;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const { t } = useI18n();
const tm = useTrismegistosStore();

const kind = ref<TmKind>(props.initialKind ?? "place");
const identifier = ref("");
const source = ref<TmTextSource>("trismegistos");

const result = ref<TrismegistosHit | null>(null);
const notFound = ref(false);
const error = ref<string | null>(null);

const lastApplied = ref<{ tmId: string; tagName: string } | null>(null);
const applyError = ref<string | null>(null);

const TEXT_SOURCES: TmTextSource[] = [
  "trismegistos", "ddbdp", "hgv", "phi", "edh", "edcs",
  "edr", "edb", "isic", "rib", "lupa", "pn", "ba", "he", "uoxf",
];

async function runResolve(): Promise<void> {
  error.value = null;
  notFound.value = false;
  result.value = null;
  applyError.value = null;
  lastApplied.value = null;

  const id = identifier.value.trim();
  if (!id) return;

  try {
    const hit = await tm.resolveId({
      kind: kind.value,
      identifier: id,
      source: kind.value === "text" ? source.value : "trismegistos",
    });
    if (hit === null) {
      notFound.value = true;
      return;
    }
    result.value = hit;
  } catch (err) {
    const resp = (err as { response?: { data?: { error?: { message?: string } } } }).response;
    error.value = resp?.data?.error?.message ?? (err as Error).message ?? t("common.error");
  }
}

function clearForm(): void {
  identifier.value = "";
  result.value = null;
  notFound.value = false;
  error.value = null;
  applyError.value = null;
  lastApplied.value = null;
}

function applyHit(): void {
  if (!result.value) return;
  applyError.value = null;
  const outcome = props.onApply(result.value.uri);
  if (outcome.ok) {
    lastApplied.value = { tmId: result.value.tm_id, tagName: outcome.tagName };
    return;
  }
  applyError.value =
    outcome.reason === "no_enclosing_tag"
      ? t("trismegistos.apply_error_no_enclosing_tag")
      : t("trismegistos.apply_error_not_entity_tag", { tag: outcome.tagName });
}

function kindBadge(k: TmKind): string {
  const map: Record<TmKind, string> = {
    person: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    place: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    text: "bg-violet-50 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  };
  return map[k];
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-900">
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#c49a6c]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 3h14v18H5z" />
          <path d="M9 7h6M9 11h6M9 15h6" />
        </svg>
        <span class="text-sm font-semibold text-gray-700 dark:text-gray-200">{{ t("trismegistos.panel_title") }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="emit('close')">✕</button>
    </div>

    <div class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-[11px] text-gray-500 dark:border-gray-700 dark:text-gray-400">
      {{ t("trismegistos.resolver_intro") }}
    </div>

    <div class="flex flex-shrink-0 flex-col gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
      <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
        <span class="w-14 shrink-0">{{ t("trismegistos.field_kind") }}</span>
        <select v-model="kind" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
          <option value="person">{{ t("trismegistos.kind_person") }}</option>
          <option value="place">{{ t("trismegistos.kind_place") }}</option>
          <option value="text">{{ t("trismegistos.kind_text") }}</option>
        </select>
      </label>
      <label v-if="kind === 'text'" class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
        <span class="w-14 shrink-0">{{ t("trismegistos.field_source") }}</span>
        <select v-model="source" class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
          <option v-for="s in TEXT_SOURCES" :key="s" :value="s">{{ s.toUpperCase() }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
        <span class="w-14 shrink-0">{{ t("trismegistos.field_id") }}</span>
        <input
          v-model="identifier"
          type="text"
          :placeholder="t('trismegistos.id_placeholder')"
          class="flex-1 rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          @keydown.enter.prevent="runResolve()"
        />
      </label>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          :disabled="tm.isResolving || !identifier.trim()"
          @click="runResolve"
        >
          {{ tm.isResolving ? t("common.loading") : t("trismegistos.resolve") }}
        </button>
        <button
          v-if="identifier || result || notFound"
          type="button"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
          @click="clearForm"
        >
          {{ t("trismegistos.clear") }}
        </button>
      </div>
    </div>

    <div v-if="lastApplied || applyError" class="flex-shrink-0 border-b border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
      <p v-if="applyError" class="text-red-600 dark:text-red-400">{{ applyError }}</p>
      <p v-else-if="lastApplied" class="text-green-700 dark:text-green-400">
        {{ t("trismegistos.applied_success", { tm: lastApplied.tmId, tag: lastApplied.tagName }) }}
      </p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="error" class="px-3 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-else-if="notFound" class="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">
        {{ t("trismegistos.not_found") }}
      </p>
      <div v-else-if="result" class="px-3 py-3">
        <p class="text-sm font-medium text-gray-800 dark:text-gray-100">{{ result.label }}</p>
        <p class="mt-1 text-[11px]">
          <span :class="['rounded px-1.5 py-0.5 font-mono', kindBadge(result.kind)]">{{ result.kind }}</span>
        </p>
        <p class="mt-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
          TM {{ result.tm_id }} · <a :href="result.uri" target="_blank" rel="noopener" class="hover:underline">trismegistos.org</a>
        </p>
        <div v-if="Object.keys(result.partners).length > 0" class="mt-3 border-t border-gray-100 pt-2 dark:border-gray-700">
          <p class="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
            {{ t("trismegistos.partners_title") }}
          </p>
          <ul class="mt-1 space-y-0.5 text-xs">
            <li v-for="(ids, partner) in result.partners" :key="partner" class="font-mono text-gray-600 dark:text-gray-300">
              <span class="font-semibold">{{ partner }}</span>: {{ ids.join(", ") }}
            </li>
          </ul>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <button
            v-if="result.kind !== 'text'"
            type="button"
            class="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            @click="applyHit"
          >
            {{ t("trismegistos.apply") }}
          </button>
          <span v-else class="text-[11px] text-gray-400">{{ t("trismegistos.text_not_applicable") }}</span>
        </div>
      </div>
      <p v-else-if="!tm.isResolving" class="px-3 py-3 text-xs text-gray-400">
        {{ t("trismegistos.idle_hint") }}
      </p>
    </div>

    <div class="flex-shrink-0 border-t border-gray-100 px-3 py-2 text-[11px] text-gray-400 dark:border-gray-700 dark:text-gray-500">
      {{ t("trismegistos.footer_hint") }}
    </div>
  </div>
</template>
