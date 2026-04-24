/**
 * OpenAlex lookup plugin store.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface OpenAlexPreview {
  title: string;
  authors: string[];
  year: number | null;
  type: string | null;
  container: string | null;
  publisher: string | null;
  doi: string | null;
  openalex_id: string;
  uri: string;
}

export interface OpenAlexHit {
  xml_id: string;
  biblstruct_xml: string;
  preview: OpenAlexPreview;
}

export interface OpenAlexConfig {
  contact_email: string;
  fallback_email: string;
}

export type OpenAlexConfigUpdate = Partial<{
  contact_email: string | null;
}>;

export const useOpenAlexStore = defineStore("openalex", () => {
  const config = ref<OpenAlexConfig | null>(null);
  const isSearching = ref(false);
  const isSaving = ref(false);

  async function search(q: string, rows = 15): Promise<OpenAlexHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<OpenAlexHit[]>("/plugins/openalex/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<OpenAlexConfig>("/plugins/openalex/config");
  }

  async function updateConfig(patch: OpenAlexConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<OpenAlexConfig>(
        "/plugins/openalex/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  return { config, isSearching, isSaving, search, fetchConfig, updateConfig };
});
