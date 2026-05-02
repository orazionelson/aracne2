<script setup lang="ts">
/**
 * DiffViewer — renders a backend-computed unified diff (line-based) with
 * minimal classes for ``+`` / ``-`` / ``@@`` lines. The backend uses
 * ``difflib.unified_diff`` so we just split on newlines and colour each
 * row by its leading character. No third-party diff library.
 */
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useDocumentVersionsStore } from '@/stores/documentVersions';

const { t } = useI18n();
const store = useDocumentVersionsStore();

const props = defineProps<{
  modelValue: boolean;
  slug: string;
  filename: string;
  /** The version being inspected ("to" side of the diff). */
  versionNumber: number;
  /** The version to compare against (the "from" side). When matching the
   *  current state, callers pass the highest version_number on file. */
  againstVersion: number;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const diffText = ref<string>('');
const isLoading = ref(false);

interface Line {
  text: string;
  kind: 'add' | 'del' | 'hunk' | 'header' | 'ctx';
}

const lines = computed<Line[]>(() => {
  if (!diffText.value) return [];
  return diffText.value.split('\n').map((raw) => {
    if (raw.startsWith('+++') || raw.startsWith('---')) {
      return { text: raw, kind: 'header' };
    }
    if (raw.startsWith('@@')) return { text: raw, kind: 'hunk' };
    if (raw.startsWith('+')) return { text: raw, kind: 'add' };
    if (raw.startsWith('-')) return { text: raw, kind: 'del' };
    return { text: raw, kind: 'ctx' };
  });
});

watch(
  () => [props.modelValue, props.versionNumber, props.againstVersion],
  async ([open]) => {
    if (!open) return;
    diffText.value = '';
    isLoading.value = true;
    const res = await store.getDiff(
      props.slug,
      props.filename,
      props.versionNumber,
      props.againstVersion,
    );
    diffText.value = res?.diff ?? '';
    isLoading.value = false;
  },
  { immediate: true },
);

function close(): void {
  emit('update:modelValue', false);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="close"
    >
      <div class="flex h-[80vh] w-full max-w-4xl flex-col rounded-lg bg-white shadow-xl">
        <header class="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 class="text-base font-semibold text-slate-900">
            {{
              t('version.diff.title', {
                a: againstVersion,
                b: versionNumber,
              })
            }}
          </h2>
          <button
            type="button"
            class="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
            @click="close"
          >
            {{ t('version.diff.close') }}
          </button>
        </header>

        <div class="flex-1 overflow-auto bg-slate-50 p-4 font-mono text-xs leading-relaxed">
          <p v-if="isLoading" class="text-slate-500">
            {{ t('version.diff.loading') }}
          </p>
          <p v-else-if="!diffText" class="text-slate-500">
            {{ t('version.diff.no_changes') }}
          </p>
          <pre v-else class="whitespace-pre-wrap"><span
              v-for="(line, idx) in lines"
              :key="idx"
              :class="{
                'block bg-emerald-100 text-emerald-900': line.kind === 'add',
                'block bg-red-100 text-red-900': line.kind === 'del',
                'block bg-slate-200 text-slate-700': line.kind === 'hunk',
                'block bg-slate-100 text-slate-600': line.kind === 'header',
                'block text-slate-800': line.kind === 'ctx',
              }"
            >{{ line.text }}</span></pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>
