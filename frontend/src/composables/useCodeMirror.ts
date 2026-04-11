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

    cm.operation(() => {
      // ── 1. Insert <ref> at cursor ──────────────────────────────────────────
      const refTag = `<ref target="#${noteId}" type="${type}"/>`;
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

      // ── 4. Mark the newly inserted <ref> as read-only ─────────────────────
      // cursor is still valid after both insertions because both were made
      // after the cursor position in the document.
      const refEnd = cm.posFromIndex(cm.indexFromPos(cursor) + refTag.length);
      cm.markText(cursor, refEnd, {
        className: 'cm-note-ref',
        title: noteId,
      });
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
  };
}
