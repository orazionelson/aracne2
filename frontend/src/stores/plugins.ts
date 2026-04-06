import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

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
