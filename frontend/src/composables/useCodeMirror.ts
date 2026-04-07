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

import { ref, watch, onMounted, onBeforeUnmount, type Ref } from 'vue';
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
    // Preserve cursor position when possible
    const cursor = editorInstance.value.getCursor();
    editorInstance.value.setValue(content);
    editorInstance.value.setCursor(cursor);
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

  onMounted(() => {
    if (!containerRef.value) return;

    const hintOptions = options.schema
      ? { schemaInfo: options.schema, completeSingle: false }
      : undefined;

    const instance = CodeMirror(containerRef.value, {
      mode: 'application/xml',
      lineNumbers: true,
      lineWrapping: true,
      styleActiveLine: true,
      autoRefresh: true,
      foldGutter: true,
      matchTags: { bothTags: false },
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
  });

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
    toggleFullscreen,
    foldAll,
    prettyPrint,
  };
}
