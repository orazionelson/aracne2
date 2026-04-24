/**
 * GND (lobid.org) lookup plugin store.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface GndHit {
  gnd_id: string;
  uri: string;
  label: string;
  detail: string;
  kind: "person" | "corporate" | "place" | "work" | "subject" | "other";
}

export const useGndStore = defineStore("gnd", () => {
  const isSearching = ref(false);

  async function search(q: string, rows = 15): Promise<GndHit[]> {
    isSearching.value = true;
    try {
      return await apiClient.get<GndHit[]>("/plugins/gnd/search", {
        params: { q, rows },
      });
    } finally {
      isSearching.value = false;
    }
  }

  return { isSearching, search };
});
