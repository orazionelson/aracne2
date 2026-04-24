/**
 * Zenodo (InvenioRDM) deposit plugin store.
 *
 * Surfaces:
 *  - the plugin's non-sensitive config
 *  - the live resource-type vocabulary (proxied from Zenodo)
 *  - the deposit status for a specific collection slug
 *  - a manual re-deposit action for admins
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export type AccessMode = "open" | "restricted";

export interface ZenodoConfig {
  token_set: boolean;
  base_url: string;
  default_community: string;
  auto_publish: boolean;
  access: AccessMode;
  /** InvenioRDM vocabulary id, e.g. "publication-book", "dataset". */
  resource_type: string;
  public_base_url: string;
}

export type ZenodoConfigUpdate = Partial<
  Omit<ZenodoConfig, "token_set"> & { api_token: string | null }
>;

export interface ResourceTypeOption {
  id: string;
  label: string;
  group: string;
}

export interface DepositStatus {
  deposit_id: string | null;
  doi: string | null;
  record_url: string | null;
  status: "draft" | "published" | "failed";
  submitted_at: string;
  error: string | null;
}

/**
 * Per-website deposit status. Adds two fields the collection-side
 * status doesn't carry: how many files were uploaded and whether they
 * were bundled as a single zip.
 */
export interface WebsiteDepositStatus extends DepositStatus {
  uploaded_as_zip: boolean | null;
  file_count: number | null;
}

export interface WebsiteDepositRequest {
  upload_as_zip: boolean;
}

export const useZenodoStore = defineStore("zenodo", () => {
  const config = ref<ZenodoConfig | null>(null);
  const resourceTypes = ref<ResourceTypeOption[]>([]);
  const isLoading = ref(false);
  const isSaving = ref(false);
  const isLoadingResourceTypes = ref(false);

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

  async function fetchResourceTypes(): Promise<void> {
    isLoadingResourceTypes.value = true;
    try {
      resourceTypes.value = await apiClient.get<ResourceTypeOption[]>(
        "/plugins/zenodo-deposit/resource-types",
      );
    } finally {
      isLoadingResourceTypes.value = false;
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

  // ── Website deposits ──────────────────────────────────────────────────

  const isDepositingWebsite = ref(false);

  async function fetchWebsiteStatus(
    slug: string,
  ): Promise<WebsiteDepositStatus | null> {
    return apiClient.get<WebsiteDepositStatus | null>(
      `/plugins/zenodo-deposit/websites/${encodeURIComponent(slug)}/status`,
    );
  }

  async function forceWebsiteDeposit(
    slug: string, body: WebsiteDepositRequest,
  ): Promise<WebsiteDepositStatus> {
    isDepositingWebsite.value = true;
    try {
      return await apiClient.post<WebsiteDepositStatus>(
        `/plugins/zenodo-deposit/websites/${encodeURIComponent(slug)}/deposit`,
        body,
      );
    } finally {
      isDepositingWebsite.value = false;
    }
  }

  return {
    config,
    resourceTypes,
    isLoading,
    isSaving,
    isLoadingResourceTypes,
    isDepositingWebsite,
    fetchConfig,
    updateConfig,
    fetchResourceTypes,
    fetchStatus,
    forceDeposit,
    fetchWebsiteStatus,
    forceWebsiteDeposit,
  };
});
