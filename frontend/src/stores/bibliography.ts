/**
 * Bibliography store — external-service integrations that resolve to a
 * TEI <biblStruct> fragment.
 *
 * Currently hosts only the CrossRef DOI resolver. Isolated from
 * ``useCollectionStore`` because it is scoped to the editor UI, not to a
 * specific collection.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface BiblStructPreview {
  title: string | null;
  authors: string[];
  year: number | null;
  container: string | null;
  publisher: string | null;
  doi: string | null;
  /** TEI biblStruct/@type as mapped by the backend. */
  type: string | null;
}

export interface CrossrefLookupResult {
  xml_id: string;
  biblstruct_xml: string;
  preview: BiblStructPreview;
}

export const useBibliographyStore = defineStore("bibliography", () => {
  const isResolving = ref(false);
  const lastResult = ref<CrossrefLookupResult | null>(null);

  async function lookupDoi(doi: string): Promise<CrossrefLookupResult> {
    isResolving.value = true;
    try {
      const result = await apiClient.get<CrossrefLookupResult>(
        "/bibliography/crossref",
        { params: { doi } },
      );
      lastResult.value = result;
      return result;
    } finally {
      isResolving.value = false;
    }
  }

  function reset(): void {
    lastResult.value = null;
  }

  return {
    isResolving,
    lastResult,
    lookupDoi,
    reset,
  };
});
