/**
 * Trismegistos lookup plugin store.
 *
 * The search endpoint returns 503 with ``code: "TMG_API_KEY_MISSING"``
 * when the admin has not yet configured a key. Consumers are expected
 * to catch the rejected promise and render a "Set API key" banner.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface TrismegistosHit {
  tm_id: string;
  uri: string;
  label: string;
  detail: string;
  kind: "person" | "place" | "text";
}

export interface TrismegistosConfig {
  api_key_set: boolean;
  registration_url: string;
}

export type TrismegistosConfigUpdate = Partial<{ api_key: string | null }>;

export const useTrismegistosStore = defineStore("trismegistos", () => {
  const config = ref<TrismegistosConfig | null>(null);
  const isSearching = ref(false);
  const isSaving = ref(false);

  async function search(q: string, rows = 15): Promise<TrismegistosHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<TrismegistosHit[]>(
        "/plugins/trismegistos/search",
        { params: { q, rows } },
      );
    } finally {
      isSearching.value = false;
    }
  }

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<TrismegistosConfig>(
      "/plugins/trismegistos/config",
    );
  }

  async function updateConfig(patch: TrismegistosConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<TrismegistosConfig>(
        "/plugins/trismegistos/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  return { config, isSearching, isSaving, search, fetchConfig, updateConfig };
});
