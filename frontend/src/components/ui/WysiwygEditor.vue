<script setup lang="ts">
import { watch, ref } from "vue";
import { useEditor, EditorContent } from "@tiptap/vue-3";
import { Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import MediaPicker from "@/components/ui/MediaPicker.vue";

// ── Widget nodes ──────────────────────────────────────────────────────────────

/**
 * SearchBarWidget — a Tiptap block node that serialises to
 * <div data-widget="search-bar"></div> in the HTML stored in the DB.
 * The static builder replaces that tag with the real search-bar HTML+JS.
 */
const SearchBarWidget = Node.create({
  name: "searchBarWidget",
  group: "block",
  atom: true,   // treated as a single indivisible unit (like an image)

  parseHTML() {
    return [{ tag: 'div[data-widget="search-bar"]' }];
  },

  renderHTML() {
    return ["div", { "data-widget": "search-bar" }];
  },

  addNodeView() {
    return () => {
      const dom = document.createElement("div");
      dom.className = "widget-preview";
      dom.setAttribute("contenteditable", "false");
      dom.innerHTML = "&#128269; Search Bar";
      return { dom };
    };
  },
});

/**
 * PageMenuWidget — a Tiptap block node that serialises to
 * <div data-widget="page-menu"></div> in the HTML stored in the DB.
 * The static builder replaces that tag with the full page-link list.
 */
const PageMenuWidget = Node.create({
  name: "pageMenuWidget",
  group: "block",
  atom: true,

  parseHTML() {
    return [{ tag: 'div[data-widget="page-menu"]' }];
  },

  renderHTML() {
    return ["div", { "data-widget": "page-menu" }];
  },

  addNodeView() {
    return () => {
      const dom = document.createElement("div");
      dom.className = "widget-preview";
      dom.setAttribute("contenteditable", "false");
      dom.innerHTML = "&#128196; Page Menu";
      return { dom };
    };
  },
});

/**
 * IndexListWidget — a Tiptap block node that serialises to
 * <div data-widget="index-list"></div> in the HTML stored in the DB.
 * The static/dynamic builder replaces that tag with a nav list of built indices.
 */
const IndexListWidget = Node.create({
  name: "indexListWidget",
  group: "block",
  atom: true,

  parseHTML() {
    return [{ tag: 'div[data-widget="index-list"]' }];
  },

  renderHTML() {
    return ["div", { "data-widget": "index-list" }];
  },

  addNodeView() {
    return () => {
      const dom = document.createElement("div");
      dom.className = "widget-preview";
      dom.setAttribute("contenteditable", "false");
      dom.innerHTML = "&#128203; Index List";
      return { dom };
    };
  },
});

const props = defineProps<{
  modelValue: string;
  /**
   * When set, a second image-insert button appears in the toolbar
   * that opens the per-website media picker. Picking an image there
   * emits ``setImage({ src: "media://filename" })`` so the website
   * renderer can rewrite the pseudo-URL to a real URL at serve /
   * build time. Leave undefined to hide the library button (the free
   * URL dialog remains available).
   */
  websiteSlug?: string;
}>();
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

// Fullscreen state
const isFullscreen = ref(false);

function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value;
}

// Link dialog state
const showLinkDialog = ref(false);
const linkUrl = ref("");
const linkText = ref("");

// Image dialog state
const showImageDialog = ref(false);
const imageUrl = ref("");
const imageAlt = ref("");

const editor = useEditor({
  content: props.modelValue || "",
  extensions: [
    StarterKit,
    Image.configure({ inline: false }),
    Link.configure({ openOnClick: false, HTMLAttributes: { rel: "noopener" } }),
    TextAlign.configure({ types: ["heading", "paragraph"] }),
    SearchBarWidget,
    PageMenuWidget,
    IndexListWidget,
  ],
  editorProps: {
    /**
     * Intercept external drag-and-drop of widget chips.
     * Internal ProseMirror drags (moved === true) are left untouched.
     */
    handleDrop(view, event, _slice, moved) {
      if (moved) return false;
      const widgetType = event.dataTransfer?.getData("widget-type");
      const widgetNodeName: Record<string, string> = {
        "search-bar": "searchBarWidget",
        "page-menu":  "pageMenuWidget",
        "index-list": "indexListWidget",
      };
      const nodeName = widgetType ? widgetNodeName[widgetType] : undefined;
      if (nodeName) {
        const pos = view.posAtCoords({ left: event.clientX, top: event.clientY });
        if (pos) {
          const nodeType = view.state.schema.nodes[nodeName];
          if (nodeType) {
            view.dispatch(view.state.tr.insert(pos.pos, nodeType.create()));
          }
        }
        return true;
      }
      return false;
    },
  },
  onUpdate({ editor: ed }) {
    emit("update:modelValue", ed.getHTML());
  },
});

