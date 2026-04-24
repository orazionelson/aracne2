/**
 * Codeberg Integration plugin store.
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

export interface CodebergConfig {
  pat_set: boolean;
}

export interface CodebergConfigUpdate {
  pat?: string | null;
}

// ── Links ───────────────────────────────────────────────────────────────

export interface CodebergLink {
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

export interface CodebergLinkCreate {
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

export interface CodebergPushRequest {
  message?: string | null;
}

export interface CodebergPushResponse {
  sha: string;
  committed_at: string;
  html_url: string | null;
  file_count: number;
}

export interface CodebergInitializeResponse {
  file_count: number;
  head_sha: string;
  initialized_at: string;
}

export const useCodebergStore = defineStore("codeberg", () => {
  const config = ref<CodebergConfig | null>(null);
  const isSaving = ref(false);
  const isPushing = ref(false);
  const isInitializing = ref(false);

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<CodebergConfig>(
      "/plugins/codeberg/config",
    );
  }

  async function updateConfig(patch: CodebergConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<CodebergConfig>(
        "/plugins/codeberg/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function getLink(slug: string): Promise<CodebergLink | null> {
    try {
      return await apiClient.get<CodebergLink>(
        `/plugins/codeberg/collections/${encodeURIComponent(slug)}/link`,
      );
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) return null;
      throw err;
    }
  }

  async function writeLink(
    slug: string, body: CodebergLinkCreate,
  ): Promise<CodebergLink> {
    return await apiClient.put<CodebergLink>(
      `/plugins/codeberg/collections/${encodeURIComponent(slug)}/link`,
      body,
    );
  }

  async function deleteLink(slug: string): Promise<void> {
    await apiClient.delete(
      `/plugins/codeberg/collections/${encodeURIComponent(slug)}/link`,
    );
  }

  async function pushCollection(
    slug: string, message: string | null = null,
  ): Promise<CodebergPushResponse> {
    isPushing.value = true;
    try {
      return await apiClient.post<CodebergPushResponse>(
        `/plugins/codeberg/collections/${encodeURIComponent(slug)}/push`,
        { message },
      );
    } finally {
      isPushing.value = false;
    }
  }

  async function initializeCollection(
    slug: string,
  ): Promise<CodebergInitializeResponse> {
    isInitializing.value = true;
    try {
      return await apiClient.post<CodebergInitializeResponse>(
        `/plugins/codeberg/collections/${encodeURIComponent(slug)}/initialize`,
        {},
      );
    } finally {
      isInitializing.value = false;
    }
  }

  return {
    config, isSaving, isPushing, isInitializing,
    fetchConfig, updateConfig,
    getLink, writeLink, deleteLink, pushCollection, initializeCollection,
  };
});
