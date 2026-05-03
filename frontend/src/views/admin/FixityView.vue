<script setup lang="ts">
/**
 * /admin/fixity — CTS R7 fixity surface.
 *
 * Layout:
 *   - 4 dashboard cards (per-status counts).
 *   - Status filter + "Recheck now" button.
 *   - Paginated table sorted drift-first; the body of a tampered
 *     row shows the expected vs. observed hash side-by-side.
 *
 * No detail side panel: the row already carries every field worth
 * inspecting — short hashes, timestamps, version number. JSONB
 * payloads belong to /admin/audit-log, not here.
 */
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  ArrowPathIcon,
  ShieldCheckIcon,
  ExclamationTriangleIcon,
  QuestionMarkCircleIcon,
  XCircleIcon,
} from "@heroicons/vue/24/outline";
import { useFixityStore, type FixityStatus } from "@/stores/fixity";

const { t } = useI18n();
const store = useFixityStore();

onMounted(async () => {
  await Promise.all([store.fetchSummary(), store.fetchPage(1)]);
});

async function handleRecheck(): Promise<void> {
  await store.recheckNow();
}

function shortHash(h: string | null): string {
  if (!h) return "—";
  return `${h.slice(0, 8)}…${h.slice(-6)}`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function applyStatusFilter(status: FixityStatus | ""): void {
  store.filterStatus = status;
  store.fetchPage(1);
}

const pageNumbers = computed<Array<number | "…">>(() => {
  const n = store.totalPages;
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1);
  const cur = store.page;
  const set = new Set([1, n, cur - 1, cur, cur + 1].filter((x) => x >= 1 && x <= n));
  const sorted = [...set].sort((a, b) => a - b);
  const result: Array<number | "…"> = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && (sorted[i] as number) - (sorted[i - 1] as number) > 1) result.push("…");
    result.push(sorted[i]);
  }
  return result;
});

function statusClass(s: FixityStatus): string {
  switch (s) {
    case "ok":
      return "bg-emerald-50 text-emerald-700";
    case "drifted":
      return "bg-rose-50 text-rose-700";
    case "missing":
      return "bg-amber-50 text-amber-700";
    case "error":
      return "bg-orange-50 text-orange-700";
  }
}
</script>