// Sync external modelValue changes (e.g. form reset)
watch(
  () => props.modelValue,
  (val) => {
    if (editor.value && editor.value.getHTML() !== val) {
      editor.value.commands.setContent(val || "", false);
    }
  },
);

function openLinkDialog(): void {
  const prev = editor.value?.getAttributes("link").href ?? "";
  linkUrl.value = prev;
  linkText.value = editor.value?.state.doc.textBetween(
    editor.value.state.selection.from,
    editor.value.state.selection.to,
    "",
  ) ?? "";
  showLinkDialog.value = true;
}

function applyLink(): void {
  if (!linkUrl.value) {
    editor.value?.chain().focus().unsetLink().run();
  } else {
    editor.value?.chain().focus().setLink({ href: linkUrl.value }).run();
  }
  showLinkDialog.value = false;
  linkUrl.value = "";
  linkText.value = "";
}

function openImageDialog(): void {
  imageUrl.value = "";
  imageAlt.value = "";
  showImageDialog.value = true;
}

function applyImage(): void {
  if (imageUrl.value) {
    editor.value?.chain().focus().setImage({ src: imageUrl.value, alt: imageAlt.value }).run();
  }
  showImageDialog.value = false;
  imageUrl.value = "";
  imageAlt.value = "";
}

// Media-library picker — only wired when ``websiteSlug`` is provided.
// The picker emits the ``media://filename`` pseudo-URL; inserted as-is,
// the website renderer translates it to a real URL at serve/build time.
const mediaPickerOpen = ref(false);

function onMediaPicked(ref: string): void {
  editor.value?.chain().focus().setImage({ src: ref }).run();
}

function isActive(nameOrAttrs: string | Record<string, unknown>, attrs?: Record<string, unknown>): boolean {
  if (typeof nameOrAttrs === "string") {
    return editor.value?.isActive(nameOrAttrs, attrs) ?? false;
  }
  return editor.value?.isActive(nameOrAttrs) ?? false;
}
</script>

