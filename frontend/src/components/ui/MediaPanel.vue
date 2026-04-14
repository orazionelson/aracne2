<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMediaStore, type MediaItem } from '@/stores/mediaStore';

interface FacsimileSurface {
  id: string;
  url: string;
}

const props = defineProps<{
  slug: string;
  docFilename: string;
  /** Surfaces currently registered in the document's <facsimile> block. */
  surfaces: FacsimileSurface[];
  /** Raw <facsimile>…</facsimile> XML managed in memory; null = not present. */
  facsimileXml: string | null;
}>();

const emit = defineEmits<{
  (e: 'insertFigure', url: string): void;
  /** Adds a <surface> to <facsimile> (if needed) and inserts <pb facs="#id"/>. */
  (e: 'insertAsCard', url: string): void;
  /** Removes <surface xml:id="id"> from <facsimile> and strips facs="#id" from all <pb>. */
  (e: 'deleteSurface', surfaceId: string): void;
  /** Moves a surface one position up or down inside <facsimile>. */
  (e: 'moveSurface', surfaceId: string, direction: 'up' | 'down'): void;
  /**
   * Fired after a media file is successfully deleted from storage.
   * The parent must strip dead <graphic url="mediaUrl"> references from the
   * editor and remove the linked <surface> (if any) from <facsimile>.
   */
  (e: 'cleanupMediaRefs', mediaUrl: string): void;
  /** Open the ZoneEditor panel for the given surface. */
  (e: 'editZones', surfaceId: string): void;
  (e: 'close'): void;
}>();

type PanelTab = 'images' | 'facsimile';

const { t } = useI18n();
const store = useMediaStore();

const activeTab = ref<PanelTab>('images');

// Switch to facsimile tab automatically when the first surface is added.
watch(() => props.surfaces.length, (newLen, oldLen) => {
  if (oldLen === 0 && newLen > 0) activeTab.value = 'facsimile';
});

// Per-item blob URL cache (revoked on unmount).
const blobUrls = ref<Record<string, string>>({});
// Track which items are currently loading their blob URL.
const loadingBlobs = ref<Set<string>>(new Set());

const fileInput = ref<HTMLInputElement | null>(null);
const confirmDeleteFilename = ref<string | null>(null);
const confirmDeleteSurfaceId = ref<string | null>(null);

onMounted(async () => {
  await store.fetchMedia(props.slug, props.docFilename);
  loadVisibleThumbnails();
});

onBeforeUnmount(() => {
  for (const url of Object.values(blobUrls.value)) {
    URL.revokeObjectURL(url);
  }
});

async function loadBlobUrl(item: MediaItem): Promise<void> {
  if (blobUrls.value[item.filename] || loadingBlobs.value.has(item.filename)) return;
  loadingBlobs.value = new Set([...loadingBlobs.value, item.filename]);
  const blobUrl = await store.fetchBlobUrl(item.url);
  loadingBlobs.value = new Set([...loadingBlobs.value].filter((f) => f !== item.filename));
  if (blobUrl) {
    blobUrls.value = { ...blobUrls.value, [item.filename]: blobUrl };
  }
}

function loadVisibleThumbnails(): void {
  for (const item of store.items) {
    loadBlobUrl(item);
  }
}

async function handleUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  input.value = '';
  const item = await store.uploadMedia(props.slug, props.docFilename, file);
  if (item) {
    await loadBlobUrl(item);
  }
}

async function handleDelete(filename: string): Promise<void> {
  confirmDeleteFilename.value = null;
  // Capture the URL before the item disappears from the store.
  const item = store.items.find((i) => i.filename === filename);
  const ok = await store.deleteMedia(props.slug, props.docFilename, filename);
  if (ok) {
    if (blobUrls.value[filename]) {
      URL.revokeObjectURL(blobUrls.value[filename]);
      const updated = { ...blobUrls.value };
      delete updated[filename];
      blobUrls.value = updated;
    }
    // Ask the parent to clean up any dead XML references to this file.
    if (item) emit('cleanupMediaRefs', item.url);
  }
}

/** Return the surface registered for this image URL, or undefined. */
function surfaceFor(item: MediaItem): FacsimileSurface | undefined {
  return props.surfaces.find((s) => s.url === item.url);
}

