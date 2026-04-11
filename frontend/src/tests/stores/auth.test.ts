/**
 * Tests for useAuthStore.
 *
 * The axios instance and the i18n singleton are mocked so that tests run
 * without a real backend or DOM locale setup.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

// ── Module mocks ──────────────────────────────────────────────────────────────

// Mock @/main so i18n.global.locale.value is writable without a real Vue app.
vi.mock("@/main", () => ({
  i18n: {
    global: {
      locale: { value: "en" },
      t: (key: string) => key,
    },
  },
}));

// Mock @/services/api so no real HTTP calls are made.
const mockPost = vi.fn();
const mockGet = vi.fn();
vi.mock("@/services/api", () => ({
  default: {
    post: mockPost,
    get: mockGet,
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Mock useNotificationStore to avoid cascading store dependencies.
vi.mock("@/stores/notifications", () => ({
  useNotificationStore: () => ({
    reset: vi.fn(),
    fetchUnreadCount: vi.fn().mockResolvedValue(undefined),
  }),
}));

// ── Import AFTER mocks are registered ─────────────────────────────────────────
import { useAuthStore } from "@/stores/auth";

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeUserResponse(overrides: Partial<{
  role: string;
  preferred_lang: string;
}> = {}) {
  return {
    data: {
      data: {
        access_token: "test-access-token",
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          display_name: null,
          role: overrides.role ?? "Editor",
          preferred_lang: overrides.preferred_lang ?? "en",
          created_at: "2024-01-01T00:00:00Z",
          last_login_at: null,
        },
      },
    },
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useAuthStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  // ── login ──────────────────────────────────────────────────────────────────

  it("login sets accessToken and user on success", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse());
    const store = useAuthStore();

    await store.login("testuser", "password123");

    expect(store.accessToken).toBe("test-access-token");
    expect(store.user?.username).toBe("testuser");
    expect(store.isAuthenticated).toBe(true);
  });

  it("login applies the user preferred_lang to i18n", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse({ preferred_lang: "it" }));
    const { i18n } = await import("@/main");
    const store = useAuthStore();

    await store.login("testuser", "password123");

    expect(i18n.global.locale.value).toBe("it");
  });

  it("login failure leaves state unauthenticated", async () => {
    mockPost.mockRejectedValueOnce(new Error("401 Unauthorized"));
    const store = useAuthStore();

    await expect(store.login("bad", "bad")).rejects.toThrow();
    expect(store.accessToken).toBeNull();
    expect(store.isAuthenticated).toBe(false);
  });

  // ── logout ─────────────────────────────────────────────────────────────────

  it("logout clears accessToken and user", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse());
    const store = useAuthStore();
    await store.login("testuser", "password123");

    mockPost.mockResolvedValueOnce({});
    await store.logout();

    expect(store.accessToken).toBeNull();
    expect(store.user).toBeNull();
    expect(store.isAuthenticated).toBe(false);
  });

  it("logout succeeds even when the server call fails (best-effort)", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse());
    const store = useAuthStore();
    await store.login("testuser", "password123");

    mockPost.mockRejectedValueOnce(new Error("network error"));
    await expect(store.logout()).resolves.not.toThrow();
    expect(store.user).toBeNull();
  });

  // ── isAuthenticated ────────────────────────────────────────────────────────

  it("isAuthenticated is false when there is no token", () => {
    const store = useAuthStore();
    expect(store.isAuthenticated).toBe(false);
  });

  // ── hasMinRole ─────────────────────────────────────────────────────────────

  it("hasMinRole returns true when user level >= required level", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse({ role: "EditorInChief" }));
    const store = useAuthStore();
    await store.login("eic", "pass");

    expect(store.hasMinRole("Editor")).toBe(true);
    expect(store.hasMinRole("EditorInChief")).toBe(true);
    expect(store.hasMinRole("Admin")).toBe(false);
  });

  it("hasMinRole returns false for User role when Editor is required", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse({ role: "User" }));
    const store = useAuthStore();
    await store.login("user", "pass");

    expect(store.hasMinRole("Editor")).toBe(false);
  });

  // ── hasRole ────────────────────────────────────────────────────────────────

  it("hasRole returns true only for the exact role", async () => {
    mockPost.mockResolvedValueOnce(makeUserResponse({ role: "Designer" }));
    const store = useAuthStore();
    await store.login("designer", "pass");

    expect(store.hasRole("Designer")).toBe(true);
    expect(store.hasRole("Editor")).toBe(false);
    expect(store.hasRole("Admin")).toBe(false);
  });

  // ── hydrate ────────────────────────────────────────────────────────────────

  it("hydrate sets user when refresh + loadMe succeed", async () => {
    mockPost.mockResolvedValueOnce({
      data: { data: { access_token: "refreshed-token" } },
    });
    mockGet.mockResolvedValueOnce({
      data: {
        data: {
          id: "u1",
          username: "admin",
          email: "a@b.com",
          display_name: null,
          role: "Admin",
          preferred_lang: "en",
          created_at: "2024-01-01T00:00:00Z",
          last_login_at: null,
        },
      },
    });
    const store = useAuthStore();

    await store.hydrate();

    expect(store.accessToken).toBe("refreshed-token");
    expect(store.user?.role).toBe("Admin");
  });

  it("hydrate leaves state unauthenticated when refresh fails", async () => {
    mockPost.mockRejectedValueOnce(new Error("no cookie"));
    const store = useAuthStore();

    await store.hydrate();

    expect(store.accessToken).toBeNull();
    expect(store.user).toBeNull();
  });
});