<template>
  <div class="wysiwyg-editor rounded border border-gray-300 bg-white" :class="{ 'wysiwyg-fullscreen': isFullscreen }" @dragover.prevent>
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-0.5 border-b border-gray-200 bg-gray-50 px-2 py-1">
      <!-- Text format -->
      <button
        type="button"
        title="Bold"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('bold') }"
        @click="editor?.chain().focus().toggleBold().run()"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        title="Italic"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('italic') }"
        @click="editor?.chain().focus().toggleItalic().run()"
      >
        <em>I</em>
      </button>

      <span class="toolbar-sep" />

      <!-- Headings -->
      <button
        type="button"
        title="Heading 2"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('heading', { level: 2 }) }"
        @click="editor?.chain().focus().toggleHeading({ level: 2 }).run()"
      >
        H2
      </button>
      <button
        type="button"
        title="Heading 3"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('heading', { level: 3 }) }"
        @click="editor?.chain().focus().toggleHeading({ level: 3 }).run()"
      >
        H3
      </button>
      <button
        type="button"
        title="Heading 4"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('heading', { level: 4 }) }"
        @click="editor?.chain().focus().toggleHeading({ level: 4 }).run()"
      >
        H4
      </button>

      <span class="toolbar-sep" />

      <!-- Lists -->
      <button
        type="button"
        title="Bullet list"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('bulletList') }"
        @click="editor?.chain().focus().toggleBulletList().run()"
      >
        &#8226;&#8212;
      </button>
      <button
        type="button"
        title="Ordered list"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('orderedList') }"
        @click="editor?.chain().focus().toggleOrderedList().run()"
      >
        1&#8212;
      </button>

      <span class="toolbar-sep" />

      <!-- Link -->
      <button
        type="button"
        title="Link"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('link') }"
        @click="openLinkDialog"
      >
        🔗
      </button>
      <button
        v-if="isActive('link')"
        type="button"
        title="Remove link"
        class="toolbar-btn text-red-500"
        @click="editor?.chain().focus().unsetLink().run()"
      >
        ✕
      </button>

      <!-- Image -->
      <button
        type="button"
        title="Insert image from URL"
        class="toolbar-btn"
        @click="openImageDialog"
      >
        🖼
      </button>

      <!-- Media library picker — appears only when the editor was
           mounted with a website slug (e.g. inside the website editor).
           Clicking it opens the per-site image library; picking a file
           inserts it with the stable ``media://filename`` ref. -->
      <button
        v-if="websiteSlug"
        type="button"
        title="Insert image from website media library"
        class="toolbar-btn"
        @click="mediaPickerOpen = true"
      >
        📁
      </button>

      <span class="toolbar-sep" />

      <!-- Block quote & horizontal rule -->
      <button
        type="button"
        title="Blockquote"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive('blockquote') }"
        @click="editor?.chain().focus().toggleBlockquote().run()"
      >
        ❝
      </button>
      <button
        type="button"
        title="Horizontal rule"
        class="toolbar-btn"
        @click="editor?.chain().focus().setHorizontalRule().run()"
      >
        ─
      </button>

      <span class="toolbar-sep" />

      <!-- Text alignment -->
      <button
        type="button"
        title="Align left"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive({ textAlign: 'left' }) }"
        @click="editor?.chain().focus().setTextAlign('left').run()"
      >
        &#8676;
      </button>
      <button
        type="button"
        title="Align center"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive({ textAlign: 'center' }) }"
        @click="editor?.chain().focus().setTextAlign('center').run()"
      >
        &#8633;
      </button>
      <button
        type="button"
        title="Align right"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive({ textAlign: 'right' }) }"
        @click="editor?.chain().focus().setTextAlign('right').run()"
      >
        &#8677;
      </button>
      <button
        type="button"
        title="Justify"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isActive({ textAlign: 'justify' }) }"
        @click="editor?.chain().focus().setTextAlign('justify').run()"
      >
        &#8660;
      </button>

      <span class="toolbar-sep" />

      <!-- Undo / Redo -->
      <button
        type="button"
        title="Undo"
        class="toolbar-btn"
        :disabled="!editor?.can().undo()"
        @click="editor?.chain().focus().undo().run()"
      >
        ↩
      </button>
      <button
        type="button"
        title="Redo"
        class="toolbar-btn"
        :disabled="!editor?.can().redo()"
        @click="editor?.chain().focus().redo().run()"
      >
        ↪
      </button>

      <span class="toolbar-sep" />

      <!-- Fullscreen -->
      <button
        type="button"
        :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': isFullscreen }"
        @click="toggleFullscreen"
      >
        {{ isFullscreen ? '⤡' : '⤢' }}
      </button>
    </div>

    <!-- Editable area -->
    <EditorContent :editor="editor" class="prose-area" />

    <!-- Link dialog -->
    <div v-if="showLinkDialog" class="dialog-overlay">
      <div class="dialog-box">
        <p class="dialog-title">Insert link</p>
        <label class="dialog-label">URL</label>
        <input
          v-model="linkUrl"
          type="url"
          class="dialog-input"
          placeholder="https://..."
          @keydown.enter.prevent="applyLink"
        />
        <div class="dialog-actions">
          <button type="button" class="btn-apply" @click="applyLink">Apply</button>
          <button type="button" class="btn-cancel" @click="showLinkDialog = false">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Image dialog -->
    <div v-if="showImageDialog" class="dialog-overlay">
      <div class="dialog-box">
        <p class="dialog-title">Insert image</p>
        <label class="dialog-label">Image URL</label>
        <input
          v-model="imageUrl"
          type="url"
          class="dialog-input"
          placeholder="https://..."
        />
        <label class="dialog-label mt-2">Alt text</label>
        <input
          v-model="imageAlt"
          type="text"
          class="dialog-input"
          placeholder="Image description"
          @keydown.enter.prevent="applyImage"
        />
        <div class="dialog-actions">
          <button type="button" class="btn-apply" @click="applyImage">Insert</button>
          <button type="button" class="btn-cancel" @click="showImageDialog = false">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Media library picker — Teleport'd to body by the component itself. -->
    <MediaPicker
      v-if="websiteSlug"
      :slug="websiteSlug"
      mode="modal"
      :open="mediaPickerOpen"
      @update:open="mediaPickerOpen = $event"
      @selected="onMediaPicked"
    />
  </div>
