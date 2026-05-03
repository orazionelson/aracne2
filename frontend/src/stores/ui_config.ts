import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

/**
 * One link surfaced on the public site by an active plugin advertising
 * the ``public_navigation`` capability. Returned by the platform's
 * public-config endpoint only when the per-plugin admin toggle
 * (``public_link_<plugin_name>_enabled`` system_setting) is ``"true"``.
 *
 * The label resolves with this preference order:
 *   ``label_key`` → vue-i18n lookup wins when defined and resolvable
 *   ``label_<lang>`` → plain string for the active locale
 *   ``label_en`` → fallback when neither of the above is available
 */
export interface PublicNavEntry {
  plugin_name: string;
  section: "header" | "home_quick_links" | "footer";
  url: string;
  component: string;
  label_key: string | null;
  label_en: string | null;
  label_it: string | null;
  icon: string | null;
  priority: number;
}

export interface UiConfig {
  platform_name: string;
  platform_logo_url: string;
  navbar_bg_color: string;
  public_home_enabled: boolean;
  home_show_collections: boolean;
  home_show_search: boolean;
  home_show_login_button: boolean;
  has_custom_homepage_css: boolean;
  home_propagate_css: boolean;
  evt_enabled: boolean;
  public_search_engine_enabled: boolean;
  public_search_engine_slug: string;
  public_pages_doc_frame_enabled: boolean;
  home_intro_html: string;
  public_nav: PublicNavEntry[];
}

const DEFAULTS: UiConfig = {
  platform_name: "Aracne2",
  platform_logo_url: "/aracne-icons/lockup/aracne-lockup-vertical-512.png",
  navbar_bg_color: "#1e40af",
  public_home_enabled: false,
  home_show_collections: true,
  home_show_search: true,
  home_show_login_button: true,
  has_custom_homepage_css: false,
  home_propagate_css: false,
  evt_enabled: false,
  public_search_engine_enabled: false,
  public_search_engine_slug: "",
  public_pages_doc_frame_enabled: true,
  home_intro_html: "",
  public_nav: [],
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
