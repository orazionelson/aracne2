<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
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
import MediaPanel from '@/components/ui/MediaPanel.vue';
import ZoneEditor from '@/components/ui/ZoneEditor.vue';
import AiPanel from '@/components/AiPanel.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const settingStore = useSettingStore();
const aiStore = useAiStore();

// settingStore imported above to keep the store registered; not used directly here.
void settingStore;

const slug = route.params.slug as string;
const filename = route.params.filename as string;

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

// ── Facsimile state ────────────────────────────────────────────────────────────
interface FacsimileSurface {
  id: string;   // xml:id of the <surface> element
  url: string;  // url attribute of the nested <graphic> element
}
/** The <facsimile>…</facsimile> block extracted on load; kept in sync with the
 *  editor whenever addSurface / deleteSurface modifies it.  null = not present. */
const facsimileXml = ref<string | null>(null);

// ── Editor container ───────────────────────────────────────────────────────────
const editorContainer = ref<HTMLElement | null>(null);
const initialXml = ref('');

// ── CM5 instance ───────────────────────────────────────────────────────────────
const singleCm = useCodeMirror(editorContainer, {
  get initialValue() { return initialXml.value; },
  get schema() { return schema.value; },
  onChange: () => { saved.value = false; },
  onRefClick: (noteId, noteType, content) => openNoteEditModal(noteId, noteType, content),
});

// ── Media panel ───────────────────────────────────────────────────────────────
const showMediaPanel = ref(false);

// ── Zone editor panel ─────────────────────────────────────────────────────────
const showZonePanel = ref(false);
const currentZoneSurface = ref<FacsimileSurface | null>(null);

// ── Validation panel ──────────────────────────────────────────────────────────
const showValidationPanel = ref(false);

// ── Panel resize ──────────────────────────────────────────────────────────────
const PANEL_MIN_PX = 240;
const PANEL_MAX_PX = 720;
const panelWidth    = ref(384);   // initial width matching w-96
const isDragging    = ref(false);
const dragStartX    = ref(0);
const dragStartW    = ref(0);

const anyPanelOpen = computed(
  () =>
    showHelpPanel.value ||
    showAiPanel.value ||
    showMediaPanel.value ||
    showValidationPanel.value ||
    showZonePanel.value,
);

function startPanelDrag(e: MouseEvent): void {
  isDragging.value  = true;
  dragStartX.value  = e.clientX;
  dragStartW.value  = panelWidth.value;
  e.preventDefault();
}

function onPanelDragMove(e: MouseEvent): void {
  if (!isDragging.value) return;
  // Dragging left (negative delta) widens the panel.
  const delta = dragStartX.value - e.clientX;
  panelWidth.value = Math.max(PANEL_MIN_PX, Math.min(PANEL_MAX_PX, dragStartW.value + delta));
}

function onPanelDragEnd(): void {
  isDragging.value = false;
}

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

// ── Toolbar actions ────────────────────────────────────────────────────────────
const isFullscreen = computed(() => singleCm.isFullscreen.value);

function toggleFullscreen(): void { singleCm.toggleFullscreen(); }
function prettyPrint(): void { singleCm.prettyPrint(); }

// ── XML utilities ──────────────────────────────────────────────────────────────

/**
 * Find the start/end offsets of the first <tagName>…</tagName> block in xml.
 * Uses depth tracking so nested same-name elements are handled correctly.
 */
function findBlock(xml: string, tagName: string): { start: number; end: number } | null {
  const openTag  = `<${tagName}`;
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
  return null;
}

// ── Surfaces computed from facsimile XML ──────────────────────────────────────
const surfaces = computed((): FacsimileSurface[] => {
  if (!facsimileXml.value) return [];
  const result: FacsimileSurface[] = [];
  const surfaceRe = /<surface\b([^>]*)>([\s\S]*?)<\/surface>/g;
  let sm: RegExpExecArray | null;
  while ((sm = surfaceRe.exec(facsimileXml.value)) !== null) {
    const idMatch  = /xml:id="([^"]+)"/.exec(sm[1]);
    const urlMatch = /url="([^"]+)"/.exec(sm[2]);
    if (idMatch && urlMatch) {
      result.push({ id: idMatch[1], url: urlMatch[1] });
    }
  }
  return result;
});

