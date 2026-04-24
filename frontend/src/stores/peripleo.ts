/**
 * Peripleo (Pelagios aggregator) lookup plugin store.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface PeripleoHit {
  uri: string;
  label: string;
  source: string;
  detail: string;
}

export const usePeripleoStore = defineStore("peripleo", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<PeripleoHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<PeripleoHit[]>("/plugins/peripleo/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
