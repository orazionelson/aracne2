/**
 * Github Integration plugin store.
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

export interface GithubConfig {
  pat_set: boolean;
}

export interface GithubConfigUpdate {
  pat?: string | null;
}

// ── Links ───────────────────────────────────────────────────────────────

export interface GithubLink {
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

export interface GithubLinkCreate {
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

export interface GithubPushRequest {
  message?: string | null;
}

export interface GithubPushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export interface GithubInitializeResponse {
  file_count: number;
  head_sha: string;
  initialized_at: string;
}

// ── Website links ───────────────────────────────────────────────────────

export interface GithubWebsiteLink {
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

export interface GithubWebsiteLinkCreate {
  base_url: string;
  repo_owner: string;
  repo_name: string;
  branch: string;
  pat_override?: string | null;
}

export interface GithubWebsitePushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export const useGithubStore = defineStore("github", () => {
  const config = ref<GithubConfig | null>(null);
  const isSaving = ref(false);
  const isPushing = ref(false);
  const isInitializing = ref(false);

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<GithubConfig>(
      "/plugins/github/config",
    );
  }

  async function updateConfig(patch: GithubConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<GithubConfig>(
        "/plugins/github/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function getLink(slug: string): Promise<GithubLink | null> {
    try {
      return await apiClient.get<GithubLink>(
        `/plugins/github/collections/${encodeURIComponent(slug)}/link`,
      );
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) return null;
      throw err;
    }
  }

  async function writeLink(
    slug: string, body: GithubLinkCreate,
  ): Promise<GithubLink> {
    return await apiClient.put<GithubLink>(
      `/plugins/github/collections/${encodeURIComponent(slug)}/link`,
      body,
    );
  }

  async function deleteLink(slug: string): Promise<void> {
    await apiClient.delete(
      `/plugins/github/collections/${encodeURIComponent(slug)}/link`,
    );
  }

  async function pushCollection(
    slug: string, message: string | null = null,
  ): Promise<GithubPushResponse> {
    isPushing.value = true;
    try {
      return await apiClient.post<GithubPushResponse>(
        `/plugins/github/collections/${encodeURIComponent(slug)}/push`,
        { message },
      );
    } finally {
      isPushing.value = false;
    }
  }

  async function initializeCollection(
    slug: string,
  ): Promise<GithubInitializeResponse> {
    isInitializing.value = true;
    try {
      return await apiClient.post<GithubInitializeResponse>(
        `/plugins/github/collections/${encodeURIComponent(slug)}/initialize`,
        {},
      );
    } finally {
      isInitializing.value = false;
    }
  }

  // ── Website link operations ──────────────────────────────────────────
  const isPushingWebsite = ref(false);

  async function getWebsiteLink(slug: string): Promise<GithubWebsiteLink | null> {
    try {
      return await apiClient.get<GithubWebsiteLink>(
        `/plugins/github/websites/${encodeURIComponent(slug)}/link`,
      );
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) return null;
      throw err;
    }
  }

  async function writeWebsiteLink(
    slug: string, body: GithubWebsiteLinkCreate,
  ): Promise<GithubWebsiteLink> {
    return await apiClient.put<GithubWebsiteLink>(
      `/plugins/github/websites/${encodeURIComponent(slug)}/link`,
      body,
    );
  }

  async function deleteWebsiteLink(slug: string): Promise<void> {
    await apiClient.delete(
      `/plugins/github/websites/${encodeURIComponent(slug)}/link`,
    );
  }

  async function pushWebsite(
    slug: string, message: string | null = null,
  ): Promise<GithubWebsitePushResponse> {
    isPushingWebsite.value = true;
    try {
      return await apiClient.post<GithubWebsitePushResponse>(
        `/plugins/github/websites/${encodeURIComponent(slug)}/push`,
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
