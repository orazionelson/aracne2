import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";
import api from "@/services/api";

export type SchemaFormat = "rng" | "dtd" | "xsd";

export interface TeiSchema {
  id: string;
  name: string;
  validation_filename: string | null;
  validation_format: SchemaFormat | null;
  cm5_filename: string | null;
  created_by: string | null;
  created_at: string;
}

export interface ValidationError {
  line: number;
  col: number;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

export const useSchemaStore = defineStore("schemas", () => {
  const schemas = ref<TeiSchema[]>([]);
  const isLoading = ref(false);

  async function fetchSchemas(): Promise<void> {
    isLoading.value = true;
    try {
      schemas.value = await apiClient.get<TeiSchema[]>("/schemas");
    } finally {
      isLoading.value = false;
    }
  }

  async function createSchema(name: string): Promise<TeiSchema> {
    const schema = await apiClient.post<TeiSchema>("/schemas", { name });
    schemas.value.unshift(schema);
    return schema;
  }

  async function deleteSchema(id: string): Promise<void> {
    await apiClient.delete<void>(`/schemas/${id}`);
    schemas.value = schemas.value.filter((s) => s.id !== id);
  }

  async function uploadValidation(id: string, file: File): Promise<TeiSchema> {
    const form = new FormData();
    form.append("file", file);
    const updated = await apiClient.upload<TeiSchema>(`/schemas/${id}/upload-validation`, form);
    _replace(updated);
    return updated;
  }

  async function importValidation(id: string, url: string): Promise<TeiSchema> {
    const updated = await apiClient.post<TeiSchema>(`/schemas/${id}/import-validation`, { url });
    _replace(updated);
    return updated;
  }

  async function uploadCm5(id: string, file: File): Promise<TeiSchema> {
    const form = new FormData();
    form.append("file", file);
    const updated = await apiClient.upload<TeiSchema>(`/schemas/${id}/upload-cm5`, form);
    _replace(updated);
    return updated;
  }

  async function importCm5(id: string, url: string): Promise<TeiSchema> {
    const updated = await apiClient.post<TeiSchema>(`/schemas/${id}/import-cm5`, { url });
    _replace(updated);
    return updated;
  }

  /** Generate the CM5 autocomplete schema from the uploaded validation schema. */
  async function generateCm5(id: string): Promise<TeiSchema> {
    const updated = await apiClient.post<TeiSchema>(`/schemas/${id}/generate-cm5`, {});
    _replace(updated);
    return updated;
  }

  /** Load the raw CM5 XML text for use in the CodeMirror editor. */
  async function fetchCm5Content(id: string): Promise<string> {
    const response = await api.get<string>(`/schemas/${id}/cm5-file`, { responseType: "text" });
    return response.data;
  }

  /** Validate a document against its collection's schema. */
  async function validateDocument(
    slug: string,
    filename: string,
  ): Promise<ValidationResult> {
    return await apiClient.post<ValidationResult>(
      `/collections/${slug}/documents/${filename}/validate`,
      {},
    );
  }

  function _replace(updated: TeiSchema): void {
    const idx = schemas.value.findIndex((s) => s.id === updated.id);
    if (idx >= 0) schemas.value[idx] = updated;
  }

  return {
    schemas,
    isLoading,
    fetchSchemas,
    createSchema,
    deleteSchema,
    uploadValidation,
    importValidation,
    uploadCm5,
    importCm5,
    fetchCm5Content,
    generateCm5,
    validateDocument,
  };
});
