import { defineStore } from "pinia";
import { ref } from "vue";
import api, { apiClient } from "@/services/api";

export interface EditorOption {
  id: string;
  username: string;
  display_name: string | null;
}

export type CollectionStatus = "draft" | "assigned" | "review" | "published";

export interface Collection {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  status: CollectionStatus;
  is_public: boolean;
  owner_id: string | null;
  editor_id: string | null;
  assigned_at: string | null;
  submitted_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentInfo {
  filename: string;
}

export interface SearchHit {
  filename: string;
  snippet: string;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export const useCollectionStore = defineStore("collections", () => {
  const collections = ref<Collection[]>([]);
  const current = ref<Collection | null>(null);
  const documents = ref<DocumentInfo[]>([]);
  const editors = ref<EditorOption[]>([]);
  const pagination = ref<Pagination | null>(null);
  const isLoading = ref(false);

  // ── Collection CRUD ──────────────────────────────────────────────────────────

  async function fetchCollections(
    page = 1,
    status?: CollectionStatus,
    search?: string,
  ): Promise<void> {
    isLoading.value = true;
    try {
      const params: Record<string, unknown> = { page, per_page: 20 };
      if (status) params.status = status;
      if (search) params.search = search;
      const res = await apiClient.getPaginated<Collection>("/collections", { params });
      collections.value = res.data as Collection[];
      pagination.value = res.pagination as Pagination;
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchCollection(slug: string): Promise<void> {
    current.value = await apiClient.get<Collection>(`/collections/${slug}`);
  }

  async function fetchEditors(): Promise<void> {
    // Fetch all active users for the assign-editor autocomplete.
    // Role validation (Editor required) is enforced by the backend on assignment.
    interface UserRow { id: string; username: string; display_name: string | null }
    const res = await apiClient.getPaginated<UserRow>("/users", {
      params: { per_page: 200 },
    });
    editors.value = res.data as EditorOption[];
  }

  async function createCollection(body: {
    slug: string;
    title: string;
    description?: string;
    is_public: boolean;
  }): Promise<Collection> {
    return await apiClient.post<Collection>("/collections", body);
  }

  async function updateCollection(
    id: string,
    body: { title?: string; description?: string; is_public?: boolean },
  ): Promise<void> {
    current.value = await apiClient.patch<Collection>(`/collections/${id}`, body);
  }

  async function deleteCollection(id: string): Promise<void> {
    await apiClient.delete<void>(`/collections/${id}`);
    collections.value = collections.value.filter((c) => c.id !== id);
  }

  // ── Workflow ─────────────────────────────────────────────────────────────────

  async function assignCollection(
    id: string,
    userId: string,
    note?: string,
  ): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/assign`, {
      user_id: userId,
      note: note || undefined,
    });
  }

  async function submitCollection(id: string, note?: string): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/submit`, {
      note: note || undefined,
    });
  }

  async function rejectCollection(id: string, note: string): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/reject`, { note });
  }

  async function publishCollection(id: string, note?: string): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/publish`, {
      note: note || undefined,
    });
  }

  async function unpublishCollection(id: string, note?: string): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/unpublish`, {
      note: note || undefined,
    });
  }

  // ── Documents ────────────────────────────────────────────────────────────────

  async function fetchDocuments(collectionId: string): Promise<void> {
    documents.value = await apiClient.get<DocumentInfo[]>(
      `/collections/${collectionId}/documents`,
    );
  }

  async function uploadDocument(collectionId: string, file: File): Promise<void> {
    const form = new FormData();
    form.append("file", file);
    const doc = await apiClient.upload<DocumentInfo>(
      `/collections/${collectionId}/documents`,
      form,
    );
    documents.value.push(doc);
  }

  async function downloadDocument(collectionId: string, filename: string): Promise<void> {
    // Use raw api instance (not apiClient) because the response is a binary blob,
    // not a JSON { data: ... } envelope.
    const response = await api.get(
      `/collections/${collectionId}/documents/${filename}`,
      { responseType: "blob" },
    );
    const url = URL.createObjectURL(response.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function deleteDocument(collectionId: string, filename: string): Promise<void> {
    await apiClient.delete<void>(`/collections/${collectionId}/documents/${filename}`);
    documents.value = documents.value.filter((d) => d.filename !== filename);
  }

  async function searchDocuments(
    collectionId: string,
    query: string,
    maxResults = 50,
  ): Promise<SearchHit[]> {
    return await apiClient.get<SearchHit[]>(`/collections/${collectionId}/search`, {
      params: { q: query, max_results: maxResults },
    });
  }

  return {
    collections,
    current,
    documents,
    editors,
    pagination,
    isLoading,
    fetchCollections,
    fetchCollection,
    fetchEditors,
    createCollection,
    updateCollection,
    deleteCollection,
    assignCollection,
    submitCollection,
    rejectCollection,
    publishCollection,
    unpublishCollection,
    fetchDocuments,
    uploadDocument,
    downloadDocument,
    deleteDocument,
    searchDocuments,
  };
});
