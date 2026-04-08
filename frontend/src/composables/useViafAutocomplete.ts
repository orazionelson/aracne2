import { ref } from "vue";
import { apiClient } from "@/services/api";

const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;

/**
 * Provides debounced VIAF AutoSuggest lookup via the backend proxy.
 * Returns `results` (display names), `isLoading`, `search(query)` and `clear()`.
 *
 * Usage: call `search(value)` on every input event; bind the dropdown to `results`.
 */
export function useViafAutocomplete() {
  const results = ref<string[]>([]);
  const isLoading = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function _fetch(query: string): Promise<void> {
    isLoading.value = true;
    try {
      results.value = await apiClient.get<string[]>("/viaf/autosuggest", {
        params: { query },
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
