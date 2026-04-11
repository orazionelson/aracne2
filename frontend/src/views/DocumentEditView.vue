<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCollectionStore } from '@/stores/collections';
import { useSchemaStore } from '@/stores/schemas';
import { useSettingStore } from '@/stores/settings';
import { useAiStore } from '@/stores/ai';
import type { ValidationResult } from '@/stores/schemas';
import { useCodeMirror } from '@/composables/useCodeMirror';
import { loadTeiSchema, type CM5Schema } from '@/utils/teiSchema';
import NoteModal from '@/components/ui/NoteModal.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const settingStore = useSettingStore();
const aiStore = useAiStore();

const slug = route.params.slug as string;
const filename = route.params.filename as string;

// ── Editor mode ────────────────────────────────────────────────────────────────
const splitMode = computed(() => settingStore.getSetting('document_editor_mode') === 'split');

// ── State ──────────────────────────────────────────────────────────────────────
const isLoading = ref(true);   // true until XML + schema are both ready
const isSchemaLoading = ref(true);
const isSaving = ref(false);
const isValidating = ref(false);
const error = ref<string | null>(null);
const saveError = ref<string | null>(null);
const saved = ref(false);
const schema = ref<CM5Schema | undefined>(undefined);
const hasValidationSchema = ref(false);
const validationResult = ref<ValidationResult | null>(null);
const schemaWarning = ref<string | null>(null);

// ── Split-mode state ───────────────────────────────────────────────────────────
const activeEditorTab = ref<'header' | 'body'>('header');
// Outer XML context preserved for reassembly
const outerBefore = ref('');
const outerBetween = ref(''); // whitespace/elements between </teiHeader> and <text>
const outerAfter = ref('');
// False when the document lacks <teiHeader>/<text> — falls back to single editor
const canSplit = ref(true);

// ── Editor containers ──────────────────────────────────────────────────────────
// Single-mode (non-split or split-fallback)
const editorContainer = ref<HTMLElement | null>(null);
// Split-mode — two independent CM5 instances, toggled with v-show
const headerEditorContainer = ref<HTMLElement | null>(null);
const bodyEditorContainer = ref<HTMLElement | null>(null);

// ── Initial XML values (set before isLoading → false so CM5 gets them at init) ─
const initialXml = ref('');       // single mode
const headerInitialXml = ref(''); // split — teiHeader
const bodyInitialXml = ref('');   // split — text

// ── CM5 instances ──────────────────────────────────────────────────────────────
// Each instance only initialises if its container ref ever becomes non-null
// (the watch in useCodeMirror fires only when the element appears in the DOM).

const singleCm = useCodeMirror(editorContainer, {
  get initialValue() { return initialXml.value; },
  get schema() { return schema.value; },
  onChange: () => { saved.value = false; },
  onRefClick: (noteId, noteType, content) => openNoteEditModal(noteId, noteType, content, 'single'),
});

const headerCm = useCodeMirror(headerEditorContainer, {
  get initialValue() { return headerInitialXml.value; },
  get schema() { return schema.value; },
  onChange: () => { saved.value = false; },
  lockBoundaryLines: 1, // locks <teiHeader> and </teiHeader>
  onRefClick: (noteId, noteType, content) => openNoteEditModal(noteId, noteType, content, 'header'),
});

const bodyCm = useCodeMirror(bodyEditorContainer, {
  get initialValue() { return bodyInitialXml.value; },
  get schema() { return schema.value; },
  onChange: () => { saved.value = false; },
  lockBoundaryLines: 2, // locks <text><body> and </body></text>
  onRefClick: (noteId, noteType, content) => openNoteEditModal(noteId, noteType, content, 'body'),
});

// ── TEI Help panel ────────────────────────────────────────────────────────────
const showHelpPanel = ref(false);
const helpTagInput = ref('');
const selectedHelpTag = ref('');
const helpDropdownOpen = ref(false);

/** All element names from the loaded CM5 schema, sorted alphabetically. */
const elementNames = computed((): string[] => {
  if (!schema.value) return [];
  return Object.keys(schema.value).filter((k) => k !== '!top').sort();
});

