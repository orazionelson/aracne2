<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useCollectionStore } from '@/stores/collections';
import { useSchemaStore } from '@/stores/schemas';
import { useSettingStore } from '@/stores/settings';
import { useAiStore } from '@/stores/ai';
import { usePluginStore } from '@/stores/plugins';
import type { ValidationResult } from '@/stores/schemas';
import { useCodeMirror } from '@/composables/useCodeMirror';
import CodeMirror, { type Editor as CM5Editor } from 'codemirror';
import { loadTeiSchema, type CM5Schema } from '@/utils/teiSchema';
import NoteModal from '@/components/ui/NoteModal.vue';
import MediaPanel from '@/components/ui/MediaPanel.vue';
import WikidataLinkPanel from '@/components/ui/WikidataLinkPanel.vue';
import OrcidLinkPanel from '@/components/ui/OrcidLinkPanel.vue';
import RorLinkPanel from '@/components/ui/RorLinkPanel.vue';
import ViafLinkPanel from '@/components/ui/ViafLinkPanel.vue';
import GeonamesLinkPanel from '@/components/ui/GeonamesLinkPanel.vue';
import GndLinkPanel from '@/components/ui/GndLinkPanel.vue';
import CerlLinkPanel from '@/components/ui/CerlLinkPanel.vue';
import PeripleoLinkPanel from '@/components/ui/PeripleoLinkPanel.vue';
import GettyAatLinkPanel from '@/components/ui/GettyAatLinkPanel.vue';
import OpenAlexPanel from '@/components/ui/OpenAlexPanel.vue';
import TrismegistosLinkPanel from '@/components/ui/TrismegistosLinkPanel.vue';
import CrossrefPanel from '@/components/ui/CrossrefPanel.vue';
import ZoneEditor from '@/components/ui/ZoneEditor.vue';
import AiPanel from '@/components/AiPanel.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useCollectionStore();
const schemaStore = useSchemaStore();
const settingStore = useSettingStore();
const aiStore = useAiStore();
const pluginStore = usePluginStore();

// Editor-side integrations that live as non-native plugins. The
// toolbar buttons (ORCID lookup, CrossRef DOI resolver) are visible
// only when the matching plugin is active in /admin/plugins —
// otherwise clicking them would hit endpoints mounted conditionally.
const wikidataPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'wikidata' && p.status === 'active'),
);
const orcidPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'orcid' && p.status === 'active'),
);
const rorPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'ror' && p.status === 'active'),
);
const viafPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'viaf' && p.status === 'active'),
);
const geonamesPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'geonames' && p.status === 'active'),
);
const gndPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'gnd' && p.status === 'active'),
);
const cerlPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'cerl' && p.status === 'active'),
);
const peripleoPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'peripleo' && p.status === 'active'),
);
const gettyAatPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'getty_aat' && p.status === 'active'),
);
const openalexPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'openalex' && p.status === 'active'),
);
const trismegistosPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === 'trismegistos' && p.status === 'active'),
);
const crossrefPluginActive = computed(() =>
  pluginStore.plugins.some(
    (p) => p.name === 'crossref_lookup' && p.status === 'active',
  ),
);

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

// ── Wikidata entity-linking panel ─────────────────────────────────────────────
// Lets an editor resolve a <persName>/<placeName>/<orgName> selection to a
// canonical Wikidata URI and write it back as @ref on the enclosing TEI tag.
const showWikidataPanel = ref(false);
const wikidataInitialQuery = ref('');
// Whitelist of TEI entity elements that may receive an @ref via this panel.
// Keep in sync with backend/app/db/seed.py -> entity_index_tags default; we
// keep a local copy rather than fetching it from the settings store because
// the helper runs synchronously against the editor buffer.
const ENTITY_TAGS = ['persName', 'placeName', 'orgName'] as const;

// ── ORCID lookup panel ────────────────────────────────────────────────────────
// Resolves a <persName> selection to a canonical ORCID URI. Narrower
// than the Wikidata panel — ORCID identifies people only.
const ORCID_TAGS = ['persName'] as const;
const showOrcidPanel = ref(false);
const orcidInitialQuery = ref('');

// ── ROR lookup panel ──────────────────────────────────────────────────────────
// Resolves an <orgName> selection to a canonical ROR URI. Scoped to
// institutions only — ROR does not identify people or places.
const ROR_TAGS = ['orgName'] as const;
const showRorPanel = ref(false);
const rorInitialQuery = ref('');

// ── VIAF lookup panel ─────────────────────────────────────────────────────────
// Resolves a <persName> or <orgName> selection to a canonical VIAF URI.
// VIAF covers both persons and corporate bodies; the panel shows the
// returned name-type so the editor can pick the right record.
const VIAF_TAGS = ['persName', 'orgName'] as const;
const showViafPanel = ref(false);
const viafInitialQuery = ref('');

// ── GeoNames lookup panel ─────────────────────────────────────────────────────
// Resolves a <placeName> selection to a canonical GeoNames URI. URI
// format (web vs semantic-web) comes from the plugin's config — the
// panel renders whatever the backend returns.
const GEO_TAGS = ['placeName'] as const;
const showGeonamesPanel = ref(false);
const geonamesInitialQuery = ref('');

