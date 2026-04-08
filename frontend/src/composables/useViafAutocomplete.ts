import { ref } from "vue";
import axios from "axios";

interface ViafSuggestion {
  displayForm: string;
  viafid: string;
}

interface ViafResponse {
  result: ViafSuggestion[] | null;
}

const VIAF_URL = "https://www.viaf.org/viaf/AutoSuggest";
const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;

/**
 * Provides debounced VIAF AutoSuggest lookup.
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
      const { data } = await axios.get<ViafResponse>(VIAF_URL, {
        params: { query },
      });
      results.value = data.result ? data.result.map((r) => r.displayForm) : [];
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
