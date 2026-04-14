<script setup lang="ts">
/**
 * ZoneEditor — right-side panel for drawing and managing TEI <zone> elements
 * on a manuscript surface image.
 *
 * The panel displays the surface image with an SVG overlay.  The user draws
 * rectangles by clicking and dragging, selects them by clicking, and associates
 * a selected zone with the nearest opening tag in the CodeMirror editor by
 * clicking the Associate button (which emits 'associateZone' — the parent
 * calls singleCm.insertFacsRef(zoneId)).
 *
 * Coordinates stored in zones are pixel values relative to the original
 * (full-resolution) image.  The SVG overlay converts them for display using
 * the scale factor: scale = naturalWidth / clientWidth.
 */

import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useZonesStore, type ZoneIn } from '@/stores/zonesStore'
import { useMediaStore } from '@/stores/mediaStore'

// ── Flash state ───────────────────────────────────────────────────────────────
// Transient visual feedback after an "associate" attempt.
type AssociateFlash = 'ok' | 'fail' | null

// ── Types ──────────────────────────────────────────────────────────────────────

interface Surface {
  id: string   // xml:id of the <surface> element
  url: string  // url attribute of the nested <graphic> element
}

interface DrawPoint {
  x: number
  y: number
}

// ── Props / emits ─────────────────────────────────────────────────────────────

const props = defineProps<{
  slug: string
  docFilename: string
  surface: Surface
  /** Called when the user clicks "Associate"; must return true on success. */
  onAssociate: (zoneId: string) => boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  /** Emitted after zones are successfully persisted to eXist-db. */
  (e: 'zonesSaved'): void
}>()

// ── Composables ───────────────────────────────────────────────────────────────

const { t } = useI18n()
const store = useZonesStore()
const mediaStore = useMediaStore()

// ── Refs ──────────────────────────────────────────────────────────────────────

const imgEl = ref<HTMLImageElement | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
const blobUrl = ref<string | null>(null)

// Working copy of zones (editable before saving; store is the committed state)
const localZones = ref<ZoneIn[]>([])
const selectedZoneId = ref<string | null>(null)

// Scale factor: original image pixels / displayed pixels
const scale = ref(1)

// Drawing state
const isDrawing = ref(false)
const drawStart = ref<DrawPoint | null>(null)
const drawCurrent = ref<DrawPoint | null>(null)

// Associate feedback flash (clears after 2 s)
const associateFlash = ref<AssociateFlash>(null)
let _flashTimer: ReturnType<typeof setTimeout> | null = null

// ── Computed ──────────────────────────────────────────────────────────────────

