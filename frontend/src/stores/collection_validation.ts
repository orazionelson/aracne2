import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export type ValidationRunStatus = "pending" | "running" | "done" | "failed" | "cancelled";

export interface DocValidationError {
  line: number;
  col: number;
  message: string;
  path?: string;
}

export interface DocValidationResult {
  filename: string;
  valid: boolean;
  errors: DocValidationError[];
}

export interface ValidationRunInfo {
  id: number;
  collection_id: string;
  status: ValidationRunStatus;
  doc_count: number;
  validated_count: number;
  error_count: number;
  results: { documents: DocValidationResult[] } | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

const POLL_INTERVAL_MS = 2000;

export const useCollectionValidationStore = defineStore("collectionValidation", () => {
  const currentRun = ref<ValidationRunInfo | null>(null);
  const isStarting = ref(false);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function startRun(slug: string): Promise<void> {
    isStarting.value = true;
    try {
      currentRun.value = await apiClient.post<ValidationRunInfo>(
        `/collections/${slug}/validate-all`,
        {},
      );
      _startPolling(slug);
    } finally {
      isStarting.value = false;
    }
  }

  async function fetchLatest(slug: string): Promise<void> {
    try {
      const data = await apiClient.get<ValidationRunInfo | null>(
        `/collections/${slug}/validate-all/latest`,
      );
      currentRun.value = data;
      // Resume polling if the run is still in progress.
      if (data && (data.status === "pending" || data.status === "running")) {
        _startPolling(slug);
      }
    } catch {
      currentRun.value = null;
    }
  }

  async function cancelRun(slug: string, runId: number): Promise<void> {
    try {
      currentRun.value = await apiClient.post<ValidationRunInfo>(
        `/collections/${slug}/validate-all/${runId}/cancel`,
        {},
      );
    } catch {
      // Ignore — the status will be updated on the next poll.
    } finally {
      _stopPolling();
    }
  }

  async function _poll(slug: string): Promise<void> {
    if (!currentRun.value) return;
    try {
      const data = await apiClient.get<ValidationRunInfo>(
        `/collections/${slug}/validate-all/${currentRun.value.id}`,
      );
      currentRun.value = data;
      if (data.status === "done" || data.status === "failed" || data.status === "cancelled") {
        _stopPolling();
      }
    } catch {
      _stopPolling();
    }
  }

  function _startPolling(slug: string): void {
    _stopPolling();
    pollTimer = setInterval(() => { _poll(slug); }, POLL_INTERVAL_MS);
  }

  function _stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function reset(): void {
    _stopPolling();
    currentRun.value = null;
  }

  return { currentRun, isStarting, startRun, fetchLatest, cancelRun, reset };
});