/** Up to 30 matching element names for the autocomplete dropdown. */
const filteredHelpTags = computed((): string[] => {
  const q = helpTagInput.value.trim().toLowerCase();
  if (!q) return elementNames.value.slice(0, 30);
  return elementNames.value.filter((n) => n.toLowerCase().startsWith(q)).slice(0, 30);
});

/** TEI P5 documentation URL for the currently selected tag. */
const helpUrl = computed((): string => {
  if (!selectedHelpTag.value) return '';
  return `https://tei-c.org/release/doc/tei-p5-doc/en/html/ref-${selectedHelpTag.value}.html`;
});

function selectHelpTag(tag: string): void {
  selectedHelpTag.value = tag;
  helpTagInput.value = tag;
  helpDropdownOpen.value = false;
}

function onHelpInputBlur(): void {
  // Delay so a click on a dropdown item fires before the list disappears.
  setTimeout(() => { helpDropdownOpen.value = false; }, 150);
}

// ── Delegate toolbar actions to the active editor ──────────────────────────────
const isFullscreen = computed(() => {
  if (!splitMode.value || !canSplit.value) return singleCm.isFullscreen.value;
  return activeEditorTab.value === 'header'
    ? headerCm.isFullscreen.value
    : bodyCm.isFullscreen.value;
});

function toggleFullscreen(): void {
  if (!splitMode.value || !canSplit.value) { singleCm.toggleFullscreen(); return; }
  if (activeEditorTab.value === 'header') headerCm.toggleFullscreen();
  else bodyCm.toggleFullscreen();
}

function prettyPrint(): void {
  if (!splitMode.value || !canSplit.value) { singleCm.prettyPrint(); return; }
  if (activeEditorTab.value === 'header') headerCm.prettyPrint();
  else bodyCm.prettyPrint();
}

// ── XML split utilities ────────────────────────────────────────────────────────

/**
 * Find the start/end byte offsets of the first <tagName>…</tagName> block.
 * Uses depth tracking so nested same-name elements are handled correctly.
 */
function findBlock(xml: string, tagName: string): { start: number; end: number } | null {
  const openTag = `<${tagName}`;
  const closeTag = `</${tagName}>`;

  let firstOpen = -1;
  for (let i = 0; i <= xml.length - openTag.length; i++) {
    if (xml.startsWith(openTag, i)) {
      const next = xml[i + openTag.length];
      if (next === '>' || next === '/' || next === ' ' || next === '\t' || next === '\n' || next === '\r') {
        firstOpen = i;
        break;
      }
    }
  }
  if (firstOpen === -1) return null;

  let depth = 0;
  let i = firstOpen;
  while (i < xml.length) {
    if (xml.startsWith(closeTag, i)) {
      depth--;
      if (depth === 0) return { start: firstOpen, end: i + closeTag.length };
      i += closeTag.length;
    } else if (xml.startsWith(openTag, i)) {
      const next = xml[i + openTag.length];
      if (next === '>' || next === '/' || next === ' ' || next === '\t' || next === '\n' || next === '\r') {
        depth++;
      }
      i++;
    } else {
      i++;
    }
  }
  return null; // unbalanced — document is malformed
}

/** Split a TEI XML string into its structural parts. Returns null if the
 *  document does not contain both <teiHeader> and <text>. */
function splitXml(xml: string): {
  header: string;
  body: string;
  before: string;
  between: string;
  after: string;
} | null {
  const hb = findBlock(xml, 'teiHeader');
  const tb = findBlock(xml, 'text');
  if (!hb || !tb) return null;

  return {
    before:   xml.slice(0, hb.start),
    header:   xml.slice(hb.start, hb.end),
    between:  xml.slice(hb.end, tb.start),
    body:     xml.slice(tb.start, tb.end),
    after:    xml.slice(tb.end),
  };
}

/** Reassemble a full TEI XML string from its parts. */
function reassembleXml(newHeader: string, newBody: string): string {
  return outerBefore.value + newHeader + outerBetween.value + newBody + outerAfter.value;
}

