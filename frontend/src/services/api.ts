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
    error ? reject(error) : resolve(token!),
  );
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    // Never retry the refresh endpoint itself — it would deadlock hydrate().
    const isRefreshCall = original.url?.includes("/auth/refresh");
    if (error.response?.status !== 401 || original._retry || isRefreshCall) {
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
  },
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
    api
      .post<{ data: T }>(url, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data.data),
};

export default api;
