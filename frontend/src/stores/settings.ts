import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface SettingInfo {
  key: string;
  value: string;
  type: string;
  description: string | null;
  updated_at: string;
}

export const useSettingStore = defineStore("settings", () => {
  const settings = ref<SettingInfo[]>([]);
  const isLoading = ref(false);

  async function fetchSettings(): Promise<void> {
    isLoading.value = true;
    try {
      settings.value = await apiClient.get<SettingInfo[]>("/settings");
    } finally {
      isLoading.value = false;
    }
  }

  async function updateSetting(key: string, value: string): Promise<void> {
    const updated = await apiClient.patch<SettingInfo>(`/settings/${key}`, { value });
    const idx = settings.value.findIndex((s) => s.key === key);
    if (idx !== -1) settings.value[idx] = updated;
  }

  async function uploadLogo(file: File): Promise<string> {
    const form = new FormData();
    form.append("file", file);
    const result = await apiClient.upload<{ url: string }>("/settings/logo", form);
    // Refresh so the platform_logo_url key in the table reflects the new value.
    await fetchSettings();
    return result.url;
  }

  function getSetting(key: string): string | null {
    return settings.value.find((s) => s.key === key)?.value ?? null;
  }

  return { settings, isLoading, fetchSettings, updateSetting, uploadLogo, getSetting };
});
