import { ref, computed } from "vue";
import { defineStore } from "pinia";
import { useLocalStorage } from "@vueuse/core";

const SECTION_KEYS = ["content", "tools", "admin"] as const;
export type SidebarSectionKey = (typeof SECTION_KEYS)[number];

type SidebarSections = Record<SidebarSectionKey, boolean>;

const DEFAULT_SECTIONS: SidebarSections = {
  content: true,
  tools: true,
  admin: true,
};

export const useUiStore = defineStore("ui", () => {
  // Persisted user preference for the sidebar collapsed state.
  const sidebarCollapsed = useLocalStorage("aracne2.sidebarCollapsed", false);

  // Per-section open/closed preference (only meaningful when expanded).
  const sidebarSections = useLocalStorage<SidebarSections>(
    "aracne2.sidebarSections",
    { ...DEFAULT_SECTIONS },
    { mergeDefaults: true },
  );

  // Runtime override used by full-bleed views (e.g. document editor) to force
  // the collapsed strip regardless of the persisted user preference.
  const sidebarForceCollapsed = ref(false);

  const theme = ref<"light" | "dark">("light");

  const isSidebarCollapsed = computed(
    () => sidebarForceCollapsed.value || sidebarCollapsed.value,
  );

  function toggleSidebar(): void {
    // User-initiated toggle: clear any force flag so the manual preference wins.
    sidebarForceCollapsed.value = false;
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  function setSidebarForceCollapsed(value: boolean): void {
    sidebarForceCollapsed.value = value;
  }

  function toggleSection(key: SidebarSectionKey): void {
    sidebarSections.value = {
      ...sidebarSections.value,
      [key]: !sidebarSections.value[key],
    };
  }

  function setTheme(value: "light" | "dark"): void {
    theme.value = value;
  }

  return {
    sidebarCollapsed,
    sidebarSections,
    sidebarForceCollapsed,
    isSidebarCollapsed,
    theme,
    toggleSidebar,
    toggleSection,
    setSidebarForceCollapsed,
    setTheme,
  };
});