/** In-progress rectangle in SVG (display) coordinates. */
const inProgressRect = computed(() => {
  if (!isDrawing.value || !drawStart.value || !drawCurrent.value) return null
  return {
    x: Math.min(drawStart.value.x, drawCurrent.value.x),
    y: Math.min(drawStart.value.y, drawCurrent.value.y),
    w: Math.abs(drawCurrent.value.x - drawStart.value.x),
    h: Math.abs(drawCurrent.value.y - drawStart.value.y),
  }
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function imageToDisplay(px: number): number {
  return px / scale.value
}

function displayToImage(px: number): number {
  return Math.round(px * scale.value)
}

/** Generate the next sequential zone xml:id for this surface. */
function nextZoneId(): string {
  const sid = props.surface.id
  const existing = localZones.value
    .map((z) => {
      const m = new RegExp(`^z_${sid}_([0-9]+)$`).exec(z.xml_id)
      return m ? parseInt(m[1], 10) : 0
    })
    .filter((n) => n > 0)
  const max = existing.length > 0 ? Math.max(...existing) : 0
  return `z_${sid}_${max + 1}`
}

/** Extract the bare filename from a media url like "media/carta_1r.jpg". */
function mediaFilenameFromUrl(url: string): string {
  return url.split('/').pop() ?? url
}

// ── Event handlers ────────────────────────────────────────────────────────────

function onImageLoad(): void {
  const img = imgEl.value
  if (!img || img.clientWidth === 0) return
  scale.value = img.naturalWidth / img.clientWidth
}

function getSvgPoint(event: MouseEvent): DrawPoint {
  const rect = svgEl.value!.getBoundingClientRect()
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  }
}

function onMousedown(event: MouseEvent): void {
  if (!svgEl.value) return
  drawStart.value = getSvgPoint(event)
  drawCurrent.value = { ...drawStart.value }
  isDrawing.value = true
}

function onMousemove(event: MouseEvent): void {
  if (!isDrawing.value || !svgEl.value) return
  drawCurrent.value = getSvgPoint(event)
}

function onMouseup(): void {
  if (!isDrawing.value || !drawStart.value || !drawCurrent.value) return
  isDrawing.value = false

  // Normalise coordinates so upper-left < lower-right.
  const ulx = displayToImage(Math.min(drawStart.value.x, drawCurrent.value.x))
  const uly = displayToImage(Math.min(drawStart.value.y, drawCurrent.value.y))
  const lrx = displayToImage(Math.max(drawStart.value.x, drawCurrent.value.x))
  const lry = displayToImage(Math.max(drawStart.value.y, drawCurrent.value.y))

  drawStart.value = null
  drawCurrent.value = null

  // Discard accidental single-click (< 5 display pixels in either dimension).
  if (lrx - ulx < 5 || lry - uly < 5) return

  const zone: ZoneIn = { xml_id: nextZoneId(), ulx, uly, lrx, lry }
  localZones.value = [...localZones.value, zone]
  selectedZoneId.value = zone.xml_id
}

function selectZone(zoneId: string): void {
  selectedZoneId.value = zoneId
}

function deleteZone(zoneId: string): void {
  localZones.value = localZones.value.filter((z) => z.xml_id !== zoneId)
  if (selectedZoneId.value === zoneId) selectedZoneId.value = null
}

function handleAssociate(): void {
  if (!selectedZoneId.value) return
  const ok = props.onAssociate(selectedZoneId.value)
  if (_flashTimer) clearTimeout(_flashTimer)
  associateFlash.value = ok ? 'ok' : 'fail'
  _flashTimer = setTimeout(() => { associateFlash.value = null }, 2000)
}

async function handleSave(): Promise<void> {
  const ok = await store.saveZones(props.slug, props.docFilename, props.surface.id, localZones.value)
  if (ok) emit('zonesSaved')
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  // Load zones from the API and populate the local working copy.
  await store.fetchZones(props.slug, props.docFilename, props.surface.id)
  localZones.value = store.zones.map((z) => ({ ...z }))

  // Load the surface image as an authenticated blob URL.
  const imageFilename = mediaFilenameFromUrl(props.surface.url)
  const apiUrl = `/api/v1/collections/${props.slug}/documents/${encodeURIComponent(props.docFilename)}/media/${encodeURIComponent(imageFilename)}`
  blobUrl.value = await mediaStore.fetchBlobUrl(apiUrl)
})

onBeforeUnmount(() => {
  if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
  if (_flashTimer) clearTimeout(_flashTimer)
  store.reset()
})
</script>

