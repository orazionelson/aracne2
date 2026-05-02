/**
 * Pinia store for /admin/fixity (CTS R7 deliverable).
 *
 * Tracks the paginated list of fixity rows, the per-status summary
 * cards, and a "rechecking" flag for the synchronous recheck-now
 * button. Filters are kept here, not in the URL — admins page
 * through them interactively.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { apiClient } from "@/services/api";

export type FixityStatus = "ok" | "drifted" | "missing" | "error";

export interface FixityRecordView {
  id: string;
  collection_id: string;
  document_filename: string;
  expected_sha256: string;
  last_seen_sha256: string | null;
  version_number: number;
  size_bytes: number;
  status: FixityStatus;
  first_recorded_at: string;
  last_checked_at: string | null;
  drifted_at: string | null;
}

export interface FixitySummary {
  ok: number;
  drifted: number;
  missing: number;
  error: number;
}

export interface FixityRecheckResult extends FixitySummary {
  total: number;
}

export const useFixityStore = defineStore("fixity", () => {
  const rows = ref<FixityRecordView[]>([]);
  const total = ref(0);
  const page = ref(1);
  const perPage = ref(50);
  const totalPages = ref(0);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const summary = ref<FixitySummary>({ ok: 0, drifted: 0, missing: 0, error: 0 });

  const filterStatus = ref<FixityStatus | "">("");
  const isRechecking = ref(false);

  const driftCount = computed(
    () => summary.value.drifted + summary.value.missing + summary.value.error,
  );

  async function fetchPage(newPage = page.value): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const params = new URLSearchParams();
      params.set("page", String(newPage));
      params.set("per_page", String(perPage.value));
      if (filterStatus.value) params.set("status", filterStatus.value);
      const res = await apiClient.getPaginated<FixityRecordView>(
        `/fixity?${params.toString()}`,
      );
      rows.value = res.data;
      const meta = res.pagination as {
        page: number;
        per_page: number;
        total: number;
        total_pages: number;
      };
      total.value = meta.total;
      page.value = meta.page;
      totalPages.value = meta.total_pages;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchSummary(): Promise<void> {
    try {
      summary.value = await apiClient.get<FixitySummary>("/fixity/summary");
    } catch {
      // Non-fatal: dashboard cards stay at last value.
    }
  }

  async function recheckNow(): Promise<FixityRecheckResult | null> {
    isRechecking.value = true;
    try {
      const res = await apiClient.post<FixityRecheckResult>("/fixity/recheck");
      await Promise.all([fetchSummary(), fetchPage(1)]);
      return res;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      return null;
    } finally {
      isRechecking.value = false;
    }
  }

  return {
    rows,
    total,
    page,
    perPage,
    totalPages,
    isLoading,
    error,
    summary,
    filterStatus,
    isRechecking,
    driftCount,
    fetchPage,
    fetchSummary,
    recheckNow,
  };
});
