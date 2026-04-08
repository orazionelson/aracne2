import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface LicenseInfo {
  id: string;
  name: string;
  target: string | null;
  is_active: boolean;
  created_at: string;
}

export const useLicenseStore = defineStore("licenses", () => {
  const licenses = ref<LicenseInfo[]>([]);
  const isLoading = ref(false);

  async function fetchLicenses(): Promise<void> {
    isLoading.value = true;
    try {
      licenses.value = await apiClient.get<LicenseInfo[]>("/licenses");
    } finally {
      isLoading.value = false;
    }
  }

  async function createLicense(name: string, target: string | null): Promise<LicenseInfo> {
    const created = await apiClient.post<LicenseInfo>("/licenses", { name, target });
    licenses.value.push(created);
    licenses.value.sort((a, b) => a.name.localeCompare(b.name));
    return created;
  }

  async function patchLicense(
    id: string,
    payload: Partial<Pick<LicenseInfo, "name" | "target" | "is_active">>,
  ): Promise<void> {
    const updated = await apiClient.patch<LicenseInfo>(`/licenses/${id}`, payload);
    const idx = licenses.value.findIndex((l) => l.id === id);
    if (idx !== -1) licenses.value[idx] = updated;
  }

  async function deleteLicense(id: string): Promise<void> {
    await apiClient.delete(`/licenses/${id}`);
    licenses.value = licenses.value.filter((l) => l.id !== id);
  }

  return { licenses, isLoading, fetchLicenses, createLicense, patchLicense, deleteLicense };
});
