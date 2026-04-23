/**
 * ROR lookup plugin store.
 *
 * Single action: search(q) → list of ROR hits shown in the
 * RorLinkPanel inside the TEI editor. No config — the plugin's
 * admin page is purely informational.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface RorHit {
  ror_id: string;
  uri: string;
  name: string;
  aliases: string[];
  country: string | null;
  types: string[];
}

export const useRorStore = defineStore("ror", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<RorHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<RorHit[]>("/plugins/ror/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
