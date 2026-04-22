import { ref, computed, watch } from "vue";
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

export type Theme = "light" | "dark";

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

  // Persisted admin UI theme.
  const theme = useLocalStorage<Theme>("aracne2.theme", "light");

  const isSidebarCollapsed = computed(
    () => sidebarForceCollapsed.value || sidebarCollapsed.value,
  );

  // Apply or remove the `dark` class on <html> so Tailwind's class-based
  // dark mode is active for every descendant.
  function applyThemeClass(value: Theme): void {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (value === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  }

  applyThemeClass(theme.value);
  watch(theme, (value) => applyThemeClass(value));

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

  function toggleTheme(): void {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  function setTheme(value: Theme): void {
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
    toggleTheme,
    setTheme,
  };
});
