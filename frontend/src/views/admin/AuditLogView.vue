<script setup lang="ts">
/**
 * /admin/audit-log — Admin-only audit-trail viewer (FUTURE_IDEAS §20).
 *
 * Layout: filter bar at the top (free-text + structured), paginated
 * table in the middle, side panel for the JSONB payload of the row
 * the admin clicks. CSV export downloads the same filtered query.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  ArrowDownTrayIcon,
  XMarkIcon,
  ArrowPathIcon,
} from "@heroicons/vue/24/outline";
import { useAuditLogStore, type AuditLogEntry } from "@/stores/auditLog";

const { t } = useI18n();
const store = useAuditLogStore();

const draft = ref({ ...store.filters });

onMounted(async () => {
  await Promise.all([store.fetchActions(), store.fetchPage(1)]);
});

function applyFilters(): void {
  store.filters = { ...draft.value };
  store.fetchPage(1);
}

function clearFilters(): void {
  draft.value = {
    q: "",
    action: "",
    actor_username: "",
    target_type: "",
    target_id: "",
    from: "",
    to: "",
  };
  store.resetFilters();
  store.fetchPage(1);
}

function goToPage(p: number): void {
  if (p < 1 || p > store.totalPages) return;
  store.fetchPage(p);
}

function openDetail(row: AuditLogEntry): void {
  store.fetchDetail(row.id);
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function prettyJson(payload: Record<string, unknown> | null): string {
  if (payload == null) return "—";
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
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
</script>

<template>
  <div class="px-6 py-6">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">
          {{ t("audit_log.title") }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t("audit_log.subtitle") }}
        </p>
      </div>
      <a
        :href="store.csvUrl()"
        class="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
      >
        <ArrowDownTrayIcon class="h-4 w-4" />
        {{ t("audit_log.export_csv") }}
      </a>
    </div>

    <!-- Filter bar -->
    <section class="mb-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div class="md:col-span-3">
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_q_label") }}
          </label>
          <input
            v-model="draft.q"
            type="search"
            :placeholder="t('audit_log.filter_q_placeholder')"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            @keyup.enter="applyFilters"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_action") }}
          </label>
          <select
            v-model="draft.action"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          >
            <option value="">{{ t("audit_log.filter_any") }}</option>
            <option v-for="a in store.knownActions" :key="a" :value="a">
              {{ a }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_actor") }}
          </label>
          <input
            v-model="draft.actor_username"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            @keyup.enter="applyFilters"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_target_type") }}
          </label>
          <input
            v-model="draft.target_type"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            @keyup.enter="applyFilters"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_from") }}
          </label>
          <input
            v-model="draft.from"
            type="datetime-local"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600">
            {{ t("audit_log.filter_to") }}
          </label>
          <input
            v-model="draft.to"
            type="datetime-local"
            class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
      </div>
      <div class="mt-3 flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          @click="applyFilters"
        >
          {{ t("audit_log.apply") }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
          @click="clearFilters"
        >
          {{ t("audit_log.clear") }}
        </button>
        <span class="ml-auto text-xs text-gray-500">
          {{ t("audit_log.total_rows", { n: store.total }) }}
        </span>
      </div>
    </section>

    <!-- Results table -->
    <section class="rounded-xl border border-gray-200 bg-white shadow-sm">
      <div v-if="store.isLoading" class="px-4 py-6 text-sm text-gray-500">
        <ArrowPathIcon class="mr-1 inline h-4 w-4 animate-spin" />
        {{ t("common.loading") }}
      </div>
      <div v-else-if="store.entries.length === 0" class="px-4 py-6 text-sm text-gray-500">
        {{ t("audit_log.no_results") }}
      </div>
      <table v-else class="min-w-full divide-y divide-gray-200 text-sm">
        <thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th class="px-4 py-2 text-left">{{ t("audit_log.col_time") }}</th>
            <th class="px-4 py-2 text-left">{{ t("audit_log.col_action") }}</th>
            <th class="px-4 py-2 text-left">{{ t("audit_log.col_actor") }}</th>
            <th class="px-4 py-2 text-left">{{ t("audit_log.col_target") }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr
            v-for="row in store.entries"
            :key="row.id"
            class="cursor-pointer hover:bg-indigo-50/50"
            @click="openDetail(row)"
          >
            <td class="whitespace-nowrap px-4 py-2 font-mono text-xs text-gray-600">
              {{ formatTime(row.occurred_at) }}
            </td>
            <td class="px-4 py-2">
              <span class="inline-flex rounded bg-indigo-50 px-2 py-0.5 font-mono text-xs text-indigo-700">
                {{ row.action }}
              </span>
            </td>
            <td class="px-4 py-2 text-gray-700">{{ row.actor_username || "—" }}</td>
            <td class="px-4 py-2 text-gray-600">
              <span v-if="row.target_label">
                <span class="text-xs text-gray-400">{{ row.target_type }}/</span>
                {{ row.target_label }}
              </span>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <!-- Pagination -->
      <nav
        v-if="store.totalPages > 1"
        class="flex items-center justify-center gap-1 border-t border-gray-100 px-4 py-3"
        :aria-label="t('audit_log.pagination_label')"
      >
        <button
          class="rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
          :disabled="store.page === 1"
          @click="goToPage(store.page - 1)"
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
            @click="goToPage(num as number)"
          >
            {{ num }}
          </button>
        </template>
        <button
          class="rounded border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-100"
          :disabled="store.page === store.totalPages"
          @click="goToPage(store.page + 1)"
        >
          {{ t("audit_log.page_next") }}
        </button>
      </nav>
    </section>

    <!-- Detail side panel -->
    <aside
      v-if="store.detail || store.detailLoading"
      class="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l border-gray-200 bg-white shadow-xl"
    >
      <div class="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <h2 class="text-sm font-semibold text-gray-800">
          {{ t("audit_log.detail_title") }}
        </h2>
        <button
          type="button"
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          @click="store.closeDetail()"
        >
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>
      <div class="flex-1 overflow-y-auto px-4 py-3 text-sm">
        <p v-if="store.detailLoading" class="text-gray-500">
          {{ t("common.loading") }}
        </p>
        <div v-else-if="store.detail" class="space-y-4">
          <dl class="grid grid-cols-3 gap-2">
            <dt class="text-xs uppercase text-gray-500">{{ t("audit_log.col_time") }}</dt>
            <dd class="col-span-2 font-mono text-xs">{{ formatTime(store.detail.occurred_at) }}</dd>
            <dt class="text-xs uppercase text-gray-500">{{ t("audit_log.col_action") }}</dt>
            <dd class="col-span-2 font-mono text-xs">{{ store.detail.action }}</dd>
            <dt class="text-xs uppercase text-gray-500">{{ t("audit_log.col_actor") }}</dt>
            <dd class="col-span-2 text-xs">{{ store.detail.actor_username || "—" }}</dd>
            <dt class="text-xs uppercase text-gray-500">{{ t("audit_log.col_target") }}</dt>
            <dd class="col-span-2 text-xs">
              <span v-if="store.detail.target_label">
                <span class="text-gray-400">{{ store.detail.target_type }}/</span>
                {{ store.detail.target_label }}
              </span>
              <span v-else>—</span>
            </dd>
            <dt class="text-xs uppercase text-gray-500">{{ t("audit_log.user_agent") }}</dt>
            <dd class="col-span-2 break-all text-xs text-gray-600">
              {{ store.detail.user_agent || "—" }}
            </dd>
          </dl>
          <div>
            <p class="mb-1 text-xs uppercase text-gray-500">{{ t("audit_log.payload") }}</p>
            <pre class="overflow-x-auto rounded-lg bg-gray-50 p-3 font-mono text-xs leading-relaxed text-gray-800">{{ prettyJson(store.detail.payload) }}</pre>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