// ── CM5 schema loader ──────────────────────────────────────────────────────────
async function loadCm5Schema(schemaId: string | null): Promise<CM5Schema | undefined> {
  if (schemaId) {
    const schemaRecord = schemaStore.schemas.find((s) => s.id === schemaId);
    if (schemaRecord?.cm5_filename) {
      try {
        const xmlText = await schemaStore.fetchCm5Content(schemaId);
        return await loadTeiSchema(xmlText, 'text');
      } catch (err) {
        schemaWarning.value = err instanceof Error ? err.message : String(err);
      }
    }
  }
  try {
    return await loadTeiSchema('/cmschemas/tei-p5.xml', 'url');
  } catch {
    return undefined;
  }
}

// ── Tab switching ──────────────────────────────────────────────────────────────
// Both editor containers are always in the layout (absolute-positioned, same
// slot) so CM5 always has real dimensions and never needs a refresh on switch.
// Only the CSS visibility/pointer-events change — no measurement is cleared.
function switchTab(tab: 'header' | 'body'): void {
  activeEditorTab.value = tab;
}

// ── Get full XML value (handles both modes) ────────────────────────────────────
function getFullValue(): string {
  if (!splitMode.value || !canSplit.value) return singleCm.getValue();
  return reassembleXml(headerCm.getValue(), bodyCm.getValue());
}

// ── Init ───────────────────────────────────────────────────────────────────────
onMounted(async () => {
  const [collectionResult, xmlResult] = await Promise.allSettled([
    store.fetchCollection(slug),
    store.fetchDocumentRaw(slug, filename),
  ]);

  if (schemaStore.schemas.length === 0) {
    try { await schemaStore.fetchSchemas(); } catch { /* non-fatal */ }
  }

  if (xmlResult.status === 'fulfilled') {
    const xml = xmlResult.value;
    if (splitMode.value) {
      const parts = splitXml(xml);
      if (parts) {
        headerInitialXml.value = parts.header;
        bodyInitialXml.value   = parts.body;
        outerBefore.value      = parts.before;
        outerBetween.value     = parts.between;
        outerAfter.value       = parts.after;
        canSplit.value = true;
      } else {
        canSplit.value = false;
        initialXml.value = xml; // fallback to single editor
      }
    } else {
      initialXml.value = xml;
    }
  } else {
    error.value = t('common.error');
  }

  const schemaId = collectionResult.status === 'fulfilled'
    ? (store.current?.schema_id ?? null)
    : null;

  if (schemaId) {
    const rec = schemaStore.schemas.find((s) => s.id === schemaId);
    hasValidationSchema.value = !!rec?.validation_format;
    if (rec?.name) schemaLabel.value = rec.name;
  }

  schema.value = await loadCm5Schema(schemaId);
  isSchemaLoading.value = false;
  // isLoading = false triggers v-if on the editor wrappers. The containers
  // mount with the initial XML already set, so CM5 gets the content at init
  // time on a visible, properly sized element.
  isLoading.value = false;
  // Fetch AI config to know whether to show the AI button (non-fatal).
  try { await aiStore.fetchConfig(); } catch { /* non-fatal */ }
});

// ── Note insertion / editing ───────────────────────────────────────────────────

type CmKey = 'single' | 'header' | 'body';

const showNoteModal = ref(false);
const pendingNoteType = ref<'alpha' | 'numeric'>('alpha');
/** null = inserting a new note; non-null = editing the note with this ID */
const pendingNoteId = ref<string | null>(null);
const noteModalInitialContent = ref('');
/** Which CM instance owns the note being edited */
const editingCmKey = ref<CmKey>('single');

/** Generate a unique note ID matching old-Aracne format: N + 9 base-36 chars. */
function generateNoteId(): string {
  return `N${Math.random().toString(36).slice(2, 11).padEnd(9, '0')}`;
}

function openNoteModal(type: 'alpha' | 'numeric'): void {
  pendingNoteType.value = type;
  pendingNoteId.value = null;
  noteModalInitialContent.value = '';
  showNoteModal.value = true;
}

