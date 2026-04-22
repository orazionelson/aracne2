/**
 * Zenodo deposit plugin store.
 *
 * Surfaces:
 *  - the plugin's non-sensitive config (GET/PUT /plugins/zenodo-deposit/config)
 *  - the deposit status for a specific collection slug
 *  - a manual re-deposit action for admins
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export type ZenodoAccessRight = "open" | "embargoed" | "restricted" | "closed";
export type ZenodoPublicationType =
  | "article"
  | "book"
  | "section"
  | "preprint"
  | "thesis"
  | "report"
  | "other";

export interface ZenodoConfig {
  token_set: boolean;
  base_url: string;
  default_community: string;
  auto_publish: boolean;
  access_right: ZenodoAccessRight;
  publication_type: ZenodoPublicationType;
  public_base_url: string;
}

export type ZenodoConfigUpdate = Partial<
  Omit<ZenodoConfig, "token_set"> & { api_token: string | null }
>;

export interface DepositStatus {
  deposit_id: number;
  doi: string | null;
  record_url: string | null;
  status: "draft" | "published" | "failed";
  submitted_at: string;
  error: string | null;
}

export const useZenodoStore = defineStore("zenodo", () => {
  const config = ref<ZenodoConfig | null>(null);
  const isLoading = ref(false);
  const isSaving = ref(false);

  async function fetchConfig(): Promise<void> {
    isLoading.value = true;
    try {
      config.value = await apiClient.get<ZenodoConfig>(
        "/plugins/zenodo-deposit/config",
      );
    } finally {
      isLoading.value = false;
    }
  }

  async function updateConfig(patch: ZenodoConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<ZenodoConfig>(
        "/plugins/zenodo-deposit/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function fetchStatus(slug: string): Promise<DepositStatus | null> {
    return apiClient.get<DepositStatus | null>(
      `/plugins/zenodo-deposit/collections/${slug}/status`,
    );
  }

  async function forceDeposit(slug: string): Promise<DepositStatus> {
    return apiClient.post<DepositStatus>(
      `/plugins/zenodo-deposit/collections/${slug}/deposit`,
    );
  }

  return {
    config,
    isLoading,
    isSaving,
    fetchConfig,
    updateConfig,
    fetchStatus,
    forceDeposit,
  };
});
