/**
 * Dataverse Integration plugin store.
 *
 * Mirrors useZenodoStore in shape: config surface, per-collection /
 * per-website status, manual deposit actions. Both deposit
 * endpoints accept a per-deposit alias override that wins over the
 * plugin's default Dataverse alias.
 */

import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export type PublishType = "major" | "minor" | "updatecurrent";

export interface DataverseConfig {
  token_set: boolean;
  base_url: string;
  default_alias: string;
  auto_deposit: boolean;
  auto_publish: boolean;
  default_subject: string;
  contact_name: string;
  contact_email: string;
  publish_type: PublishType;
  public_base_url: string;
}

export type DataverseConfigUpdate = Partial<
  Omit<DataverseConfig, "token_set"> & { api_token: string | null }
>;

export interface DataverseDepositStatus {
  persistent_id: string | null;
  doi: string | null;
  landing_url: string | null;
  status: "draft" | "published" | "failed";
  submitted_at: string;
  error: string | null;
  alias?: string | null;
  uploaded_as_zip?: boolean | null;
  file_count?: number | null;
}

export interface CollectionDepositRequest {
  alias?: string | null;
}

export interface WebsiteDepositRequest {
  upload_as_zip: boolean;
  alias?: string | null;
}

export const useDataverseStore = defineStore("dataverse", () => {
  const config = ref<DataverseConfig | null>(null);
  const isLoading = ref(false);
  const isSaving = ref(false);
  const isDepositingCollection = ref(false);
  const isDepositingWebsite = ref(false);

  async function fetchConfig(): Promise<void> {
    isLoading.value = true;
    try {
      config.value = await apiClient.get<DataverseConfig>(
        "/plugins/dataverse/config",
      );
    } finally {
      isLoading.value = false;
    }
  }

  async function updateConfig(patch: DataverseConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<DataverseConfig>(
        "/plugins/dataverse/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function fetchCollectionStatus(
    slug: string,
  ): Promise<DataverseDepositStatus | null> {
    return apiClient.get<DataverseDepositStatus | null>(
      `/plugins/dataverse/collections/${encodeURIComponent(slug)}/status`,
    );
  }

  async function forceCollectionDeposit(
    slug: string, body: CollectionDepositRequest = {},
  ): Promise<DataverseDepositStatus> {
    isDepositingCollection.value = true;
    try {
      return await apiClient.post<DataverseDepositStatus>(
        `/plugins/dataverse/collections/${encodeURIComponent(slug)}/deposit`,
        body,
      );
    } finally {
      isDepositingCollection.value = false;
    }
  }

  async function fetchWebsiteStatus(
    slug: string,
  ): Promise<DataverseDepositStatus | null> {
    return apiClient.get<DataverseDepositStatus | null>(
      `/plugins/dataverse/websites/${encodeURIComponent(slug)}/status`,
    );
  }

  async function forceWebsiteDeposit(
    slug: string, body: WebsiteDepositRequest,
  ): Promise<DataverseDepositStatus> {
    isDepositingWebsite.value = true;
    try {
      return await apiClient.post<DataverseDepositStatus>(
        `/plugins/dataverse/websites/${encodeURIComponent(slug)}/deposit`,
        body,
      );
    } finally {
      isDepositingWebsite.value = false;
    }
  }

  return {
    config,
    isLoading, isSaving,
    isDepositingCollection, isDepositingWebsite,
    fetchConfig, updateConfig,
    fetchCollectionStatus, forceCollectionDeposit,
    fetchWebsiteStatus, forceWebsiteDeposit,
  };
});
