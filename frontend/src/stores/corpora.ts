import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface CorpusCollectionItem {
  id: string;
  slug: string;
  title: string;
  is_public: boolean;
  status: string;
}

export interface Corpus {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  collections: CorpusCollectionItem[];
  token_count: number;
}

export interface McpToken {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** Returned exactly once at creation time — carries the plaintext value. */
export interface McpTokenCreated extends McpToken {
  plaintext: string;
  claude_desktop_snippet: string;
}

export const useCorpusStore = defineStore("corpora", () => {
  const corpora = ref<Corpus[]>([]);
  const tokensByCorpus = ref<Record<string, McpToken[]>>({});
  const isLoading = ref(false);

  async function fetchAll(): Promise<void> {
    isLoading.value = true;
    try {
      corpora.value = await apiClient.get<Corpus[]>("/corpora");
    } finally {
      isLoading.value = false;
    }
  }

  async function getOne(id: string): Promise<Corpus> {
    return await apiClient.get<Corpus>(`/corpora/${id}`);
  }

  async function create(payload: {
    name: string;
    description: string | null;
    collection_ids: string[];
  }): Promise<Corpus> {
    const created = await apiClient.post<Corpus>("/corpora", payload);
    corpora.value.push(created);
    corpora.value.sort((a, b) => a.name.localeCompare(b.name));
    return created;
  }

  async function update(
    id: string,
    payload: { name?: string; description?: string | null; collection_ids?: string[] },
  ): Promise<Corpus> {
    const updated = await apiClient.put<Corpus>(`/corpora/${id}`, payload);
    const idx = corpora.value.findIndex((c) => c.id === id);
    if (idx !== -1) corpora.value[idx] = updated;
    return updated;
  }

  async function remove(id: string): Promise<void> {
    await apiClient.delete(`/corpora/${id}`);
    corpora.value = corpora.value.filter((c) => c.id !== id);
    delete tokensByCorpus.value[id];
  }

  // ── Token sub-resource ──────────────────────────────────────────────────────

  async function fetchTokens(corpusId: string): Promise<McpToken[]> {
    const tokens = await apiClient.get<McpToken[]>(`/corpora/${corpusId}/tokens`);
    tokensByCorpus.value[corpusId] = tokens;
    return tokens;
  }

  async function issueToken(corpusId: string, label: string): Promise<McpTokenCreated> {
    const created = await apiClient.post<McpTokenCreated>(
      `/corpora/${corpusId}/tokens`,
      { label },
    );
    const list = tokensByCorpus.value[corpusId] ?? [];
    list.unshift({
      id: created.id,
      label: created.label,
      created_at: created.created_at,
      last_used_at: created.last_used_at,
      revoked_at: created.revoked_at,
    });
    tokensByCorpus.value[corpusId] = list;
    // Bump the count on the parent corpus so the list view reflects it
    // without a full refetch.
    const c = corpora.value.find((x) => x.id === corpusId);
    if (c) c.token_count += 1;
    return created;
  }

  async function revokeToken(corpusId: string, tokenId: string): Promise<void> {
    await apiClient.delete(`/corpora/${corpusId}/tokens/${tokenId}`);
    const list = tokensByCorpus.value[corpusId];
    if (list) {
      const t = list.find((x) => x.id === tokenId);
      if (t) t.revoked_at = new Date().toISOString();
    }
    const c = corpora.value.find((x) => x.id === corpusId);
    if (c && c.token_count > 0) c.token_count -= 1;
  }

  return {
    corpora,
    tokensByCorpus,
    isLoading,
    fetchAll,
    getOne,
    create,
    update,
    remove,
    fetchTokens,
    issueToken,
    revokeToken,
  };
});