function openNoteEditModal(
  noteId: string,
  type: 'alpha' | 'numeric',
  content: string,
  cmKey: CmKey,
): void {
  pendingNoteType.value = type;
  pendingNoteId.value = noteId;
  noteModalInitialContent.value = content;
  editingCmKey.value = cmKey;
  showNoteModal.value = true;
}

function handleNoteDelete(): void {
  if (!pendingNoteId.value) return;
  const cmMap = { single: singleCm, header: headerCm, body: bodyCm } as const;
  cmMap[editingCmKey.value].deleteNote(pendingNoteId.value);
}

function handleNoteConfirm(content: string): void {
  if (pendingNoteId.value) {
    // Edit the content of an existing <note> without touching the <ref> marker.
    const cmMap = { single: singleCm, header: headerCm, body: bodyCm } as const;
    cmMap[editingCmKey.value].editNote(pendingNoteId.value, content);
  } else {
    // Insert a brand-new <ref> + <note> pair.
    const noteId = generateNoteId();
    if (!splitMode.value || !canSplit.value) {
      singleCm.insertNote(pendingNoteType.value, noteId, content);
    } else if (activeEditorTab.value === 'header') {
      headerCm.insertNote(pendingNoteType.value, noteId, content);
    } else {
      bodyCm.insertNote(pendingNoteType.value, noteId, content);
    }
  }
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  isSaving.value = true;
  try {
    await store.updateDocument(slug, filename, getFullValue());
    saved.value = true;
    if (hasValidationSchema.value) runValidation();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t('common.error');
  } finally {
    isSaving.value = false;
  }
}

// ── AI ────────────────────────────────────────────────────────────────────────
const showAiPanel = ref(false);
const aiEnabled = computed(() => aiStore.config !== null && aiStore.config.provider !== 'disabled');
const lastAiPrompt = ref<'validate' | 'improve' | null>(null);
const schemaLabel = ref('TEI P5');
const aiNoErrors = ref(false);

const activeEditor = computed(() => {
  if (splitMode.value && canSplit.value) {
    return activeEditorTab.value === 'header'
      ? headerCm.editorInstance.value
      : bodyCm.editorInstance.value;
  }
  return singleCm.editorInstance.value;
});

function openAiPanel(): void {
  showHelpPanel.value = false;
  showAiPanel.value = true;
}

function closeAiPanel(): void {
  aiStore.stopStream();
  aiStore.clearResponse();
  aiNoErrors.value = false;
  showAiPanel.value = false;
}

async function runValidateAi(): Promise<void> {
  aiStore.clearResponse();
  aiNoErrors.value = false;
  lastAiPrompt.value = 'validate';
  if (!validationResult.value) {
    await runValidation();
  }
  if (!validationResult.value || validationResult.value.valid) {
    aiNoErrors.value = true;
    return;
  }
  const errorsText = validationResult.value.errors
    .map(e => `Line ${e.line}, col ${e.col}: ${e.message}`)
    .join('\n');
  await aiStore.startStream('validate_errors_explain', {
    filename,
    schema: schemaLabel.value,
    errors: errorsText,
  });
}

async function runImproveAi(): Promise<void> {
  lastAiPrompt.value = 'improve';
  aiNoErrors.value = false;
  aiStore.clearResponse();
  await aiStore.startStream('document_edit_suggest', {
    filename,
    collection_slug: slug,
    selection: activeEditor.value?.getSelection() || activeEditor.value?.getValue() || '',
  });
}

function applyAiResponse(): void {
  const cm = activeEditor.value;
  if (!cm) return;
  // Strip markdown code fences that some models add despite instructions.
  const clean = aiStore.response.replace(/^```(?:xml)?\r?\n?/, '').replace(/\r?\n?```$/, '').trim();
  // If there is an active selection, replace only that. Otherwise replace the
  // full document content (the AI received the whole document as context).
  if (cm.getSelection()) {
    cm.replaceSelection(clean);
  } else {
    cm.setValue(clean);
  }
  closeAiPanel();
}

