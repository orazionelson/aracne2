/**
 * documentVersions store — editor surface for the document_versions REST API.
 *
 * The store is per-document: the History panel calls ``loadList(slug, filename)``
 * when it opens for a specific document and ``reset()`` when it closes. The
 * ``manualSave`` / ``rollback`` / ``deleteVersion`` actions refresh the list
 * automatically after a successful write.
 *
 * Errors are surfaced via the ``error`` ref and through the action's boolean
 * return value so the caller can pick its own UX (toast, banner, modal).
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient } from '@/services/api'
import { i18n } from '@/main'

export type VersionOrigin =
  | 'creation'
  | 'manual'
  | 'submission'
  | 'rejection'
  | 'publication'
  | 'rollback'

export interface DocumentVersion {
  id: string
  collection_id: string
  document_filename: string
  version_number: number
  content_sha256: string
  size_bytes: number
  origin: VersionOrigin
  message: string | null
  created_at: string
  created_by_id: string | null
  audit_log_id: number | null
}

export interface DocumentVersionDiff {
  from_version: number
  to_version: number
  diff: string
}

interface ApiErrorPayload {
  response?: { data?: { error?: { code?: string; message?: string } } }
  message?: string
}

function _extractError(err: unknown): string {
  const e = err as ApiErrorPayload
  return (
    e?.response?.data?.error?.message ??
    e?.message ??
    i18n.global.t('version.errors.generic')
  )
}

function _base(slug: string, filename: string): string {
  const fn = encodeURIComponent(filename)
  return `/collections/${slug}/documents/${fn}/versions`
}

export const useDocumentVersionsStore = defineStore('documentVersions', () => {
  const versions = ref<DocumentVersion[]>([])
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<string | null>(null)
  const currentSlug = ref<string | null>(null)
  const currentFilename = ref<string | null>(null)

  async function loadList(
    slug: string,
    filename: string,
    origin?: VersionOrigin,
  ): Promise<void> {
    currentSlug.value = slug
    currentFilename.value = filename
    isLoading.value = true
    error.value = null
    try {
      const url = origin
        ? `${_base(slug, filename)}?origin=${origin}`
        : _base(slug, filename)
      versions.value = await apiClient.get<DocumentVersion[]>(url)
    } catch (err) {
      error.value = _extractError(err)
      versions.value = []
    } finally {
      isLoading.value = false
    }
  }

  async function getContent(
    slug: string,
    filename: string,
    versionNumber: number,
  ): Promise<string | null> {
    error.value = null
    try {
      // The backend returns ``application/xml`` raw bytes — we want the
      // string body, not the unwrapped data envelope, so call axios directly.
      const { default: api } = await import('@/services/api')
      const res = await api.get<string>(
        `${_base(slug, filename)}/${versionNumber}/content`,
        { responseType: 'text', transformResponse: [(d) => d as string] },
      )
      return res.data
    } catch (err) {
      error.value = _extractError(err)
      return null
    }
  }

  async function manualSave(
    slug: string,
    filename: string,
    message: string,
  ): Promise<DocumentVersion | null> {
    isSaving.value = true
    error.value = null
    try {
      const created = await apiClient.post<DocumentVersion>(
        _base(slug, filename),
        { message },
      )
      // Refresh the list so the new row shows immediately.
      await loadList(slug, filename)
      return created
    } catch (err) {
      error.value = _extractError(err)
      return null
    } finally {
      isSaving.value = false
    }
  }

  async function rollback(
    slug: string,
    filename: string,
    versionNumber: number,
    note?: string,
  ): Promise<DocumentVersion | null> {
    isSaving.value = true
    error.value = null
    try {
      const created = await apiClient.post<DocumentVersion>(
        `${_base(slug, filename)}/${versionNumber}/rollback`,
        { note: note ?? null },
      )
      await loadList(slug, filename)
      return created
    } catch (err) {
      error.value = _extractError(err)
      return null
    } finally {
      isSaving.value = false
    }
  }

  async function deleteVersion(
    slug: string,
    filename: string,
    versionNumber: number,
  ): Promise<boolean> {
    isSaving.value = true
    error.value = null
    try {
      await apiClient.delete<unknown>(
        `${_base(slug, filename)}/${versionNumber}`,
      )
      await loadList(slug, filename)
      return true
    } catch (err) {
      error.value = _extractError(err)
      return false
    } finally {
      isSaving.value = false
    }
  }

  async function getDiff(
    slug: string,
    filename: string,
    versionNumber: number,
    againstVersion: number,
  ): Promise<DocumentVersionDiff | null> {
    error.value = null
    try {
      return await apiClient.get<DocumentVersionDiff>(
        `${_base(slug, filename)}/${versionNumber}/diff?against=${againstVersion}`,
      )
    } catch (err) {
      error.value = _extractError(err)
      return null
    }
  }

  function reset(): void {
    versions.value = []
    currentSlug.value = null
    currentFilename.value = null
    error.value = null
  }

  return {
    versions,
    isLoading,
    isSaving,
    error,
    currentSlug,
    currentFilename,
    loadList,
    getContent,
    manualSave,
    rollback,
    deleteVersion,
    getDiff,
    reset,
  }
})
