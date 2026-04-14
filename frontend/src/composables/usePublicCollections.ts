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

const PER_PAGE = 9;

export function usePublicCollections() {
  const collections = ref<PublicCollectionItem[]>([]);
  const total = ref(0);
  const page = ref(1);
  const totalPages = ref(1);
  const isLoading = ref(false);

  async function fetchCollections(search = "", p = 1): Promise<void> {
    page.value = p;
    isLoading.value = true;
    try {
      if (search) {
        // Full-text search returns a flat unordered list — no server-side pagination.
        const data = await apiClient.get<
          Array<{ collection: Collection; doc_hits: PublicDocHit[] }>
        >(
          `/collections/public/search?q=${encodeURIComponent(search)}&max_doc_hits=3`,
        );
        collections.value = data.map((r) => ({ ...r.collection, doc_hits: r.doc_hits }));
        total.value = collections.value.length;
        totalPages.value = 1;
      } else {
        // Paginated listing ordered by published_at DESC.
        const result = await apiClient.getPaginated<Collection>(
          `/collections/public?per_page=${PER_PAGE}&page=${p}`,
        );
        collections.value = result.data.map((c) => ({ ...c, doc_hits: [] }));
        const pag = result.pagination as {
          total: number;
          total_pages: number;
          page: number;
        };
        total.value = pag.total;
        totalPages.value = pag.total_pages ?? Math.ceil(pag.total / PER_PAGE);
      }
    } catch {
      collections.value = [];
      total.value = 0;
      totalPages.value = 1;
    } finally {
      isLoading.value = false;
    }
  }

  return { collections, total, page, totalPages, isLoading, fetchCollections };
}
