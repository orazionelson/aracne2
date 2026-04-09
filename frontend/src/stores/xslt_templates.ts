import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface XsltTemplateSummary {
  id: string;
  name: string;
  description: string | null;
  processor: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface XsltTemplateDetail extends XsltTemplateSummary {
  content: string;
  created_by: string | null;
}

export interface XsltTemplateCreate {
  name: string;
  description?: string | null;
  content: string;
  processor?: string;
  tags?: string[];
}

export interface XsltTemplatePatch {
  name?: string;
  description?: string | null;
  content?: string;
  processor?: string;
  tags?: string[];
}

export const useXsltTemplateStore = defineStore("xslt_templates", () => {
  const templates = ref<XsltTemplateSummary[]>([]);

  async function fetchTemplates(): Promise<void> {
    templates.value = await apiClient.get<XsltTemplateSummary[]>("/xslt-templates");
  }

  async function getTemplate(id: string): Promise<XsltTemplateDetail> {
    return apiClient.get<XsltTemplateDetail>(`/xslt-templates/${id}`);
  }

  async function createTemplate(payload: XsltTemplateCreate): Promise<XsltTemplateDetail> {
    const tpl = await apiClient.post<XsltTemplateDetail>("/xslt-templates", payload);
    templates.value.push(tpl);
    templates.value.sort((a, b) => a.name.localeCompare(b.name));
    return tpl;
  }

  async function patchTemplate(id: string, payload: XsltTemplatePatch): Promise<XsltTemplateDetail> {
    const tpl = await apiClient.patch<XsltTemplateDetail>(`/xslt-templates/${id}`, payload);
    const idx = templates.value.findIndex((t) => t.id === id);
    if (idx !== -1) templates.value[idx] = tpl;
    return tpl;
  }

  async function deleteTemplate(id: string): Promise<void> {
    await apiClient.delete<void>(`/xslt-templates/${id}`);
    templates.value = templates.value.filter((t) => t.id !== id);
  }

  return { templates, fetchTemplates, getTemplate, createTemplate, patchTemplate, deleteTemplate };
});
