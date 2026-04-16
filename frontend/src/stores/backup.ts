import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export type BackupScope = "database" | "collections" | "media";
export type BackupJobStatus = "pending" | "running" | "done" | "failed";

export interface BackupJob {
  id: string;
  label: string;
  scopes: BackupScope[];
  status: BackupJobStatus;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  filename: string | null;
  size_bytes: number | null;
}

export const useBackupStore = defineStore("backup", () => {
  const jobs = ref<BackupJob[]>([]);
  const isLoading = ref(false);

  async function fetchJobs(): Promise<void> {
    isLoading.value = true;
    try {
      jobs.value = await apiClient.get<BackupJob[]>("/backup/jobs");
    } finally {
      isLoading.value = false;
    }
  }

  async function createBackup(scopes: BackupScope[], label: string): Promise<BackupJob> {
    const job = await apiClient.post<BackupJob>("/backup/jobs", { scopes, label });
    jobs.value.unshift(job);
    return job;
  }

  async function refreshJob(jobId: string): Promise<void> {
    const updated = await apiClient.get<BackupJob>(`/backup/jobs/${jobId}`);
    const idx = jobs.value.findIndex((j) => j.id === jobId);
    if (idx !== -1) {
      jobs.value[idx] = updated;
    }
  }

  async function deleteJob(jobId: string): Promise<void> {
    await apiClient.delete<void>(`/backup/jobs/${jobId}`);
    jobs.value = jobs.value.filter((j) => j.id !== jobId);
  }

  function downloadUrl(jobId: string): string {
    return `/api/v1/backup/jobs/${jobId}/download`;
  }

  return { jobs, isLoading, fetchJobs, createBackup, refreshJob, deleteJob, downloadUrl };
});
