/**
 * zonesStore — manages <zone> elements for a single <surface> of a TEI document.
 *
 * State is surface-scoped: call fetchZones(slug, docFilename, surfaceId) when the
 * ZoneEditor opens for a specific surface, and reset() when it closes.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient } from '@/services/api'

export interface ZoneOut {
  xml_id: string
  ulx: number
  uly: number
  lrx: number
  lry: number
}

export interface ZoneIn {
  xml_id: string
  ulx: number
  uly: number
  lrx: number
  lry: number
}

interface SurfaceZonesResponse {
  surface_id: string
  zones: ZoneOut[]
}

export const useZonesStore = defineStore('zones', () => {
  const zones = ref<ZoneOut[]>([])
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<string | null>(null)
  const currentSurfaceId = ref<string | null>(null)

  function _base(slug: string, docFilename: string, surfaceId: string): string {
    return `/collections/${slug}/documents/${encodeURIComponent(docFilename)}/facsimile/${encodeURIComponent(surfaceId)}/zones`
  }

  async function fetchZones(slug: string, docFilename: string, surfaceId: string): Promise<void> {
    isLoading.value = true
    error.value = null
    currentSurfaceId.value = surfaceId
    try {
      const response = await apiClient.get<SurfaceZonesResponse>(_base(slug, docFilename, surfaceId))
      zones.value = response.zones
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      isLoading.value = false
    }
  }

  async function saveZones(
    slug: string,
    docFilename: string,
    surfaceId: string,
    newZones: ZoneIn[],
  ): Promise<boolean> {
    isSaving.value = true
    error.value = null
    try {
      const response = await apiClient.put<SurfaceZonesResponse>(_base(slug, docFilename, surfaceId), {
        zones: newZones,
      })
      zones.value = response.zones
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return false
    } finally {
      isSaving.value = false
    }
  }

  function reset(): void {
    zones.value = []
    currentSurfaceId.value = null
    error.value = null
  }

  return { zones, isLoading, isSaving, error, currentSurfaceId, fetchZones, saveZones, reset }
})
