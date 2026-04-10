import { ref } from "vue";
import { defineStore } from "pinia";
import api from "@/services/api";

export type RenderingMode = "STATIC" | "DYNAMIC" | "HYBRID";
export type BuildStatus = "idle" | "pending" | "building" | "done" | "failed";
export type XsltSource = "default" | "custom" | "url" | "catalog";
export type XsltProcessor = "lxml" | "saxon";

export interface XsltConfig {
  source: XsltSource;
  content: string | null;
  url: string | null;
  catalog_id: string | null;
  processor: XsltProcessor;
}

export interface AracnePageConfig {
  id: "home" | "browse" | "search";
  sort_order: number;
  is_hidden: boolean;
}

export interface WebsitePage {
  id: string;
  website_id: string;
  slug: string;
  title: string;
  content_md: string | null;
  sort_order: number;
  is_hidden: boolean;
  created_at: string;
  updated_at: string;
}

export interface Website {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  collection_id: string | null;
  rendering_mode: RenderingMode;
  theme_config: Record<string, string>;
  meta_config: Record<string, string | string[]>;
  nav_config: AracnePageConfig[];
  xslt_config: XsltConfig;
  xslt_schema_id: string | null;
  build_status: BuildStatus;
  last_build_at: string | null;
  build_error: string | null;
  is_published: boolean;
  distinct_tags: Record<string, string[]> | null;
  tags_refreshed_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  pages: WebsitePage[];
  indices: WebsiteIndex[];
}

export interface WebsiteCreate {
  slug: string;
  title: string;
  description?: string | null;
  collection_id?: string | null;
  rendering_mode?: RenderingMode;
  theme_config?: Record<string, string>;
  meta_config?: Record<string, string | string[]>;
  is_published?: boolean;
}

export interface WebsiteUpdate {
  title?: string;
  description?: string | null;
  collection_id?: string | null;
  rendering_mode?: RenderingMode;
  theme_config?: Record<string, string>;
  meta_config?: Record<string, string | string[]>;
  nav_config?: AracnePageConfig[];
  xslt_config?: XsltConfig;
  is_published?: boolean;
}

export interface WebsitePageCreate {
  slug: string;
  title: string;
  content_md?: string | null;
  sort_order?: number;
  is_hidden?: boolean;
}

export interface WebsitePageUpdate {
  title?: string;
  content_md?: string | null;
  sort_order?: number;
  is_hidden?: boolean;
}

