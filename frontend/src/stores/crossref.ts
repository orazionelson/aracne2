/**
 * CrossRef Lookup plugin store.
 *
 * Resolves a DOI to a ready-to-insert TEI ``<biblStruct>`` via the
 * plugin's proxy of CrossRef's public ``/works/{doi}``. The plugin
 * also exposes a single-field config (polite-pool contact email)
 * which the admin UI edits through ``/plugins/crossref-lookup/config``.
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

export interface CrossrefConfig {
  contact_email: string;
  /** Falls back to this when ``contact_email`` is empty. Shown read-only. */
  fallback_email: string;
}

export type CrossrefConfigUpdate = Partial<{
  contact_email: string | null;
}>;

export const useCrossrefStore = defineStore("crossref", () => {
  const config = ref<CrossrefConfig | null>(null);
  const isResolving = ref(false);
  const isSaving = ref(false);
  const lastResult = ref<CrossrefLookupResult | null>(null);

  async function fetchConfig(): Promise<void> {
    config.value = await apiClient.get<CrossrefConfig>(
      "/plugins/crossref-lookup/config",
    );
  }

  async function updateConfig(patch: CrossrefConfigUpdate): Promise<void> {
    isSaving.value = true;
    try {
      config.value = await apiClient.put<CrossrefConfig>(
        "/plugins/crossref-lookup/config",
        patch,
      );
    } finally {
      isSaving.value = false;
    }
  }

  async function lookupDoi(doi: string): Promise<CrossrefLookupResult> {
    isResolving.value = true;
    try {
      const result = await apiClient.get<CrossrefLookupResult>(
        "/plugins/crossref-lookup/lookup",
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
    config,
    isResolving,
    isSaving,
    lastResult,
    fetchConfig,
    updateConfig,
    lookupDoi,
    reset,
  };
});
