/**
 * ORCID lookup plugin store.
 *
 * Single action: search(q) → list of ORCID hits shown in the
 * OrcidLinkPanel inside the TEI editor. No config — the plugin's
 * admin page is purely informational.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface OrcidHit {
  orcid: string;
  uri: string;
  given_names: string | null;
  family_name: string | null;
  credit_name: string | null;
  affiliations: string[];
}

export const useOrcidStore = defineStore("orcid", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<OrcidHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<OrcidHit[]>("/plugins/orcid/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
