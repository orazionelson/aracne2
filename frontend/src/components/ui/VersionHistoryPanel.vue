<script setup lang="ts">
/**
 * VersionHistoryPanel — sidebar listing the version history of a single
 * document. Powers the editor's "history" surface: every row carries the
 * version number, an origin badge, the optional manual-save message,
 * author + timestamp, and per-row actions (compare, rollback, delete).
 *
 * Self-contained: opens / closes by toggling ``modelValue`` from the
 * parent. Emits ``compare`` and ``rollback-confirmed`` so the host editor
 * can mount the diff viewer / refresh the document body, but does the
 * delete in-place (it has no editor-side consequence).
 */
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  useDocumentVersionsStore,
  type DocumentVersion,
  type VersionOrigin,
} from '@/stores/documentVersions';
import { useAuthStore } from '@/stores/auth';

const { t, locale } = useI18n();
const store = useDocumentVersionsStore();
const auth = useAuthStore();

const props = defineProps<{
  modelValue: boolean;
  slug: string;
  filename: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  compare: [versionNumber: number];
  'rollback-confirmed': [versionNumber: number];
  'manual-save-clicked': [];
}>();

const filterPublicationOnly = ref(false);

/** Refresh the list every time the panel opens or the filter toggles. */
watch(
  () => [props.modelValue, filterPublicationOnly.value, props.filename],
  async ([open]) => {
    if (!open) return;
    await store.loadList(
      props.slug,
      props.filename,
      filterPublicationOnly.value ? 'publication' : undefined,
    );
  },
  { immediate: true },
);

const rows = computed<DocumentVersion[]>(() => store.versions);

/** Format a backend timestamp using the user's preferred locale. */
function fmtWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(locale.value, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

/** Tailwind classes for the origin badge — colour is informational, not
 *  semantic, so a colour-blind editor still reads the label. */
const ORIGIN_CLASSES: Record<VersionOrigin, string> = {
  creation: 'bg-slate-100 text-slate-800',
  manual: 'bg-blue-100 text-blue-800',
  submission: 'bg-amber-100 text-amber-800',
  rejection: 'bg-orange-100 text-orange-800',
  publication: 'bg-emerald-100 text-emerald-800',
  rollback: 'bg-purple-100 text-purple-800',
};

function originLabel(o: VersionOrigin): string {
  return t(`version.origin.${o}`);
}

/** Per-row action visibility. The DELETE endpoint is gated on
 *  author-or-Admin server-side; we mirror that check client-side so the
 *  button is hidden when it would 403. */
function canDelete(row: DocumentVersion): boolean {
  if (row.origin !== 'manual') return false;
  const me = auth.user;
  if (!me) return false;
  if (me.role === 'Admin') return true;
  return row.created_by_id === me.id;
}

async function onRollback(row: DocumentVersion): Promise<void> {
  if (!window.confirm(t('version.rollback.title', { n: row.version_number }))) return;
  const created = await store.rollback(props.slug, props.filename, row.version_number);
  if (created !== null) {
    emit('rollback-confirmed', row.version_number);
  }
}

async function onDelete(row: DocumentVersion): Promise<void> {
  if (!window.confirm(t('version.delete.confirm_title', { n: row.version_number }))) return;
  await store.deleteVersion(props.slug, props.filename, row.version_number);
}

function close(): void {
  emit('update:modelValue', false);
}
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="modelValue"
      class="fixed top-0 right-0 z-40 flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl"
      role="complementary"
      :aria-label="t('version.history.title')"
    >
      <header class="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">{{ t('version.history.title') }}</h2>
          <p class="text-sm text-slate-500">{{ filename }}</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            @click="emit('manual-save-clicked')"
          >
            {{ t('version.actions.save_version') }}
          </button>
          <button
            type="button"
            class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            @click="close"
          >
            {{ t('version.history.close') }}
          </button>
        </div>
      </header>

      <div class="flex items-center gap-3 border-b border-slate-100 bg-slate-50 px-4 py-2">
        <label class="text-sm text-slate-700">
          <input v-model="filterPublicationOnly" type="checkbox" class="mr-2" />
          {{ t('version.history.filter_publication_only') }}
        </label>
      </div>

      <div class="flex-1 overflow-y-auto">
        <p
          v-if="store.isLoading"
          class="px-4 py-8 text-center text-sm text-slate-500"
        >
          {{ t('version.history.loading') }}
        </p>
        <p
          v-else-if="store.error"
          class="m-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          {{ store.error }}
        </p>
        <p
          v-else-if="rows.length === 0"
          class="px-4 py-8 text-center text-sm text-slate-500"
        >
          {{ t('version.history.empty') }}
        </p>
        <table v-else class="w-full text-left text-sm">
          <thead class="sticky top-0 bg-white text-xs uppercase text-slate-500">
            <tr>
              <th class="px-3 py-2">{{ t('version.history.column_version') }}</th>
              <th class="px-3 py-2">{{ t('version.history.column_origin') }}</th>
              <th class="px-3 py-2">{{ t('version.history.column_message') }}</th>
              <th class="px-3 py-2">{{ t('version.history.column_when') }}</th>
              <th class="px-3 py-2 text-right">{{ t('version.history.column_actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.id"
              class="border-t border-slate-100 align-top"
            >
              <td class="px-3 py-2 font-mono text-slate-900">v{{ row.version_number }}</td>
              <td class="px-3 py-2">
                <span
                  class="inline-block rounded-full px-2 py-0.5 text-xs font-medium"
                  :class="ORIGIN_CLASSES[row.origin]"
                >
                  {{ originLabel(row.origin) }}
                </span>
              </td>
              <td class="px-3 py-2 text-slate-700">
                <span v-if="row.message">{{ row.message }}</span>
                <span v-else class="text-slate-400">{{ t('version.history.no_message') }}</span>
              </td>
              <td class="px-3 py-2 whitespace-nowrap text-slate-600">{{ fmtWhen(row.created_at) }}</td>
              <td class="px-3 py-2 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    type="button"
                    class="text-sm text-blue-700 hover:underline"
                    @click="emit('compare', row.version_number)"
                  >
                    {{ t('version.actions.compare_with_current') }}
                  </button>
                  <button
                    type="button"
                    class="text-sm text-purple-700 hover:underline"
                    @click="onRollback(row)"
                  >
                    {{ t('version.actions.rollback') }}
                  </button>
                  <button
                    v-if="canDelete(row)"
                    type="button"
                    class="text-sm text-red-700 hover:underline"
                    @click="onDelete(row)"
                  >
                    {{ t('version.actions.delete') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </aside>
  </Teleport>
</template>
