/**
 * Pinia store for the admin audit-log view (FUTURE_IDEAS §20).
 *
 * Holds the current page of rows, the active filter set, and the
 * detail-panel target. Filters are kept here (not in the URL) so the
 * back/forward buttons inside the admin layout don't churn — admins
 * page through filters interactively, not via deep links.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { apiClient } from "@/services/api";

export interface AuditLogEntry {
  id: number;
  occurred_at: string;
  action: string;
  actor_id: string | null;
  actor_username: string | null;
  target_type: string | null;
  target_id: string | null;
  target_label: string | null;
}

export interface AuditLogDetail extends AuditLogEntry {
  payload: Record<string, unknown> | null;
  user_agent: string | null;
}

export interface AuditLogFilters {
  q: string;
  action: string;
  actor_username: string;
  target_type: string;
  target_id: string;
  from: string;
  to: string;
}

const EMPTY_FILTERS: AuditLogFilters = {
  q: "",
  action: "",
  actor_username: "",
  target_type: "",
  target_id: "",
  from: "",
  to: "",
};

function buildQuery(filters: AuditLogFilters, page: number, perPage: number): URLSearchParams {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("per_page", String(perPage));
  for (const [key, value] of Object.entries(filters)) {
    const v = value.trim();
    if (v) params.set(key, v);
  }
  return params;
}

export const useAuditLogStore = defineStore("auditLog", () => {
  const entries = ref<AuditLogEntry[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(20);
  const totalPages = ref(0);

  const filters = ref<AuditLogFilters>({ ...EMPTY_FILTERS });
  const knownActions = ref<string[]>([]);

  const detail = ref<AuditLogDetail | null>(null);
  const detailLoading = ref(false);

  const hasFilters = computed(() =>
    Object.values(filters.value).some((v) => v.trim().length > 0),
  );

  async function fetchPage(newPage = page.value): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const qs = buildQuery(filters.value, newPage, perPage.value).toString();
      const res = await apiClient.getPaginated<AuditLogEntry>(`/audit-log?${qs}`);
      entries.value = res.data;
      const meta = res.pagination as {
        page: number;
        per_page: number;
        total: number;
        total_pages: number;
      };
      total.value = meta.total;
      totalPages.value = meta.total_pages;
      page.value = meta.page;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchActions(): Promise<void> {
    if (knownActions.value.length > 0) return;
    try {
      const data = await apiClient.get<string[]>("/audit-log/actions");
      knownActions.value = data;
    } catch {
      // Non-fatal: dropdown stays empty; the free-text box still works.
    }
  }

  async function fetchDetail(id: number): Promise<void> {
    detailLoading.value = true;
    detail.value = null;
    try {
      detail.value = await apiClient.get<AuditLogDetail>(`/audit-log/${id}`);
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      detailLoading.value = false;
    }
  }

  function closeDetail(): void {
    detail.value = null;
  }

  function resetFilters(): void {
    filters.value = { ...EMPTY_FILTERS };
    page.value = 1;
  }

  function csvUrl(): string {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(filters.value)) {
      const v = value.trim();
      if (v) qs.set(key, v);
    }
    const tail = qs.toString();
    return `/api/v1/audit-log/export.csv${tail ? "?" + tail : ""}`;
  }

  return {
    entries,
    isLoading,
    error,
    total,
    page,
    perPage,
    totalPages,
    filters,
    hasFilters,
    knownActions,
    detail,
    detailLoading,
    fetchPage,
    fetchActions,
    fetchDetail,
    closeDetail,
    resetFilters,
    csvUrl,
  };
});