<template>
  <div class="flex flex-shrink-0 flex-col overflow-hidden bg-white border-l border-gray-200">

    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <span class="text-sm font-semibold text-gray-700">{{ t('zones.panel_title') }}</span>
      <button
        class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        :title="t('common.close')"
        @click="emit('close')"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Surface id badge -->
    <div class="flex-shrink-0 border-b border-gray-100 bg-gray-50 px-3 py-1.5">
      <span class="font-mono text-xs text-gray-500">#{{ surface.id }}</span>
    </div>

    <!-- Image + SVG overlay -->
    <div
      class="relative flex-shrink-0 select-none overflow-hidden bg-gray-100"
      style="cursor: crosshair"
    >
      <img
        ref="imgEl"
        :src="blobUrl ?? ''"
        class="block w-full"
        draggable="false"
        :alt="surface.id"
        @load="onImageLoad"
      />
      <svg
        v-if="blobUrl"
        ref="svgEl"
        class="absolute inset-0 h-full w-full"
        @mousedown.prevent="onMousedown"
        @mousemove="onMousemove"
        @mouseup="onMouseup"
      >
        <!-- Existing zones -->
        <template v-for="z in localZones" :key="z.xml_id">
          <rect
            :x="imageToDisplay(z.ulx)"
            :y="imageToDisplay(z.uly)"
            :width="imageToDisplay(z.lrx - z.ulx)"
            :height="imageToDisplay(z.lry - z.uly)"
            :fill="selectedZoneId === z.xml_id ? 'rgba(99,102,241,0.20)' : 'rgba(99,102,241,0.10)'"
            :stroke="selectedZoneId === z.xml_id ? '#4338ca' : '#6366f1'"
            stroke-width="1.5"
            style="cursor: pointer"
            @click.stop="selectZone(z.xml_id)"
          />
          <text
            :x="imageToDisplay(z.ulx) + 2"
            :y="imageToDisplay(z.uly) + 10"
            font-size="8"
            fill="#4338ca"
            pointer-events="none"
          >{{ z.xml_id }}</text>
        </template>

        <!-- In-progress rectangle while drawing -->
        <rect
          v-if="inProgressRect"
          :x="inProgressRect.x"
          :y="inProgressRect.y"
          :width="inProgressRect.w"
          :height="inProgressRect.h"
          fill="rgba(20,184,166,0.10)"
          stroke="#0d9488"
          stroke-width="1"
          stroke-dasharray="4 2"
          pointer-events="none"
        />
      </svg>

      <!-- Loading indicator shown before blob URL is ready -->
      <div v-if="!blobUrl" class="flex h-24 items-center justify-center text-xs text-gray-400">
        {{ t('common.loading') }}
      </div>
    </div>

    <!-- Zone list -->
    <div class="min-h-0 flex-1 divide-y divide-gray-100 overflow-y-auto">
      <div v-if="store.isLoading" class="px-3 py-4 text-center text-xs text-gray-400">
        {{ t('common.loading') }}
      </div>

      <div v-else-if="localZones.length === 0" class="px-3 py-4 text-center text-xs text-gray-400">
        {{ t('zones.empty_hint') }}
      </div>

      <div
        v-else
        v-for="z in localZones"
        :key="z.xml_id"
        class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs"
        :class="selectedZoneId === z.xml_id ? 'bg-indigo-50' : 'hover:bg-gray-50'"
        @click="selectZone(z.xml_id)"
      >
        <span class="flex-1 font-mono text-indigo-700">{{ z.xml_id }}</span>
        <span class="font-mono text-gray-400">{{ z.ulx }},{{ z.uly }}</span>
        <button
          class="rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
          @click.stop="deleteZone(z.xml_id)"
        >
          <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Footer actions -->
    <div class="flex flex-shrink-0 gap-1.5 border-t border-gray-200 px-3 py-2">
      <button
        :class="[
          'flex-1 rounded px-2 py-1.5 text-xs font-medium transition-colors duration-150',
          associateFlash === 'ok'   ? 'bg-green-100 text-green-700' :
          associateFlash === 'fail' ? 'bg-red-100   text-red-700'   :
          'bg-teal-50 text-teal-700 hover:bg-teal-100',
          !selectedZoneId ? 'cursor-not-allowed opacity-40' : '',
        ]"
        :disabled="!selectedZoneId"
        :title="t('zones.associate_hint')"
        @click="handleAssociate"
      >
        <template v-if="associateFlash === 'ok'">{{ t('zones.associate_ok') }}</template>
        <template v-else-if="associateFlash === 'fail'">{{ t('zones.associate_fail') }}</template>
        <template v-else>{{ t('zones.associate_btn') }}</template>
      </button>
      <button
        class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="store.isSaving"
        @click="handleSave"
      >
        {{ store.isSaving ? t('common.saving') : t('common.save') }}
      </button>
    </div>

    <!-- Error display -->
    <p v-if="store.error" class="flex-shrink-0 px-3 pb-2 text-xs text-red-600">
      {{ store.error }}
    </p>
  </div>
</template>
