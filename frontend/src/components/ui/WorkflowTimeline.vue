<script setup lang="ts">
/**
 * Editorial-workflow timeline for a collection.
 *
 * Renders a horizontal stepper of the collection's lifecycle
 * transitions (from ``GET /collections/{id}/history``). Each step is a
 * clickable pill that opens an inline popover showing who performed
 * the action, when, and the note they attached. The last step is
 * highlighted because it represents the current state.
 *
 * The history can get long for collections that cycle through
 * review / request-revisions several times — the container scrolls
 * horizontally rather than wrapping, keeping the temporal reading
 * left-to-right.
 */
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { WorkflowHistoryEntry } from "@/stores/collections";

const props = defineProps<{
  entries: WorkflowHistoryEntry[];
}>();

const { t } = useI18n();

// Index of the step whose popover is currently open. ``null`` = closed.
// We use index (not action name) because actions repeat.
const openIdx = ref<number | null>(null);

function toggle(i: number): void {
  openIdx.value = openIdx.value === i ? null : i;
}

function close(): void {
  openIdx.value = null;
}

// Known action → short label (localised). Unknown actions fall back to
// the raw action string so nothing silently disappears if the backend
// starts emitting a new one.
const ACTION_LABELS: Record<string, string> = {
  "collection.created": "collections.history_action_created",
  "collection.assigned": "collections.history_action_assigned",
  "collection.reassigned": "collections.history_action_reassigned",
  "collection.submitted": "collections.history_action_submitted",
  "collection.rejected": "collections.history_action_revisions",
  "collection.published": "collections.history_action_published",
  "collection.direct_published": "collections.history_action_direct_published",
  "collection.unpublished": "collections.history_action_unpublished",
};

// Tailwind colour classes per action, for the step pill. Revisions =
// amber, published = green, unpublished = rose, submitted = indigo,
// assigned = blue, created = grey. The current step (last entry) gets
// a ring around it.
const ACTION_COLORS: Record<string, string> = {
  "collection.created": "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200",
  "collection.assigned": "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  "collection.reassigned": "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  "collection.submitted": "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200",
  "collection.rejected": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  "collection.published": "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  "collection.direct_published": "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  "collection.unpublished": "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
};

function labelFor(entry: WorkflowHistoryEntry): string {
  const key = ACTION_LABELS[entry.action];
  return key ? t(key) : entry.action;
}

function colorFor(entry: WorkflowHistoryEntry): string {
  return ACTION_COLORS[entry.action]
    ?? "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200";
}

function actorLabel(entry: WorkflowHistoryEntry): string {
  return entry.actor_display_name
    ?? entry.actor_username
    ?? t("collections.history_actor_unknown");
}

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString();
}

const lastIdx = computed(() => props.entries.length - 1);
</script>

<template>
  <div v-if="entries.length > 0" class="relative">
    <!-- Wrap steps onto multiple rows instead of scrolling horizontally —
         a long history is easier to scan as several short lines than one
         extra-long scrollable strip. ``overflow-visible`` is important
         so that the popover below can escape this container (a parent
         with ``overflow-x`` set would clip it and force a scrollbar). -->
    <div
      class="flex flex-wrap items-center gap-x-0 gap-y-2 overflow-visible"
      role="list"
      @click.self="close"
    >
      <template v-for="(entry, i) in entries" :key="i">
        <!-- Connector line between steps (not before the first). -->
        <span
          v-if="i > 0"
          class="inline-block h-px w-4 flex-shrink-0 bg-gray-300 dark:bg-gray-600"
          aria-hidden="true"
        />

        <div class="relative flex-shrink-0" role="listitem">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition"
            :class="[
              colorFor(entry),
              i === lastIdx
                ? 'ring-2 ring-offset-1 ring-indigo-400 dark:ring-offset-gray-900'
                : 'opacity-80 hover:opacity-100',
            ]"
            :aria-expanded="openIdx === i"
            :aria-label="labelFor(entry)"
            @click="toggle(i)"
          >
            {{ labelFor(entry) }}
          </button>

          <!-- Popover anchored below the step. ``z-40`` so it floats
               above any sibling section (the amber revision-note card,
               the deposit panel, etc.) and the clamped max-width keeps
               it from spilling off the right edge on narrow viewports. -->
          <div
            v-if="openIdx === i"
            class="absolute left-0 top-full z-40 mt-2 w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded border border-gray-200 bg-white p-3 text-xs shadow-lg dark:border-gray-700 dark:bg-gray-800"
          >
            <p class="mb-1 font-medium text-gray-800 dark:text-gray-100">
              {{ labelFor(entry) }}
            </p>
            <p class="text-gray-500 dark:text-gray-400">
              <span class="font-mono">{{ actorLabel(entry) }}</span>
              · {{ formatWhen(entry.occurred_at) }}
            </p>
            <p
              v-if="entry.note"
              class="mt-2 whitespace-pre-wrap border-t border-gray-100 pt-2 text-gray-700 dark:border-gray-700 dark:text-gray-200"
            >
              {{ entry.note }}
            </p>
            <button
              type="button"
              class="mt-2 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              @click="close"
            >
              {{ t("common.close") }}
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