// ── GND (lobid.org) — broad: persName / placeName / orgName.
const GND_TAGS = ['persName', 'placeName', 'orgName'] as const;
const showGndPanel = ref(false);
const gndInitialQuery = ref('');

// ── CERL Thesaurus — broad: persName / placeName / orgName
// (imprints live on <orgName>).
const CERL_TAGS = ['persName', 'placeName', 'orgName'] as const;
const showCerlPanel = ref(false);
const cerlInitialQuery = ref('');

// ── Peripleo (ancient places) — placeName only.
const PERIPLEO_TAGS = ['placeName'] as const;
const showPeripleoPanel = ref(false);
const peripleoInitialQuery = ref('');

// ── Getty AAT — term only.
const GETTY_AAT_TAGS = ['term'] as const;
const showGettyAatPanel = ref(false);
const gettyAatInitialQuery = ref('');

// ── OpenAlex — biblStruct insert (no @ref on enclosing tag).
const showOpenAlexPanel = ref(false);
const openAlexInitialQuery = ref('');

// ── Trismegistos — ID resolver; @ref application only on persName / placeName.
const TMG_TAGS = ['persName', 'placeName'] as const;
const showTrismegistosPanel = ref(false);
const trismegistosInitialKind = ref<'person' | 'place' | 'text'>('place');

// ── CrossRef DOI resolver panel ───────────────────────────────────────────────
// Paste a DOI and get back a TEI <biblStruct> fragment (populated by the
// backend via CrossRef's /works/{doi}). Complements the AI `tei_bibl_inline`
// prompt which takes free prose and guesses structure — CrossRef is
// deterministic.
const showCrossrefPanel = ref(false);
const crossrefInitialDoi = ref('');
const _DOI_RE = /^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:)?10\.\d+\/[-._;()/:A-Za-z0-9]+$/;

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
    showZonePanel.value ||
    showWikidataPanel.value ||
    showOrcidPanel.value ||
    showRorPanel.value ||
    showViafPanel.value ||
    showGeonamesPanel.value ||
    showGndPanel.value ||
    showCerlPanel.value ||
    showPeripleoPanel.value ||
    showGettyAatPanel.value ||
    showOpenAlexPanel.value ||
    showTrismegistosPanel.value ||
    showCrossrefPanel.value,
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

  // Needed for the plugin-gated toolbar buttons (ORCID / CrossRef).
  if (pluginStore.plugins.length === 0) {
    try { await pluginStore.fetchPlugins(); } catch { /* non-fatal */ }
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
 * Toggle the Wikidata entity-linking panel. On open, pre-fills the search
 * query with the current editor selection (or, if nothing is selected, the
 * text content of the entity element enclosing the cursor — best-effort).
 */
function toggleWikidataPanel(): void {
  if (showWikidataPanel.value) {
    showWikidataPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showCrossrefPanel.value = false;
  showOrcidPanel.value = false;
  showRorPanel.value = false;
  showViafPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) {
    wikidataInitialQuery.value = sel;
  } else if (cm) {
    // Extract the text inside the enclosing entity tag, if any.
    const text = cm.getValue();
    const offset = cm.indexFromPos(cm.getCursor());
    const open = text.lastIndexOf('<', offset - 1);
    const close = text.indexOf('>', open);
    const end = text.indexOf('<', close);
    if (open !== -1 && close !== -1 && end !== -1 && end > close) {
      wikidataInitialQuery.value = text.slice(close + 1, end).trim();
    } else {
      wikidataInitialQuery.value = '';
    }
  } else {
    wikidataInitialQuery.value = '';
  }
  showWikidataPanel.value = true;
}

type EntityRefOutcome =
  | { ok: true; tagName: string }
  | { ok: false; reason: 'no_enclosing_tag' }
  | { ok: false; reason: 'not_entity_tag'; tagName: string };

/** Apply the Wikidata URI chosen by the panel to the current selection. */
function applyWikidataRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, ENTITY_TAGS);
}

/**
 * Toggle the ORCID lookup panel. Pre-fills the search query with the
 * current editor selection (or the text of the enclosing persName, if
 * any), same heuristic the Wikidata panel uses.
 */
function toggleOrcidPanel(): void {
  if (showOrcidPanel.value) {
    showOrcidPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showWikidataPanel.value = false;
  showCrossrefPanel.value = false;
  showRorPanel.value = false;
  showViafPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) {
    orcidInitialQuery.value = sel;
  } else if (cm) {
    // Pull the text inside the enclosing tag when nothing is selected —
    // typical case: cursor inside <persName>Dante Alighieri</persName>.
    const text = cm.getValue();
    const offset = cm.indexFromPos(cm.getCursor());
    const open = text.lastIndexOf('<', offset - 1);
    const close = text.indexOf('>', open);
    const end = text.indexOf('<', close);
    if (open !== -1 && close !== -1 && end !== -1 && end > close) {
      orcidInitialQuery.value = text.slice(close + 1, end).trim();
    } else {
      orcidInitialQuery.value = '';
    }
  } else {
    orcidInitialQuery.value = '';
  }
  showOrcidPanel.value = true;
}

/** Apply the ORCID URI chosen by the panel — only to <persName> elements. */
function applyOrcidRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, ORCID_TAGS);
}