<template>
  <div class="px-6 py-6">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ t("fixity.title") }}</h1>
        <p class="mt-1 text-sm text-gray-500">{{ t("fixity.subtitle") }}</p>
      </div>
      <button
        type="button"
        :disabled="store.isRechecking"
        class="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
        @click="handleRecheck"
      >
        <ArrowPathIcon
          class="h-4 w-4"
          :class="{ 'animate-spin': store.isRechecking }"
        />
        {{ store.isRechecking ? t("fixity.rechecking") : t("fixity.recheck_now") }}
      </button>
    </div>

    <!-- Summary cards -->
    <section class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <button
        type="button"
        class="rounded-xl border border-emerald-200 bg-white p-4 text-left shadow-sm transition hover:border-emerald-300 hover:shadow"
        :class="{ 'ring-2 ring-emerald-300': store.filterStatus === 'ok' }"
        @click="applyStatusFilter(store.filterStatus === 'ok' ? '' : 'ok')"
      >
        <div class="flex items-center gap-2">
          <ShieldCheckIcon class="h-5 w-5 text-emerald-500" />
          <span class="text-xs uppercase text-gray-500">{{ t("fixity.status_ok") }}</span>
        </div>
        <p class="mt-1 text-2xl font-semibold text-gray-900">{{ store.summary.ok }}</p>
      </button>
      <button
        type="button"
        class="rounded-xl border border-rose-200 bg-white p-4 text-left shadow-sm transition hover:border-rose-300 hover:shadow"
        :class="{ 'ring-2 ring-rose-300': store.filterStatus === 'drifted' }"
        @click="applyStatusFilter(store.filterStatus === 'drifted' ? '' : 'drifted')"
      >
        <div class="flex items-center gap-2">
          <ExclamationTriangleIcon class="h-5 w-5 text-rose-500" />
          <span class="text-xs uppercase text-gray-500">{{ t("fixity.status_drifted") }}</span>
        </div>
        <p class="mt-1 text-2xl font-semibold text-gray-900">{{ store.summary.drifted }}</p>
      </button>
      <button
        type="button"
        class="rounded-xl border border-amber-200 bg-white p-4 text-left shadow-sm transition hover:border-amber-300 hover:shadow"
        :class="{ 'ring-2 ring-amber-300': store.filterStatus === 'missing' }"
        @click="applyStatusFilter(store.filterStatus === 'missing' ? '' : 'missing')"
      >
        <div class="flex items-center gap-2">
          <QuestionMarkCircleIcon class="h-5 w-5 text-amber-500" />
          <span class="text-xs uppercase text-gray-500">{{ t("fixity.status_missing") }}</span>
        </div>
        <p class="mt-1 text-2xl font-semibold text-gray-900">{{ store.summary.missing }}</p>
      </button>
      <button
        type="button"
        class="rounded-xl border border-orange-200 bg-white p-4 text-left shadow-sm transition hover:border-orange-300 hover:shadow"
        :class="{ 'ring-2 ring-orange-300': store.filterStatus === 'error' }"
        @click="applyStatusFilter(store.filterStatus === 'error' ? '' : 'error')"
      >
        <div class="flex items-center gap-2">
          <XCircleIcon class="h-5 w-5 text-orange-500" />
          <span class="text-xs uppercase text-gray-500">{{ t("fixity.status_error") }}</span>
        </div>
        <p class="mt-1 text-2xl font-semibold text-gray-900">{{ store.summary.error }}</p>
      </button>
    </section>

    <p v-if="store.driftCount > 0" class="mb-3 text-sm text-rose-700">
      {{ t("fixity.drift_banner", { n: store.driftCount }) }}
    </p>

    <section class="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div v-if="store.isLoading" class="px-4 py-6 text-sm text-gray-500">
        {{ t("common.loading") }}
      </div>
      <div v-else-if="store.rows.length === 0" class="px-4 py-6 text-sm text-gray-500">
        {{ t("fixity.no_rows") }}
      </div>
      <table v-else class="min-w-full divide-y divide-gray-200 text-sm">
        <thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_status") }}</th>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_document") }}</th>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_expected") }}</th>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_observed") }}</th>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_version") }}</th>
            <th class="px-4 py-2 text-left">{{ t("fixity.col_last_checked") }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="row in store.rows" :key="row.id">
            <td class="px-4 py-2">
              <span
                class="inline-flex rounded px-2 py-0.5 text-xs font-medium"
                :class="statusClass(row.status)"
              >
                {{ row.status }}
              </span>
            </td>
            <td class="px-4 py-2 font-mono text-xs text-gray-700">
              {{ row.document_filename }}
            </td>
            <td class="px-4 py-2 font-mono text-xs text-gray-500">
              <span :title="row.expected_sha256">{{ shortHash(row.expected_sha256) }}</span>
            </td>
            <td class="px-4 py-2 font-mono text-xs text-gray-500">
              <span
                :title="row.last_seen_sha256 ?? ''"
                :class="row.status === 'drifted' ? 'text-rose-700 font-semibold' : ''"
              >
                {{ shortHash(row.last_seen_sha256) }}
              </span>
            </td>
            <td class="px-4 py-2 text-xs text-gray-600">v{{ row.version_number }}</td>
            <td class="px-4 py-2 text-xs text-gray-500">{{ formatTime(row.last_checked_at) }}</td>
          </tr>
        </tbody>
      </table>
      <nav
        v-if="store.totalPages > 1"
        class="flex items-center justify-center gap-1 border-t border-gray-100 px-4 py-3"
        :aria-label="t('fixity.pagination_label')"
      >
        <button
          class="rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
          :disabled="store.page === 1"
          @click="store.fetchPage(store.page - 1)"
        >
          {{ t("audit_log.page_prev") }}
        </button>
        <template v-for="(num, idx) in pageNumbers" :key="idx">
          <span v-if="num === '…'" class="px-2 text-gray-400 select-none">…</span>
          <button
            v-else
            class="min-w-[2rem] rounded border px-2 py-1.5 text-sm transition"
            :class="num === store.page
              ? 'bg-indigo-600 border-indigo-600 text-white font-semibold'
              : 'hover:bg-gray-100'"
            @click="store.fetchPage(num as number)"
          >
            {{ num }}
          </button>
        </template>
        <button
          class="rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
          :disabled="store.page === store.totalPages"
          @click="store.fetchPage(store.page + 1)"
        >
          {{ t("audit_log.page_next") }}
        </button>
      </nav>
    </section>
  </div>
</template>
