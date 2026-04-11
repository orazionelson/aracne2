<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
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
}>();

const emit = defineEmits<{
  (e: 'insertFigure', url: string): void;
  /** Adds a <surface> to <facsimile> (if needed) and inserts <pb facs="#id"/>. */
  (e: 'insertAsCard', url: string): void;
  (e: 'close'): void;
}>();

const { t } = useI18n();
const store = useMediaStore();

// Per-item blob URL cache (revoked on unmount).
const blobUrls = ref<Record<string, string>>({});
// Track which items are currently loading their blob URL.
const loadingBlobs = ref<Set<string>>(new Set());

const fileInput = ref<HTMLInputElement | null>(null);
const confirmDeleteFilename = ref<string | null>(null);

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
  const ok = await store.deleteMedia(props.slug, props.docFilename, filename);
  if (ok && blobUrls.value[filename]) {
    URL.revokeObjectURL(blobUrls.value[filename]);
    const updated = { ...blobUrls.value };
    delete updated[filename];
    blobUrls.value = updated;
  }
}

/** Return the surface registered for this image URL, or undefined. */
function surfaceFor(item: MediaItem): FacsimileSurface | undefined {
  return props.surfaces.find((s) => s.url === item.url);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
</script>

<template>
  <div class="flex w-80 flex-shrink-0 flex-col border-l border-gray-200 bg-white">
    <!-- Header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <span class="text-sm font-semibold text-gray-700">{{ t('media.panel_title') }}</span>
      <button class="text-gray-400 hover:text-gray-700" @click="emit('close')">✕</button>
    </div>

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
  </div>
</template>
