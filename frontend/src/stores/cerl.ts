/**
 * CERL Thesaurus lookup plugin store.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface CerlHit {
  cerl_id: string;
  uri: string;
  label: string;
  detail: string;
  kind: "person" | "corporate" | "place" | "imprint" | "other";
}

export const useCerlStore = defineStore("cerl", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<CerlHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<CerlHit[]>("/plugins/cerl/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