/**
 * Toggle the ROR lookup panel. Pre-fills the search query with the
 * current editor selection (or the text of the enclosing orgName, if
 * any), same heuristic the ORCID panel uses.
 */
function toggleRorPanel(): void {
  if (showRorPanel.value) {
    showRorPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showWikidataPanel.value = false;
  showCrossrefPanel.value = false;
  showOrcidPanel.value = false;
  showViafPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) {
    rorInitialQuery.value = sel;
  } else if (cm) {
    const text = cm.getValue();
    const offset = cm.indexFromPos(cm.getCursor());
    const open = text.lastIndexOf('<', offset - 1);
    const close = text.indexOf('>', open);
    const end = text.indexOf('<', close);
    if (open !== -1 && close !== -1 && end !== -1 && end > close) {
      rorInitialQuery.value = text.slice(close + 1, end).trim();
    } else {
      rorInitialQuery.value = '';
    }
  } else {
    rorInitialQuery.value = '';
  }
  showRorPanel.value = true;
}

/** Apply the ROR URI chosen by the panel — only to <orgName> elements. */
function applyRorRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, ROR_TAGS);
}

/**
 * Toggle the VIAF lookup panel. Pre-fills the search query with the
 * current editor selection (or the text of the enclosing persName /
 * orgName, if any), same heuristic the ORCID and ROR panels use.
 */
function toggleViafPanel(): void {
  if (showViafPanel.value) {
    showViafPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showWikidataPanel.value = false;
  showCrossrefPanel.value = false;
  showOrcidPanel.value = false;
  showRorPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) {
    viafInitialQuery.value = sel;
  } else if (cm) {
    const text = cm.getValue();
    const offset = cm.indexFromPos(cm.getCursor());
    const open = text.lastIndexOf('<', offset - 1);
    const close = text.indexOf('>', open);
    const end = text.indexOf('<', close);
    if (open !== -1 && close !== -1 && end !== -1 && end > close) {
      viafInitialQuery.value = text.slice(close + 1, end).trim();
    } else {
      viafInitialQuery.value = '';
    }
  } else {
    viafInitialQuery.value = '';
  }
  showViafPanel.value = true;
}

/** Apply the VIAF URI — targets persName or orgName (the two VIAF name types). */
function applyViafRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, VIAF_TAGS);
}

/**
 * Toggle the GeoNames lookup panel. Pre-fills with the current
 * editor selection (or the text of the enclosing placeName, if any).
 */
function toggleGeonamesPanel(): void {
  if (showGeonamesPanel.value) {
    showGeonamesPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showWikidataPanel.value = false;
  showCrossrefPanel.value = false;
  showOrcidPanel.value = false;
  showRorPanel.value = false;
  showViafPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) {
    geonamesInitialQuery.value = sel;
  } else if (cm) {
    const text = cm.getValue();
    const offset = cm.indexFromPos(cm.getCursor());
    const open = text.lastIndexOf('<', offset - 1);
    const close = text.indexOf('>', open);
    const end = text.indexOf('<', close);
    if (open !== -1 && close !== -1 && end !== -1 && end > close) {
      geonamesInitialQuery.value = text.slice(close + 1, end).trim();
    } else {
      geonamesInitialQuery.value = '';
    }
  } else {
    geonamesInitialQuery.value = '';
  }
  showGeonamesPanel.value = true;
}

/** Apply the GeoNames URI — only to <placeName> elements. */
function applyGeonamesRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, GEO_TAGS);
}


// ── Shared toggle helpers for the new authority panels ───────────────────────
//
// Extract the "pre-fill query" from the editor: current selection when
// present, else the text inside the enclosing TEI tag (best-effort
// scan for "<…>…<"). Same heuristic every older toggle function uses
// inline; factored out here to keep the six new toggles terse.

function _computePrefill(): string {
  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  if (sel) return sel;
  if (!cm) return '';
  const text = cm.getValue();
  const offset = cm.indexFromPos(cm.getCursor());
  const open = text.lastIndexOf('<', offset - 1);
  const close = text.indexOf('>', open);
  const end = text.indexOf('<', close);
  if (open !== -1 && close !== -1 && end !== -1 && end > close) {
    return text.slice(close + 1, end).trim();
  }
  return '';
}

/** Close every authority + non-authority panel except the one named. */
function _closeAllExcept(keep: string): void {
  const panels: Record<string, { value: boolean }> = {
    help: showHelpPanel,
    ai: showAiPanel,
    media: showMediaPanel,
    validation: showValidationPanel,
    wikidata: showWikidataPanel,
    orcid: showOrcidPanel,
    ror: showRorPanel,
    viaf: showViafPanel,
    geonames: showGeonamesPanel,
    gnd: showGndPanel,
    cerl: showCerlPanel,
    peripleo: showPeripleoPanel,
    gettyAat: showGettyAatPanel,
    openalex: showOpenAlexPanel,
    trismegistos: showTrismegistosPanel,
    crossref: showCrossrefPanel,
  };
  for (const [name, ref] of Object.entries(panels)) {
    if (name !== keep) ref.value = false;
  }
}

// ── GND ──────────────────────────────────────────────────────────────────────

function toggleGndPanel(): void {
  if (showGndPanel.value) { showGndPanel.value = false; return; }
  _closeAllExcept('gnd');
  gndInitialQuery.value = _computePrefill();
  showGndPanel.value = true;
}
function applyGndRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, GND_TAGS);
}

