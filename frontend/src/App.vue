<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useSettingStore } from "@/stores/settings";
import { useUiConfigStore } from "@/stores/ui_config";
import { useUiStore } from "@/stores/ui";
import AdminLayout from "@/layouts/AdminLayout.vue";
import PublicLayout from "@/layouts/PublicLayout.vue";
import AuthLayout from "@/layouts/AuthLayout.vue";

const auth = useAuthStore();
const route = useRoute();
const settingStore = useSettingStore();
const uiConfig = useUiConfigStore();
// Instantiate the UI store so the persisted theme is applied to <html> before
// the first paint (the store's onInit hook sets the `dark` class).
useUiStore();

// Fetch public UI config at boot so the header/sidebar has the correct logo
// and colour even before the user logs in.
onMounted(() => { uiConfig.fetchConfig(); });

// Fetch platform settings once the user is authenticated (login or session
// restore at boot).
watch(
  () => auth.isAuthenticated,
  (authenticated) => { if (authenticated) settingStore.fetchSettings(); },
  { immediate: true },
);

const layoutName = computed<"admin" | "public" | "auth">(() => {
  const meta = route.meta.layout;
  if (meta === "admin" || meta === "public" || meta === "auth") return meta;
  // Fallback: authenticated routes default to admin, everything else to public.
  return auth.isAuthenticated ? "admin" : "public";
});

const LAYOUTS = {
  admin: AdminLayout,
  public: PublicLayout,
  auth: AuthLayout,
} as const;

const layoutComponent = computed(() => LAYOUTS[layoutName.value]);
</script>

<template>
  <component :is="layoutComponent" />
</template>
