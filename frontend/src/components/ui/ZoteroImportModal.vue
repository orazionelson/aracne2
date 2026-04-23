<script setup lang="ts">
/**
 * Zotero import flow — modal for collection detail.
 *
 * Two phases:
 *   1. Preview — POST .../preview to fetch the library diff (new vs
 *      already-imported). Editor ticks which new items to import.
 *   2. Commit — POST .../import with the selected keys; modal closes
 *      with the count reported to the parent via an emit.
 */

import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  useZoteroImportStore,
  type ImportPreview,
  type ZoteroItemPreview,
} from '@/stores/zotero_import';

const props = defineProps<{ slug: string }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'imported', payload: { imported: number; version: number }): void;
}>();

const { t } = useI18n();
const store = useZoteroImportStore();

const loading = ref(false);
const importing = ref(false);
const error = ref<string | null>(null);
const preview = ref<ImportPreview | null>(null);
const selectedKeys = ref<Set<string>>(new Set());

const allNewSelected = computed(() => {
  const total = preview.value?.new.length ?? 0;
  return total > 0 && selectedKeys.value.size === total;
});

const canImport = computed(
  () => !importing.value && !loading.value && selectedKeys.value.size > 0,
);

function toggleAll(): void {
  if (!preview.value) return;
  if (allNewSelected.value) {
    selectedKeys.value = new Set();
  } else {
    selectedKeys.value = new Set(preview.value.new.map((i) => i.key));
  }
}

function toggle(item: ZoteroItemPreview): void {
  const next = new Set(selectedKeys.value);
  if (next.has(item.key)) next.delete(item.key);
  else next.add(item.key);
  selectedKeys.value = next;
}

async function doPreview(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const result = await store.previewImport(props.slug);
    preview.value = result;
    // Default: pre-select every new item. Editor ticks off any they
    // want to exclude — the common case is "import everything new".
    selectedKeys.value = new Set(result.new.map((i) => i.key));
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    error.value = msg ?? t('common.error');
  } finally {
    loading.value = false;
  }
}

async function doImport(): Promise<void> {
  if (!preview.value) return;
  importing.value = true;
  error.value = null;
  try {
    const body =
      selectedKeys.value.size === preview.value.new.length
        ? { all_new: true }
        : { keys: Array.from(selectedKeys.value) };
    const result = await store.importItems(props.slug, body);
    emit('imported', {
      imported: result.imported,
      version: result.bibliography_version,
    });
    emit('close');
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    error.value = msg ?? t('common.error');
  } finally {
    importing.value = false;
  }
}

// Fetch automatically on mount.
doPreview();
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    @click.self="emit('close')"
  >
    <div class="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl dark:bg-gray-800">
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3 dark:border-gray-700">
        <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">
          {{ t('zotero_import.modal_title') }}
        </h2>
        <button
          class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          @click="emit('close')"
        >✕</button>
      </div>

      <!-- Body -->
      <div class="flex-1 overflow-y-auto px-5 py-4">
        <p v-if="error" class="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700 dark:bg-red-900/20 dark:text-red-300">
          {{ error }}
        </p>

        <p v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">
          {{ t('zotero_import.loading_preview') }}
        </p>

        <template v-else-if="preview">
          <!-- Summary row -->
          <div class="mb-3 flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
            <span>{{ t('zotero_import.total_fetched', { n: preview.total_fetched }) }}</span>
            <span class="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">
              {{ t('zotero_import.count_new', { n: preview.new.length }) }}
            </span>
            <span class="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {{ t('zotero_import.count_already', { n: preview.already_imported.length }) }}
            </span>
          </div>

          <!-- New items (selectable) -->
          <div v-if="preview.new.length > 0" class="mb-4">
            <div class="mb-2 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-200">
                {{ t('zotero_import.section_new') }}
              </h3>
              <button
                class="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                @click="toggleAll"
              >
                {{ allNewSelected ? t('zotero_import.deselect_all') : t('zotero_import.select_all') }}
              </button>
            </div>
            <ul class="divide-y divide-gray-100 rounded border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
              <li
                v-for="item in preview.new"
                :key="item.key"
                class="flex items-start gap-3 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700/60"
              >
                <input
                  type="checkbox"
                  :checked="selectedKeys.has(item.key)"
                  class="mt-1 h-4 w-4"
                  @change="toggle(item)"
                />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">
                    {{ item.title }}
                  </p>
                  <p v-if="item.creators.length" class="mt-0.5 truncate text-xs text-gray-600 dark:text-gray-400">
                    {{ item.creators.join(', ') }}
                  </p>
                  <p class="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
                    {{ item.item_type }}
                    <span v-if="item.year"> · {{ item.year }}</span>
                    <span v-if="item.doi"> · {{ item.doi }}</span>
                    <span class="ml-1 font-mono">[{{ item.key }}]</span>
                  </p>
                </div>
              </li>
            </ul>
          </div>
          <p v-else class="mb-4 text-sm text-gray-500 dark:text-gray-400">
            {{ t('zotero_import.no_new') }}
          </p>

          <!-- Already-imported (informational only) -->
          <details v-if="preview.already_imported.length > 0" class="rounded border border-gray-200 dark:border-gray-700">
            <summary class="cursor-pointer px-3 py-2 text-xs text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800/60">
              {{ t('zotero_import.show_already_imported', { n: preview.already_imported.length }) }}
            </summary>
            <ul class="max-h-48 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700">
              <li
                v-for="item in preview.already_imported"
                :key="item.key"
                class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400"
              >
                <span class="truncate font-medium">{{ item.title }}</span>
                <span v-if="item.year" class="ml-2">{{ item.year }}</span>
                <span class="ml-2 font-mono text-gray-400">[{{ item.key }}]</span>
              </li>
            </ul>
          </details>
        </template>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-end gap-3 border-t border-gray-200 px-5 py-3 dark:border-gray-700">
        <button
          class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
          @click="emit('close')"
        >
          {{ t('common.cancel') }}
        </button>
        <button
          :disabled="!canImport"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="doImport"
        >
          {{
            importing
              ? t('zotero_import.importing')
              : t('zotero_import.import_n', { n: selectedKeys.size })
          }}
        </button>
      </div>
    </div>
  </div>
</template>