// ── CERL ─────────────────────────────────────────────────────────────────────

function toggleCerlPanel(): void {
  if (showCerlPanel.value) { showCerlPanel.value = false; return; }
  _closeAllExcept('cerl');
  cerlInitialQuery.value = _computePrefill();
  showCerlPanel.value = true;
}
function applyCerlRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, CERL_TAGS);
}

// ── Peripleo ─────────────────────────────────────────────────────────────────

function togglePeripleoPanel(): void {
  if (showPeripleoPanel.value) { showPeripleoPanel.value = false; return; }
  _closeAllExcept('peripleo');
  peripleoInitialQuery.value = _computePrefill();
  showPeripleoPanel.value = true;
}
function applyPeripleoRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, PERIPLEO_TAGS);
}

// ── Getty AAT ────────────────────────────────────────────────────────────────

function toggleGettyAatPanel(): void {
  if (showGettyAatPanel.value) { showGettyAatPanel.value = false; return; }
  _closeAllExcept('gettyAat');
  gettyAatInitialQuery.value = _computePrefill();
  showGettyAatPanel.value = true;
}
function applyGettyAatRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, GETTY_AAT_TAGS);
}

// ── OpenAlex ─────────────────────────────────────────────────────────────────

function toggleOpenAlexPanel(): void {
  if (showOpenAlexPanel.value) { showOpenAlexPanel.value = false; return; }
  _closeAllExcept('openalex');
  openAlexInitialQuery.value = _computePrefill();
  showOpenAlexPanel.value = true;
}
function applyOpenAlexFragment(xml: string): void {
  singleCm.insertXmlFragment(xml);
}

// ── Trismegistos ─────────────────────────────────────────────────────────────

/** Sniff the enclosing TEI tag name and pick the matching TM kind —
 * so persName defaults to person, placeName to place, anything else
 * to place (the most common editorial need). */
function _computeTmKindFromCursor(): 'person' | 'place' | 'text' {
  const cm = singleCm.editorInstance.value;
  if (!cm) return 'place';
  const text = cm.getValue();
  const offset = cm.indexFromPos(cm.getCursor());
  const open = text.lastIndexOf('<', offset - 1);
  if (open === -1) return 'place';
  const m = /^<\/?([A-Za-z][A-Za-z0-9:._-]*)/.exec(text.slice(open));
  if (!m) return 'place';
  const tag = m[1];
  if (tag === 'persName') return 'person';
  if (tag === 'placeName') return 'place';
  return 'place';
}

function toggleTrismegistosPanel(): void {
  if (showTrismegistosPanel.value) { showTrismegistosPanel.value = false; return; }
  _closeAllExcept('trismegistos');
  trismegistosInitialKind.value = _computeTmKindFromCursor();
  showTrismegistosPanel.value = true;
}
function applyTrismegistosRef(uri: string): EntityRefOutcome {
  return singleCm.insertEntityRef(uri, TMG_TAGS);
}

/**
 * Toggle the CrossRef DOI resolver panel. On open, pre-fills the DOI
 * input with the current editor selection when it looks like a DOI —
 * otherwise leaves it empty for the editor to paste.
 */
function toggleCrossrefPanel(): void {
  if (showCrossrefPanel.value) {
    showCrossrefPanel.value = false;
    return;
  }
  // Mutex: other panels close.
  showHelpPanel.value = false;
  showAiPanel.value = false;
  showMediaPanel.value = false;
  showValidationPanel.value = false;
  showWikidataPanel.value = false;
  showOrcidPanel.value = false;
  showRorPanel.value = false;
  showViafPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;

  const cm = singleCm.editorInstance.value;
  const sel = cm?.getSelection()?.trim() ?? '';
  crossrefInitialDoi.value = sel && _DOI_RE.test(sel) ? sel : '';
  showCrossrefPanel.value = true;
}

