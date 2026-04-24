/**
 * Trismegistos ID-resolver store.
 *
 * Trismegistos does not publish a free-text search API — the plugin
 * exposes a single ``POST /plugins/trismegistos/resolve`` that
 * takes ``{ kind, identifier, source }`` and returns either a
 * ``TrismegistosHit`` or ``null``. The backend uses the public
 * ``texrelations`` / ``georelations`` endpoints plus offline URL
 * composition for persons. No credentials are stored.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export type TmKind = "person" | "place" | "text";

export type TmTextSource =
  | "trismegistos"
  | "ddbdp"
  | "hgv"
  | "phi"
  | "edh"
  | "edcs"
  | "edr"
  | "edb"
  | "isic"
  | "rib"
  | "lupa"
  | "pn"
  | "ba"
  | "he"
  | "uoxf";

export interface TrismegistosHit {
  tm_id: string;
  uri: string;
  label: string;
  kind: TmKind;
  partners: Record<string, string[]>;
}

export interface TrismegistosResolveRequest {
  kind: TmKind;
  identifier: string;
  source: TmTextSource;
}

export const useTrismegistosStore = defineStore("trismegistos", () => {
  const isResolving = ref(false);

  async function resolveId(
    req: TrismegistosResolveRequest,
  ): Promise<TrismegistosHit | null> {
    isResolving.value = true;
    try {
      return await apiClient.post<TrismegistosHit | null>(
        "/plugins/trismegistos/resolve",
        req,
      );
    } finally {
      isResolving.value = false;
    }
  }

  return { isResolving, resolveId };
});
