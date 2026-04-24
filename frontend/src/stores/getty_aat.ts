/**
 * Getty AAT lookup plugin store.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface GettyAatHit {
  aat_id: string;
  uri: string;
  label: string;
  scope_note: string;
}

export const useGettyAatStore = defineStore("gettyAat", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<GettyAatHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<GettyAatHit[]>("/plugins/getty-aat/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
