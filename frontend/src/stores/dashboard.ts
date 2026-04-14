import { ref } from "vue";
import { defineStore } from "pinia";
import api, { apiClient } from "@/services/api";

export interface DashboardCollection {
  id: string;
  slug: string;
  title: string;
  status: string;
  created_at: string;
}

interface HealthService {
  status: string;
  detail?: string;
}

export interface DashboardHealth {
  status: string;
  services: {
    postgres: HealthService;
    existdb: HealthService;
  };
}

interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export const useDashboardStore = defineStore("dashboard", () => {
  const collectionsTotal = ref(0);
  const collectionsDraft = ref(0);
  const collectionsReview = ref(0);
  const collectionsPublished = ref(0);
  const usersTotal = ref<number | null>(null);
  const recentCollections = ref<DashboardCollection[]>([]);
  const health = ref<DashboardHealth | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchDashboard(role: string): Promise<void> {
    loading.value = true;
    error.value = null;

    const isAdmin = role === "Admin";

    try {
      // All collection requests run in parallel.
      const [recent, draft, review, published, ...adminResults] =
        await Promise.all([
          api
            .get<{ data: DashboardCollection[]; pagination: PaginationMeta }>(
              "/collections",
              { params: { page: 1, per_page: 5 } },
            )
            .then((r) => r.data),
          api
            .get<{ data: unknown[]; pagination: PaginationMeta }>(
              "/collections",
              { params: { page: 1, per_page: 1, status: "draft" } },
            )
            .then((r) => r.data),
          api
            .get<{ data: unknown[]; pagination: PaginationMeta }>(
              "/collections",
              { params: { page: 1, per_page: 1, status: "review" } },
            )
            .then((r) => r.data),
          api
            .get<{ data: unknown[]; pagination: PaginationMeta }>(
              "/collections",
              { params: { page: 1, per_page: 1, status: "published" } },
            )
            .then((r) => r.data),
          // Admin-only: users count and health
          ...(isAdmin
            ? [
                api
                  .get<{ data: unknown[]; pagination: PaginationMeta }>(
                    "/users",
                    { params: { page: 1, per_page: 1 } },
                  )
                  .then((r) => r.data),
                apiClient.get<DashboardHealth>("/health"),
              ]
            : []),
        ]);

      collectionsTotal.value = recent.pagination.total;
      recentCollections.value = recent.data;
      collectionsDraft.value = draft.pagination.total;
      collectionsReview.value = review.pagination.total;
      collectionsPublished.value = published.pagination.total;

      if (isAdmin && adminResults.length === 2) {
        const usersResult = adminResults[0] as {
          data: unknown[];
          pagination: PaginationMeta;
        };
        usersTotal.value = usersResult.pagination.total;
        health.value = adminResults[1] as DashboardHealth;
      } else {
        usersTotal.value = null;
        health.value = null;
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Dashboard load failed";
    } finally {
      loading.value = false;
    }
  }

  return {
    collectionsTotal,
    collectionsDraft,
    collectionsReview,
    collectionsPublished,
    usersTotal,
    recentCollections,
    health,
    loading,
    error,
    fetchDashboard,
  };
});
