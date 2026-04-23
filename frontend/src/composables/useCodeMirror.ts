/**
 * useCodeMirror — Vue 3 composable wrapping CodeMirror 5.
 *
 * Initialises a CM5 instance on a container <div>, loads the TEI P5 schema
 * for XML autocomplete, and exposes getValue/setValue so the parent component
 * never touches the CM5 API directly.
 *
 * Addons included (all shipped with codemirror@5):
 *   mode/xml, fold/xml-fold, fold/foldgutter, edit/closetag,
 *   edit/matchtags, selection/active-line, search/search,
 *   search/searchcursor, search/jump-to-line, dialog/dialog,
 *   hint/show-hint, hint/xml-hint, display/fullscreen,
 *   display/autorefresh, scroll/annotatescrollbar, comment/comment
 */

import { ref, watch, toRaw, onBeforeUnmount, type Ref } from 'vue';
import CodeMirror, { type Editor } from 'codemirror';
import type { CM5Schema } from '@/utils/teiSchema';

// ── Addon side-effect imports ──────────────────────────────────────────────────
import 'codemirror/mode/xml/xml';
import 'codemirror/addon/fold/foldcode';
import 'codemirror/addon/fold/foldgutter';
import 'codemirror/addon/fold/xml-fold';
import 'codemirror/addon/edit/closetag';
import 'codemirror/addon/edit/matchtags';
import 'codemirror/addon/selection/active-line';
import 'codemirror/addon/search/search';
import 'codemirror/addon/search/searchcursor';
import 'codemirror/addon/search/jump-to-line';
import 'codemirror/addon/dialog/dialog';
import 'codemirror/addon/hint/show-hint';
import 'codemirror/addon/hint/xml-hint';
import 'codemirror/addon/display/fullscreen';
import 'codemirror/addon/display/autorefresh';
import 'codemirror/addon/scroll/annotatescrollbar';
import 'codemirror/addon/comment/comment';

// ── CSS ────────────────────────────────────────────────────────────────────────
import 'codemirror/lib/codemirror.css';
import 'codemirror/addon/fold/foldgutter.css';
import 'codemirror/addon/dialog/dialog.css';
import 'codemirror/addon/hint/show-hint.css';
import 'codemirror/addon/display/fullscreen.css';

// ── Autocomplete trigger helpers (ported from cm-tei-schema.js) ────────────────

function completeAfter(cm: Editor, pred?: () => boolean): typeof CodeMirror.Pass {
  if (!pred || pred()) {
    window.setTimeout(() => {
      if (!(cm as unknown as { state: { completionActive: unknown } }).state.completionActive) {
        cm.showHint({ completeSingle: false });
      }
    }, 100);
  }
  return CodeMirror.Pass;
}

function completeIfAfterLt(cm: Editor): typeof CodeMirror.Pass {
  return completeAfter(cm, () => {
    const cur = cm.getCursor();
    return cm.getRange(CodeMirror.Pos(cur.line, cur.ch - 1), cur) === '<';
  });
}

