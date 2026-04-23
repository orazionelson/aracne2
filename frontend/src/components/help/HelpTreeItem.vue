<script setup lang="ts">
/**
 * One recursive node of the help navigation tree.
 *
 * Sections render a caret + children (collapsible via the expanded
 * map owned by HelpView). Pages render a leaf button that navigates
 * to ``/help?path=<logical_path>``.
 */
import {
  ChevronRightIcon,
  ChevronDownIcon,
  DocumentTextIcon,
} from "@heroicons/vue/24/outline";
import type { HelpTreeNode } from "@/stores/help";

interface Props {
  node: HelpTreeNode;
  currentPath: string;
  expanded: Record<string, boolean>;
  depth?: number;
}
const props = withDefaults(defineProps<Props>(), { depth: 0 });

const emit = defineEmits<{
  (e: "navigate", path: string): void;
  (e: "toggle", path: string): void;
}>();

function onClick(): void {
  if (props.node.is_section) {
    emit("toggle", props.node.path);
  } else {
    emit("navigate", props.node.path);
  }
}

function isExpanded(path: string): boolean {
  return props.expanded[path] === true;
}
</script>

<template>
  <div>
    <button
      class="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-sm transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
      :class="[
        node.is_section
          ? 'font-medium text-gray-700 dark:text-gray-200'
          : 'text-gray-600 dark:text-gray-300',
        !node.is_section && currentPath === node.path
          ? '!bg-indigo-50 !text-indigo-700 dark:!bg-indigo-900/40 dark:!text-indigo-300'
          : '',
      ]"
      :style="{ paddingLeft: `${0.5 + depth * 0.75}rem` }"
      @click="onClick"
    >
      <ChevronDownIcon v-if="node.is_section && isExpanded(node.path)" class="h-3.5 w-3.5 shrink-0" />
      <ChevronRightIcon v-else-if="node.is_section" class="h-3.5 w-3.5 shrink-0" />
      <DocumentTextIcon v-else class="h-3.5 w-3.5 shrink-0 text-gray-400" />
      <span class="truncate">{{ node.title }}</span>
    </button>

    <div v-if="node.is_section && isExpanded(node.path)">
      <HelpTreeItem
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :current-path="currentPath"
        :expanded="expanded"
        :depth="depth + 1"
        @navigate="(p) => emit('navigate', p)"
        @toggle="(p) => emit('toggle', p)"
      />
    </div>
  </div>
</template>
