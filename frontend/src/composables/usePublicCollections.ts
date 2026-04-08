import { ref } from "vue";
import { apiClient } from "@/services/api";
import type { Collection } from "@/stores/collections";

export function usePublicCollections() {
  const collections = ref<Collection[]>([]);
  const total = ref(0);
  const isLoading = ref(false);

  async function fetchCollections(search = ""): Promise<void> {
    isLoading.value = true;
    try {
      const params = new URLSearchParams({ per_page: "50" });
      if (search) params.set("search", search);
      const result = await apiClient.getPaginated<Collection>(
        `/collections/public?${params.toString()}`,
      );
      collections.value = result.data;
      total.value =
        typeof result.pagination === "object" && result.pagination !== null
          ? (result.pagination as { total: number }).total
          : 0;
    } catch {
      collections.value = [];
      total.value = 0;
    } finally {
      isLoading.value = false;
    }
  }

  return { collections, total, isLoading, fetchCollections };
}
