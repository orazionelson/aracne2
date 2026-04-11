/**
 * mediaStore — manages images associated with a TEI document.
 *
 * The store is document-scoped: call fetchMedia(slug, docFilename) whenever
 * the panel mounts or the document changes. State is intentionally flat —
 * no nested map — because only one document is open at a time in the editor.
 */

import { defineStore } from 'pinia';
import { ref } from 'vue';
import api, { apiClient } from '@/services/api';

export interface MediaItem {
  filename: string;
  /** Full API URL for serving the file (requires auth Bearer — use fetchBlobUrl for <img>). */
  url: string;
  size: number;
  content_type: string;
}

export const useMediaStore = defineStore('media', () => {
  const items = ref<MediaItem[]>([]);
  const isLoading = ref(false);
  const isUploading = ref(false);
  const error = ref<string | null>(null);

  function _base(slug: string, docFilename: string): string {
    return `/collections/${slug}/documents/${encodeURIComponent(docFilename)}/media`;
  }

  /** Load the image list for a document. */
  async function fetchMedia(slug: string, docFilename: string): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      // Backend returns { data: MediaItem[] } — apiClient.get unwraps to MediaItem[].
      items.value = await apiClient.get<MediaItem[]>(_base(slug, docFilename));
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  /** Upload a single image file and prepend it to the list on success. */
  async function uploadMedia(
    slug: string,
    docFilename: string,
    file: File,
  ): Promise<MediaItem | null> {
    isUploading.value = true;
    error.value = null;
    try {
      const form = new FormData();
      form.append('file', file);
      const item = await apiClient.upload<MediaItem>(_base(slug, docFilename), form);
      items.value.unshift(item);
      return item;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return null;
    } finally {
      isUploading.value = false;
    }
  }

  /** Delete an image by filename and remove it from the list. */
  async function deleteMedia(
    slug: string,
    docFilename: string,
    filename: string,
  ): Promise<boolean> {
    error.value = null;
    try {
      // 204 No Content — apiClient.delete<void> handles the empty body gracefully.
      await apiClient.delete<void>(
        `${_base(slug, docFilename)}/${encodeURIComponent(filename)}`,
      );
      items.value = items.value.filter((i) => i.filename !== filename);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return false;
    }
  }

  /**
   * Fetch an image via the authenticated Axios instance and return a Blob URL.
   *
   * <img src> cannot carry the Bearer token, so raw API URLs cannot be used
   * directly as thumbnail sources.  This function fetches via the authenticated
   * client and wraps the result in an object URL that <img> can consume.
   *
   * The caller must revoke the URL with URL.revokeObjectURL() when done.
   */
  async function fetchBlobUrl(apiUrl: string): Promise<string | null> {
    try {
      const res = await api.get<Blob>(apiUrl, { responseType: 'blob' });
      return URL.createObjectURL(res.data);
    } catch {
      return null;
    }
  }

  return {
    items,
    isLoading,
    isUploading,
    error,
    fetchMedia,
    uploadMedia,
    deleteMedia,
    fetchBlobUrl,
  };
});
