/**
 * Store for the per-website media library.
 *
 * The backend stores files on disk under ``media/websites/<slug>/``
 * and this store mirrors the list client-side. References in content
 * (theme config, Markdown, WYSIWYG HTML) travel as ``media://<filename>``
 * pseudo-URLs — the caller pastes the ``ref`` field returned by this
 * store verbatim into the edit form, and the backend rewrites it
 * at render / build time.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface WebsiteMediaFile {
  filename: string;
  size_bytes: number;
  content_type: string;
  uploaded_at: string;
  /** ``media://<filename>`` — paste this into theme / Markdown fields. */
  ref: string;
}

export const useWebsiteMediaStore = defineStore("website_media", () => {
  // Files are cached per-slug so multiple pickers on the same site share
  // a single fetch. A fresh fetch is triggered on demand (explicit call);
  // we don't auto-refresh, so the caller controls when to re-hit the API.
  const filesBySlug = ref<Record<string, WebsiteMediaFile[]>>({});
  const isLoading = ref(false);
  const isUploading = ref(false);

  function getFiles(slug: string): WebsiteMediaFile[] {
    return filesBySlug.value[slug] ?? [];
  }

  async function fetchFiles(slug: string): Promise<WebsiteMediaFile[]> {
    isLoading.value = true;
    try {
      const data = await apiClient.get<WebsiteMediaFile[]>(
        `/websites/${slug}/media`,
      );
      filesBySlug.value[slug] = data;
      return data;
    } finally {
      isLoading.value = false;
    }
  }

  async function uploadFile(slug: string, file: File): Promise<WebsiteMediaFile> {
    const form = new FormData();
    form.append("file", file, file.name);
    isUploading.value = true;
    try {
      const data = await apiClient.upload<WebsiteMediaFile>(
        `/websites/${slug}/media`,
        form,
      );
      // Replace or insert into the cache.
      const list = filesBySlug.value[slug] ?? [];
      const i = list.findIndex((f) => f.filename === data.filename);
      if (i >= 0) list.splice(i, 1, data);
      else list.push(data);
      // Keep the list sorted alphabetically to match the backend listing.
      list.sort((a, b) => a.filename.localeCompare(b.filename));
      filesBySlug.value[slug] = [...list];
      return data;
    } finally {
      isUploading.value = false;
    }
  }

  async function deleteFile(slug: string, filename: string): Promise<void> {
    await apiClient.delete<void>(`/websites/${slug}/media/${encodeURIComponent(filename)}`);
    const list = filesBySlug.value[slug];
    if (list) {
      filesBySlug.value[slug] = list.filter((f) => f.filename !== filename);
    }
  }

  return { filesBySlug, isLoading, isUploading, getFiles, fetchFiles, uploadFile, deleteFile };
});
