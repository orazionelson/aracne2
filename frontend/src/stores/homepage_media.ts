/**
 * Store for the public homepage media library.
 *
 * One shared folder per platform — there's only one homepage. Files
 * live at ``/api/v1/settings/homepage-media/<filename>`` server-side;
 * each ``ref`` returned by the backend is the same path, ready to be
 * pasted as ``<img src="...">`` into the homepage intro WYSIWYG.
 *
 * Mirrors :func:`useWebsiteMediaStore` but without the slug — the
 * surface is platform-wide.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface HomepageMediaFile {
  filename: string;
  size_bytes: number;
  content_type: string;
  uploaded_at: string;
  /** Absolute serve URL — paste verbatim into the editor. */
  ref: string;
}

export const useHomepageMediaStore = defineStore("homepage_media", () => {
  const files = ref<HomepageMediaFile[]>([]);
  const isLoading = ref(false);
  const isUploading = ref(false);

  async function fetchFiles(): Promise<HomepageMediaFile[]> {
    isLoading.value = true;
    try {
      const data = await apiClient.get<HomepageMediaFile[]>(
        "/settings/homepage-media",
      );
      files.value = data;
      return data;
    } finally {
      isLoading.value = false;
    }
  }

  async function uploadFile(file: File): Promise<HomepageMediaFile> {
    const form = new FormData();
    form.append("file", file, file.name);
    isUploading.value = true;
    try {
      const data = await apiClient.upload<HomepageMediaFile>(
        "/settings/homepage-media",
        form,
      );
      const i = files.value.findIndex((f) => f.filename === data.filename);
      if (i >= 0) files.value.splice(i, 1, data);
      else files.value.push(data);
      files.value.sort((a, b) => a.filename.localeCompare(b.filename));
      return data;
    } finally {
      isUploading.value = false;
    }
  }

  async function deleteFile(filename: string): Promise<void> {
    await apiClient.delete<void>(
      `/settings/homepage-media/${encodeURIComponent(filename)}`,
    );
    files.value = files.value.filter((f) => f.filename !== filename);
  }

  return { files, isLoading, isUploading, fetchFiles, uploadFile, deleteFile };
});
