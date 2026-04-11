/**
 * Tests for useCollectionStore.
 *
 * All API calls go through apiClient which is mocked here.
 * The _buildSkeleton XSS escaping is tested indirectly via createDocument.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock("@/main", () => ({
  i18n: {
    global: {
      locale: { value: "en" },
      t: (key: string) => key,
    },
  },
}));

// Capture calls to apiClient so we can inspect request bodies.
// vi.mock is hoisted to the top of the file, so variables referenced inside
// the factory must be created with vi.hoisted() to be initialized in time.
const { mockGet, mockPost, mockPatch, mockDelete, mockGetPaginated, mockUpload } =
  vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    mockPatch: vi.fn(),
    mockDelete: vi.fn(),
    mockGetPaginated: vi.fn(),
    mockUpload: vi.fn(),
  }));

vi.mock("@/services/api", () => ({
  default: {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  apiClient: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
    getPaginated: mockGetPaginated,
    upload: mockUpload,
  },
}));

// ── Import AFTER mocks ────────────────────────────────────────────────────────

import { useCollectionStore } from "@/stores/collections";

// ── Test data ─────────────────────────────────────────────────────────────────

const mockCollection = {
  id: "col-1",
  slug: "test-collection",
  title: "Test Collection",
  description: null,
  status: "draft" as const,
  is_public: false,
  owner_id: null,
  editor_id: null,
  assigned_at: null,
  submitted_at: null,
  published_at: null,
  schema_id: null,
  publisher: null,
  pub_place: null,
  pub_year: null,
  license_id: null,
  resp_stmts: null,
  author: null,
  listbibl_bibl_main: null,
  msidentifier_idno: null,
  objectdesc_form: null,
  identifier_url: null,
  body_template_id: null,
  doc_count: 0,
  evt_enabled: false,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useCollectionStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  // ── fetchCollections ───────────────────────────────────────────────────────

  it("fetchCollections updates collections and pagination", async () => {
    const pagination = { page: 1, per_page: 20, total: 1, total_pages: 1 };
    mockGetPaginated.mockResolvedValueOnce({
      data: [mockCollection],
      pagination,
    });

    const store = useCollectionStore();
    await store.fetchCollections();

    expect(store.collections).toHaveLength(1);
    expect(store.collections[0].slug).toBe("test-collection");
    expect(store.pagination?.total).toBe(1);
  });

  // ── createCollection ──────────────────────────────────────────────────────

  it("createCollection calls POST /collections and returns the new collection", async () => {
    mockPost.mockResolvedValueOnce(mockCollection);

    const store = useCollectionStore();
    const result = await store.createCollection({
      slug: "test-collection",
      title: "Test Collection",
      is_public: false,
    });

    expect(mockPost).toHaveBeenCalledWith("/collections", expect.objectContaining({
      slug: "test-collection",
    }));
    expect(result.id).toBe("col-1");
  });

  // ── deleteCollection ──────────────────────────────────────────────────────

  it("deleteCollection removes the collection from the local list", async () => {
    // Pre-populate the store
    const pagination = { page: 1, per_page: 20, total: 1, total_pages: 1 };
    mockGetPaginated.mockResolvedValueOnce({ data: [mockCollection], pagination });
    mockDelete.mockResolvedValueOnce(undefined);

    const store = useCollectionStore();
    await store.fetchCollections();
    expect(store.collections).toHaveLength(1);

    await store.deleteCollection("col-1");

    expect(store.collections).toHaveLength(0);
    expect(mockDelete).toHaveBeenCalledWith("/collections/col-1");
  });

  // ── _buildSkeleton XSS escaping ───────────────────────────────────────────

  it("createDocument escapes HTML entities in collection metadata", async () => {
    let capturedForm: FormData | undefined;
    mockUpload.mockImplementation(async (_url: string, form: FormData) => {
      capturedForm = form;
      return { filename: "doc.xml" };
    });

    const store = useCollectionStore();
    await store.createDocument("col-1", "doc.xml", {
      publisher: "<Evil & Co>",
      author: '"Quoted Author"',
    });

    expect(capturedForm).toBeDefined();
    // jsdom's File may not implement .text() or support Response(blob) body.
    // FileReader is universally supported in jsdom.
    const file = capturedForm!.get("file") as File;
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(file);
    });

    // Entities must be escaped — raw HTML chars must not appear inside attributes/text
    expect(text).toContain("&lt;Evil &amp; Co&gt;");
    expect(text).toContain("&quot;Quoted Author&quot;");
    expect(text).not.toContain("<Evil");
    expect(text).not.toContain("& Co>");
  });

  // ── fetchDocuments ────────────────────────────────────────────────────────

  it("fetchDocuments updates the documents list", async () => {
    mockGet.mockResolvedValueOnce([{ filename: "doc1.xml" }, { filename: "doc2.xml" }]);

    const store = useCollectionStore();
    await store.fetchDocuments("col-1");

    expect(store.documents).toHaveLength(2);
    expect(store.documents[0].filename).toBe("doc1.xml");
  });
});
