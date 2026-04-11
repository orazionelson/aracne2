import { ref } from "vue";
import { defineStore } from "pinia";
import api from "@/services/api";

export interface SearchEngineCollection {
  id: string;
  slug: string;
  title: string;
}

export type SearchEngineBuildStatus = "idle" | "pending" | "building" | "done" | "failed";

export interface AdvancedSearchTag {
  label: string;
  element: string;
}

export interface AdvancedSearchAttributeFilter {
  label: string;
  attribute: string;
}

export interface AdvancedSearchConfig {
  named_tags: AdvancedSearchTag[];
  attribute_filters: AdvancedSearchAttributeFilter[];
}

export interface SearchEngine {
  id: string;
  slug: string;
  title: string;
  xslt_template_id: string | null;
  build_status: SearchEngineBuildStatus;
  last_build_at: string | null;
  build_error: string | null;
  cache_ttl_minutes: number;
  advanced_search_enabled: boolean;
  advanced_search_config: AdvancedSearchConfig;
  collections: SearchEngineCollection[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SearchEngineCreate {
  slug: string;
  title: string;
  xslt_template_id?: string | null;
  collection_ids?: string[];
  cache_ttl_minutes?: number;
  advanced_search_enabled?: boolean;
  advanced_search_config?: AdvancedSearchConfig;
}

export interface SearchEngineUpdate {
  title?: string;
  xslt_template_id?: string | null;
  collection_ids?: string[];
  cache_ttl_minutes?: number;
  advanced_search_enabled?: boolean;
  advanced_search_config?: AdvancedSearchConfig;
}

export interface PublicCollection {
  id: string;
  slug: string;
  title: string;
}

export const useSearchEngineStore = defineStore("searchEngines", () => {
  const engines = ref<SearchEngine[]>([]);
  const publicCollections = ref<PublicCollection[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const res = await api.get("/search-engines");
      engines.value = res.data.data as SearchEngine[];
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : "Unknown error";
    } finally {
      loading.value = false;
    }
  }

  async function fetchPublicCollections(): Promise<void> {
    try {
      const res = await api.get("/search-engines/public-collections");
      publicCollections.value = res.data.data as PublicCollection[];
    } catch {
      publicCollections.value = [];
    }
  }

  async function create(payload: SearchEngineCreate): Promise<SearchEngine> {
    const res = await api.post("/search-engines", payload);
    const engine = res.data.data as SearchEngine;
    engines.value.push(engine);
    return engine;
  }

  async function update(slug: string, payload: SearchEngineUpdate): Promise<SearchEngine> {
    const res = await api.put(`/search-engines/${slug}`, payload);
    const updated = res.data.data as SearchEngine;
    const idx = engines.value.findIndex((e) => e.slug === slug);
    if (idx !== -1) engines.value[idx] = updated;
    return updated;
  }

  async function remove(slug: string): Promise<void> {
    await api.delete(`/search-engines/${slug}`);
    engines.value = engines.value.filter((e) => e.slug !== slug);
  }

  async function build(slug: string): Promise<SearchEngine> {
    const res = await api.post(`/search-engines/${slug}/build`);
    const updated = res.data.data as SearchEngine;
    const idx = engines.value.findIndex((e) => e.slug === slug);
    if (idx !== -1) engines.value[idx] = updated;
    return updated;
  }

  async function clearCache(slug: string): Promise<number> {
    const res = await api.post(`/search-engines/${slug}/cache/clear`);
    return (res.data.data as { deleted: number }).deleted;
  }

  return {
    engines,
    publicCollections,
    loading,
    error,
    fetchAll,
    fetchPublicCollections,
    create,
    update,
    remove,
    build,
    clearCache,
  };
});
