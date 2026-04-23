/**
 * GeoNames lookup plugin store.
 *
 * Two actions:
 *   - search(q)        → list of populated-place hits for the editor panel
 *   - fetchConfig()    → current url_format + shared username (Admin only)
 *   - updateConfig(p)  → Admin change of url_format
 *
 * File name is ``geonames_lookup.ts`` (rather than ``geonames.ts``) so
 * it does not clash with any future plain GeoNames helper module.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface GeonamesHit {
  geoname_id: string;
  uri: string;
  display: string;
  name: string;
  region: string;
  country: string;
  feature_class: string;
}

export type GeonamesUrlFormat = "web" | "sws";

export interface GeonamesConfig {
  url_format: GeonamesUrlFormat;
  geonames_username: string;
}

export interface GeonamesConfigUpdate {
  url_format?: GeonamesUrlFormat;
}

export const useGeonamesLookupStore = defineStore("geonamesLookup", () => {
  const config = ref<GeonamesConfig | null>(null);
  const isSearching = ref(false);
  const isSaving = ref(false);

  async function search(q: string, rows = 15): Promise<GeonamesHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<GeonamesHit[]>("/plugins/geonames/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<GeonamesConfig>("/plugins/geonames/config");
  }

  async function updateConfig(patch: GeonamesConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<GeonamesConfig>(
        "/plugins/geonames/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  return {
    config,
    isSearching,
    isSaving,
    search,
    fetchConfig,
    updateConfig,
  };
});