function completeIfInTag(cm: Editor): typeof CodeMirror.Pass {
  return completeAfter(cm, () => {
    const tok = cm.getTokenAt(cm.getCursor());
    if (
      tok.type === 'string' &&
      (!/['"]/.test(tok.string.charAt(tok.string.length - 1)) || tok.string.length === 1)
    ) {
      return false;
    }
    const inner = CodeMirror.innerMode(cm.getMode(), tok.state).state as { tagName?: string };
    return !!inner.tagName;
  });
}

// ── Composable ─────────────────────────────────────────────────────────────────

export interface UseCodeMirrorOptions {
  /** Initial XML content to load into the editor. */
  initialValue?: string;
  /** Parsed TEI schema from loadTeiSchema(). Enables XML autocomplete. */
  schema?: CM5Schema;
  /** Make the editor read-only. Default: false. */
  readOnly?: boolean;
  /** Called whenever the editor content changes. */
  onChange?: (value: string) => void;
  /**
   * Number of lines to lock at the top and bottom of the document.
   * Changes that touch those lines are cancelled via beforeChange.
   * A visual class `cm-locked-line` is applied for styling.
   *
   * 1 → locks first + last line (e.g. <teiHeader> / </teiHeader>)
   * 2 → locks first 2 + last 2 lines (e.g. <text><body> / </body></text>)
   */
  lockBoundaryLines?: number;
  /**
   * Called when the user clicks on a <ref> inline marker.
   * Receives the note ID, its type, and the current note text content.
   * Use this to open an edit modal pre-filled with the existing note.
   */
  onRefClick?: (noteId: string, noteType: 'alpha' | 'numeric', currentContent: string) => void;
}

export function useCodeMirror(
  containerRef: Ref<HTMLElement | null>,
  options: UseCodeMirrorOptions = {},
) {
  const editorInstance = ref<Editor | null>(null);
  const isFullscreen = ref(false);

  function getValue(): string {
    return editorInstance.value?.getValue() ?? '';
  }

  function setValue(content: string): void {
    if (!editorInstance.value) return;
    editorInstance.value.setValue(content);
    // Reset scroll and cursor to the top after a full document swap.
    // CM5's setValue resets the cursor to {line:0,ch:0} but does NOT reliably
    // reset the pixel scroll offset when the container is hidden (v-show:false).
    // Without this, a subsequent autoRefresh repaint starts at the old scroll
    // position and the first N lines appear missing.
    editorInstance.value.scrollTo(0, 0);
    // Force a synchronous display update after a full document swap.
    // Without this, CM5's internal line-measure cache is stale and
    // click events crash with "Cannot read properties of undefined (reading 'map')".
    editorInstance.value.refresh();
    // Re-apply read-only markers for <ref> tags that may be present in the new content.
    markRefTagsOnInstance(editorInstance.value);
  }

  function toggleFullscreen(): void {
    if (!editorInstance.value) return;
    const next = !editorInstance.value.getOption('fullScreen');
    editorInstance.value.setOption('fullScreen', next);
    isFullscreen.value = next;
  }

  function foldAll(): void {
    if (!editorInstance.value) return;
    const cm = editorInstance.value;
    const count = cm.lineCount();
    for (let i = 0; i <= count; i++) {
      cm.foldCode(CodeMirror.Pos(i, 0));
    }
  }

  function refresh(): void {
    // Force CM5 to re-measure and repaint — needed after the container
    // transitions from display:none (v-show) to visible.
    editorInstance.value?.refresh();
  }

  /**
   * Insert a TEI footnote at the current cursor position.
   *
   * Two writes are performed atomically inside a CM5 operation:
   *   1. A self-closing <ref target="#id" type="…"/> is inserted at the cursor.
   *   2. A <note xml:id="id" type="…"> element is appended to the nearest
   *      ancestor container element's <span type="notes"> block (or a new one
   *      is created before the container's closing tag if none exists yet).
   *
   * Container elements searched in order (nearest match wins):
   *   <div>     — body sections (narratio, petitio, …)
   *   <summary> — teiHeader msContents summary
   *
   * Both replaceRange calls use origin '+programmatic' so the beforeChange
   * boundary-lock guard allows them through even in split mode.
   */
  function insertNote(
    type: 'alpha' | 'numeric',
    noteId: string,
    noteContent: string,
  ): void {
    const cm = editorInstance.value;
    if (!cm) return;

    const cursor = cm.getCursor();
    const refTag = `<ref target="#${noteId}" type="${type}"/>`;
    // Cursor position right after the inserted <ref> tag.
    // Captured before the operation so we can restore it after the
    // setValue round-trip that follows.
    const cursorAfterRef = { line: cursor.line, ch: cursor.ch + refTag.length };

    cm.operation(() => {
      // ── 1. Insert <ref> at cursor ──────────────────────────────────────────
      cm.replaceRange(refTag, cursor, undefined, '+programmatic');

      // ── 2. Find the nearest ancestor container closing tag ─────────────────
      // Try each candidate container tag and return the nearest match.
      const NOTE_CONTAINERS = ['div', 'summary'];
      const newText  = cm.getValue();
      const refOffset = cm.indexFromPos(cursor) + refTag.length;

      function nearestContainerClose(text: string, from: number): number {
        let best = -1;
        for (const tag of NOTE_CONTAINERS) {
          const open  = `<${tag}`;
          const close = `</${tag}>`;
          let depth = 0;
          let i = from;
          while (i < text.length) {
            if (text.startsWith(close, i)) {
              if (depth === 0) { if (best === -1 || i < best) best = i; break; }
              depth--;
              i += close.length;
              continue;
            }
            if (text.startsWith(open, i)) {
              const next = text[i + open.length];
              if (next === '>' || next === ' ' || next === '\t' || next === '\n' || next === '/') {
                depth++;
                i += open.length;
                continue;
              }
            }
            i++;
          }
        }
        return best;
      }

      const containerCloseOffset = nearestContainerClose(newText, refOffset);
      if (containerCloseOffset === -1) return; // no known container found

      // ── 3. Decide where to insert the <note> ──────────────────────────────
      // Priority order for an existing notes block in [refOffset, containerClose]:
      //   a) <span type="notes"> … </span>  (open form — already has notes)
      //   b) <span type="notes"/>            (self-closing placeholder from template)
      //   c) none → create a new block
      const segment = newText.slice(refOffset, containerCloseOffset);
      const openSpanIdx       = segment.lastIndexOf('<span type="notes">');
      const placeholderIdx    = segment.lastIndexOf('<span type="notes"/>');

      let noteMarkup: string;
      let insertFrom: number;
      let insertTo: number | undefined; // defined only when replacing a range

      if (openSpanIdx !== -1) {
        // (a) Append inside existing open <span type="notes">.
        const absSpanStart   = refOffset + openSpanIdx;
        const closeSpanOffset = newText.indexOf('</span>', absSpanStart);
        if (closeSpanOffset === -1) return; // malformed
        noteMarkup = `\n        <note xml:id="${noteId}" type="${type}">${noteContent}</note>`;
        insertFrom = closeSpanOffset;
      } else if (placeholderIdx !== -1) {
        // (b) Replace self-closing placeholder with a full notes block.
        const absPlaceholder = refOffset + placeholderIdx;
        noteMarkup = [
          '<span type="notes">',
          `        <note xml:id="${noteId}" type="${type}">${noteContent}</note>`,
          '      </span>',
        ].join('\n');
        insertFrom = absPlaceholder;
        insertTo   = absPlaceholder + '<span type="notes"/>'.length;
      } else {
        // (c) Create a brand-new <span type="notes"> before the container close.
        noteMarkup = [
          '',
          '      <span type="notes">',
          `        <note xml:id="${noteId}" type="${type}">${noteContent}</note>`,
          '      </span>',
        ].join('\n');
        insertFrom = containerCloseOffset;
      }

      const fromPos = cm.posFromIndex(insertFrom);
      const toPos   = insertTo !== undefined ? cm.posFromIndex(insertTo) : undefined;
      cm.replaceRange(noteMarkup, fromPos, toPos, '+programmatic');
    });

    // ── 4. Full document rebuild to fix CM5's internal state ──────────────
    // After two replaceRange calls, CM5's view array contains new LineView
    // objects whose .measure property is uninitialised. Any call to
    // coordsChar or findPosV (arrow-key navigation) crashes in
    // prepareMeasureForLine with "Cannot read properties of undefined
    // (reading 'map')". cm.refresh() only clears character-width caches —
    // it does NOT rebuild LineView.measure for new lines.
    //
    // The only reliable reset is cm.setValue() with the same content, which
    // internally calls makeChange({full:true}) and rebuilds every line
    // object from scratch. We wrap in rAF so CM5 finishes its own rendering
    // pipeline before the rebuild, then restore cursor + focus.
    requestAnimationFrame(() => {
      const content = cm.getValue();
      cm.setValue(content);
      cm.refresh();
      markRefTagsOnInstance(cm);
      cm.setCursor(cursorAfterRef);
      cm.focus();
    });
  }

  /**
   * Scan the document for all <ref target="#..." type="…"/> patterns and
   * apply a read-only TextMarker with class `cm-note-ref` to each one.
   * Existing ref markers are cleared first to avoid duplicates (e.g. after
   * setValue() replaces the full document content).
   */
  function markRefTagsOnInstance(instance: Editor): void {
    // Clear only markers that wrap a <ref …/> tag.
    // Unconditional getAllMarks().clear() would also remove fold markers
    // (collapsed TextMarkers created by the fold addon). Clearing those
    // unexpectedly expands folded sections, changes the line count, and
    // corrupts CM5's viewport state — causing "Cannot read properties of
    // undefined (reading 'map')" crashes in prepareMeasureForLine on the
    // next vertical cursor movement.
    instance.getAllMarks().forEach((m) => {
      const range = m.find() as { from: CodeMirror.Position; to: CodeMirror.Position } | undefined;
      if (!range || !('from' in range)) return;
      if (instance.getRange(range.from, range.to).startsWith('<ref ')) m.clear();
    });

    const text = instance.getValue();
    const pattern = /<ref target="#([^"]+)" type="(alpha|numeric)"\/>/g;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      const from = instance.posFromIndex(match.index);
      const to   = instance.posFromIndex(match.index + match[0].length);
      instance.markText(from, to, {
        className: 'cm-note-ref',
        title: match[1],
      });
    }
  }

  /**
   * Return the text content of the <note xml:id="noteId"> element, or ''
   * if not found. Used to pre-fill the edit modal.
   */
  function getNoteContent(noteId: string): string {
    const cm = editorInstance.value;
    if (!cm) return '';
    const pattern = new RegExp(
      `<note xml:id="${noteId}" type="(?:alpha|numeric)">(.*?)</note>`,
      's',
    );
    const match = pattern.exec(cm.getValue());
    return match ? match[1] : '';
  }

  /**
   * Replace the text content of an existing <note xml:id="noteId"> element.
   * Used when the editor re-opens a ref marker and the user saves edits.
   */
  function editNote(noteId: string, newContent: string): void {
    const cm = editorInstance.value;
    if (!cm) return;
    const text = cm.getValue();
    const pattern = new RegExp(
      `(<note xml:id="${noteId}" type="(?:alpha|numeric)">)(.*?)(</note>)`,
      's',
    );
    const match = pattern.exec(text);
    if (!match) return;
    const contentStart = match.index + match[1].length;
    const contentEnd   = contentStart + match[2].length;
    cm.replaceRange(
      newContent,
      cm.posFromIndex(contentStart),
      cm.posFromIndex(contentEnd),
      '+programmatic',
    );
  }

  /**
   * Delete a TEI note by ID: removes both the inline <ref> marker and the
   * corresponding <note> element. If the <span type="notes"> block becomes
   * empty after the removal, it is deleted as well.
   *
   * Removals are done end-first (note block, then ref) so that the first
   * replaceRange does not shift the position of the second.
   */
  function deleteNote(noteId: string): void {
    const cm = editorInstance.value;
    if (!cm) return;
    const savedCursor = cm.getCursor();

    cm.operation(() => {
      const text = cm.getValue();

      // ── 1. Remove the <note> element (and its <span> if it becomes empty) ──
      const noteRe = new RegExp(
        `<note xml:id="${noteId}" type="(?:alpha|numeric)">[\\s\\S]*?</note>`,
      );
      const noteMatch = noteRe.exec(text);
      if (!noteMatch) return;

      // Determine whether the enclosing <span type="notes"> becomes empty.
      const spanOpenTag = '<span type="notes">';
      const spanOpenIdx = text.lastIndexOf(spanOpenTag, noteMatch.index);

      let blockStart = noteMatch.index;
      let blockEnd   = noteMatch.index + noteMatch[0].length;

      if (spanOpenIdx !== -1) {
        const afterSpanOpen   = text.slice(spanOpenIdx + spanOpenTag.length);
        const spanCloseRelIdx = afterSpanOpen.indexOf('</span>');
        if (spanCloseRelIdx !== -1) {
          const noteCountInSpan =
            (afterSpanOpen.slice(0, spanCloseRelIdx).match(/<note /g) ?? []).length;

          if (noteCountInSpan <= 1) {
            // Only note — remove the entire <span type="notes">…</span> block.
            const spanEnd = spanOpenIdx + spanOpenTag.length + spanCloseRelIdx + '</span>'.length;
            // Consume the leading whitespace / newline before the span.
            let start = spanOpenIdx;
            while (start > 0 && (text[start - 1] === ' ' || text[start - 1] === '\t')) start--;
            if (start > 0 && text[start - 1] === '\n') start--;
            blockStart = start;
            blockEnd   = spanEnd;
          } else {
            // Other notes remain — remove only this <note> line.
            let start = noteMatch.index;
            while (start > 0 && (text[start - 1] === ' ' || text[start - 1] === '\t')) start--;
            if (start > 0 && text[start - 1] === '\n') start--;
            blockStart = start;
          }
        }
      }

      cm.replaceRange(
        '',
        cm.posFromIndex(blockStart),
        cm.posFromIndex(blockEnd),
        '+programmatic',
      );

      // ── 2. Remove the <ref target="#noteId" .../> (earlier in document) ────
      const updatedText = cm.getValue();
      const refRe    = new RegExp(`<ref target="#${noteId}" type="(?:alpha|numeric)"\\/>`);
      const refMatch = refRe.exec(updatedText);
      if (!refMatch) return;

      cm.replaceRange(
        '',
        cm.posFromIndex(refMatch.index),
        cm.posFromIndex(refMatch.index + refMatch[0].length),
        '+programmatic',
      );
      // The TextMarker covering the <ref> is automatically invalidated by CM5
      // when its content range is removed; no explicit clear() needed.
    });

    // Same full-rebuild pattern as insertNote: replaceRange leaves new/removed
    // LineView objects with uninitialised .measure, crashing coordsChar.
    requestAnimationFrame(() => {
      const content = cm.getValue();
      cm.setValue(content);
      cm.refresh();
      markRefTagsOnInstance(cm);
      cm.setCursor(savedCursor);
      cm.focus();
    });
  }

  /**
   * Insert a TEI <pb> page-break element at the current cursor position.
   *
   * Produces: <pb facs="#surfaceId"/>
   */
  function insertPageBreak(surfaceId: string): void {
    const cm = editorInstance.value;
    if (!cm) return;

    const cursor = cm.getCursor();
    const snippet = `<pb facs="#${surfaceId}"/>`;
    cm.replaceRange(snippet, cursor, undefined, '+programmatic');
    const after = { line: cursor.line, ch: cursor.ch + snippet.length };
    cm.setCursor(after);
    cm.focus();
  }

  /**
   * Insert a TEI <figure> element at the current cursor position.
   *
   * Produces:
   *   <figure><graphic url="URL"/></figure>
   *
   * The cursor is placed after the inserted block.
   */
  function insertFigure(url: string): void {
    const cm = editorInstance.value;
    if (!cm) return;

    const cursor = cm.getCursor();
    const snippet = `<figure><graphic url="${url}"/></figure>`;
    cm.replaceRange(snippet, cursor, undefined, '+programmatic');
    const after = { line: cursor.line, ch: cursor.ch + snippet.length };
    cm.setCursor(after);
    cm.focus();
  }

  /**
   * Insert or append a ``facs="#zoneId"`` attribute on the nearest opening tag
   * relative to the cursor position.
   *
   * The algorithm scans backwards from the cursor to find the opening ``<`` of
   * the enclosing tag, then inserts the facs attribute before the closing ``>``.
   * If the tag already has a ``facs`` attribute (multi-zone case), the new id
   * is appended space-separated — matching the TEI spec for ``facs="#z1 #z2"``.
   *
   * Returns ``true`` on success, ``false`` when no suitable tag is found at the
   * cursor position.
   */
  function insertFacsRef(zoneId: string): boolean {
    const cm = editorInstance.value;
    if (!cm) return false;

    const text = cm.getValue();
    const cursorOffset = cm.indexFromPos(cm.getCursor());

    // Scan backwards to find the opening '<' of the nearest opening tag.
    // We do NOT break on '>' because the cursor may be inside the text
    // content of an element (e.g. "<w>tex|t</w>") — in that case the
    // backwards scan must keep going past the '>' of the opening tag until
    // it finds the '<'.  We only stop on a closing tag '</': that marks a
    // true element boundary where there is no enclosing opening tag to attach
    // the facs attribute to.
    // Skip processing instructions (<?).
    let tagStart = -1;
    for (let i = cursorOffset - 1; i >= 0; i--) {
      if (text[i] === '<') {
        if (text[i + 1] === '/' || text[i + 1] === '?') break; // element boundary
        tagStart = i;
        break;
      }
    }
    if (tagStart === -1) return false;

    // Find the closing '>' of this opening tag.
    const tagEnd = text.indexOf('>', tagStart);
    if (tagEnd === -1) return false;

    const tagText = text.slice(tagStart, tagEnd + 1);
    const existingMatch = /\bfacs="([^"]*)"/.exec(tagText);
    let newTag: string;

    if (existingMatch) {
      // Multi-zone: append the new id if it is not already present.
      const existingRefs = existingMatch[1].split(' ');
      const newRef = `#${zoneId}`;
      if (existingRefs.includes(newRef)) return true; // idempotent
      const newVal = `${existingMatch[1]} ${newRef}`;
      newTag = tagText.replace(/\bfacs="[^"]*"/, `facs="${newVal}"`);
    } else {
      // Insert facs attribute before the closing '>' or '/>'.
      if (tagText.endsWith('/>')) {
        newTag = tagText.slice(0, -2) + ` facs="#${zoneId}"/>`;
      } else {
        newTag = tagText.slice(0, -1) + ` facs="#${zoneId}">`;
      }
    }

    cm.replaceRange(newTag, cm.posFromIndex(tagStart), cm.posFromIndex(tagEnd + 1), '+programmatic');
    cm.focus();
    return true;
  }

  /**
   * Result of ``insertEntityRef``.
   *
   * - ``ok: true`` — the enclosing tag was found, matched the whitelist, and
   *   the ``@ref`` attribute was written (or replaced). ``tagName`` is the
   *   local-name of the element that received the attribute.
   * - ``ok: false`` — explains why the attribute could not be written:
   *     * ``no_enclosing_tag``: cursor is not inside a well-formed opening tag
   *       (e.g. it sits right after a ``</p>`` closure).
   *     * ``not_entity_tag``: the enclosing tag is not in ``allowedTags``
   *       (the tag name is returned for the caller's error message).
   */
  type EntityRefResult =
    | { ok: true; tagName: string }
    | { ok: false; reason: 'no_enclosing_tag' }
    | { ok: false; reason: 'not_entity_tag'; tagName: string };

  /**
   * Write (or replace) a ``@ref`` attribute on the TEI entity element
   * enclosing the cursor. Used by the "Link entity" sidebar to attach a
   * Wikidata / VIAF / GeoNames canonical URI to a ``<persName>`` /
   * ``<placeName>`` / ``<orgName>`` element without requiring the editor
   * to hand-edit XML.
   *
   * The caller passes an explicit ``allowedTags`` whitelist so the set of
   * "linkable" elements stays in one place (the sidebar calling code) and
   * can be extended per project.
   */
  function insertEntityRef(
    uri: string,
    allowedTags: readonly string[],
  ): EntityRefResult {
    const cm = editorInstance.value;
    if (!cm) return { ok: false, reason: 'no_enclosing_tag' };

    const text = cm.getValue();
    const cursorOffset = cm.indexFromPos(cm.getCursor());

    // Scan backwards to the opening '<' of the enclosing tag. Same rule as
    // insertFacsRef: stop on a closing '</' or PI '<?' boundary — those
    // mean there is no enclosing opening tag at the cursor position.
    let tagStart = -1;
    for (let i = cursorOffset - 1; i >= 0; i--) {
      if (text[i] === '<') {
        if (text[i + 1] === '/' || text[i + 1] === '?') break;
        tagStart = i;
        break;
      }
    }
    if (tagStart === -1) return { ok: false, reason: 'no_enclosing_tag' };

    const tagEnd = text.indexOf('>', tagStart);
    if (tagEnd === -1) return { ok: false, reason: 'no_enclosing_tag' };

    const tagText = text.slice(tagStart, tagEnd + 1);
    // Extract the local-name (first word after '<', stripping any namespace prefix).
    const nameMatch = /^<([A-Za-z_][\w.-]*)(?::([\w.-]+))?/.exec(tagText);
    if (!nameMatch) return { ok: false, reason: 'no_enclosing_tag' };
    // local-name = part after the optional colon (XML namespace prefix).
    const tagName = nameMatch[2] ?? nameMatch[1];

    if (!allowedTags.includes(tagName)) {
      return { ok: false, reason: 'not_entity_tag', tagName };
    }

    const safeUri = uri.replace(/"/g, '&quot;');
    let newTag: string;
    const existing = /\bref="([^"]*)"/.exec(tagText);
    if (existing) {
      if (existing[1] === safeUri) return { ok: true, tagName }; // idempotent
      newTag = tagText.replace(/\bref="[^"]*"/, `ref="${safeUri}"`);
    } else if (tagText.endsWith('/>')) {
      newTag = tagText.slice(0, -2) + ` ref="${safeUri}"/>`;
    } else {
      newTag = tagText.slice(0, -1) + ` ref="${safeUri}">`;
    }

    cm.replaceRange(
      newTag,
      cm.posFromIndex(tagStart),
      cm.posFromIndex(tagEnd + 1),
      '+programmatic',
    );
    cm.focus();
    return { ok: true, tagName };
  }

  function prettyPrint(): void {
    if (!editorInstance.value) return;
    const cm = editorInstance.value;
    const count = cm.lineCount();
    cm.operation(() => {
      for (let i = 0; i <= count; i++) {
        cm.indentLine(i, 'smart');
      }
    });
  }

  function initializeEditor(el: HTMLElement): void {
    const hintOptions = options.schema
      ? { schemaInfo: options.schema, completeSingle: false }
      : undefined;

    const instance = CodeMirror(el, {
      mode: 'application/xml',
      lineNumbers: true,
      lineWrapping: true,
      styleActiveLine: true,
      autoRefresh: true,
      foldGutter: true,
      // matchTags disabled: the addon crashes with "Cannot read properties of
      // undefined (reading 'from')" when setValue() invalidates TextMarkers that
      // a pending doMatchTags callback still holds. Ctrl+J (toMatchingTag) still
      // works — it uses a separate code path that does not depend on this addon.
      matchTags: false,
      autoCloseTags: true,
      readOnly: options.readOnly ?? false,
      gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
      hintOptions,
      extraKeys: {
        // Autocomplete triggers (only active when schema is loaded)
        ...(options.schema
          ? {
              "'<'": completeIfAfterLt,
              "'/'": completeIfAfterLt,
              "' '": completeIfInTag,
              "'='": completeIfInTag,
            }
          : {}),
        'Ctrl-Space': 'autocomplete',
        // Navigation
        'Ctrl-J': 'toMatchingTag',
        'Ctrl-/': 'toggleComment',
        // Fullscreen
        'F11': (cm: Editor) => {
          const next = !cm.getOption('fullScreen');
          cm.setOption('fullScreen', next);
          isFullscreen.value = next;
        },
        'Esc': (cm: Editor) => {
          if (cm.getOption('fullScreen')) {
            cm.setOption('fullScreen', false);
            isFullscreen.value = false;
          }
        },
      },
    });

    if (options.initialValue) {
      instance.setValue(options.initialValue);
      // Auto-indent on load
      const count = instance.lineCount();
      instance.operation(() => {
        for (let i = 0; i <= count; i++) {
          instance.indentLine(i, 'smart');
        }
      });
      // Reset scroll and cursor to the top of the document.
      // The indentLine loop leaves the cursor at the last processed line; without
      // this reset the viewport starts there when the container first becomes visible.
      instance.scrollTo(0, 0);
      instance.setCursor({ line: 0, ch: 0 });
      // Mark any <ref> tags already present in the initial content.
      markRefTagsOnInstance(instance);
    }

    if (options.onChange) {
      instance.on('change', (cm) => {
        options.onChange!(cm.getValue());
      });
    }

    // Protect <ref> inline markers from direct keyboard/paste editing.
    // The visual marker (cm-note-ref class) carries no readOnly flag — that
    // would block cursor navigation in CM5. Instead, we intercept beforeChange
    // and cancel any edit whose range overlaps a <ref> marker.
    // +programmatic and setValue origins are exempt (note insertion / loading).
    instance.on('beforeChange', (_cm, change) => {
      if (change.origin === '+programmatic' || change.origin === 'setValue') return;
      const isRefMark = (m: CodeMirror.TextMarker): boolean => {
        const r = m.find() as { from: CodeMirror.Position; to: CodeMirror.Position } | undefined;
        return !!r && 'from' in r && instance.getRange(r.from, r.to).startsWith('<ref ');
      };
      if (
        instance.findMarksAt(change.from).some(isRefMark) ||
        instance.findMarksAt(change.to).some(isRefMark) ||
        instance.findMarks(change.from, change.to).some(isRefMark)
      ) {
        change.cancel();
      }
    });

    if (options.lockBoundaryLines) {
      const n = options.lockBoundaryLines;

      // Cancel any user change that touches the top-n or bottom-n lines.
      // origin 'setValue' is allowed so programmatic content replacement works.
      instance.on('beforeChange', (cm, change) => {
        if (change.origin === 'setValue' || change.origin === '+programmatic') return;
        const last = cm.lastLine();
        if (change.from.line < n || change.to.line > last - n) {
          change.cancel();
        }
      });

      // Apply the visual lock class to the top-n and bottom-n lines.
      const markLockedLines = (cm: typeof instance) => {
        const last = cm.lastLine();
        for (let i = 0; i < n; i++) {
          cm.addLineClass(i, 'wrap', 'cm-locked-line');
        }
        for (let i = last - (n - 1); i <= last; i++) {
          cm.addLineClass(i, 'wrap', 'cm-locked-line');
        }
      };
      markLockedLines(instance);
    }

    // Detect clicks on <ref> markers and fire onRefClick so the parent can
    // open a pre-filled edit modal. preventDefault() stops CM5 from placing
    // the cursor inside the read-only marker range.
    if (options.onRefClick) {
      instance.on('mousedown', (_cm, event) => {
        const pos = instance.coordsChar({ left: event.clientX, top: event.clientY });
        const markers = instance.findMarksAt(pos);
        const refMarker = markers.find((m) => {
          const r = m.find() as { from: CodeMirror.Position; to: CodeMirror.Position } | undefined;
          if (!r || !('from' in r)) return false;
          return instance.getRange(r.from, r.to).startsWith('<ref ');
        });
        if (!refMarker) return;
        event.preventDefault();
        const range = refMarker.find() as { from: CodeMirror.Position; to: CodeMirror.Position };
        const refText  = instance.getRange(range.from, range.to);
        const idMatch   = /target="#([^"]+)"/.exec(refText);
        const typeMatch = /type="(alpha|numeric)"/.exec(refText);
        if (idMatch && typeMatch) {
          const noteId   = idMatch[1];
          const noteType = typeMatch[1] as 'alpha' | 'numeric';
          options.onRefClick!(noteId, noteType, getNoteContent(noteId));
        }
      });
    }

    editorInstance.value = instance;

    // Watch for schema arriving after the editor is initialized (async load).
    // Update hintOptions and extraKeys so Ctrl+Space and trigger keys work.
    watch(
      () => options.schema,
      (s) => {
        if (!editorInstance.value) return;
        editorInstance.value.setOption(
          'hintOptions',
          s ? { schemaInfo: s, completeSingle: false } : undefined,
        );
        const current = (
          editorInstance.value.getOption('extraKeys') ?? {}
        ) as unknown as CodeMirror.KeyMap;
        if (s) {
          current["'<'"] = completeIfAfterLt;
          current["'/'"] = completeIfAfterLt;
          current["' '"] = completeIfInTag;
          current["'='"] = completeIfInTag;
        } else {
          delete current["'<'"];
          delete current["'/'"];
          delete current["' '"];
          delete current["'='"];
        }
        editorInstance.value.setOption('extraKeys', current);
      },
    );
  }

  // Watch the container ref with flush:'post' so CM5 initialises the moment
  // the element is actually inserted into the DOM (handles both the always-visible
  // case and the v-if case where the element appears later).
  // When the container is removed from the DOM (v-if becomes false), null out the
  // instance so that the next appearance of the element triggers re-initialisation
  // with the current initialValue getter.  This is essential for components that
  // reuse the same composable across multiple v-if toggling cycles (e.g. a form
  // that opens/closes for different records without unmounting the parent view).
  watch(
    containerRef,
    (el) => {
      if (el && !editorInstance.value) {
        // toRaw() unwraps any Vue reactive Proxy so CodeMirror receives the
        // actual HTMLElement.  Browsers validate DOM types internally: a Proxy
        // wrapping an HTMLElement fails "instanceof HTMLElement" checks and
        // causes CM5 to throw "place is not a function".
        const rawEl = toRaw(el) as HTMLElement;
        // Defer to the next animation frame so the browser completes layout
        // before CodeMirror measures the container (needed when nested v-ifs
        // become true in the same update cycle).
        requestAnimationFrame(() => {
          // isConnected verifies the element is still in the live DOM;
          // it may have been removed between the watch trigger and the rAF.
          if (rawEl.isConnected && !editorInstance.value) {
            initializeEditor(rawEl);
          }
        });
      } else if (!el) {
        // Clear the autoRefresh polling timer (set by autorefresh addon when the
        // editor initialises inside a display:none container) before dropping the
        // reference, so the timer does not keep the CM5 instance alive indefinitely.
        const raw = toRaw(editorInstance.value) as (Editor & { state: { autoRefreshTimer?: ReturnType<typeof setTimeout> } }) | null;
        if (raw?.state?.autoRefreshTimer !== undefined) {
          clearTimeout(raw.state.autoRefreshTimer);
        }
        editorInstance.value = null;
      }
    },
    { flush: 'post' },
  );

  onBeforeUnmount(() => {
    // CM5 does not have a formal destroy — just null the ref.
    // The DOM node is removed by Vue automatically.
    editorInstance.value = null;
  });

  /**
   * Insert a pre-formatted XML fragment at the current cursor position,
   * re-indenting every line to match the current line's leading whitespace
   * so the fragment visually fits the surrounding document.
   *
   * Used by the CrossRef resolver to drop a ``<biblStruct>`` into a
   * ``<listBibl>`` / ``<sourceDesc>`` without the editor having to re-tab
   * the block by hand. The caller is responsible for positioning the cursor
   * at a valid insertion point (typically an empty line at the right
   * nesting depth) — this helper does not attempt structural validation.
   */
  function insertXmlFragment(xml: string): void {
    const cm = editorInstance.value;
    if (!cm || !xml) return;
    const cursor = cm.getCursor();
    const line = cm.getLine(cursor.line) ?? '';
    const leadingMatch = /^(\s*)/.exec(line);
    const indent = leadingMatch ? leadingMatch[1] : '';
    // Trim one trailing newline so the caller does not have to care about
    // whether the fragment ends with '\n'.
    const trimmed = xml.replace(/\n+$/, '');
    const lines = trimmed.split('\n');
    // Re-indent every line EXCEPT the first — the first takes the
    // indentation of the cursor's current column. This matches what the
    // editor would do if they had pasted the fragment onto a blank
    // properly-indented line.
    const reindented = lines
      .map((l, idx) => (idx === 0 ? l : indent + l))
      .join('\n');
    cm.replaceRange(reindented, cursor, undefined, '+programmatic');
    cm.focus();
  }

  return {
    editorInstance,
    isFullscreen,
    getValue,
    setValue,
    refresh,
    toggleFullscreen,
    foldAll,
    prettyPrint,
    insertNote,
    editNote,
    deleteNote,
    insertFigure,
    insertPageBreak,
    insertFacsRef,
    insertEntityRef,
    insertXmlFragment,
  };
}
