import { ref } from "vue";
import { apiClient } from "@/services/api";
import type { Collection } from "@/stores/collections";

export interface PublicDocHit {
  filename: string;
  snippet: string;
}

/** Collection card item enriched with optional document-level search hits. */
export interface PublicCollectionItem extends Collection {
  doc_hits: PublicDocHit[];
}

export function usePublicCollections() {
  const collections = ref<PublicCollectionItem[]>([]);
  const total = ref(0);
  const isLoading = ref(false);

  async function fetchCollections(search = ""): Promise<void> {
    isLoading.value = true;
    try {
      if (search) {
        // Full-text search: metadata + document content
        const data = await apiClient.get<
          Array<{ collection: Collection; doc_hits: PublicDocHit[] }>
        >(
          `/collections/public/search?q=${encodeURIComponent(search)}&max_doc_hits=3`,
        );
        collections.value = data.map((r) => ({ ...r.collection, doc_hits: r.doc_hits }));
        total.value = collections.value.length;
      } else {
        // Plain listing
        const result = await apiClient.getPaginated<Collection>(
          "/collections/public?per_page=50",
        );
        collections.value = result.data.map((c) => ({ ...c, doc_hits: [] }));
        total.value =
          typeof result.pagination === "object" && result.pagination !== null
            ? (result.pagination as { total: number }).total
            : 0;
      }
    } catch {
      collections.value = [];
      total.value = 0;
    } finally {
      isLoading.value = false;
    }
  }

  return { collections, total, isLoading, fetchCollections };
}