</template>

<style scoped>
/* ── Toolbar ── */
.toolbar-btn {
  min-width: 1.75rem;
  height: 1.75rem;
  padding: 0 0.3rem;
  border-radius: 0.25rem;
  font-size: 0.8rem;
  font-family: inherit;
  background: transparent;
  border: none;
  cursor: pointer;
  color: #374151;
  display: flex;
  align-items: center;
  justify-content: center;
}
.toolbar-btn:hover:not(:disabled) { background: #e5e7eb; }
.toolbar-btn:disabled { opacity: 0.35; cursor: default; }
.toolbar-btn-active { background: #dbeafe; color: #1d4ed8; }
.toolbar-sep { width: 1px; height: 1.25rem; background: #d1d5db; margin: 0 0.2rem; }

/* ── Editor content area ── */
.prose-area {
  min-height: 160px;
  padding: 0.625rem 0.875rem;
  font-size: 0.875rem;
  line-height: 1.65;
  outline: none;
  cursor: text;
}
/* ProseMirror root element */
:deep(.ProseMirror) {
  outline: none;
  min-height: 140px;
}
:deep(.ProseMirror p)   { margin-bottom: 0.6rem; }
:deep(.ProseMirror h2)  { font-size: 1.15rem; font-weight: 700; margin: 1.1rem 0 0.4rem; }
:deep(.ProseMirror h3)  { font-size: 1rem;   font-weight: 700; margin: 0.9rem 0 0.35rem; }
:deep(.ProseMirror h4)  { font-size: 0.9rem; font-weight: 600; margin: 0.75rem 0 0.3rem; }
:deep(.ProseMirror ul)  { list-style: disc;    padding-left: 1.25rem; margin-bottom: 0.6rem; }
:deep(.ProseMirror ol)  { list-style: decimal; padding-left: 1.25rem; margin-bottom: 0.6rem; }
:deep(.ProseMirror li)  { margin-bottom: 0.2rem; }
:deep(.ProseMirror a)   { color: #2563eb; text-decoration: underline; }
:deep(.ProseMirror img) { max-width: 100%; height: auto; border-radius: 0.25rem; margin: 0.5rem 0; display: block; }
:deep(.ProseMirror blockquote) {
  border-left: 3px solid #d1d5db;
  padding-left: 0.75rem;
  color: #6b7280;
  margin: 0.75rem 0;
}
:deep(.ProseMirror hr) { border: none; border-top: 1px solid #e5e7eb; margin: 1rem 0; }
:deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  float: left;
  color: #9ca3af;
  pointer-events: none;
  height: 0;
}

/* ── Dialogs ── */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0,0,0,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog-box {
  background: white;
  border-radius: 0.5rem;
  padding: 1.25rem 1.5rem;
  width: 22rem;
  max-width: 90vw;
  box-shadow: 0 10px 30px rgba(0,0,0,0.15);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.dialog-title { font-weight: 600; font-size: 0.9rem; color: #111827; }
.dialog-label { font-size: 0.75rem; color: #374151; }
.dialog-input {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  padding: 0.375rem 0.625rem;
  font-size: 0.8rem;
  outline: none;
}
.dialog-input:focus { border-color: #6366f1; box-shadow: 0 0 0 2px #eef2ff; }
.dialog-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.25rem; }
.btn-apply {
  background: #4f46e5;
  color: white;
  border: none;
  border-radius: 0.25rem;
  padding: 0.35rem 0.9rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.btn-apply:hover { background: #4338ca; }
.btn-cancel {
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.25rem;
  padding: 0.35rem 0.9rem;
  font-size: 0.8rem;
  cursor: pointer;
  color: #374151;
}
.btn-cancel:hover { background: #f9fafb; }

/* ── Widget node preview (in-editor rendering) ── */
:deep(.widget-preview) {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.85rem;
  background: #ede9fe;
  border: 1px dashed #a78bfa;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  font-family: system-ui, sans-serif;
  color: #5b21b6;
  user-select: none;
  cursor: default;
  margin: 0.4rem 0;
}

/* ── Fullscreen ── */
.wysiwyg-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  border-radius: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wysiwyg-fullscreen .prose-area {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