/**
 * Register a new <surface> for mediaUrl in the <facsimile> block.
 * Creates the block from scratch if it does not exist yet, inserting it after
 * </teiHeader> in the editor.  Also updates the editor content so that the
 * editor is always the single source of truth — no reassembly is needed on save.
 * Returns the xml:id of the new (or already existing) surface.
 */
function addSurface(mediaUrl: string): string {
  const existing = surfaces.value.find((s) => s.url === mediaUrl);
  if (existing) return existing.id;

  const nextId  = `s${surfaces.value.length + 1}`;
  const surface = `<surface xml:id="${nextId}"><graphic url="${mediaUrl}"/></surface>`;
  const current = singleCm.getValue();

  if (facsimileXml.value === null) {
    // No facsimile block yet — create one and insert it after </teiHeader>.
    const newFacs = `<facsimile>\n    ${surface}\n  </facsimile>`;
    facsimileXml.value = newFacs;
    const hb = findBlock(current, 'teiHeader');
    if (hb) {
      singleCm.setValue(current.slice(0, hb.end) + '\n' + newFacs + current.slice(hb.end));
    }
  } else {
    const newFacs = facsimileXml.value.replace(
      /\s*<\/facsimile>/,
      `\n    ${surface}\n  </facsimile>`,
    );
    facsimileXml.value = newFacs;
    const fb = findBlock(current, 'facsimile');
    if (fb) {
      singleCm.setValue(current.slice(0, fb.start) + newFacs + current.slice(fb.end));
    }
  }
  saved.value = false;
  return nextId;
}

/**
 * Remove a <surface> from the <facsimile> block and strip the corresponding
 * facs="#id" attribute from all <pb> elements.  Both the in-memory ref and
 * the editor content are updated so they stay in sync.
 * If the facsimile block becomes empty it is removed from the editor entirely.
 */
function deleteSurface(surfaceId: string): void {
  if (!facsimileXml.value) return;

  const surfaceRe = new RegExp(
    `\\s*<surface\\b[^>]*xml:id="${surfaceId}"[^>]*>[\\s\\S]*?<\\/surface>`,
    'g',
  );
  const newFacs  = facsimileXml.value.replace(surfaceRe, '');
  const pbFacsRe = new RegExp(`(<pb\\b[^>]*)\\s+facs="#${surfaceId}"`, 'g');

  // Apply both changes (strip facs + update/remove facsimile) in one setValue.
  let current = singleCm.getValue();
  current = current.replace(pbFacsRe, '$1');

  if (/<facsimile[^>]*>\s*<\/facsimile>/.test(newFacs)) {
    // Block is now empty — remove it from the editor entirely.
    const fb = findBlock(current, 'facsimile');
    if (fb) {
      current = current.slice(0, fb.start).trimEnd() + '\n' + current.slice(fb.end).trimStart();
    }
    facsimileXml.value = null;
  } else {
    facsimileXml.value = newFacs;
    const fb = findBlock(current, 'facsimile');
    if (fb) {
      current = current.slice(0, fb.start) + newFacs + current.slice(fb.end);
    }
  }

  singleCm.setValue(current);
  saved.value = false;
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

// (split mode removed — editor is always the single source of truth)

/** Populate facsimileXml from the full document XML so the MediaPanel can
 *  display the surface list.  The editor receives the full unmodified XML —
 *  facsimileXml is kept in sync via addSurface / deleteSurface. */
function _extractFacsimileFromXml(xml: string): void {
  const fb = findBlock(xml, 'facsimile');
  facsimileXml.value = fb ? xml.slice(fb.start, fb.end) : null;
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
    _extractFacsimileFromXml(xml);
    initialXml.value = xml;
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

  document.addEventListener('mousemove', onPanelDragMove);
  document.addEventListener('mouseup',   onPanelDragEnd);
});

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onPanelDragMove);
  document.removeEventListener('mouseup',   onPanelDragEnd);
});

// ── Note insertion / editing ───────────────────────────────────────────────────

