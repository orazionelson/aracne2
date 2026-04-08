import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface UiConfig {
  platform_name: string;
  platform_logo_url: string;
  navbar_bg_color: string;
  public_home_enabled: boolean;
  home_show_collections: boolean;
  home_show_search: boolean;
  evt_enabled: boolean;
}

const DEFAULTS: UiConfig = {
  platform_name: "Aracne2",
  platform_logo_url: "/aracne-logo.png",
  navbar_bg_color: "#1e40af",
  public_home_enabled: false,
  home_show_collections: true,
  home_show_search: true,
  evt_enabled: false,
};

export const useUiConfigStore = defineStore("uiConfig", () => {
  const config = ref<UiConfig>({ ...DEFAULTS });
  const fetched = ref(false);

  async function fetchConfig(): Promise<void> {
    try {
      const data = await apiClient.get<UiConfig>("/settings/ui-config");
      config.value = data;
    } catch {
      // Keep defaults on failure — the app must remain usable without config.
    } finally {
      fetched.value = true;
    }
  }

  return { config, fetched, fetchConfig };
});
