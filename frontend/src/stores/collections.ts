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
  schema_id: string | null;
  // Publication metadata (TEI publicationStmt fields)
  publisher: string | null;
  pub_place: string | null;
  pub_year: number | null;
  license_id: string | null;
  // TEI respStmt — array of responsibility statements
  resp_stmts: { resp: string; name: string }[] | null;
  // Single author shared by all documents in the collection
  author: string | null;
  // Primary source — maps to <listBibl><bibl type="main_source">
  listbibl_bibl_main: string | null;
  // Manuscript identifier — maps to <msDesc><msIdentifier><idno>
  msidentifier_idno: string | null;
  // Physical form — maps to <msDesc><physDesc><objectDesc form="...">
  objectdesc_form: string | null;
  // Persistent identifier URL (DOI, Handle, URN, …)
  identifier_url: string | null;
  // Body template applied to new documents
  body_template_id: string | null;
  doc_count: number;
  evt_enabled: boolean;
  created_at: string;
  updated_at: string;
  // Set on public collection listings when a published website with
  // show_in_public_home=True is linked to this collection.
  website_link: string | null;
}

export interface DocumentInfo {
  filename: string;
}

export interface SearchHit {
  filename: string;
  snippet: string;
}

export interface ZipUploadError {
  filename: string;
  error: string;
}

export interface CollectionBibliography {
  id: string;
  collection_id: string;
  version: number;
  content: string;
  created_at: string;
  created_by_id: string | null;
}

export interface ZipUploadResult {
  uploaded: number;
  skipped: string[];
  errors: ZipUploadError[];
}

export interface DocumentMeta {
  publisher?: string | null;
  pub_place?: string | null;
  pub_year?: number | null;
  license_name?: string | null;
  license_url?: string | null;
  resp_stmts?: { resp: string; name: string }[] | null;
  author?: string | null;
  listbibl_bibl_main?: string | null;
  msidentifier_idno?: string | null;
  objectdesc_form?: string | null;
  body_snippet?: string | null;
}

// ── TEI skeleton helpers ──────────────────────────────────────────────────────

