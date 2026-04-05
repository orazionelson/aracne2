# PHASE 01d — Frontend: Vite, Vue 3, stores, router, views
# Prerequisite: CLAUDE.md loaded. Phase 01a (infrastructure) complete.
# Goal: frontend container starts, login page renders, auth store communicates
#   with backend via httpOnly cookie refresh token strategy.

Implement everything below. Every file must be complete and working.

---

## File: frontend/Dockerfile

```dockerfile
# Development stage
FROM node:20-alpine AS development
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage — served by nginx (see docker-compose.prod.yml)
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

## File: frontend/vite.config.ts

```typescript
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,
    outDir: "dist",
  },
});
```

---

## File: frontend/src/services/api.ts

Token strategy:
- `access_token`: injected via Authorization header from Pinia store (memory only)
- `refresh_token`: httpOnly cookie — sent automatically by the browser, never read by JS
- `withCredentials: true` is mandatory for the cookie to be sent to `/auth/refresh`

```typescript
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/stores/auth";

const api: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // required to send the httpOnly refresh cookie
});

// Request interceptor: inject access token and request ID
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore();
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  config.headers["X-Request-ID"] = crypto.randomUUID();
  return config;
});

// Response interceptor: handle 401 with automatic token refresh
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: Error | null, token: string | null = null): void => {
  failedQueue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token!)
  );
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      });
    }
    original._retry = true;
    isRefreshing = true;
    const auth = useAuthStore();
    try {
      await auth.refresh();
      processQueue(null, auth.accessToken);
      original.headers.Authorization = `Bearer ${auth.accessToken}`;
      return api(original);
    } catch (refreshError) {
      processQueue(refreshError as Error, null);
      await auth.logout();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

// Typed helpers that unwrap the `.data` envelope automatically
export const apiClient = {
  get: <T>(url: string, config = {}) =>
    api.get<{ data: T }>(url, config).then((r) => r.data.data),
  post: <T>(url: string, data?: unknown, config = {}) =>
    api.post<{ data: T }>(url, data, config).then((r) => r.data.data),
  patch: <T>(url: string, data?: unknown, config = {}) =>
    api.patch<{ data: T }>(url, data, config).then((r) => r.data.data),
  put: <T>(url: string, data?: unknown, config = {}) =>
    api.put<{ data: T }>(url, data, config).then((r) => r.data.data),
  delete: <T>(url: string, config = {}) =>
    api.delete<{ data: T }>(url, config).then((r) => r.data.data),
  // For paginated list endpoints:
  getPaginated: <T>(url: string, config = {}) =>
    api.get<{ data: T[]; pagination: unknown }>(url, config).then((r) => r.data),
  // For multipart XML uploads (bypasses JSON serialization):
  upload: <T>(url: string, form: FormData) =>
    api.post<{ data: T }>(url, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data.data),
};

export default api;
```

---

## File: frontend/src/stores/auth.ts

Token strategy:
- `access_token`: Pinia ref (memory only) — lost on page reload, recovered by `hydrate()`
- `refresh_token`: NOT managed by the frontend — travels as httpOnly cookie set by the
  server on `POST /auth/login` and renewed on `POST /auth/refresh`.
  The browser sends it automatically. Frontend JS never reads it.

```typescript
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import api from "@/services/api";

const ROLE_ORDER: Record<string, number> = {
  User: 0, Editor: 1, Designer: 2, EditorInChief: 3, Admin: 4,
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

export const useAuthStore = defineStore("auth", () => {
  const user = ref<UserMe | null>(null);
  const accessToken = ref<string | null>(null);
  const isLoading = ref(false);

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);
  const userRole = computed(() => user.value?.role ?? "User");

  const hasMinRole = (minRole: string): boolean => {
    const userLevel = ROLE_ORDER[userRole.value] ?? 0;
    const minLevel = ROLE_ORDER[minRole] ?? 0;
    return userLevel >= minLevel;
  };

  async function login(usernameOrEmail: string, password: string): Promise<void> {
    isLoading.value = true;
    try {
      // Server responds with Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict
      // Frontend receives only access_token and user in the response body
      const res = await api.post<{ access_token: string; user: UserMe }>(
        "/auth/login",
        { username_or_email: usernameOrEmail, password },
      );
      accessToken.value = res.data.data.access_token;
      user.value = res.data.data.user;
    } finally {
      isLoading.value = false;
    }
  }

  async function logout(): Promise<void> {
    // Server revokes the refresh token and sends Set-Cookie with Max-Age=0
    try { await api.post("/auth/logout"); } catch { /* ignore network errors */ }
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
    user, accessToken, isLoading,
    isAuthenticated, userRole, hasMinRole,
    login, logout, refresh, loadMe, hydrate,
  };
});
```

---

## File: frontend/src/router/index.ts

```typescript
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: () => import("@/views/HomeView.vue"),
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/auth/LoginView.vue"),
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/auth/ProfileView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
    },
  ],
});

let hydrated = false;
router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!hydrated) {
    await auth.hydrate();
    hydrated = true;
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "home" };
  }
  if (to.meta.requiresRole && !auth.hasMinRole(to.meta.requiresRole as string)) {
    return { name: "home" };
  }
});

export default router;
```

---

## Stub views (minimal files, no logic)

**src/views/HomeView.vue**:
```vue
<template><h1>Aracne2</h1></template>
```

**src/views/NotFoundView.vue**:
```vue
<template><h1>404 — Page not found</h1></template>
```

**src/views/auth/ProfileView.vue**:
```vue
<template><p>Profile — work in progress</p></template>
```

---

## File: frontend/src/views/auth/LoginView.vue

```vue
<script setup lang="ts">
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const usernameOrEmail = ref("");
const password = ref("");
const showPassword = ref(false);
const errorMessage = ref("");
const isLoading = ref(false);

// Validates that the redirect target is a safe internal path (prevents open redirect)
function isSafeRedirect(url: string): boolean {
  return url.startsWith("/") && !url.startsWith("//") && !url.includes(":");
}

async function handleLogin(): Promise<void> {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    await auth.login(usernameOrEmail.value, password.value);
    const raw = route.query.redirect as string | undefined;
    const redirect = raw && isSafeRedirect(raw) ? raw : "/";
    await router.push(redirect);
  } catch (err: unknown) {
    // Generic message — do not distinguish between wrong username and wrong password
    errorMessage.value = "Invalid credentials. Please try again.";
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-md bg-white rounded-xl shadow p-8">
      <h1 class="text-2xl font-bold text-center mb-6">Sign in</h1>
      <form @submit.prevent="handleLogin" novalidate>
        <div class="mb-4">
          <label class="block text-sm font-medium mb-1">Username or Email</label>
          <input
            v-model="usernameOrEmail"
            type="text"
            required
            autocomplete="username"
            class="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2"
          />
        </div>
        <div class="mb-6 relative">
          <label class="block text-sm font-medium mb-1">Password</label>
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            required
            autocomplete="current-password"
            class="w-full border rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2"
          />
          <button
            type="button"
            @click="showPassword = !showPassword"
            class="absolute right-3 top-8 text-gray-500 text-sm"
          >
            {{ showPassword ? "Hide" : "Show" }}
          </button>
        </div>
        <p v-if="errorMessage" class="text-red-600 text-sm mb-4">{{ errorMessage }}</p>
        <button
          type="submit"
          :disabled="isLoading"
          class="w-full bg-blue-600 text-white py-2 rounded-lg font-semibold
                 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ isLoading ? "Signing in..." : "Sign in" }}
        </button>
      </form>
    </div>
  </div>
</template>
```
