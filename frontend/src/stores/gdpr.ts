/**
 * Pinia store for ``/admin/gdpr`` — the GDPR request queue.
 *
 * Holds the list of open requests + per-row "review notes" the
 * Admin types before approving / rejecting. Filters and detail
 * panel state are kept here, not in the URL — admins typically
 * triage one request at a time.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export type GdprRequestStatus =
  | "submitted"
  | "approved"
  | "rejected"
  | "completed";

export interface GdprRequestView {
  id: string;
  user_id: string;
  user_username: string | null;
  kind: string;
  status: GdprRequestStatus;
  reason: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  review_notes: string | null;
}

export const useGdprStore = defineStore("gdpr", () => {
  const requests = ref<GdprRequestView[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  // The Admin types review notes per row; we hold them here so the
  // textarea state survives a re-fetch of the queue.
  const reviewNotes = ref<Record<string, string>>({});
  const actingId = ref<string | null>(null);

  async function fetchRequests(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      requests.value = await apiClient.get<GdprRequestView[]>(
        "/admin/gdpr/requests",
      );
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  function getNotes(id: string): string {
    return reviewNotes.value[id] ?? "";
  }

  function setNotes(id: string, value: string): void {
    reviewNotes.value = { ...reviewNotes.value, [id]: value };
  }

  async function executeAnonymise(id: string): Promise<boolean> {
    actingId.value = id;
    error.value = null;
    try {
      await apiClient.post(`/admin/gdpr/anonymise/${id}`, {
        review_notes: (reviewNotes.value[id] ?? "").trim() || null,
      });
      delete reviewNotes.value[id];
      reviewNotes.value = { ...reviewNotes.value };
      await fetchRequests();
      return true;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      return false;
    } finally {
      actingId.value = null;
    }
  }

  async function rejectRequest(id: string): Promise<boolean> {
    actingId.value = id;
    error.value = null;
    try {
      await apiClient.post(`/admin/gdpr/reject/${id}`, {
        review_notes: (reviewNotes.value[id] ?? "").trim() || null,
      });
      delete reviewNotes.value[id];
      reviewNotes.value = { ...reviewNotes.value };
      await fetchRequests();
      return true;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      return false;
    } finally {
      actingId.value = null;
    }
  }

  return {
    requests,
    isLoading,
    error,
    reviewNotes,
    actingId,
    fetchRequests,
    getNotes,
    setNotes,
    executeAnonymise,
    rejectRequest,
  };
});
