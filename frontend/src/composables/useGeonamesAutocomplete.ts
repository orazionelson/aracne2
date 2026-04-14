import { ref } from "vue";
import { apiClient } from "@/services/api";

const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;

export interface GeonamesPlace {
  name: string;
  region: string;
  country: string;
  geonames_id: number;
}

/**
 * Provides debounced GeoNames place search via the backend proxy.
 * Returns `results` (GeonamesPlace[]), `isLoading`, `search(query)` and `clear()`.
 *
 * Usage: call `search(value)` on every input event; bind the dropdown to `results`.
 * On selection, use `place.name` as the stored value and display region/country
 * only in the dropdown for disambiguation.
 */
export function useGeonamesAutocomplete() {
  const results = ref<GeonamesPlace[]>([]);
  const isLoading = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function _fetch(query: string): Promise<void> {
    isLoading.value = true;
    try {
      results.value = await apiClient.get<GeonamesPlace[]>("/geonames/search", {
        params: { q: query },
      });
    } catch {
      results.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  function search(query: string): void {
    if (timer) clearTimeout(timer);
    if (query.length < MIN_CHARS) {
      results.value = [];
      return;
    }
    timer = setTimeout(() => _fetch(query), DEBOUNCE_MS);
  }

  function clear(): void {
    if (timer) clearTimeout(timer);
    results.value = [];
  }

  return { results, isLoading, search, clear };
}
