<script setup lang="ts">
/**
 * Per-website media picker.
 *
 * Two modes:
 *
 * - ``mode="inline"`` renders the library grid directly into the
 *   page. Used by the "Media" tab of the website editor.
 * - ``mode="modal"`` renders the same grid inside a Teleported
 *   overlay. Triggered by the picker buttons scattered around the
 *   app (logo URL field, WYSIWYG toolbar, etc.). Clicking a file
 *   emits ``@selected`` with the ``media://`` pseudo-URL the caller
 *   pastes into whatever field triggered the pick.
 *
 * Storage lives in ``useWebsiteMediaStore`` so multiple pickers on
 * the same page share a single in-memory list.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useWebsiteMediaStore,
  type WebsiteMediaFile,
} from "@/stores/website_media";

const props = withDefaults(
  defineProps<{
    slug: string;
    /** ``"inline"`` (always-on grid) or ``"modal"`` (dialog, closable). */
    mode?: "inline" | "modal";
    /** Only relevant in modal mode — v-model:open. */
    open?: boolean;
  }>(),
  { mode: "inline", open: false },
);

const emit = defineEmits<{
  (e: "selected", ref: string): void;
  (e: "update:open", value: boolean): void;
}>();

const { t } = useI18n();
const store = useWebsiteMediaStore();

const uploadError = ref<string | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const justCopiedFilename = ref<string | null>(null);

const files = computed(() => store.getFiles(props.slug));
const isEmpty = computed(() => !store.isLoading && files.value.length === 0);

// Keep in sync with the backend's ``_ALLOWED_EXT``.
const ACCEPT = ".jpg,.jpeg,.png,.gif,.webp,.avif,.svg";

onMounted(async () => {
  try {
    await store.fetchFiles(props.slug);
  } catch {
    // Non-fatal: the grid renders with an Upload CTA when empty.
  }
});

function triggerUpload(): void {
  fileInputRef.value?.click();
}

async function onFileChosen(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";  // allow re-upload of the same filename
  if (!file) return;
  uploadError.value = null;
  try {
    await store.uploadFile(props.slug, file);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    uploadError.value = msg ?? t("common.error");
  }
}

async function handleDelete(file: WebsiteMediaFile): Promise<void> {
  if (!window.confirm(t("website_media.confirm_delete", { filename: file.filename }))) {
    return;
  }
  try {
    await store.deleteFile(props.slug, file.filename);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    uploadError.value = msg ?? t("common.error");
  }
}

function handlePick(file: WebsiteMediaFile): void {
  if (props.mode === "modal") {
    emit("selected", file.ref);
    close();
    return;
  }
  // Inline mode — copy the ``media://`` ref to the clipboard so the
  // Designer can paste it into a textarea without picker button.
  navigator.clipboard.writeText(file.ref).catch(() => undefined);
  justCopiedFilename.value = file.filename;
  setTimeout(() => {
    if (justCopiedFilename.value === file.filename) justCopiedFilename.value = null;
  }, 1500);
}

