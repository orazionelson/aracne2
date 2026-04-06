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

  return { settings, isLoading, fetchSettings, updateSetting };
});