const showNoteModal = ref(false);
const pendingNoteType = ref<'alpha' | 'numeric'>('alpha');
/** null = inserting a new note; non-null = editing the note with this ID */
const pendingNoteId = ref<string | null>(null);
const noteModalInitialContent = ref('');

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
  _cmKey?: string,
): void {
  pendingNoteType.value = type;
  pendingNoteId.value = noteId;
  noteModalInitialContent.value = content;
  showNoteModal.value = true;
}

function handleNoteDelete(): void {
  if (!pendingNoteId.value) return;
  singleCm.deleteNote(pendingNoteId.value);
}

function handleNoteConfirm(content: string): void {
  if (pendingNoteId.value) {
    singleCm.editNote(pendingNoteId.value, content);
  } else {
    singleCm.insertNote(pendingNoteType.value, generateNoteId(), content);
  }
}

// ── Figure insertion ──────────────────────────────────────────────────────────

function handleInsertFigure(url: string): void {
  singleCm.insertFigure(url);
}

function handleInsertAsCard(mediaUrl: string): void {
  singleCm.insertPageBreak(addSurface(mediaUrl));
}

/**
 * Move a <surface> one position up or down inside <facsimile>.
 * The surrounding whitespace of each block is preserved; only the XML
 * content of the two adjacent blocks is swapped.
 */
function handleMoveSurface(surfaceId: string, direction: 'up' | 'down'): void {
  if (!facsimileXml.value) return;

  const facs = facsimileXml.value;

  // Extract the facsimile opening tag and trailing close tag.
  const openTagMatch = /^<facsimile\b[^>]*>/.exec(facs);
  if (!openTagMatch) return;
  const openTag   = openTagMatch[0];
  const closeTag  = '</facsimile>';
  const innerEnd  = facs.lastIndexOf(closeTag);
  if (innerEnd === -1) return;
  const inner = facs.slice(openTag.length, innerEnd);

  // Collect all <surface>…</surface> blocks with their leading whitespace.
  const surfaceRe = /(\s*)(<surface\b[\s\S]*?<\/surface>)/g;
  const blocks: Array<{ ws: string; text: string }> = [];
  let m: RegExpExecArray | null;
  while ((m = surfaceRe.exec(inner)) !== null) {
    blocks.push({ ws: m[1], text: m[2] });
  }

  const idx = blocks.findIndex((b) => b.text.includes(`xml:id="${surfaceId}"`));
  if (idx === -1) return;

  const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
  if (swapIdx < 0 || swapIdx >= blocks.length) return;

  // Swap only the XML content; whitespace slots stay in place.
  const newBlocks = blocks.map((b) => ({ ...b }));
  [newBlocks[idx].text, newBlocks[swapIdx].text] = [newBlocks[swapIdx].text, newBlocks[idx].text];

  const newFacs = openTag + newBlocks.map((b) => b.ws + b.text).join('') + closeTag;
  facsimileXml.value = newFacs;

  // Patch the editor in one operation.
  const current = singleCm.getValue();
  const fb = findBlock(current, 'facsimile');
  if (fb) {
    singleCm.setValue(current.slice(0, fb.start) + newFacs + current.slice(fb.end));
  }
  saved.value = false;
}

/**
 * Called when a media file is deleted from storage.
 * Removes dead references from the editor:
 *   1. The linked <surface> (if any) from <facsimile> + its facs="#id" on <pb>.
 *   2. Any self-closing <graphic url="mediaUrl"/> elements in the document body.
 */
function handleCleanupMediaRefs(mediaUrl: string): void {
  // 1. Remove linked surface if present.
  const surface = surfaces.value.find((s) => s.url === mediaUrl);
  if (surface) {
    deleteSurface(surface.id);
  }

  // 2. Strip inline <graphic> elements pointing to this URL.
  //    The URL may contain regex-special chars (slashes, dots, brackets) — escape them.
  const escapedUrl = mediaUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const graphicRe = new RegExp(
    `\\s*<graphic\\b[^>]*\\burl="${escapedUrl}"[^>]*/?>`,
    'g',
  );
  const current = singleCm.getValue();
  const cleaned = current.replace(graphicRe, '');
  if (cleaned !== current) {
    singleCm.setValue(cleaned);
    saved.value = false;
  }
}

// ── Zone editor ────────────────────────────────────────────────────────────────

