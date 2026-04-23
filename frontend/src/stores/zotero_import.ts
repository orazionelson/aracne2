/**
 * Zotero import plugin store.
 *
 * Exposes:
 *  - non-sensitive config (GET/PUT /plugins/zotero-import/config)
 *  - preview(slug) → diff of the library vs previously-imported keys
 *  - importItems(slug, body) → persist the new items as a
 *    CollectionBibliography version
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export type LibraryType = "user" | "group";

export interface ZoteroConfig {
  api_key_set: boolean;
  library_type: LibraryType;
  library_id: string;
  api_base: string;
}

export type ZoteroConfigUpdate = Partial<
  Omit<ZoteroConfig, "api_key_set"> & { api_key: string | null }
>;

export interface ZoteroItemPreview {
  key: string;
  item_type: string;
  title: string;
  creators: string[];
  year: number | null;
  doi: string | null;
}

export interface ImportPreview {
  new: ZoteroItemPreview[];
  already_imported: ZoteroItemPreview[];
  total_fetched: number;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  bibliography_version: number;
  imported_at: string;
}

export const useZoteroImportStore = defineStore("zotero_import", () => {
  const config = ref<ZoteroConfig | null>(null);
  const isLoading = ref(false);
  const isSaving = ref(false);

  async function fetchConfig(): Promise<void> {
    isLoading.value = true;
    try {
      config.value = await apiClient.get<ZoteroConfig>(
        "/plugins/zotero-import/config",
      );
    } finally {
      isLoading.value = false;
    }
  }

  async function updateConfig(patch: ZoteroConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<ZoteroConfig>(
        "/plugins/zotero-import/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function previewImport(slug: string): Promise<ImportPreview> {
    return apiClient.post<ImportPreview>(
      `/plugins/zotero-import/collections/${slug}/preview`,
    );
  }

  async function importItems(
    slug: string,
    body: { keys?: string[]; all_new?: boolean },
  ): Promise<ImportResult> {
    return apiClient.post<ImportResult>(
      `/plugins/zotero-import/collections/${slug}/import`,
      body,
    );
  }

  return {
    config,
    isLoading,
    isSaving,
    fetchConfig,
    updateConfig,
    previewImport,
    importItems,
  };
});
