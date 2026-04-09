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
    }

    if (options.onChange) {
      instance.on('change', (cm) => {
        options.onChange!(cm.getValue());
      });
    }

    if (options.lockBoundaryLines) {
      const n = options.lockBoundaryLines;

      // Cancel any user change that touches the top-n or bottom-n lines.
      // origin 'setValue' is allowed so programmatic content replacement works.
      instance.on('beforeChange', (cm, change) => {
        if (change.origin === 'setValue') return;
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
  };
}