/** Open the ZoneEditor panel for a specific surface. Closes other panels. */
function openZoneEditor(surface: FacsimileSurface): void {
  currentZoneSurface.value = surface;
  showZonePanel.value = true;
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
}

/**
 * Passed as the `onAssociate` prop to ZoneEditor.
 * Delegates to the CodeMirror composable and returns true on success so the
 * editor can show appropriate visual feedback.
 */
function handleZoneAssociate(zoneId: string): boolean {
  return singleCm.insertFacsRef(zoneId);
}

/**
 * Called when ZoneEditor successfully persists zones to eXist-db.
 *
 * ZoneEditor writes directly to eXist-db via the zones API, so the CodeMirror
 * buffer becomes stale.  This handler re-fetches the document, extracts the
 * updated <facsimile> block, and patches only that portion of the editor so
 * unsaved changes outside <facsimile> are preserved.
 */
async function handleZonesSaved(): Promise<void> {
  try {
    const freshXml = await store.fetchDocumentRaw(slug, filename);
    const freshFb  = findBlock(freshXml, 'facsimile');
    if (!freshFb) return;
    const newFacs = freshXml.slice(freshFb.start, freshFb.end);
    facsimileXml.value = newFacs;
    const current = singleCm.getValue();
    const edFb = findBlock(current, 'facsimile');
    if (edFb) {
      singleCm.setValue(current.slice(0, edFb.start) + newFacs + current.slice(edFb.end));
    }
  } catch {
    // Non-critical: zone data is in eXist-db; the user can reload if needed.
  }
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  saveError.value = null;
  saved.value = false;
  isSaving.value = true;
  try {
    await store.updateDocument(slug, filename, singleCm.getValue());
    saved.value = true;
    if (hasValidationSchema.value) runValidation();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value = msg ?? t('common.error');
    // Open the validation panel so the full save error is readable.
    showHelpPanel.value = false;
    showAiPanel.value = false;
    showMediaPanel.value = false;
    showValidationPanel.value = true;
  } finally {
    isSaving.value = false;
  }
}

// ── AI ────────────────────────────────────────────────────────────────────────
const showAiPanel = ref(false);
const aiEnabled = computed(() => aiStore.config !== null && aiStore.config.provider !== 'disabled');
const lastAiPrompt = ref<'validate' | 'improve' | 'discuss' | null>(null);
const schemaLabel = ref('TEI P5');
const aiNoErrors = ref(false);
// Snapshot of context captured at the moment "Discuss" is clicked; kept stable
// so AiPanel's deep context-watcher does not restart the stream on each keystroke.
const discussContext = ref<Record<string, string> | null>(null);

const activeEditor = computed(() => singleCm.editorInstance.value);

function openAiPanel(): void {
  showHelpPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showAiPanel.value = true;
}

function closeAiPanel(): void {
  aiStore.resetChat();
  aiNoErrors.value = false;
  lastAiPrompt.value = null;
  discussContext.value = null;
  showAiPanel.value = false;
}

async function runValidateAi(): Promise<void> {
  aiStore.clearResponse();
  aiNoErrors.value = false;
  lastAiPrompt.value = 'validate';
  // Always validate the current editor buffer, not the saved file, so that
  // unsaved changes are caught.  Clear any cached result to force a fresh run.
  validationResult.value = null;
  isValidating.value = true;
  try {
    validationResult.value = await schemaStore.validateDocument(
      slug,
      filename,
      singleCm.getValue(),
    );
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

function runDiscussAi(): void {
  openAiPanel();
  aiStore.resetChat();
  aiNoErrors.value = false;
  // Capture a snapshot of the current selection so AiPanel receives a stable
  // context object — a reactive computed would retrigger the stream on every edit.
  discussContext.value = {
    filename,
    collection_slug: slug,
    selection: activeEditor.value?.getSelection() || activeEditor.value?.getValue() || '',
  };
  lastAiPrompt.value = 'discuss';
}

// Strips markdown code fences that some models add to improve responses despite
// explicit instructions not to, keeping the display consistent with Apply.
const improveDisplayResponse = computed(() =>
  aiStore.response
    .replace(/^```(?:xml)?\r?\n?/, '')
    .replace(/\r?\n?```$/, '')
    .trim()
);

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
    // Auto-open the panel whenever validation finds errors.
    if (validationResult.value && !validationResult.value.valid) {
      showHelpPanel.value = false;
      showAiPanel.value = false;
      showMediaPanel.value = false;
      showValidationPanel.value = true;
    }
  }
}