function _esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _buildSkeleton(meta?: DocumentMeta): string {
  // publicationStmt
  const hasPub = meta && (meta.publisher || meta.pub_place || meta.pub_year || meta.license_name);
  let pubStmt: string;
  if (hasPub) {
    const lines: string[] = [];
    if (meta!.publisher) lines.push(`            <publisher>${_esc(meta!.publisher)}</publisher>`);
    if (meta!.pub_place) lines.push(`            <pubPlace>${_esc(meta!.pub_place)}</pubPlace>`);
    if (meta!.pub_year)  lines.push(`            <date>${meta!.pub_year}</date>`);
    if (meta!.license_name) {
      const attr = meta!.license_url ? ` target="${_esc(meta!.license_url)}"` : "";
      lines.push(
        `            <availability>\n               <licence${attr}>${_esc(meta!.license_name)}</licence>\n            </availability>`,
      );
    }
    pubStmt = `<publicationStmt>\n${lines.join("\n")}\n         </publicationStmt>`;
  } else {
    pubStmt = `<publicationStmt>\n            <p>Pub Info</p>\n         </publicationStmt>`;
  }

  // respStmt blocks inside titleStmt
  const respBlock =
    meta?.resp_stmts?.length
      ? "\n" +
        meta.resp_stmts
          .map(
            (r) =>
              `            <respStmt>\n               <resp>${_esc(r.resp)}</resp>\n               <name>${_esc(r.name)}</name>\n            </respStmt>`,
          )
          .join("\n")
      : "";

  const authorLine = meta?.author
    ? `\n            <author>${_esc(meta.author)}</author>`
    : "\n            <author>Document Author</author>";

  return `<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
   <teiHeader>
      <fileDesc>
         <titleStmt>
            <title>Document title</title>${authorLine}${respBlock}
         </titleStmt>
         ${pubStmt}
         <sourceDesc>
            ${(() => {
  const parts: string[] = [];
  if (meta?.listbibl_bibl_main)
    parts.push(`<listBibl>\n               <bibl type="main_source">${_esc(meta.listbibl_bibl_main)}</bibl>\n            </listBibl>`);
  if (meta?.msidentifier_idno || meta?.objectdesc_form) {
    const idno = meta?.msidentifier_idno
      ? `\n               <msIdentifier>\n                  <idno>${_esc(meta.msidentifier_idno)}</idno>\n               </msIdentifier>`
      : "\n               <msIdentifier/>";
    const physDesc = meta?.objectdesc_form
      ? `\n               <physDesc><objectDesc form="${_esc(meta.objectdesc_form)}"/></physDesc>`
      : "";
    parts.push(`<msDesc>${idno}${physDesc}\n            </msDesc>`);
  }
  return parts.length ? parts.join("\n            ") : "<p>Source info</p>";
})()}
         </sourceDesc>
      </fileDesc>
   </teiHeader>
   <text>
      <body>
         ${
  meta?.body_snippet
    ? meta.body_snippet
        .split("\n")
        .map((line, i) => (i === 0 ? line : `         ${line}`))
        .join("\n")
    : `<docDate>\n            <date>YYYY-MM-DD</date>\n         </docDate>\n         <div type="protocollo"/>\n         <div type="testo"/>\n         <div type="escatocollo"/>`
}
      </body>
   </text>
</TEI>`;
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
  const bibliographies = ref<CollectionBibliography[]>([]);
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
      params: { per_page: 100 },
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
    body: {
      title?: string;
      description?: string;
      is_public?: boolean;
      schema_id?: string | null;
      publisher?: string | null;
      pub_place?: string | null;
      pub_year?: number | null;
      license_id?: string | null;
      resp_stmts?: { resp: string; name: string }[] | null;
      author?: string | null;
      listbibl_bibl_main?: string | null;
      msidentifier_idno?: string | null;
      objectdesc_form?: string | null;
      identifier_url?: string | null;
      body_template_id?: string | null;
    },
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

  async function directPublishCollection(id: string, note?: string): Promise<void> {
    current.value = await apiClient.post<Collection>(`/collections/${id}/direct-publish`, {
      note: note || undefined,
    });
  }

  // ── Documents ────────────────────────────────────────────────────────────────

  async function fetchDocuments(collectionId: string): Promise<void> {
    documents.value = await apiClient.get<DocumentInfo[]>(
      `/collections/${collectionId}/documents`,
    );
  }

  /** Create a new document pre-populated with the collection's publicationStmt/respStmt. */
  async function createDocument(
    collectionId: string,
    filename: string,
    meta?: DocumentMeta,
  ): Promise<DocumentInfo> {
    const skeleton = _buildSkeleton(meta);
    const blob = new Blob([skeleton], { type: 'application/xml' });
    const file = new File([blob], filename, { type: 'application/xml' });
    const form = new FormData();
    form.append('file', file);
    const doc = await apiClient.upload<DocumentInfo>(
      `/collections/${collectionId}/documents`,
      form,
    );
    documents.value.push(doc);
    return doc;
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

  async function uploadZip(collectionId: string, file: File): Promise<ZipUploadResult> {
    const form = new FormData();
    form.append("file", file);
    const result = await apiClient.upload<ZipUploadResult>(
      `/collections/${collectionId}/documents/batch`,
      form,
    );
    // Reload the document list to reflect all newly added files.
    await fetchDocuments(collectionId);
    return result;
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

  async function updateDocument(
    collectionId: string,
    filename: string,
    content: string,
  ): Promise<void> {
    await api.put(
      `/collections/${collectionId}/documents/${filename}`,
      content,
      { headers: { "Content-Type": "application/xml" } },
    );
  }

  async function fetchDocumentRaw(collectionId: string, filename: string): Promise<string> {
    // Returns the raw XML text — used by DocumentView to display inline.
    const response = await api.get<string>(
      `/collections/${collectionId}/documents/${filename}`,
      { responseType: "text" },
    );
    return response.data;
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

  async function extractBibl(collectionId: string): Promise<string> {
    // Endpoint returns raw XML (not the standard JSON envelope), so bypass
    // apiClient and use the underlying axios instance with responseType:'text'.
    const res = await api.get<string>(
      `/collections/${collectionId}/extract-bibl`,
      { responseType: "text" },
    );
    return res.data;
  }

  // ── Bibliographies ───────────────────────────────────────────────────────────

  async function saveBibliography(
    collectionId: string,
    content: string,
  ): Promise<CollectionBibliography> {
    return await apiClient.post<CollectionBibliography>(
      `/collections/${collectionId}/bibliographies`,
      { content },
    );
  }

  async function listBibliographies(collectionId: string): Promise<void> {
    bibliographies.value = await apiClient.get<CollectionBibliography[]>(
      `/collections/${collectionId}/bibliographies`,
    );
  }

  async function deleteBibliography(
    collectionId: string,
    version: number,
  ): Promise<void> {
    await apiClient.delete<void>(
      `/collections/${collectionId}/bibliographies/${version}`,
    );
    bibliographies.value = bibliographies.value.filter(
      (b) => b.version !== version,
    );
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
    directPublishCollection,
    fetchDocuments,
    createDocument,
    uploadDocument,
    uploadZip,
    downloadDocument,
    updateDocument,
    fetchDocumentRaw,
    deleteDocument,
    searchDocuments,
    extractBibl,
    bibliographies,
    saveBibliography,
    listBibliographies,
    deleteBibliography,
  };
});
