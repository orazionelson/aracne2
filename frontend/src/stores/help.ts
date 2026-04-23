/**
 * Help plugin store.
 *
 * Backs the in-app documentation browser: navigation tree, rendered
 * page, full-text search. All endpoints require an authenticated
 * user — the plugin sits under ``/api/v1/plugins/help`` and is only
 * mounted when the ``help`` plugin is active.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { apiClient } from "@/services/api";

export interface HelpTreeNode {
  path: string;
  title: string;
  is_section: boolean;
  children: HelpTreeNode[];
}

export interface HelpPage {
  path: string;
  title: string;
  html: string;
  breadcrumb: [string, string][];
}

export interface HelpSearchHit {
  path: string;
  title: string;
  snippet: string;
}

export const useHelpStore = defineStore("help", () => {
  const tree = ref<HelpTreeNode[]>([]);
  const currentPage = ref<HelpPage | null>(null);
  const searchResults = ref<HelpSearchHit[]>([]);
  const isLoadingTree = ref(false);
  const isLoadingPage = ref(false);
  const isSearching = ref(false);
  const lastError = ref<string | null>(null);

  async function fetchTree(): Promise<void> {
    isLoadingTree.value = true;
    try {
      tree.value = await apiClient.get<HelpTreeNode[]>("/plugins/help/tree");
    } finally {
      isLoadingTree.value = false;
    }
  }

  async function fetchPage(path: string): Promise<void> {
    isLoadingPage.value = true;
    lastError.value = null;
    try {
      currentPage.value = await apiClient.get<HelpPage>("/plugins/help/page", {
        params: { path },
      });
    } catch (err) {
      currentPage.value = null;
      lastError.value = (err as Error).message;
    } finally {
      isLoadingPage.value = false;
    }
  }

  async function search(q: string): Promise<void> {
    if (q.trim().length < 2) {
      searchResults.value = [];
      return;
    }
    isSearching.value = true;
    try {
      searchResults.value = await apiClient.get<HelpSearchHit[]>(
        "/plugins/help/search",
        { params: { q } },
      );
    } finally {
      isSearching.value = false;
    }
  }

  function clearSearch(): void {
    searchResults.value = [];
  }

  async function refreshCache(): Promise<void> {
    await apiClient.post<{ ok: boolean }>("/plugins/help/refresh");
  }

  return {
    tree,
    currentPage,
    searchResults,
    isLoadingTree,
    isLoadingPage,
    isSearching,
    lastError,
    fetchTree,
    fetchPage,
    search,
    clearSearch,
    refreshCache,
  };
});
