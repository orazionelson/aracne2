import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface BodyTemplateInfo {
  id: string;
  label: string;
  snippet: string;
  is_native: boolean;
  created_at: string;
}

export const useBodyTemplateStore = defineStore("body_templates", () => {
  const templates = ref<BodyTemplateInfo[]>([]);

  async function fetchTemplates(): Promise<void> {
    templates.value = await apiClient.get<BodyTemplateInfo[]>("/body-templates");
  }

  async function createTemplate(label: string, snippet: string): Promise<void> {
    const tpl = await apiClient.post<BodyTemplateInfo>("/body-templates", { label, snippet });
    templates.value.push(tpl);
  }

  async function patchTemplate(
    id: string,
    payload: { label?: string; snippet?: string },
  ): Promise<void> {
    const tpl = await apiClient.patch<BodyTemplateInfo>(`/body-templates/${id}`, payload);
    const idx = templates.value.findIndex((t) => t.id === id);
    if (idx !== -1) templates.value[idx] = tpl;
  }

  async function deleteTemplate(id: string): Promise<void> {
    await apiClient.delete<void>(`/body-templates/${id}`);
    templates.value = templates.value.filter((t) => t.id !== id);
  }

  return { templates, fetchTemplates, createTemplate, patchTemplate, deleteTemplate };
});
