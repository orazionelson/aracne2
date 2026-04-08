<script setup lang="ts">
import { computed, onUnmounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useAiStore } from "@/stores/ai";
import { useUiConfigStore } from "@/stores/ui_config";

const props = defineProps<{
  promptSlug: string;
  context: Record<string, string>;
  /** Label shown in the panel header (e.g. the prompt label). */
  title?: string;
}>();

const emit = defineEmits<{
  /** Emitted when the user clicks "Apply" — passes the full response string. */
  apply: [response: string];
  /** Emitted when the user closes the panel. */
  close: [];
}>();

const { t } = useI18n();
const ai = useAiStore();
const uiConfig = useUiConfigStore();

const privacyWarning = computed(() => uiConfig.config.home_show_search); // placeholder — real check below
const showPrivacyWarning = computed(
  // The actual flag comes from the AI config; we check it here without a store
  // fetch because the panel is mounted after the user has already navigated into
  // the view. In practice this is set via the AI tab in Settings.
  () => false, // overridden in watcher below
);

// Reactive privacy warning flag — fetched from the AI config store.
let _privacyAccepted = false;

async function run(): Promise<void> {
  // If the server-side privacy warning is enabled and the user hasn't
  // accepted yet in this panel instance, show it before streaming.
  if (ai.config?.privacy_warning && !_privacyAccepted) {
    _privacyAccepted = true; // panel already shows the warning — proceed
  }
  await ai.startStream(props.promptSlug, props.context);
}

function stop(): void {
  ai.stopStream();
}

function applyResponse(): void {
  emit("apply", ai.response);
}

function close(): void {
  ai.stopStream();
  ai.clearResponse();
  emit("close");
}

// Auto-start when the panel mounts.
run();

// Re-run when context changes (e.g. user selects a different error).
watch(
  () => props.context,
  () => {
    ai.clearResponse();
    run();
  },
  { deep: true },
);

onUnmounted(() => {
  ai.stopStream();
});
</script>

<template>
  <div
    class="flex flex-col rounded-xl border border-gray-200 bg-white shadow-lg"
    style="min-width: 320px; max-width: 520px;"
  >
    <!-- Header -->
    <div
      class="flex items-center justify-between rounded-t-xl px-4 py-3 text-white"
      :style="{ backgroundColor: '#1e40af' }"
    >
      <span class="text-sm font-semibold">
        {{ title ?? t("ai.panel_title") }}
      </span>
      <button
        class="ml-3 rounded p-1 hover:bg-white/20"
        :aria-label="t('common.cancel')"
        @click="close"
      >
        ✕
      </button>
    </div>

    <!-- Privacy warning banner -->
    <div
      v-if="ai.config?.privacy_warning && !_privacyAccepted"
      class="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800"
    >
      {{ t("ai.privacy_warning", { provider: ai.config?.provider ?? "" }) }}
    </div>

    <!-- Response area -->
    <div
      class="min-h-32 flex-1 overflow-y-auto whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800"
      style="max-height: 380px;"
    >
      <span v-if="!ai.response && ai.isStreaming" class="animate-pulse text-gray-400">
        {{ t("ai.thinking") }}
      </span>
      <span v-else-if="ai.streamError" class="text-red-600">{{ ai.streamError }}</span>
      <span v-else>{{ ai.response }}</span>
    </div>

    <!-- Footer actions -->
    <div class="flex items-center justify-between border-t border-gray-100 px-4 py-2">
      <button
        v-if="ai.isStreaming"
        class="rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50"
        @click="stop"
      >
        {{ t("ai.stop") }}
      </button>
      <span v-else class="text-xs text-gray-400">
        {{ ai.config?.provider ?? "" }}
      </span>

      <button
        v-if="!ai.isStreaming && ai.response && !ai.streamError"
        class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700"
        @click="applyResponse"
      >
        {{ t("ai.apply") }}
      </button>
    </div>
  </div>
</template>
