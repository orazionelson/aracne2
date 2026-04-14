/**
 * Tests for useDashboardStore.
 *
 * The store uses the raw `api` instance (api.get) for collection / user count
 * requests, and `apiClient.get` for the health check.  Both are mocked here.
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

const { mockApiGet, mockClientGet } = vi.hoisted(() => ({
  mockApiGet: vi.fn(),
  mockClientGet: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  default: {
    get: mockApiGet,
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  apiClient: {
    get: mockClientGet,
  },
}));

// ── Import AFTER mocks ────────────────────────────────────────────────────────

import { useDashboardStore } from "@/stores/dashboard";

// ── Helpers ───────────────────────────────────────────────────────────────────

function makePaginatedResponse<T>(items: T[], total: number) {
  return {
    data: {
      data: items,
      pagination: { page: 1, per_page: items.length || 1, total, total_pages: 1 },
    },
  };
}

const MOCK_COLLECTIONS = [
  { id: "c1", slug: "col-1", title: "Collection One", status: "draft", created_at: "2026-01-01T00:00:00Z" },
  { id: "c2", slug: "col-2", title: "Collection Two", status: "published", created_at: "2026-01-02T00:00:00Z" },
];

const MOCK_HEALTH = {
  status: "healthy",
  services: {
    postgres: { status: "ok" },
    existdb: { status: "ok" },
  },
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useDashboardStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  // ── Non-Admin fetch ───────────────────────────────────────────────────────

  it("fetchDashboard as Editor: calls collection endpoints, skips users and health", async () => {
    // recent (per_page=5), draft, review, published — 4 calls
    mockApiGet
      .mockResolvedValueOnce(makePaginatedResponse(MOCK_COLLECTIONS, 10))
      .mockResolvedValueOnce(makePaginatedResponse([], 3))
      .mockResolvedValueOnce(makePaginatedResponse([], 1))
      .mockResolvedValueOnce(makePaginatedResponse([], 6));

    const store = useDashboardStore();
    await store.fetchDashboard("Editor");

    expect(mockApiGet).toHaveBeenCalledTimes(4);
    expect(mockClientGet).not.toHaveBeenCalled();

    expect(store.collectionsTotal).toBe(10);
    expect(store.collectionsDraft).toBe(3);
    expect(store.collectionsReview).toBe(1);
    expect(store.collectionsPublished).toBe(6);
    expect(store.usersTotal).toBeNull();
    expect(store.health).toBeNull();
    expect(store.recentCollections).toHaveLength(2);
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
  });

  it("fetchDashboard as EditorInChief: skips users and health", async () => {
    mockApiGet
      .mockResolvedValueOnce(makePaginatedResponse([], 5))
      .mockResolvedValueOnce(makePaginatedResponse([], 2))
      .mockResolvedValueOnce(makePaginatedResponse([], 0))
      .mockResolvedValueOnce(makePaginatedResponse([], 3));

    const store = useDashboardStore();
    await store.fetchDashboard("EditorInChief");

    expect(mockApiGet).toHaveBeenCalledTimes(4);
    expect(mockClientGet).not.toHaveBeenCalled();
    expect(store.usersTotal).toBeNull();
    expect(store.health).toBeNull();
  });

  // ── Admin fetch ───────────────────────────────────────────────────────────

  it("fetchDashboard as Admin: calls users and health in addition to collections", async () => {
    mockApiGet
      .mockResolvedValueOnce(makePaginatedResponse(MOCK_COLLECTIONS, 10))
      .mockResolvedValueOnce(makePaginatedResponse([], 3))
      .mockResolvedValueOnce(makePaginatedResponse([], 1))
      .mockResolvedValueOnce(makePaginatedResponse([], 6))
      .mockResolvedValueOnce(makePaginatedResponse([], 42)); // users

    mockClientGet.mockResolvedValueOnce(MOCK_HEALTH);

    const store = useDashboardStore();
    await store.fetchDashboard("Admin");

    expect(mockApiGet).toHaveBeenCalledTimes(5);
    expect(mockClientGet).toHaveBeenCalledTimes(1);
    expect(mockClientGet).toHaveBeenCalledWith("/health");

    expect(store.usersTotal).toBe(42);
    expect(store.health).toEqual(MOCK_HEALTH);
    expect(store.collectionsTotal).toBe(10);
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
  });

  // ── Request parameters ────────────────────────────────────────────────────

  it("uses correct status params for count requests", async () => {
    mockApiGet
      .mockResolvedValueOnce(makePaginatedResponse([], 0))
      .mockResolvedValueOnce(makePaginatedResponse([], 0))
      .mockResolvedValueOnce(makePaginatedResponse([], 0))
      .mockResolvedValueOnce(makePaginatedResponse([], 0));

    const store = useDashboardStore();
    await store.fetchDashboard("Editor");

    const calls = mockApiGet.mock.calls;
    expect(calls[0][1]).toMatchObject({ params: { page: 1, per_page: 5 } });
    expect(calls[1][1]).toMatchObject({ params: { page: 1, per_page: 1, status: "draft" } });
    expect(calls[2][1]).toMatchObject({ params: { page: 1, per_page: 1, status: "review" } });
    expect(calls[3][1]).toMatchObject({ params: { page: 1, per_page: 1, status: "published" } });
  });

  // ── Error handling ────────────────────────────────────────────────────────

  it("sets error and clears loading when a request fails", async () => {
    // All parallel api.get calls must be covered — unmocked calls return
    // undefined, causing a ".then() on undefined" TypeError before the
    // intended error reaches the catch block.
    mockApiGet.mockRejectedValue(new Error("Network error"));

    const store = useDashboardStore();
    await store.fetchDashboard("Editor");

    expect(store.error).toBe("Network error");
    expect(store.loading).toBe(false);
  });

  it("reports a generic error message for non-Error rejections", async () => {
    mockApiGet.mockRejectedValue("unexpected");

    const store = useDashboardStore();
    await store.fetchDashboard("Editor");

    expect(store.error).toBe("Dashboard load failed");
    expect(store.loading).toBe(false);
  });
});
