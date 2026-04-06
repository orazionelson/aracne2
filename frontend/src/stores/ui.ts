import { ref } from "vue";
import { defineStore } from "pinia";

export const useUiStore = defineStore("ui", () => {
  const sidebarOpen = ref(true);
  const theme = ref<"light" | "dark">("light");

  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value;
  }

  function setTheme(value: "light" | "dark"): void {
    theme.value = value;
  }

  return { sidebarOpen, theme, toggleSidebar, setTheme };
});
