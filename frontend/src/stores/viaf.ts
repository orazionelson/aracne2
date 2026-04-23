/**
 * VIAF lookup plugin store.
 *
 * Single action: search(q) → list of VIAF AutoSuggest hits shown in
 * the ViafLinkPanel inside the TEI editor. No config — the plugin's
 * admin page is purely informational.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface ViafHit {
  viaf_id: string;
  uri: string;
  display: string;
  name_type: string; // "personal" | "corporate" | ""
}

export const useViafStore = defineStore("viaf", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<ViafHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<ViafHit[]>("/plugins/viaf/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
