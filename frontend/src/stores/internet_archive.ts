/**
 * Internet Archive plugin store.
 *
 * Mirrors useZenodoStore in shape: config surface, per-collection
 * status, manual archive + refresh actions. The plugin's archive
 * endpoint submits to SPN2 and polls for up to 60s; the refresh
 * endpoint re-polls a pending job.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface InternetArchiveConfig {
  access_key_set: boolean;
  secret_key_set: boolean;
  auto_archive: boolean;
}

export type InternetArchiveConfigUpdate = Partial<
  Omit<InternetArchiveConfig, "access_key_set" | "secret_key_set"> & {
    access_key: string | null;
    secret_key: string | null;
  }
>;

export interface ArchiveStatus {
  job_id: string | null;
  status: "pending" | "success" | "failed";
  original_url: string | null;
  wayback_url: string | null;
  timestamp: string | null;
  submitted_at: string;
  error: string | null;
}

export const useInternetArchiveStore = defineStore("internet_archive", () => {
  const config = ref<InternetArchiveConfig | null>(null);
  const isLoading = ref(false);
  const isSaving = ref(false);

  async function fetchConfig(): Promise<void> {
    isLoading.value = true;
    try {
      config.value = await apiClient.get<InternetArchiveConfig>(
        "/plugins/internet-archive/config",
      );
    } finally {
      isLoading.value = false;
    }
  }

  async function updateConfig(
    patch: InternetArchiveConfigUpdate,
  ): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<InternetArchiveConfig>(
        "/plugins/internet-archive/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function fetchStatus(slug: string): Promise<ArchiveStatus | null> {
    return apiClient.get<ArchiveStatus | null>(
      `/plugins/internet-archive/collections/${slug}/status`,
    );
  }

  async function forceArchive(slug: string): Promise<ArchiveStatus> {
    return apiClient.post<ArchiveStatus>(
      `/plugins/internet-archive/collections/${slug}/archive`,
    );
  }

  async function refreshArchive(slug: string): Promise<ArchiveStatus> {
    return apiClient.post<ArchiveStatus>(
      `/plugins/internet-archive/collections/${slug}/refresh`,
    );
  }

  // ── Website archives ────────────────────────────────────────────────

  const isArchivingWebsite = ref(false);

  async function fetchWebsiteStatus(
    slug: string,
  ): Promise<ArchiveStatus | null> {
    return apiClient.get<ArchiveStatus | null>(
      `/plugins/internet-archive/websites/${encodeURIComponent(slug)}/status`,
    );
  }

  async function forceWebsiteArchive(slug: string): Promise<ArchiveStatus> {
    isArchivingWebsite.value = true;
    try {
      return await apiClient.post<ArchiveStatus>(
        `/plugins/internet-archive/websites/${encodeURIComponent(slug)}/archive`,
      );
    } finally {
      isArchivingWebsite.value = false;
    }
  }

  async function refreshWebsiteArchive(slug: string): Promise<ArchiveStatus> {
    return apiClient.post<ArchiveStatus>(
      `/plugins/internet-archive/websites/${encodeURIComponent(slug)}/refresh`,
    );
  }

  return {
    config,
    isLoading,
    isSaving,
    isArchivingWebsite,
    fetchConfig,
    updateConfig,
    fetchStatus,
    forceArchive,
    refreshArchive,
    fetchWebsiteStatus,
    forceWebsiteArchive,
    refreshWebsiteArchive,
  };
});