export interface WebsiteIndex {
  id: string;
  website_id: string;
  label: string;
  title: string;
  tag: string;
  key_attribute: string | null;
  subkey_attribute: string | null;
  last_built_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebsiteIndexCreate {
  label: string;
  title: string;
  tag: string;
  key_attribute?: string | null;
  subkey_attribute?: string | null;
}

export interface WebsiteIndexUpdate {
  label?: string;
  title?: string;
  tag?: string;
  key_attribute?: string | null;
  subkey_attribute?: string | null;
}

export interface MetaSuggestions {
  author: string[];
  dc_creator: string[];
  designer: string[];
  copyright: string;
  dc_publisher: string[];
  dc_format: string;
  dc_identifier: string;
}

export const useWebsiteStore = defineStore("websites", () => {
  const websites = ref<Website[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function fetchWebsites(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const res = await api.get<Website[]>("/websites");
      websites.value = res.data.data as Website[];
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : "Error loading websites";
    } finally {
      isLoading.value = false;
    }
  }

  async function createWebsite(data: WebsiteCreate): Promise<Website> {
    const res = await api.post<Website>("/websites", data);
    const created = res.data.data as Website;
    websites.value.unshift(created);
    return created;
  }

  async function updateWebsite(slug: string, data: WebsiteUpdate): Promise<Website> {
    const res = await api.put<Website>(`/websites/${slug}`, data);
    const updated = res.data.data as Website;
    const idx = websites.value.findIndex((w) => w.slug === slug);
    if (idx !== -1) websites.value[idx] = updated;
    return updated;
  }

  async function deleteWebsite(slug: string): Promise<void> {
    await api.delete(`/websites/${slug}`);
    websites.value = websites.value.filter((w) => w.slug !== slug);
  }

  async function triggerBuild(slug: string): Promise<void> {
    await api.post(`/websites/${slug}/build`);
    // Refresh to get updated build_status
    const res = await api.get<Website>(`/websites/${slug}`);
    const updated = res.data.data as Website;
    const idx = websites.value.findIndex((w) => w.slug === slug);
    if (idx !== -1) websites.value[idx] = updated;
  }

  async function pollBuildStatus(slug: string): Promise<BuildStatus> {
    const res = await api.get<Website>(`/websites/${slug}`);
    const updated = res.data.data as Website;
    const idx = websites.value.findIndex((w) => w.slug === slug);
    if (idx !== -1) websites.value[idx] = updated;
    return updated.build_status;
  }

  async function createPage(slug: string, data: WebsitePageCreate): Promise<WebsitePage> {
    const res = await api.post<WebsitePage>(`/websites/${slug}/pages`, data);
    const page = res.data.data as WebsitePage;
    const site = websites.value.find((w) => w.slug === slug);
    if (site) site.pages.push(page);
    return page;
  }

  async function updatePage(
    slug: string,
    pageSlug: string,
    data: WebsitePageUpdate,
  ): Promise<WebsitePage> {
    const res = await api.put<WebsitePage>(`/websites/${slug}/pages/${pageSlug}`, data);
    const updated = res.data.data as WebsitePage;
    const site = websites.value.find((w) => w.slug === slug);
    if (site) {
      const idx = site.pages.findIndex((p) => p.slug === pageSlug);
      if (idx !== -1) site.pages[idx] = updated;
    }
    return updated;
  }

  async function deletePage(slug: string, pageSlug: string): Promise<void> {
    await api.delete(`/websites/${slug}/pages/${pageSlug}`);
    const site = websites.value.find((w) => w.slug === slug);
    if (site) site.pages = site.pages.filter((p) => p.slug !== pageSlug);
  }

  async function fetchMetaSuggestions(slug: string): Promise<MetaSuggestions> {
    const res = await api.get<MetaSuggestions>(`/websites/${slug}/meta-suggestions`);
    return res.data.data as MetaSuggestions;
  }

  /**
   * Apply the given XSLT config to a single document and return the body HTML.
   *
   * Pass xsltConfig to preview unsaved stylesheet changes; omit it (or pass
   * null) to use the website's currently saved xslt_config.
   */
  async function previewDocument(
    slug: string,
    filename: string,
    xsltConfig?: XsltConfig | null,
  ): Promise<string> {
    const res = await api.post<{ html: string }>(
      `/websites/${slug}/preview-doc/${encodeURIComponent(filename)}`,
      { xslt_config: xsltConfig ?? null },
    );
    return (res.data.data as { html: string }).html;
  }

  /** Invalidate the in-memory rendered-page and XSLT caches for *slug*. */
  async function clearCache(slug: string): Promise<void> {
    await api.post(`/websites/${slug}/clear-cache`, {});
  }

  /** Download the built STATIC site as a ZIP file. */
  async function downloadSite(slug: string): Promise<void> {
    const res = await api.get(`/websites/${slug}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Tag discovery ────────────────────────────────────────────────────────

  async function refreshTags(slug: string): Promise<{ distinct_tags: Record<string, string[]> | null; tags_refreshed_at: string | null }> {
    const res = await api.post(`/websites/${slug}/tags/refresh`, {});
    const data = res.data.data as { distinct_tags: Record<string, string[]> | null; tags_refreshed_at: string | null };
    const site = websites.value.find((w) => w.slug === slug);
    if (site) {
      site.distinct_tags = data.distinct_tags;
      site.tags_refreshed_at = data.tags_refreshed_at;
    }
    return data;
  }

  // ── Website indices ──────────────────────────────────────────────────────

  async function createIndex(slug: string, data: WebsiteIndexCreate): Promise<WebsiteIndex> {
    const res = await api.post<WebsiteIndex>(`/websites/${slug}/indices`, data);
    const created = res.data.data as WebsiteIndex;
    const site = websites.value.find((w) => w.slug === slug);
    if (site) site.indices.push(created);
    return created;
  }

  async function updateIndex(slug: string, indexId: string, data: WebsiteIndexUpdate): Promise<WebsiteIndex> {
    const res = await api.put<WebsiteIndex>(`/websites/${slug}/indices/${indexId}`, data);
    const updated = res.data.data as WebsiteIndex;
    const site = websites.value.find((w) => w.slug === slug);
    if (site) {
      const i = site.indices.findIndex((x) => x.id === indexId);
      if (i !== -1) site.indices[i] = updated;
    }
    return updated;
  }

  async function deleteIndex(slug: string, indexId: string): Promise<void> {
    await api.delete(`/websites/${slug}/indices/${indexId}`);
    const site = websites.value.find((w) => w.slug === slug);
    if (site) site.indices = site.indices.filter((x) => x.id !== indexId);
  }

  async function rebuildIndex(slug: string, indexId: string): Promise<WebsiteIndex> {
    const res = await api.post<WebsiteIndex>(`/websites/${slug}/indices/${indexId}/rebuild`, {});
    const updated = res.data.data as WebsiteIndex;
    const site = websites.value.find((w) => w.slug === slug);
    if (site) {
      const i = site.indices.findIndex((x) => x.id === indexId);
      if (i !== -1) site.indices[i] = updated;
    }
    return updated;
  }

  async function rebuildAllIndices(slug: string): Promise<WebsiteIndex[]> {
    const res = await api.post<WebsiteIndex[]>(`/websites/${slug}/indices/rebuild-all`, {});
    const updated = res.data.data as WebsiteIndex[];
    const site = websites.value.find((w) => w.slug === slug);
    if (site) site.indices = updated;
    return updated;
  }

  return {
    websites,
    isLoading,
    error,
    fetchWebsites,
    createWebsite,
    updateWebsite,
    deleteWebsite,
    triggerBuild,
    pollBuildStatus,
    createPage,
    updatePage,
    deletePage,
    fetchMetaSuggestions,
    previewDocument,
    clearCache,
    downloadSite,
    refreshTags,
    createIndex,
    updateIndex,
    deleteIndex,
    rebuildIndex,
    rebuildAllIndices,
  };
});