/** Extract the bare filename from a media API URL or any path. */
function filenameFromUrl(url: string): string {
  return url.split('/').pop() ?? url;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
</script>

<template>
  <div class="flex flex-shrink-0 flex-col bg-white" style="min-width: 240px;">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <span class="text-sm font-semibold text-gray-700">{{ t('media.panel_title') }}</span>
      <button class="text-gray-400 hover:text-gray-700" @click="emit('close')">✕</button>
    </div>

    <!-- Tab bar -->
    <div class="flex flex-shrink-0 border-b border-gray-200">
      <button
        :class="[
          'flex-1 px-3 py-1.5 text-xs font-medium transition-colors',
          activeTab === 'images'
            ? 'border-b-2 border-indigo-500 text-indigo-700'
            : 'text-gray-500 hover:text-gray-700',
        ]"
        @click="activeTab = 'images'"
      >
        {{ t('media.tab_images') }}
      </button>
      <button
        :class="[
          'flex-1 px-3 py-1.5 text-xs font-medium transition-colors',
          activeTab === 'facsimile'
            ? 'border-b-2 border-teal-500 text-teal-700'
            : 'text-gray-500 hover:text-gray-700',
        ]"
        @click="activeTab = 'facsimile'"
      >
        {{ t('media.tab_facsimile') }}
        <span
          v-if="surfaces.length > 0"
          class="ml-1 rounded-full bg-teal-100 px-1.5 py-0.5 text-xs font-semibold text-teal-700"
        >{{ surfaces.length }}</span>
      </button>
    </div>

    <!-- ── Images tab ──────────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'images'">
    <!-- Upload button -->
    <div class="flex-shrink-0 border-b border-gray-100 px-3 py-2">
      <input
        ref="fileInput"
        type="file"
        accept=".jpg,.jpeg,.png,.webp,.tif,.tiff"
        class="hidden"
        @change="handleUpload"
      />
      <button
        :disabled="store.isUploading"
        class="w-full rounded border border-dashed border-gray-300 px-3 py-2 text-xs text-gray-500 hover:border-indigo-400 hover:text-indigo-600 disabled:opacity-50"
        @click="fileInput?.click()"
      >
        {{ store.isUploading ? t('media.uploading') : t('media.upload_btn') }}
      </button>
      <p v-if="store.error" class="mt-1 text-xs text-red-600">{{ store.error }}</p>
    </div>

    <!-- Image grid -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="store.isLoading" class="px-3 py-4 text-xs text-gray-400">
        {{ t('common.loading') }}
      </p>
      <p v-else-if="store.items.length === 0" class="px-3 py-4 text-xs text-gray-400">
        {{ t('media.empty') }}
      </p>
      <ul v-else class="divide-y divide-gray-100">
        <li
          v-for="item in store.items"
          :key="item.filename"
          class="flex items-center gap-2 px-3 py-2"
        >
          <!-- Thumbnail -->
          <div class="h-14 w-14 flex-shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
            <img
              v-if="blobUrls[item.filename]"
              :src="blobUrls[item.filename]"
              :alt="item.filename"
              class="h-full w-full object-cover"
            />
            <div
              v-else-if="loadingBlobs.has(item.filename)"
              class="flex h-full items-center justify-center"
            >
              <span class="text-xs text-gray-300">…</span>
            </div>
            <div v-else class="flex h-full items-center justify-center">
              <span class="text-xs text-gray-300">?</span>
            </div>
          </div>

          <!-- Info + actions -->
          <div class="min-w-0 flex-1">
            <!-- Filename + surface badge -->
            <div class="flex items-center gap-1">
              <p class="min-w-0 truncate font-mono text-xs text-gray-700" :title="item.filename">
                {{ item.filename }}
              </p>
              <span
                v-if="surfaceFor(item)"
                class="flex-shrink-0 rounded bg-teal-50 px-1 py-0.5 font-mono text-xs text-teal-700"
                :title="t('media.surface_registered')"
              >
                #{{ surfaceFor(item)!.id }}
              </span>
            </div>
            <p class="text-xs text-gray-400">{{ formatSize(item.size) }}</p>

            <!-- Action buttons -->
            <div class="mt-1 flex flex-wrap gap-1">
              <button
                class="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700 hover:bg-indigo-100"
                @click="emit('insertFigure', item.url)"
              >
                {{ t('media.insert') }}
              </button>
              <button
                class="rounded bg-teal-50 px-2 py-0.5 text-xs text-teal-700 hover:bg-teal-100"
                :title="surfaceFor(item) ? t('media.insert_pb_title', { id: surfaceFor(item)!.id }) : t('media.insert_as_card_title')"
                @click="emit('insertAsCard', item.url)"
              >
                {{ surfaceFor(item) ? t('media.insert_pb') : t('media.insert_as_card') }}
              </button>
              <button
                v-if="confirmDeleteFilename !== item.filename"
                class="rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-500 hover:bg-red-50 hover:text-red-600"
                @click="confirmDeleteFilename = item.filename"
              >
                {{ t('common.delete') }}
              </button>
              <!-- Inline delete confirmation -->
              <template v-else>
                <button
                  class="rounded bg-red-50 px-2 py-0.5 text-xs text-red-700 hover:bg-red-100"
                  @click="handleDelete(item.filename)"
                >
                  {{ t('media.confirm_delete') }}
                </button>
                <button
                  class="rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100"
                  @click="confirmDeleteFilename = null"
                >
                  {{ t('common.cancel') }}
                </button>
              </template>
            </div>
          </div>
        </li>
      </ul>
    </div>
    </template><!-- end images tab -->

    <!-- ── Facsimile tab ───────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'facsimile'">
      <div class="min-h-0 flex-1 overflow-y-auto">
        <!-- Empty state -->
        <div v-if="surfaces.length === 0" class="px-3 py-6 text-center">
          <p class="text-xs text-gray-400">{{ t('media.facsimile_empty') }}</p>
          <p class="mt-1 text-xs text-gray-300">{{ t('media.facsimile_empty_hint') }}</p>
        </div>

        <!-- Surface list -->
        <template v-else>
          <p class="px-3 py-2 text-xs text-gray-400">
            {{ t('media.facsimile_hint') }}
          </p>
          <ul class="divide-y divide-gray-100">
            <li
              v-for="(surface, idx) in surfaces"
              :key="surface.id"
              class="flex items-center gap-3 px-3 py-2"
            >
              <!-- Up/Down reorder controls -->
              <div class="flex flex-shrink-0 flex-col gap-0.5">
                <button
                  :disabled="idx === 0"
                  class="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-25"
                  :title="t('media.surface_move_up')"
                  @click="emit('moveSurface', surface.id, 'up')"
                >▲</button>
                <button
                  :disabled="idx === surfaces.length - 1"
                  class="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-25"
                  :title="t('media.surface_move_down')"
                  @click="emit('moveSurface', surface.id, 'down')"
                >▼</button>
              </div>

              <!-- Thumbnail -->
              <div class="h-12 w-12 flex-shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
                <img
                  v-if="blobUrls[filenameFromUrl(surface.url)]"
                  :src="blobUrls[filenameFromUrl(surface.url)]"
                  alt=""
                  class="h-full w-full object-cover"
                />
                <div v-else class="flex h-full items-center justify-center">
                  <span class="text-xs text-gray-300">?</span>
                </div>
              </div>
              <!-- Info -->
              <div class="min-w-0 flex-1">
                <p class="font-mono text-xs font-semibold text-teal-700">xml:id="{{ surface.id }}"</p>
                <p class="mt-0.5 truncate font-mono text-xs text-gray-400" :title="surface.url">
                  {{ filenameFromUrl(surface.url) }}
                </p>
                <div class="mt-1 flex flex-wrap gap-1">
                  <button
                    class="rounded bg-teal-50 px-2 py-0.5 text-xs text-teal-700 hover:bg-teal-100"
                    :title="t('media.insert_pb_title', { id: surface.id })"
                    @click="emit('insertAsCard', surface.url)"
                  >
                    {{ t('media.insert_pb') }} facs="#{{ surface.id }}"
                  </button>
                  <button
                    class="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700 hover:bg-indigo-100"
                    @click="emit('editZones', surface.id)"
                  >
                    {{ t('zones.edit_btn') }}
                  </button>
                  <!-- Delete surface with inline confirmation -->
                  <template v-if="confirmDeleteSurfaceId !== surface.id">
                    <button
                      class="rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-500 hover:bg-red-50 hover:text-red-600"
                      :title="t('media.surface_delete_confirm', { id: surface.id })"
                      @click="confirmDeleteSurfaceId = surface.id"
                    >
                      {{ t('media.surface_delete') }}
                    </button>
                  </template>
                  <template v-else>
                    <button
                      class="rounded bg-red-50 px-2 py-0.5 text-xs text-red-700 hover:bg-red-100"
                      @click="emit('deleteSurface', surface.id); confirmDeleteSurfaceId = null"
                    >
                      {{ t('media.surface_delete_confirm_btn') }}
                    </button>
                    <button
                      class="rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100"
                      @click="confirmDeleteSurfaceId = null"
                    >
                      {{ t('common.cancel') }}
                    </button>
                  </template>
                </div>
              </div>
            </li>
          </ul>

          <!-- Raw XML preview -->
          <details class="border-t border-gray-100">
            <summary class="cursor-pointer px-3 py-2 text-xs text-gray-400 hover:text-gray-600">
              {{ t('media.facsimile_xml_preview') }}
            </summary>
            <pre class="overflow-x-auto whitespace-pre-wrap break-all px-3 py-2 font-mono text-xs text-gray-500">{{ facsimileXml }}</pre>
          </details>
        </template>
      </div>
    </template><!-- end facsimile tab -->
  </div>
</template>
