/**
 * Gitlab Integration plugin store.
 *
 * Two concerns: the global plugin config (PAT) managed by Admin,
 * and per-collection links (repo binding + push bookkeeping)
 * managed by EditorInChief+.
 *
 * Phase 1 covers collection push only. Phase 2 will add Initialize
 * and website links.
 */

import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

// ── Config ──────────────────────────────────────────────────────────────

export interface GitlabConfig {
  pat_set: boolean;
}

export interface GitlabConfigUpdate {
  pat?: string | null;
}

// ── Links ───────────────────────────────────────────────────────────────

export interface GitlabLink {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  pat_override_set: boolean;
  last_push_sha: string | null;
  last_push_at: string | null;
  initialized_at: string | null;
  initialized_from_sha: string | null;
  html_url: string;
}

export interface GitlabLinkCreate {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  /**
   * ``undefined``/omitted → leave existing override alone.
   * ``""`` → clear the override (use global PAT).
   * any string → encrypt and store as new override.
   */
  pat_override?: string | null;
}

// ── Push ────────────────────────────────────────────────────────────────

export interface GitlabPushRequest {
  message?: string | null;
}

export interface GitlabPushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export interface GitlabInitializeResponse {
  file_count: number;
  head_sha: string;
  initialized_at: string;
}

// ── Website links ───────────────────────────────────────────────────────

export interface GitlabWebsiteLink {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  pat_override_set: boolean;
  last_push_sha: string | null;
  last_push_at: string | null;
  last_push_file_count: number | null;
  html_url: string;
}

export interface GitlabWebsiteLinkCreate {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  pat_override?: string | null;
}

export interface GitlabWebsitePushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export const useGitlabStore = defineStore("gitlab", () => {
  const config = ref<GitlabConfig | null>(null);
  const isSaving = ref(false);
  const isPushing = ref(false);
  const isInitializing = ref(false);

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<GitlabConfig>(
      "/plugins/gitlab/config",
    );
  }

  async function updateConfig(patch: GitlabConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<GitlabConfig>(
        "/plugins/gitlab/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function getLink(slug: string): Promise<GitlabLink | null> {
    try {
      return await apiClient.get<GitlabLink>(
        `/plugins/gitlab/collections/${encodeURIComponent(slug)}/link`,
      );
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) return null;
      throw err;
    }
  }

  async function writeLink(
    slug: string, body: GitlabLinkCreate,
  ): Promise<GitlabLink> {
    return await apiClient.put<GitlabLink>(
      `/plugins/gitlab/collections/${encodeURIComponent(slug)}/link`,
      body,
    );
  }

  async function deleteLink(slug: string): Promise<void> {
    await apiClient.delete(
      `/plugins/gitlab/collections/${encodeURIComponent(slug)}/link`,
    );
  }

  async function pushCollection(
    slug: string, message: string | null = null,
  ): Promise<GitlabPushResponse> {
    isPushing.value = true;
    try {
      return await apiClient.post<GitlabPushResponse>(
        `/plugins/gitlab/collections/${encodeURIComponent(slug)}/push`,
        { message },
      );
    } finally {
      isPushing.value = false;
    }
  }

  async function initializeCollection(
    slug: string,
  ): Promise<GitlabInitializeResponse> {
    isInitializing.value = true;
    try {
      return await apiClient.post<GitlabInitializeResponse>(
        `/plugins/gitlab/collections/${encodeURIComponent(slug)}/initialize`,
        {},
      );
    } finally {
      isInitializing.value = false;
    }
  }

  // ── Website link operations ──────────────────────────────────────────
  const isPushingWebsite = ref(false);

  async function getWebsiteLink(slug: string): Promise<GitlabWebsiteLink | null> {
    try {
      return await apiClient.get<GitlabWebsiteLink>(
        `/plugins/gitlab/websites/${encodeURIComponent(slug)}/link`,
      );
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) return null;
      throw err;
    }
  }

  async function writeWebsiteLink(
    slug: string, body: GitlabWebsiteLinkCreate,
  ): Promise<GitlabWebsiteLink> {
    return await apiClient.put<GitlabWebsiteLink>(
      `/plugins/gitlab/websites/${encodeURIComponent(slug)}/link`,
      body,
    );
  }

  async function deleteWebsiteLink(slug: string): Promise<void> {
    await apiClient.delete(
      `/plugins/gitlab/websites/${encodeURIComponent(slug)}/link`,
    );
  }

  async function pushWebsite(
    slug: string, message: string | null = null,
  ): Promise<GitlabWebsitePushResponse> {
    isPushingWebsite.value = true;
    try {
      return await apiClient.post<GitlabWebsitePushResponse>(
        `/plugins/gitlab/websites/${encodeURIComponent(slug)}/push`,
        { message },
      );
    } finally {
      isPushingWebsite.value = false;
    }
  }

  return {
    config, isSaving, isPushing, isInitializing, isPushingWebsite,
    fetchConfig, updateConfig,
    getLink, writeLink, deleteLink, pushCollection, initializeCollection,
    getWebsiteLink, writeWebsiteLink, deleteWebsiteLink, pushWebsite,
  };
});
