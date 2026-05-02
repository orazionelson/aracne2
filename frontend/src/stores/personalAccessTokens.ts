/**
 * personalAccessTokens store — Editor+ self-service for the long-lived
 * bearer tokens consumed by the standalone ``aracne-cli``.
 *
 * Mirrors the MCP-token sub-resource shape from ``stores/corpora.ts`` but
 * the surface is per-user (``/users/me/tokens``), not per-corpus.
 *
 * The ``issue`` action returns the plaintext token in its response — the
 * caller must render the "copy this once" UI immediately because the
 * value is gone from the backend forever after this call.
 */

import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface PersonalAccessToken {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** Returned exactly once at creation time — carries the plaintext value. */
export interface PersonalAccessTokenCreated {
  id: string;
  label: string;
  created_at: string;
  /** The plaintext bearer token. Visible only in this response.
   *  Field name on the wire is ``token``. */
  token: string;
}

export const usePersonalAccessTokensStore = defineStore(
  "personalAccessTokens",
  () => {
    const tokens = ref<PersonalAccessToken[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    async function loadList(): Promise<void> {
      isLoading.value = true;
      error.value = null;
      try {
        tokens.value = await apiClient.get<PersonalAccessToken[]>(
          "/users/me/tokens",
        );
      } catch (err) {
        const e = err as { response?: { data?: { error?: { message?: string } } } };
        error.value = e?.response?.data?.error?.message ?? String(err);
      } finally {
        isLoading.value = false;
      }
    }

    async function issue(label: string): Promise<PersonalAccessTokenCreated | null> {
      error.value = null;
      try {
        const created = await apiClient.post<PersonalAccessTokenCreated>(
          "/users/me/tokens",
          { label },
        );
        tokens.value = [
          {
            id: created.id,
            label: created.label,
            created_at: created.created_at,
            last_used_at: null,
            revoked_at: null,
          },
          ...tokens.value,
        ];
        return created;
      } catch (err) {
        const e = err as { response?: { data?: { error?: { message?: string } } } };
        error.value = e?.response?.data?.error?.message ?? String(err);
        return null;
      }
    }

    async function revoke(tokenId: string): Promise<boolean> {
      error.value = null;
      try {
        await apiClient.delete(`/users/me/tokens/${tokenId}`);
        // Optimistic local update: drop from the list (the backend hides
        // revoked rows from GET /users/me/tokens).
        tokens.value = tokens.value.filter((t) => t.id !== tokenId);
        return true;
      } catch (err) {
        const e = err as { response?: { data?: { error?: { message?: string } } } };
        error.value = e?.response?.data?.error?.message ?? String(err);
        return false;
      }
    }

    function reset(): void {
      tokens.value = [];
      error.value = null;
    }

    return {
      tokens,
      isLoading,
      error,
      loadList,
      issue,
      revoke,
      reset,
    };
  },
);
