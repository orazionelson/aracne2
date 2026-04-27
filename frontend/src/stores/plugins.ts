import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

/**
 * Per-capability UI metadata. The platform doesn't interpret these
 * dicts — each capability tag (e.g. ``inline_authority``,
 * ``collection_deposit``) defines its own contract, documented
 * inline below and on the backend in ``app/core/plugin_base.py``.
 */
export interface InlineAuthorityDescriptor {
  /** Vue component name registered in src/components/lookup/registry.ts. */
  component: string;
  /** vue-i18n key for the toolbar button label. Falls back to display_name. */
  label_key?: string;
  /** Tailwind class applied to the toolbar icon (e.g. "text-amber-500"). */
  icon_color?: string;
  /** "ref" → emit @apply(uri); "fragment" → emit @insert(xmlFragment). */
  apply: "ref" | "fragment";
  /** What seed value to feed the panel:
   * "selection" — pass the active editor selection as initialQuery,
   * "selection-or-empty" — same but tolerate emptiness silently,
   * "kind-picker" — open the panel without seeding (e.g. Trismegistos),
   * "doi" — seed with selection text expected to be a DOI (e.g. CrossRef). */
  initial_context: "selection" | "selection-or-empty" | "kind-picker" | "doi";
  /** Toolbar sort key — lower = leftmost. */
  priority?: number;
}

/** UI metadata for the collection detail page's "Deposita" foldable. */
export interface CollectionDepositDescriptor {
  /** Vue component name registered in src/components/deposit/registry.ts. */
  component: string;
  /** Plain-text fallback label for the tab (used when label_key is absent or unresolved). */
  label?: string;
  /** Optional vue-i18n key for the tab label — wins over `label` when defined and resolvable. */
  label_key?: string;
  /** Tab sort key — lower = leftmost. */
  priority?: number;
}

/** UI metadata for the website edit page's "Deposito" tab. */
export interface WebsiteDepositDescriptor {
  /** Vue component name registered in src/components/website-deposit/registry.ts. */
  component: string;
  /** Plain-text fallback label for the sub-tab. */
  label?: string;
  /** Optional vue-i18n key — wins over `label` when defined and resolvable. */
  label_key?: string;
  /** Sub-tab sort key — lower = leftmost. */
  priority?: number;
}

export interface PluginInfo {
  id: string;
  name: string;
  display_name: string;
  version: string | null;
  description: string | null;
  author: string | null;
  entry_point: string | null;
  is_native: boolean;
  status: "active" | "inactive" | "error";
  /** Capability tags advertised by the plugin (e.g. ["inline_authority"]). */
  capabilities: string[];
  /** Per-capability UI descriptor blob, keyed by capability tag. */
  ui_descriptor: Record<string, unknown> | null;
  installed_at: string;
  updated_at: string;
}

export const usePluginStore = defineStore("plugins", () => {
  const plugins = ref<PluginInfo[]>([]);
  const isLoading = ref(false);

  /** True if a plugin with the given name slug is currently active. */
  function isActive(name: string): boolean {
    return plugins.value.some((p) => p.name === name && p.status === "active");
  }

  async function fetchPlugins(): Promise<void> {
    isLoading.value = true;
    try {
      plugins.value = await apiClient.get<PluginInfo[]>("/plugins");
    } finally {
      isLoading.value = false;
    }
  }

  async function activate(name: string): Promise<void> {
    await apiClient.post<PluginInfo>(`/plugins/${name}/activate`);
    await fetchPlugins();
  }

  async function deactivate(name: string): Promise<void> {
    await apiClient.post<PluginInfo>(`/plugins/${name}/deactivate`);
    await fetchPlugins();
  }

  async function removePlugin(name: string): Promise<void> {
    await apiClient.delete<void>(`/plugins/${name}`);
    await fetchPlugins();
  }

  return { plugins, isLoading, isActive, fetchPlugins, activate, deactivate, removePlugin };
});
