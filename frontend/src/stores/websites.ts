import { ref } from "vue";
import { defineStore } from "pinia";
import api from "@/services/api";

export type RenderingMode = "STATIC" | "DYNAMIC" | "HYBRID";
export type BuildStatus = "idle" | "pending" | "building" | "done" | "failed";

export interface WebsitePage {
  id: string;
  website_id: string;
  slug: string;
  title: string;
  content_md: string | null;
  sort_order: number;
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
  meta_config: Record<string, string>;
  nav_config: unknown[];
  xslt_schema_id: string | null;
  build_status: BuildStatus;
  last_build_at: string | null;
  build_error: string | null;
  is_published: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  pages: WebsitePage[];
}

export interface WebsiteCreate {
  slug: string;
  title: string;
  description?: string | null;
  collection_id?: string | null;
  rendering_mode?: RenderingMode;
  theme_config?: Record<string, string>;
  meta_config?: Record<string, string>;
  is_published?: boolean;
}

export interface WebsiteUpdate {
  title?: string;
  description?: string | null;
  collection_id?: string | null;
  rendering_mode?: RenderingMode;
  theme_config?: Record<string, string>;
  meta_config?: Record<string, string>;
  is_published?: boolean;
}

export interface WebsitePageCreate {
  slug: string;
  title: string;
  content_md?: string | null;
  sort_order?: number;
}

export interface WebsitePageUpdate {
  title?: string;
  content_md?: string | null;
  sort_order?: number;
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
  };
});