/** Insert the biblStruct XML returned by the CrossRef panel at the cursor. */
function applyCrossrefFragment(xml: string): void {
  singleCm.insertXmlFragment(xml);
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
const lastAiPrompt = ref<
  | 'validate'
  | 'improve'
  | 'discuss'
  | 'bibl_inline'
  | 'extract_entities'
  | 'header_scaffold'
  | null
>(null);

// XML-output prompts share the read-only CodeMirror viewer + Apply
// button: their response is raw TEI XML the user wants to paste back
// into the document. Keep this list in sync with the toolbar buttons
// below and with the response-area template.
const XML_OUTPUT_PROMPTS = ['improve', 'bibl_inline', 'extract_entities', 'header_scaffold'] as const;
const isXmlOutputPrompt = computed(() =>
  (XML_OUTPUT_PROMPTS as readonly string[]).includes(lastAiPrompt.value ?? ''),
);
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
  showWikidataPanel.value = false;
  showCrossrefPanel.value = false;
  showOrcidPanel.value = false;
  showRorPanel.value = false;
  showViafPanel.value = false;
  showGeonamesPanel.value = false;
  showGndPanel.value = false;
  showCerlPanel.value = false;
  showPeripleoPanel.value = false;
  showGettyAatPanel.value = false;
  showOpenAlexPanel.value = false;
  showTrismegistosPanel.value = false;
  // The AI store is shared across features (Bibliobuilder, the TEI
  // editor, the Validate dialog, …). When the user lands on the
  // editor's AI panel after running a Bibliobuilder pass, the
  // leftover response/chat history would render until they clicked
  // Validate/Improve. Reset on open so the panel always starts fresh.
  aiStore.resetChat();
  lastAiPrompt.value = null;
  aiNoErrors.value = false;
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

// Three "selection-in, XML-out" prompts seeded by Aracne but never
// previously surfaced in the editor toolbar. They share the same
// streaming + viewer + Apply contract as `runImproveAi`; only the
// prompt slug + lastAiPrompt label differ.
async function runBiblInlineAi(): Promise<void> {
  lastAiPrompt.value = 'bibl_inline';
  aiNoErrors.value = false;
  aiStore.clearResponse();
  await aiStore.startStream('tei_bibl_inline', {
    filename,
    collection_slug: slug,
    selection: activeEditor.value?.getSelection() || activeEditor.value?.getValue() || '',
  });
}

async function runExtractEntitiesAi(): Promise<void> {
  lastAiPrompt.value = 'extract_entities';
  aiNoErrors.value = false;
  aiStore.clearResponse();
  await aiStore.startStream('tei_extract_entities', {
    filename,
    collection_slug: slug,
    selection: activeEditor.value?.getSelection() || activeEditor.value?.getValue() || '',
  });
}

async function runHeaderScaffoldAi(): Promise<void> {
  lastAiPrompt.value = 'header_scaffold';
  aiNoErrors.value = false;
  aiStore.clearResponse();
  await aiStore.startStream('tei_header_scaffold', {
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

// ── Improve XML — read-only CM5 syntax-highlighted viewer ─────────────────────
// Shown only after streaming completes (isStreaming=false). The container ref
// is bound via v-else-if so it mounts/unmounts with each improve run.
const improveViewContainer = ref<HTMLElement | null>(null);
let improveViewInstance: CM5Editor | null = null;

watch(
  improveViewContainer,
  (el) => {
    if (el) {
      // XML mode is already registered by the main editor's useCodeMirror import.
      improveViewInstance = CodeMirror(el, {
        mode: 'application/xml',
        value: improveDisplayResponse.value,
        readOnly: true,
        lineNumbers: false,
        lineWrapping: true,
        theme: 'default',
      });
      // Expand to full content height so the outer overflow-y-auto div scrolls.
      improveViewInstance.setSize(null, 'auto');
    } else {
      improveViewInstance = null;
    }
  },
  { flush: 'post' },
);

watch(improveDisplayResponse, (val) => {
  if (improveViewInstance) {
    improveViewInstance.setValue(val);
  }
});

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
    <!-- Header bar — two rows so the toolbar never overflows the main column
         on narrow windows / when many panel toggles are active. -->
    <div class="mb-3 flex flex-shrink-0 flex-col gap-2">
      <!-- Row 1: breadcrumb + status badges -->
      <div class="flex flex-wrap items-center gap-3">
        <button
          class="text-sm text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
          @click="router.push({ name: 'collection-detail', params: { slug } })"
        >
          ← {{ slug }}
        </button>
        <span class="text-gray-300 dark:text-gray-600">/</span>
        <span class="font-mono text-sm font-semibold text-gray-800 dark:text-gray-100">{{ filename }}</span>
        <span class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          {{ t('documents.action_edit') }}
        </span>
        <span
          v-if="!isSchemaLoading && schema"
          class="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700 dark:bg-green-900/40 dark:text-green-300"
          :title="t('documents.schema_loaded')"
        >
          TEI P5
        </span>
        <span
          v-if="!isSchemaLoading && schemaWarning"
          class="max-w-sm truncate rounded bg-red-100 px-2 py-0.5 text-xs text-red-700 dark:bg-red-900/40 dark:text-red-300"
          :title="schemaWarning"
        >
          {{ t('documents.schema_error') }}
        </span>
      </div>

      <!-- Row 1.5: authority-lookup cluster.
           Dedicated strip so the main toolbar below stays focused on
           editor actions (Format / Notes / Help / AI / Media / Save).
           All six buttons are gated on their respective plugin being
           active (Wikidata too, since it was refactored from a core
           router to a non-native plugin for consistency with the rest
           of the authority set). Service-branded colours in default
           state make each chip legible at a glance; active state
           inverts to a solid fill to signal the open panel. -->
      <div class="flex flex-wrap items-center justify-end gap-1">
        <button
          v-if="wikidataPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showWikidataPanel
              ? 'border-amber-600 bg-amber-600 text-white shadow-sm dark:border-amber-500 dark:bg-amber-500'
              : 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50',
          ]"
          :title="t('wikidata.button_hint')"
          @click="toggleWikidataPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
          {{ t('wikidata.button_label') }}
        </button>

        <button
          v-if="orcidPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showOrcidPanel
              ? 'border-lime-600 bg-lime-600 text-white shadow-sm dark:border-lime-500 dark:bg-lime-500'
              : 'border-lime-400 bg-lime-50 text-lime-800 hover:bg-lime-100 dark:border-lime-700 dark:bg-lime-900/30 dark:text-lime-300 dark:hover:bg-lime-900/50',
          ]"
          :title="t('orcid.button_hint')"
          @click="toggleOrcidPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 7v10" />
            <path d="M8 17h4" />
            <path d="M8 12a4 4 0 0 1 4-4" />
          </svg>
          {{ t('orcid.button_label') }}
        </button>

        <button
          v-if="rorPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showRorPanel
              ? 'border-blue-600 bg-blue-600 text-white shadow-sm dark:border-blue-500 dark:bg-blue-500'
              : 'border-blue-300 bg-blue-50 text-blue-800 hover:bg-blue-100 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50',
          ]"
          :title="t('ror.button_hint')"
          @click="toggleRorPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="4" y="5" width="16" height="15" rx="1" />
            <path d="M8 9h8M8 13h8M8 17h5" />
            <path d="M10 5V3h4v2" />
          </svg>
          {{ t('ror.button_label') }}
        </button>

        <button
          v-if="viafPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showViafPanel
              ? 'border-red-600 bg-red-600 text-white shadow-sm dark:border-red-500 dark:bg-red-500'
              : 'border-red-300 bg-red-50 text-red-800 hover:bg-red-100 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50',
          ]"
          :title="t('viaf.button_hint')"
          @click="toggleViafPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 20 L12 4 L20 20 Z" />
            <path d="M8 14 h8" />
          </svg>
          {{ t('viaf.button_label') }}
        </button>

        <button
          v-if="geonamesPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showGeonamesPanel
              ? 'border-emerald-600 bg-emerald-600 text-white shadow-sm dark:border-emerald-500 dark:bg-emerald-500'
              : 'border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 dark:hover:bg-emerald-900/50',
          ]"
          :title="t('geonames.button_hint')"
          @click="toggleGeonamesPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 2 C7 2 3 6 3 11 c0 7 9 11 9 11 s9-4 9-11 c0-5-4-9-9-9 z" />
            <circle cx="12" cy="11" r="3" />
          </svg>
          {{ t('geonames.button_label') }}
        </button>

        <button
          v-if="gndPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showGndPanel
              ? 'border-indigo-600 bg-indigo-600 text-white shadow-sm dark:border-indigo-500 dark:bg-indigo-500'
              : 'border-indigo-300 bg-indigo-50 text-indigo-800 hover:bg-indigo-100 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50',
          ]"
          :title="t('gnd.button_hint')"
          @click="toggleGndPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="1" />
            <path d="M7 9h10M7 13h10M7 17h7" />
          </svg>
          {{ t('gnd.button_label') }}
        </button>

        <button
          v-if="cerlPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showCerlPanel
              ? 'border-yellow-600 bg-yellow-600 text-white shadow-sm dark:border-yellow-500 dark:bg-yellow-500'
              : 'border-yellow-300 bg-yellow-50 text-yellow-800 hover:bg-yellow-100 dark:border-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300 dark:hover:bg-yellow-900/50',
          ]"
          :title="t('cerl.button_hint')"
          @click="toggleCerlPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 4h9a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4z" />
            <path d="M16 4h4v13h-4" />
          </svg>
          {{ t('cerl.button_label') }}
        </button>

        <button
          v-if="peripleoPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showPeripleoPanel
              ? 'border-orange-600 bg-orange-600 text-white shadow-sm dark:border-orange-500 dark:bg-orange-500'
              : 'border-orange-300 bg-orange-50 text-orange-800 hover:bg-orange-100 dark:border-orange-700 dark:bg-orange-900/30 dark:text-orange-300 dark:hover:bg-orange-900/50',
          ]"
          :title="t('peripleo.button_hint')"
          @click="togglePeripleoPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M3 12h18" />
          </svg>
          {{ t('peripleo.button_label') }}
        </button>

        <button
          v-if="gettyAatPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showGettyAatPanel
              ? 'border-stone-700 bg-stone-700 text-white shadow-sm dark:border-stone-500 dark:bg-stone-500'
              : 'border-stone-300 bg-stone-50 text-stone-800 hover:bg-stone-100 dark:border-stone-700 dark:bg-stone-900/30 dark:text-stone-300 dark:hover:bg-stone-900/50',
          ]"
          :title="t('getty_aat.button_hint')"
          @click="toggleGettyAatPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3l7 4v10l-7 4-7-4V7z" />
          </svg>
          {{ t('getty_aat.button_label') }}
        </button>

        <button
          v-if="openalexPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showOpenAlexPanel
              ? 'border-blue-700 bg-blue-700 text-white shadow-sm dark:border-blue-500 dark:bg-blue-500'
              : 'border-blue-300 bg-blue-50 text-blue-800 hover:bg-blue-100 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50',
          ]"
          :title="t('openalex.button_hint')"
          @click="toggleOpenAlexPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M3 12a9 9 0 0 0 18 0" />
          </svg>
          {{ t('openalex.button_label') }}
        </button>

        <button
          v-if="trismegistosPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showTrismegistosPanel
              ? 'border-rose-700 bg-rose-700 text-white shadow-sm dark:border-rose-500 dark:bg-rose-500'
              : 'border-rose-300 bg-rose-50 text-rose-800 hover:bg-rose-100 dark:border-rose-700 dark:bg-rose-900/30 dark:text-rose-300 dark:hover:bg-rose-900/50',
          ]"
          :title="t('trismegistos.button_hint')"
          @click="toggleTrismegistosPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M5 3h14v18H5z" />
            <path d="M9 7h6M9 11h6M9 15h6" />
          </svg>
          {{ t('trismegistos.button_label') }}
        </button>

        <button
          v-if="crossrefPluginActive"
          :disabled="isLoading"
          :class="[
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
            showCrossrefPanel
              ? 'border-sky-600 bg-sky-600 text-white shadow-sm dark:border-sky-500 dark:bg-sky-500'
              : 'border-sky-300 bg-sky-50 text-sky-800 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-300 dark:hover:bg-sky-900/50',
          ]"
          :title="t('crossref.button_hint')"
          @click="toggleCrossrefPanel"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          {{ t('crossref.button_label') }}
        </button>
      </div>

      <!-- Row 2: action toolbar. flex-wrap so buttons spill onto extra lines
           on narrow windows rather than being clipped. -->
      <div class="flex flex-wrap items-center gap-1">

        <!-- ── Format group ────────────────────────────────────────────────── -->
        <button
          :title="t('documents.pretty_print')"
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:border-gray-200 hover:bg-gray-100 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-700"
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
          class="inline-flex items-center rounded border border-transparent p-1.5 text-gray-600 transition-colors hover:border-gray-200 hover:bg-gray-100 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-700"
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

        <span class="mx-0.5 h-5 w-px bg-gray-200 dark:bg-gray-600" aria-hidden="true"/>

        <!-- ── Notes group ─────────────────────────────────────────────────── -->
        <button
          :disabled="isLoading"
          :title="t('documents.note_alpha_title')"
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:border-amber-200 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:border-amber-700 dark:hover:bg-amber-900/30"
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
          class="inline-flex items-center gap-1.5 rounded border border-transparent px-2 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:border-amber-200 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:border-amber-700 dark:hover:bg-amber-900/30"
          @click="openNoteModal('numeric')"
        >
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"/>
          </svg>
          {{ t('documents.note_btn_numeric') }}
        </button>


        <span class="mx-0.5 h-5 w-px bg-gray-200 dark:bg-gray-600" aria-hidden="true"/>

        <!-- ── Panel toggles ──────────────────────────────────────────────── -->
        <button
          :class="[
            'inline-flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs font-medium transition-colors',
            showHelpPanel
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-700',
          ]"
          @click="showHelpPanel = !showHelpPanel; if (showHelpPanel) { showAiPanel = false; showMediaPanel = false; showValidationPanel = false; showWikidataPanel = false; showCrossrefPanel = false; showOrcidPanel = false; showRorPanel = false; showViafPanel = false; showGeonamesPanel = false; showGndPanel = false; showCerlPanel = false; showPeripleoPanel = false; showGettyAatPanel = false; showOpenAlexPanel = false; showTrismegistosPanel = false; }"
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
              ? 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-900/40 dark:text-violet-300'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-700',
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
              ? 'border-teal-300 bg-teal-50 text-teal-700 dark:border-teal-700 dark:bg-teal-900/40 dark:text-teal-300'
              : 'border-transparent text-gray-600 hover:border-gray-200 hover:bg-gray-100 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-700',
          ]"
          @click="showMediaPanel = !showMediaPanel; if (showMediaPanel) { showHelpPanel = false; showAiPanel = false; showValidationPanel = false; showWikidataPanel = false; showCrossrefPanel = false; showOrcidPanel = false; showRorPanel = false; showViafPanel = false; showGeonamesPanel = false; showGndPanel = false; showCerlPanel = false; showPeripleoPanel = false; showGettyAatPanel = false; showOpenAlexPanel = false; showTrismegistosPanel = false; }"
        >
          <!-- icon: photo -->
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z"/>
          </svg>
          {{ t('media.media_btn') }}
        </button>

        <!-- ── Status feedback ────────────────────────────────────────────── -->
        <span v-if="saved" class="inline-flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400">
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>
          </svg>
          {{ t('documents.saved') }}
        </span>
        <span v-if="saveError" class="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-red-600 hover:underline dark:text-red-400" @click="showValidationPanel = true; showHelpPanel = false; showAiPanel = false; showMediaPanel = false;">
          <svg class="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/></svg>
          {{ t('documents.save_error_see_panel') }}
        </span>

        <!-- ── Validation error re-open badge ───────────────────────────── -->
        <button
          v-if="validationResult && !validationResult.valid && !showValidationPanel"
          class="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300 dark:hover:bg-red-900/60"
          :title="t('documents.validation_errors_title')"
          @click="showValidationPanel = true; showHelpPanel = false; showAiPanel = false; showMediaPanel = false;"
        >
          <svg class="h-3 w-3 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
          </svg>
          {{ validationResult.errors.length }}
        </button>

        <!-- Authority-lookup cluster moved up to its own dedicated row above this toolbar. -->

        <!-- ── Save (& Validate) ─────────────────────────────────────────── -->
        <button
          :disabled="isSaving || isValidating || isLoading"
          class="ml-auto inline-flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
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
      <div class="flex flex-wrap gap-1.5">
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
        <button
          :disabled="aiStore.isStreaming"
          :title="t('ai.bibl_inline_hint')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runBiblInlineAi"
        >
          {{ t('ai.bibl_inline') }}
        </button>
        <button
          :disabled="aiStore.isStreaming"
          :title="t('ai.extract_entities_hint')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runExtractEntitiesAi"
        >
          {{ t('ai.extract_entities') }}
        </button>
        <button
          :disabled="aiStore.isStreaming"
          :title="t('ai.header_scaffold_hint')"
          class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          @click="runHeaderScaffoldAi"
        >
          {{ t('ai.header_scaffold') }}
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
    <div class="min-h-0 flex-1 overflow-y-auto">
      <span v-if="aiNoErrors" class="block px-4 py-3 font-mono text-sm text-green-700">{{ t('ai.no_errors_to_explain') }}</span>
      <span v-else-if="!aiStore.response && !aiStore.streamError && !aiStore.isStreaming" class="block px-4 py-3 text-xs text-gray-400">
        {{ t('ai.idle_hint') }}
      </span>
      <span v-else-if="!aiStore.response && aiStore.isStreaming" class="block animate-pulse px-4 py-3 text-gray-400">
        {{ t('ai.thinking') }}
      </span>
      <span v-else-if="aiStore.streamError" class="block px-4 py-3 font-mono text-sm text-red-600">{{ aiStore.streamError }}</span>
      <!-- XML-output prompts: read-only CM5 with syntax highlighting (only when stream done) -->
      <div
        v-else-if="isXmlOutputPrompt && !aiStore.isStreaming"
        ref="improveViewContainer"
        class="[&_.CodeMirror]:border-x-0 [&_.CodeMirror]:border-b-0 [&_.CodeMirror]:text-sm"
      />
      <!-- XML output during streaming / other prompts: plain pre-formatted text -->
      <span v-else class="block whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800">{{ aiStore.response }}</span>
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
        v-if="isXmlOutputPrompt && !aiStore.isStreaming && aiStore.response && !aiStore.streamError"
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

  <!-- Wikidata entity-linking panel -->
  <div
    v-if="showWikidataPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <WikidataLinkPanel
      :initial-query="wikidataInitialQuery"
      :on-apply="applyWikidataRef"
      @close="showWikidataPanel = false"
    />
  </div>

  <!-- ORCID lookup panel (persName only) -->
  <div
    v-if="showOrcidPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <OrcidLinkPanel
      :initial-query="orcidInitialQuery"
      :on-apply="applyOrcidRef"
      @close="showOrcidPanel = false"
    />
  </div>

  <!-- ROR lookup panel (orgName only) -->
  <div
    v-if="showRorPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <RorLinkPanel
      :initial-query="rorInitialQuery"
      :on-apply="applyRorRef"
      @close="showRorPanel = false"
    />
  </div>

  <!-- VIAF lookup panel (persName + orgName) -->
  <div
    v-if="showViafPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <ViafLinkPanel
      :initial-query="viafInitialQuery"
      :on-apply="applyViafRef"
      @close="showViafPanel = false"
    />
  </div>

  <!-- GeoNames lookup panel (placeName only) -->
  <div
    v-if="showGeonamesPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <GeonamesLinkPanel
      :initial-query="geonamesInitialQuery"
      :on-apply="applyGeonamesRef"
      @close="showGeonamesPanel = false"
    />
  </div>

  <!-- GND (lobid.org) lookup panel -->
  <div v-if="showGndPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <GndLinkPanel :initial-query="gndInitialQuery" :on-apply="applyGndRef" @close="showGndPanel = false" />
  </div>

  <!-- CERL Thesaurus lookup panel -->
  <div v-if="showCerlPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <CerlLinkPanel :initial-query="cerlInitialQuery" :on-apply="applyCerlRef" @close="showCerlPanel = false" />
  </div>

  <!-- Peripleo lookup panel (placeName only) -->
  <div v-if="showPeripleoPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <PeripleoLinkPanel :initial-query="peripleoInitialQuery" :on-apply="applyPeripleoRef" @close="showPeripleoPanel = false" />
  </div>

  <!-- Getty AAT lookup panel (term only) -->
  <div v-if="showGettyAatPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <GettyAatLinkPanel :initial-query="gettyAatInitialQuery" :on-apply="applyGettyAatRef" @close="showGettyAatPanel = false" />
  </div>

  <!-- OpenAlex panel (biblStruct insert) -->
  <div v-if="showOpenAlexPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <OpenAlexPanel :initial-query="openAlexInitialQuery" :on-insert="applyOpenAlexFragment" @close="showOpenAlexPanel = false" />
  </div>

  <!-- Trismegistos lookup panel (persName + placeName) -->
  <div v-if="showTrismegistosPanel && !isLoading" class="flex flex-shrink-0 flex-col border-l border-gray-200" :style="{ width: panelWidth + 'px' }">
    <TrismegistosLinkPanel :initial-kind="trismegistosInitialKind" :on-apply="applyTrismegistosRef" @close="showTrismegistosPanel = false" />
  </div>

  <!-- CrossRef DOI resolver panel -->
  <div
    v-if="showCrossrefPanel && !isLoading"
    class="flex flex-shrink-0 flex-col border-l border-gray-200"
    :style="{ width: panelWidth + 'px' }"
  >
    <CrossrefPanel
      :initial-doi="crossrefInitialDoi"
      :on-insert="applyCrossrefFragment"
      @close="showCrossrefPanel = false"
    />
  </div>

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