// ── Validate ───────────────────────────────────────────────────────────────────
async function runValidation(): Promise<void> {
  isValidating.value = true;
  validationResult.value = null;
  try {
    validationResult.value = await schemaStore.validateDocument(slug, filename);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    validationResult.value = {
      valid: false,
      errors: [{ line: 0, col: 0, message: msg ?? t('common.error') }],
    };
  } finally {
    isValidating.value = false;
  }
}
</script>

<template>
  <div class="flex h-[calc(100vh-3.5rem)] flex-row">
  <!-- Main editor column -->
  <div class="flex min-w-0 flex-1 flex-col px-4 py-4">
    <!-- Header bar -->
    <div class="mb-3 flex flex-shrink-0 items-center justify-between">
      <div class="flex items-center gap-3">
        <button
          class="text-sm text-gray-500 hover:text-gray-800"
          @click="router.push({ name: 'collection-detail', params: { slug } })"
        >
          ← {{ slug }}
        </button>
        <span class="text-gray-300">/</span>
        <span class="font-mono text-sm font-semibold text-gray-800">{{ filename }}</span>
        <span class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
          {{ t('documents.action_edit') }}
        </span>
        <span
          v-if="!isSchemaLoading && schema"
          class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700"
          :title="t('documents.schema_loaded')"
        >
          TEI P5
        </span>
        <span
          v-if="!isSchemaLoading && schemaWarning"
          class="max-w-sm truncate rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
          :title="schemaWarning"
        >
          {{ t('documents.schema_error') }}
        </span>
        <span
          v-if="splitMode && !isLoading && !canSplit"
          class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700"
          :title="t('documents.split_fallback_title')"
        >
          {{ t('documents.split_fallback') }}
        </span>
      </div>

      <!-- Toolbar -->
      <div class="flex items-center gap-2">
        <button
          :title="t('documents.pretty_print')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          @click="prettyPrint"
        >
          {{ t('documents.pretty_print') }}
        </button>
        <button
          :disabled="isLoading"
          :title="t('documents.note_alpha_title')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          @click="openNoteModal('alpha')"
        >
          {{ t('documents.note_btn_alpha') }}
        </button>
        <button
          :disabled="isLoading"
          :title="t('documents.note_numeric_title')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          @click="openNoteModal('numeric')"
        >
          {{ t('documents.note_btn_numeric') }}
        </button>
        <button
          :title="isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen') }}
        </button>
        <button
          v-if="hasValidationSchema"
          :disabled="isValidating || isLoading"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          @click="runValidation"
        >
          {{ isValidating ? t('documents.validating') : t('documents.validate') }}
        </button>
        <span
          v-if="validationResult && validationResult.valid"
          class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700"
        >
          {{ t('documents.valid') }}
        </span>
        <span
          v-else-if="validationResult && !validationResult.valid"
          class="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
        >
          {{ t('documents.invalid', { n: validationResult.errors.length }) }}
        </span>
        <span v-if="saved" class="text-xs text-green-600">{{ t('documents.saved') }}</span>
        <span v-if="saveError" class="max-w-xs truncate text-xs text-red-600">{{ saveError }}</span>
        <button
          :class="[
            'rounded border px-2 py-1 text-xs',
            showHelpPanel
              ? 'border-indigo-400 bg-indigo-50 text-indigo-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-100',
          ]"
          @click="showHelpPanel = !showHelpPanel; if (showHelpPanel) showAiPanel = false"
        >
          {{ t('documents.tei_help') }}
        </button>
        <button
          v-if="aiEnabled && !isLoading"
          :class="[
            'rounded border px-2 py-1 text-xs',
            showAiPanel
              ? 'border-violet-400 bg-violet-50 text-violet-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-100',
          ]"
          @click="showAiPanel ? closeAiPanel() : openAiPanel()"
        >
          {{ t('ai.button_editor') }}
        </button>
        <button
          :disabled="isSaving || isLoading"
          class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="handleSave"
        >
          {{ isSaving ? t('common.loading') : t('common.save') }}
        </button>
      </div>
    </div>

    <!-- Hints bar -->
    <p class="mb-2 flex-shrink-0 text-xs text-gray-400">
      Ctrl+Space autocomplete · Ctrl+/ commento · Ctrl+J tag corrispondente · F11 fullscreen · Ctrl+F cerca
    </p>

    <!-- Split-mode tab bar -->
    <div
      v-if="splitMode && canSplit && !isLoading && !error"
      class="mb-2 flex flex-shrink-0 gap-1 border-b border-gray-200 pb-2"
    >
      <button
        :class="[
          'rounded-t px-4 py-1.5 text-xs font-medium transition-colors',
          activeEditorTab === 'header'
            ? 'bg-indigo-600 text-white'
            : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
        ]"
        @click="switchTab('header')"
      >
        &lt;teiHeader&gt;
      </button>
      <button
        :class="[
          'rounded-t px-4 py-1.5 text-xs font-medium transition-colors',
          activeEditorTab === 'body'
            ? 'bg-indigo-600 text-white'
            : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
        ]"
        @click="switchTab('body')"
      >
        &lt;text&gt;
      </button>
    </div>

    <!-- Loading / error states -->
    <p v-if="isLoading" class="text-sm text-gray-500">{{ t('common.loading') }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- Single-mode editor (non-split or split-fallback) -->
    <!-- v-if ensures the container has real dimensions when CM5 initialises. -->
    <div
      v-if="(!splitMode || !canSplit) && !isLoading && !error"
      ref="editorContainer"
      class="min-h-0 flex-1 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
    />

    <!-- Split-mode editors: two independent CM5 instances stacked absolutely   -->
    <!-- inside a shared flex-1 wrapper. Both always occupy the same real      -->
    <!-- dimensions — the inactive tab is hidden via visibility:hidden +       -->
    <!-- pointer-events:none so CM5 can always measure without a refresh().    -->
    <div
      v-if="splitMode && canSplit && !isLoading && !error"
      class="relative min-h-0 flex-1"
    >
      <div
        ref="headerEditorContainer"
        :class="[
          'absolute inset-0 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm',
          activeEditorTab !== 'header' ? 'invisible pointer-events-none' : '',
        ]"
      />
      <div
        ref="bodyEditorContainer"
        :class="[
          'absolute inset-0 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm',
          activeEditorTab !== 'body' ? 'invisible pointer-events-none' : '',
        ]"
      />
    </div>

    <!-- Validation errors panel -->
    <div
      v-if="validationResult && !validationResult.valid"
      class="mt-2 max-h-40 flex-shrink-0 overflow-y-auto rounded border border-red-200 bg-red-50"
    >
      <table class="w-full text-xs">
        <tbody>
          <tr
            v-for="(err, i) in validationResult.errors"
            :key="i"
            class="border-b border-red-100 last:border-0"
          >
            <td class="w-20 whitespace-nowrap px-3 py-1 font-mono text-red-400">
              {{ err.line }}:{{ err.col }}
            </td>
            <td class="px-3 py-1 text-red-700">
              {{ err.message }}
              <span v-if="err.path" class="ml-1 font-mono text-red-400">({{ err.path }})</span>
              <a
                :href="`https://www.google.com/search?q=${encodeURIComponent(err.message + (err.path ? ' ' + err.path : ''))}`"
                target="_blank"
                rel="noopener noreferrer"
                class="ml-2 whitespace-nowrap text-blue-500 underline hover:text-blue-700"
              >{{ t('documents.search_google') }}</a>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <!-- TEI Help panel -->
  <div
    v-if="showHelpPanel"
    class="flex w-96 flex-shrink-0 flex-col border-l border-gray-200 bg-white"
  >
    <!-- Panel header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <span class="text-sm font-semibold text-gray-700">{{ t('documents.tei_help') }}</span>
      <button
        class="text-gray-400 hover:text-gray-700"
        @click="showHelpPanel = false"
      >
        ✕
      </button>
    </div>

    <!-- Tag autocomplete -->
    <div class="relative flex-shrink-0 px-3 py-2">
      <input
        v-model="helpTagInput"
        type="text"
        :placeholder="schema ? t('documents.tei_help_placeholder') : t('documents.tei_help_no_schema')"
        :disabled="!schema"
        class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-400 focus:outline-none disabled:bg-gray-50 disabled:text-gray-400"
        @focus="helpDropdownOpen = true"
        @input="helpDropdownOpen = true"
        @blur="onHelpInputBlur"
      />
      <!-- Dropdown -->
      <ul
        v-if="helpDropdownOpen && filteredHelpTags.length > 0"
        class="absolute left-3 right-3 z-20 max-h-56 overflow-y-auto rounded border border-gray-200 bg-white shadow-md"
      >
        <li
          v-for="tag in filteredHelpTags"
          :key="tag"
          class="cursor-pointer px-3 py-1.5 font-mono text-sm hover:bg-indigo-50 hover:text-indigo-700"
          @mousedown.prevent="selectHelpTag(tag)"
        >
          {{ tag }}
        </li>
      </ul>
    </div>

    <!-- Documentation iframe -->
    <div class="min-h-0 flex-1">
      <iframe
        v-if="helpUrl"
        :src="helpUrl"
        class="h-full w-full border-0"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        :title="selectedHelpTag"
      />
      <p
        v-else
        class="px-3 py-4 text-xs text-gray-400"
      >
        {{ t('documents.tei_help_select') }}
      </p>
    </div>
  </div>

  <!-- AI sidebar panel -->
  <div
    v-if="showAiPanel"
    class="flex w-96 flex-shrink-0 flex-col border-l border-gray-200 bg-white"
  >
    <!-- Header with action buttons -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <div class="flex gap-1.5">
        <button
          :disabled="aiStore.isStreaming || !hasValidationSchema"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runValidateAi"
        >
          {{ t('ai.validate') }}
        </button>
        <button
          :disabled="aiStore.isStreaming"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runImproveAi"
        >
          {{ t('ai.improve') }}
        </button>
      </div>
      <button class="text-gray-400 hover:text-gray-700" @click="closeAiPanel">✕</button>
    </div>

    <!-- Response area -->
    <div class="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800">
      <span v-if="aiNoErrors" class="text-green-700">{{ t('ai.no_errors_to_explain') }}</span>
      <span v-else-if="!aiStore.response && !aiStore.streamError && !aiStore.isStreaming" class="text-xs text-gray-400">
        {{ t('ai.idle_hint') }}
      </span>
      <span v-else-if="!aiStore.response && aiStore.isStreaming" class="animate-pulse text-gray-400">
        {{ t('ai.thinking') }}
      </span>
      <span v-else-if="aiStore.streamError" class="text-red-600">{{ aiStore.streamError }}</span>
      <span v-else>{{ aiStore.response }}</span>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between border-t border-gray-100 px-4 py-2">
      <button
        v-if="aiStore.isStreaming"
        class="rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50"
        @click="aiStore.stopStream()"
      >
        {{ t('ai.stop') }}
      </button>
      <span v-else class="text-xs text-gray-400">{{ aiStore.config?.provider ?? '' }}</span>
      <button
        v-if="lastAiPrompt === 'improve' && !aiStore.isStreaming && aiStore.response && !aiStore.streamError"
        class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700"
        @click="applyAiResponse"
      >
        {{ t('ai.apply') }}
      </button>
    </div>
  </div>
  </div>

  <!-- Note insertion / editing modal -->
  <NoteModal
    v-model="showNoteModal"
    :note-type="pendingNoteType"
    :initial-content="noteModalInitialContent"
    :is-editing="pendingNoteId !== null"
    @confirm="handleNoteConfirm"
    @delete="handleNoteDelete"
  />
</template>

<style>
/* Lines protected by lockBoundaryLines — visually distinct, cursor indicates no-edit */
.cm-locked-line {
  background-color: #f3f4f6; /* gray-100 */
  opacity: 0.75;
  cursor: not-allowed;
}

/* <ref> inline markers — read-only, clickable to open edit modal */
.cm-note-ref {
  background-color: #fef3c7; /* amber-100 */
  border-bottom: 1px solid #f59e0b; /* amber-500 */
  border-radius: 2px;
  cursor: pointer;
  padding: 0 1px;
}
.cm-note-ref:hover {
  background-color: #fde68a; /* amber-200 */
}
</style>
