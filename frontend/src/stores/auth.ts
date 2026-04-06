import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { i18n } from "@/main";
import api from "@/services/api";

// Editor and Designer are lateral roles at the same level (2).
// Endpoints exclusive to one lateral role use an explicit role-name check,
// not just a numeric comparison (e.g. hasRole("Designer") for template routes).
const ROLE_ORDER: Record<string, number> = {
  User: 1,
  Editor: 2,
  Designer: 2,
  EditorInChief: 3,
  Admin: 4,
};

interface UserMe {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  role: string;
  preferred_lang: string;
  created_at: string;
  last_login_at: string | null;
}

interface ImpersonationState {
  username: string;
  role: string;
  adminToken: string;
}

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserMe | null>(null);
  const accessToken = ref<string | null>(null);
  const isLoading = ref(false);
  const impersonating = ref<ImpersonationState | null>(null);

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);
  const userRole = computed(() => user.value?.role ?? "User");

  // Numeric guard: user level >= required level.
  // Use for [E+] / [EiC+] / [A] checks.
  const hasMinRole = (minRole: string): boolean => {
    const userLevel = ROLE_ORDER[userRole.value] ?? 0;
    const minLevel = ROLE_ORDER[minRole] ?? 0;
    return userLevel >= minLevel;
  };

  // Exact role check: use for lateral-role-exclusive routes
  // (e.g. Designer-only template management, Editor-only document editing).
  const hasRole = (role: string): boolean => userRole.value === role;

  function applyLocale(lang: string): void {
    i18n.global.locale.value = lang as "en" | "it";
  }

  async function login(usernameOrEmail: string, password: string): Promise<void> {
    isLoading.value = true;
    try {
      // Server responds with Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict
      // Frontend receives only access_token and user in the response body
      const res = await api.post<{ access_token: string; user: UserMe }>("/auth/login", {
        username_or_email: usernameOrEmail,
        password,
      });
      accessToken.value = res.data.data.access_token;
      user.value = res.data.data.user;
      applyLocale(res.data.data.user.preferred_lang);
    } finally {
      isLoading.value = false;
    }
  }

  async function logout(): Promise<void> {
    // Server revokes the refresh token and sends Set-Cookie with Max-Age=0
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore network errors */
    }
    user.value = null;
    accessToken.value = null;
  }

  async function refresh(): Promise<void> {
    // No request body — browser sends the httpOnly cookie automatically
    const res = await api.post<{ access_token: string }>("/auth/refresh");
    accessToken.value = res.data.data.access_token;
  }

  async function loadMe(): Promise<void> {
    const res = await api.get<UserMe>("/auth/me");
    user.value = res.data.data;
    applyLocale(res.data.data.preferred_lang);
  }

  async function startImpersonation(userId: string): Promise<void> {
    const res = await api.post<{ access_token: string; impersonated_user: UserMe }>(
      `/auth/impersonate/${userId}`,
    );
    const data = res.data.data;
    impersonating.value = {
      username: data.impersonated_user.username,
      role: data.impersonated_user.role,
      adminToken: accessToken.value!,
    };
    accessToken.value = data.access_token;
    user.value = data.impersonated_user;
    applyLocale(data.impersonated_user.preferred_lang);
  }

  async function exitImpersonation(): Promise<void> {
    if (!impersonating.value) return;
    accessToken.value = impersonating.value.adminToken;
    impersonating.value = null;
    await loadMe();
  }

  // Called at SPA boot: attempts a silent token refresh.
  // If the refresh cookie is present and valid, recovers access_token and user data.
  // If it fails, the user is treated as unauthenticated.
  async function hydrate(): Promise<void> {
    try {
      await refresh();
      await loadMe();
    } catch {
      user.value = null;
      accessToken.value = null;
    }
  }

  return {
    user,
    accessToken,
    isLoading,
    isAuthenticated,
    userRole,
    hasMinRole,
    hasRole,
    impersonating,
    login,
    logout,
    refresh,
    loadMe,
    hydrate,
    startImpersonation,
    exitImpersonation,
  };
});