</script>

<template>
  <div class="flex h-[calc(100vh-3.5rem)] flex-row" :class="isDragging ? 'select-none' : ''">
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
      </div>

      <!-- Toolbar -->
      <div class="flex flex-shrink-0 items-center gap-1">

        <!-- ── Format group ────────────────────────────────────────────────── -->
        <button
          :title="t('documents.pretty_print')"
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:border-gray-200 hover:bg-gray-100"
          @click="prettyPrint"
        >
          <!-- icon: code brackets -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"/>
          </svg>
          {{ t('documents.pretty_print') }}
        </button>

        <button
          :title="isFullscreen ? t('documents.exit_fullscreen') : t('documents.fullscreen')"
          class="inline-flex items-center rounded border border-transparent p-1.5 text-gray-600 transition-colors hover:border-gray-200 hover:bg-gray-100"
          @click="toggleFullscreen"
        >
          <!-- icon: arrows-pointing-out / arrows-pointing-in -->
          <svg v-if="!isFullscreen" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15"/>
          </svg>
          <svg v-else class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 9V4.5M9 9H4.5M9 9 3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5 5.25 5.25"/>
          </svg>
        </button>

        <span class="mx-0.5 h-5 w-px bg-gray-200" aria-hidden="true"/>

        <!-- ── Notes group ─────────────────────────────────────────────────── -->
        <button
          :disabled="isLoading"
          :title="t('documents.note_alpha_title')"
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:border-amber-200 hover:bg-amber-50 disabled:opacity-50"
          @click="openNoteModal('alpha')"
        >
          <!-- icon: pencil -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"/>
          </svg>
          {{ t('documents.note_btn_alpha') }}
        </button>

        <button
          :disabled="isLoading"
          :title="t('documents.note_numeric_title')"
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:border-amber-200 hover:bg-amber-50 disabled:opacity-50"
          @click="openNoteModal('numeric')"
        >
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"/>
          </svg>
          {{ t('documents.note_btn_numeric') }}
        </button>


        <span class="mx-0.5 h-5 w-px bg-gray-200" aria-hidden="true"/>

        <!-- ── Panel toggles ──────────────────────────────────────────────── -->
        <button
          :class="[
            'inline-flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs font-medium transition-colors',
            showHelpPanel
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100',
          ]"
          @click="showHelpPanel = !showHelpPanel; if (showHelpPanel) { showAiPanel = false; showMediaPanel = false; showValidationPanel = false; }"
        >
          <!-- icon: book-open -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25"/>
          </svg>
          {{ t('documents.tei_help') }}
        </button>

        <button
          v-if="aiEnabled && !isLoading"
          :class="[
            'inline-flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs font-medium transition-colors',
            showAiPanel
              ? 'border-violet-300 bg-violet-50 text-violet-700'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100',
          ]"
          @click="showAiPanel ? closeAiPanel() : openAiPanel()"
        >
          <!-- icon: sparkles -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"/>
          </svg>
          {{ t('ai.button_editor') }}
        </button>

        <button
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-50',
            showMediaPanel
              ? 'border-teal-300 bg-teal-50 text-teal-700'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100',
          ]"
          @click="showMediaPanel = !showMediaPanel; if (showMediaPanel) { showHelpPanel = false; showAiPanel = false; showValidationPanel = false; }"
        >
          <!-- icon: photo -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z"/>
          </svg>
          {{ t('media.media_btn') }}
        </button>

        <!-- ── Status feedback ────────────────────────────────────────────── -->
        <span v-if="saved" class="inline-flex items-center gap-1 text-xs font-medium text-green-600">
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>
          </svg>
          {{ t('documents.saved') }}
        </span>
        <span v-if="saveError" class="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-red-600 hover:underline" @click="showValidationPanel = true; showHelpPanel = false; showAiPanel = false; showMediaPanel = false;">
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/></svg>
          {{ t('documents.save_error_see_panel') }}
        </span>

        <!-- ── Validation error re-open badge ───────────────────────────── -->
        <button
          v-if="validationResult && !validationResult.valid && !showValidationPanel"
          class="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-200"
          :title="t('documents.validation_errors_title')"
          @click="showValidationPanel = true; showHelpPanel = false; showAiPanel = false; showMediaPanel = false;"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
          </svg>
          {{ validationResult.errors.length }}
        </button>

        <!-- ── Save (& Validate) ─────────────────────────────────────────── -->
        <button
          :disabled="isSaving || isValidating || isLoading"
          class="ml-1 inline-flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          @click="handleSave"
        >
          <!-- spinner while saving or validating, save icon otherwise -->
          <svg v-if="isSaving || isValidating" class="h-3.5 w-3.5 flex-shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"/>
          </svg>
          <svg v-else class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"/>
          </svg>
          <span v-if="isSaving">{{ t('common.saving') }}</span>
          <span v-else-if="isValidating">{{ t('documents.validating') }}</span>
          <span v-else>{{ hasValidationSchema ? t('documents.save_and_validate') : t('common.save') }}</span>
        </button>
      </div>
    </div>

    <!-- Hints bar -->
    <p class="mb-2 flex-shrink-0 text-xs text-gray-400">
      Ctrl+Space autocomplete · Ctrl+/ commento · Ctrl+J tag corrispondente · F11 fullscreen · Ctrl+F cerca
    </p>

    <!-- Loading / error states -->
    <p v-if="isLoading" class="text-sm text-gray-500">{{ t('common.loading') }}</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- Editor — v-if ensures real dimensions when CM5 initialises -->
    <div
      v-if="!isLoading && !error"
      ref="editorContainer"
      class="min-h-0 flex-1 overflow-hidden rounded border border-gray-300 [&_.CodeMirror]:h-full [&_.CodeMirror]:text-sm"
    />

  </div>

  <!-- Panel resize handle — appears between editor and any open panel -->
  <div
    v-if="anyPanelOpen"
    class="group relative z-10 flex w-[5px] flex-shrink-0 cursor-col-resize select-none items-center justify-center transition-colors"
    :class="isDragging ? 'bg-indigo-400' : 'bg-gray-200 hover:bg-indigo-400'"
    @mousedown="startPanelDrag"
  >
    <!-- Grip dots -->
    <div class="pointer-events-none flex flex-col gap-[3px]">
      <span v-for="i in 5" :key="i" class="h-[3px] w-[3px] rounded-full transition-colors" :class="isDragging ? 'bg-white' : 'bg-gray-400 group-hover:bg-white'"/>
    </div>
  </div>

  <!-- TEI Help panel -->
  <div
    v-if="showHelpPanel"
    class="flex flex-shrink-0 flex-col bg-white"
    :style="{ width: panelWidth + 'px' }"
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
    class="flex flex-shrink-0 flex-col bg-white"
    :style="{ width: panelWidth + 'px' }"
  >
    <!-- Discuss mode: AiPanel takes over the full sidebar -->
    <AiPanel
      v-if="lastAiPrompt === 'discuss' && discussContext"
      prompt-slug="document_discuss"
      :context="discussContext"
      :title="t('ai.panel_discuss_title')"
      :chat="true"
      :show-apply="false"
      :sidebar="true"
      @close="closeAiPanel"
    />

    <!-- Validate / Improve mode: custom inline panel -->
    <template v-else>
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
      <div class="flex items-center gap-2">
        <button
          :disabled="aiStore.isStreaming"
          class="inline-flex items-center gap-1.5 rounded border border-violet-300 bg-violet-50 px-2 py-1 text-xs font-medium text-violet-700 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runDiscussAi"
        >
          <!-- Chat bubble icon -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          {{ t('ai.discuss') }}
        </button>
        <button class="text-gray-400 hover:text-gray-700" @click="closeAiPanel">✕</button>
      </div>
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
      <span v-else>{{ lastAiPrompt === 'improve' ? improveDisplayResponse : aiStore.response }}</span>
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
    </template>
  </div>
  <!-- Media panel sidebar -->
  <MediaPanel
    v-if="showMediaPanel && !isLoading"
    :slug="slug"
    :doc-filename="filename"
    :surfaces="surfaces"
    :facsimile-xml="facsimileXml"
    :style="{ width: panelWidth + 'px' }"
    @insert-figure="handleInsertFigure"
    @insert-as-card="handleInsertAsCard"
    @delete-surface="deleteSurface"
    @move-surface="handleMoveSurface"
    @cleanup-media-refs="handleCleanupMediaRefs"
    @edit-zones="(sid) => { const s = surfaces.find(x => x.id === sid); if (s) openZoneEditor(s); }"
    @close="showMediaPanel = false"
  />

  <!-- Zone editor panel -->
  <ZoneEditor
    v-if="showZonePanel && currentZoneSurface && !isLoading"
    :slug="slug"
    :doc-filename="filename"
    :surface="currentZoneSurface"
    :on-associate="handleZoneAssociate"
    :style="{ width: panelWidth + 'px' }"
    @zones-saved="handleZonesSaved"
    @close="showZonePanel = false; currentZoneSurface = null"
  />

  <!-- Validation errors panel -->
  <div
    v-if="showValidationPanel && (validationResult || saveError)"
    class="flex flex-shrink-0 flex-col bg-white"
    :style="{ width: panelWidth + 'px' }"
  >
    <!-- Panel header -->
    <div class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 flex-shrink-0" :class="validationResult?.valid ? 'text-green-600' : 'text-red-500'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
        </svg>
        <span class="text-sm font-semibold text-gray-700">{{ t('documents.validation_errors_title') }}</span>
        <span
          v-if="validationResult && !validationResult.valid"
          class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700"
        >{{ validationResult.errors.length }}</span>
      </div>
      <button class="text-gray-400 hover:text-gray-700" @click="showValidationPanel = false">✕</button>
    </div>

    <!-- Save error (shown even without a validationResult) -->
    <div v-if="saveError" class="flex flex-shrink-0 items-start gap-2 border-b border-red-200 bg-red-50 px-3 py-2.5">
      <svg class="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/>
      </svg>
      <div>
        <p class="text-xs font-semibold text-red-700">{{ t('documents.save_error_title') }}</p>
        <p class="mt-0.5 text-xs leading-relaxed text-red-600">{{ saveError }}</p>
      </div>
    </div>

    <!-- Valid state -->
    <div v-if="validationResult && validationResult.valid" class="flex flex-1 items-center justify-center p-6 text-sm text-green-700">
      <svg class="mr-2 h-5 w-5 flex-shrink-0 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>
      </svg>
      {{ t('documents.validation_valid') }}
    </div>

    <!-- Error list -->
    <div v-else-if="validationResult && !validationResult.valid" class="min-h-0 flex-1 overflow-y-auto">
      <div
        v-for="(err, i) in validationResult.errors"
        :key="i"
        class="border-b border-red-100 px-3 py-2.5 last:border-0 hover:bg-red-50"
      >
        <div class="mb-1 flex items-center gap-2">
          <span class="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs text-red-500">
            {{ err.line }}:{{ err.col }}
          </span>
          <a
            :href="`https://www.google.com/search?q=${encodeURIComponent(err.message + (err.path ? ' ' + err.path : ''))}`"
            target="_blank"
            rel="noopener noreferrer"
            class="ml-auto text-xs text-blue-500 hover:text-blue-700 hover:underline"
          >{{ t('documents.search_google') }}</a>
        </div>
        <p class="text-xs leading-relaxed text-red-700">{{ err.message }}</p>
        <p v-if="err.path" class="mt-0.5 font-mono text-xs text-red-400">{{ err.path }}</p>
      </div>
    </div>

    <!-- Re-validate button (only when a schema is available) -->
    <div v-if="hasValidationSchema" class="flex flex-shrink-0 border-t border-gray-100 px-3 py-2">
      <button
        :disabled="isValidating"
        class="inline-flex w-full items-center justify-center gap-1.5 rounded border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100 disabled:opacity-50"
        @click="runValidation"
      >
        <svg v-if="!isValidating" class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
        </svg>
        <svg v-else class="h-3.5 w-3.5 flex-shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"/>
        </svg>
        {{ isValidating ? t('documents.validating') : t('documents.validate') }}
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