function close(): void {
  if (props.mode === "modal") emit("update:open", false);
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Public preview URL. Resolves via the backend — works on published
 * sites and, via staff ACL, on drafts. */
function previewUrl(filename: string): string {
  return `/api/v1/websites/${props.slug}/media/${encodeURIComponent(filename)}`;
}

const renderModal = computed(() => props.mode === "modal");
</script>

<template>
  <!-- Modal chrome (Teleport'd to body) ─────────────────────────── -->
  <Teleport v-if="renderModal" to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="close"
    >
      <div class="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-xl dark:bg-gray-900">
        <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3 dark:border-gray-700">
          <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
            {{ t("website_media.picker_title") }}
          </h2>
          <button
            class="rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800"
            @click="close"
          >
            {{ t("common.close") }}
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-5 py-4">
          <!-- Body A: upload + grid -->
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              :disabled="store.isUploading"
              @click="triggerUpload"
            >
              {{ store.isUploading ? t("website_media.uploading") : t("website_media.upload") }}
            </button>
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ t("website_media.upload_hint") }}</span>
          </div>
          <p v-if="uploadError" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ uploadError }}</p>
          <p v-if="store.isLoading" class="text-sm text-gray-400 dark:text-gray-500">{{ t("common.loading") }}</p>
          <p v-else-if="isEmpty" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">{{ t("website_media.empty") }}</p>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            <div
              v-for="file in files"
              :key="file.filename"
              class="group relative overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800"
            >
              <button type="button" class="block w-full" @click="handlePick(file)">
                <div class="flex h-28 items-center justify-center bg-gray-50 dark:bg-gray-900">
                  <img :src="previewUrl(file.filename)" :alt="file.filename" class="max-h-28 max-w-full object-contain" loading="lazy" />
                </div>
                <div class="px-2 py-1.5 text-left">
                  <p class="truncate font-mono text-xs text-gray-700 dark:text-gray-200" :title="file.filename">{{ file.filename }}</p>
                  <p class="text-[10px] text-gray-400 dark:text-gray-500">{{ humanSize(file.size_bytes) }}</p>
                </div>
              </button>
              <div class="absolute right-1 top-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  type="button"
                  class="rounded bg-white/90 px-1.5 py-0.5 text-[10px] text-red-600 shadow hover:bg-red-50 dark:bg-gray-800/80 dark:text-red-300 dark:hover:bg-red-900/40"
                  :title="t('common.delete')"
                  @click.stop="handleDelete(file)"
                >✕</button>
              </div>
            </div>
          </div>
          <input
            ref="fileInputRef"
            type="file"
            :accept="ACCEPT"
            class="hidden"
            @change="onFileChosen"
          />
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Inline chrome — same body as the modal, no dialog wrapper -->
  <div v-if="!renderModal">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        :disabled="store.isUploading"
        @click="triggerUpload"
      >
        {{ store.isUploading ? t("website_media.uploading") : t("website_media.upload") }}
      </button>
      <span class="text-xs text-gray-500 dark:text-gray-400">{{ t("website_media.upload_hint") }}</span>
    </div>
    <p v-if="uploadError" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ uploadError }}</p>
    <p v-if="store.isLoading" class="text-sm text-gray-400 dark:text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="isEmpty" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">{{ t("website_media.empty") }}</p>
    <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      <div
        v-for="file in files"
        :key="file.filename"
        class="group relative overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800"
      >
        <button type="button" class="block w-full" :title="t('website_media.copy_tooltip')" @click="handlePick(file)">
          <div class="flex h-28 items-center justify-center bg-gray-50 dark:bg-gray-900">
            <img :src="previewUrl(file.filename)" :alt="file.filename" class="max-h-28 max-w-full object-contain" loading="lazy" />
          </div>
          <div class="px-2 py-1.5 text-left">
            <p class="truncate font-mono text-xs text-gray-700 dark:text-gray-200" :title="file.filename">{{ file.filename }}</p>
            <p class="text-[10px] text-gray-400 dark:text-gray-500">{{ humanSize(file.size_bytes) }}</p>
          </div>
        </button>
        <div class="absolute right-1 top-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            class="rounded bg-white/90 px-1.5 py-0.5 text-[10px] text-red-600 shadow hover:bg-red-50 dark:bg-gray-800/80 dark:text-red-300 dark:hover:bg-red-900/40"
            :title="t('common.delete')"
            @click.stop="handleDelete(file)"
          >✕</button>
        </div>
        <div
          v-if="justCopiedFilename === file.filename"
          class="pointer-events-none absolute inset-x-0 bottom-0 bg-green-600/90 px-2 py-1 text-center text-[11px] text-white"
        >
          {{ t("website_media.ref_copied") }}
        </div>
      </div>
    </div>
    <input
      ref="fileInputRef"
      type="file"
      :accept="ACCEPT"
      class="hidden"
      @change="onFileChosen"
    />
  </div>
</template>
