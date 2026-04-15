<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useAiStore } from "@/stores/ai";
import { useUiConfigStore } from "@/stores/ui_config";

const props = defineProps<{
  promptSlug: string;
  context: Record<string, string>;
  /** Label shown in the panel header (e.g. the prompt label). */
  title?: string;
  /** When true the panel fills its parent container (sidebar mode). */
  sidebar?: boolean;
  /** When true the panel operates in multi-turn chat mode. */
  chat?: boolean;
  /** When false the Apply button is hidden (default: true). */
  showApply?: boolean;
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

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const privacyWarning = computed(() => uiConfig.config.home_show_search);

let _privacyAccepted = false;

// Chat mode local state
const chatInput = ref("");
const chatContainer = ref<HTMLElement | null>(null);

async function run(): Promise<void> {
  if (ai.config?.privacy_warning && !_privacyAccepted) {
    _privacyAccepted = true;
  }
  await ai.startStream(props.promptSlug, props.context);
}

function stop(): void {
  ai.stopStream();
}

function applyResponse(): void {
  if (props.chat) {
    // In chat mode, apply the last completed assistant message from history.
    const lastAssistant = [...ai.chatHistory]
      .reverse()
      .find((m) => m.role === "assistant");
    if (lastAssistant) emit("apply", lastAssistant.content);
  } else {
    emit("apply", ai.response);
  }
}

function close(): void {
  ai.resetChat();
  emit("close");
}

async function sendChatMessage(): Promise<void> {
  const msg = chatInput.value.trim();
  if (!msg || ai.isStreaming) return;
  chatInput.value = "";
  await ai.continueChat(props.promptSlug, props.context, msg);
}

function onChatKeydown(event: KeyboardEvent): void {
  // Ctrl+Enter or Cmd+Enter sends the message.
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    sendChatMessage();
  }
}

// Auto-scroll the chat container as new chunks arrive.
watch(
  () => ai.response,
  () => {
    if (!props.chat) return;
    nextTick(() => {
      if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
      }
    });
  },
);

// Auto-scroll when a new history entry is appended.
watch(
  () => ai.chatHistory.length,
  () => {
    if (!props.chat) return;
    nextTick(() => {
      if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
      }
    });
  },
);

// Auto-start when the panel mounts.
run();

// Re-run when context changes (e.g. user selects a different error).
watch(
  () => props.context,
  () => {
    ai.resetChat();
    chatInput.value = "";
    run();
  },
  { deep: true },
);

onUnmounted(() => {
  ai.stopStream();
});

// Derived: whether the Apply button should be shown.
const canApply = computed(() => {
  if (props.showApply === false) return false;
  if (ai.isStreaming) return false;
  if (props.chat) {
    return ai.chatHistory.some((m) => m.role === "assistant");
  }
  return !!ai.response && !ai.streamError;
});
</script>

<template>
  <div
    :class="sidebar
      ? 'flex h-full flex-col'
      : 'flex w-full flex-col rounded-xl border border-gray-200 bg-white shadow-lg'"
  >
    <!-- Header -->
    <div
      :class="sidebar
        ? 'flex flex-shrink-0 items-center justify-between px-4 py-3 text-white'
        : 'flex items-center justify-between rounded-t-xl px-4 py-3 text-white'"
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

    <!-- ── Chat mode ── -->
    <template v-if="chat">
      <!-- Message history + live stream -->
      <div
        ref="chatContainer"
        :class="sidebar
          ? 'min-h-0 flex-1 overflow-y-auto px-4 py-3'
          : 'flex-1 overflow-y-auto px-4 py-3'"
        :style="sidebar ? undefined : 'max-height: 380px;'"
      >
        <!-- Thinking indicator (before first chunk arrives) -->
        <span
          v-if="!ai.response && !ai.chatHistory.length && ai.isStreaming"
          class="animate-pulse text-sm text-gray-400"
        >
          {{ t("ai.thinking") }}
        </span>

        <!-- Finalized history entries -->
        <div
          v-for="(msg, idx) in ai.chatHistory"
          :key="idx"
          :class="[
            'mb-3',
            msg.role === 'user' ? 'text-right' : 'text-left',
          ]"
        >
          <span
            class="mb-1 block text-xs font-semibold uppercase tracking-wide"
            :class="msg.role === 'user' ? 'text-indigo-500' : 'text-gray-500'"
          >
            {{ msg.role === "user" ? t("ai.you") : t("ai.assistant") }}
          </span>
          <span
            :class="[
              'inline-block rounded-xl px-3 py-2 text-sm',
              msg.role === 'user'
                ? 'bg-indigo-50 text-gray-800'
                : 'bg-gray-100 whitespace-pre-wrap font-mono text-gray-800',
            ]"
          >
            {{ msg.content }}
          </span>
        </div>

        <!-- Live streaming assistant message -->
        <div v-if="ai.response" class="mb-3 text-left">
          <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
            {{ t("ai.assistant") }}
          </span>
          <span class="inline-block whitespace-pre-wrap rounded-xl bg-gray-100 px-3 py-2 font-mono text-sm text-gray-800">
            {{ ai.response }}
          </span>
        </div>

        <!-- Error display -->
        <p v-if="ai.streamError" class="text-sm text-red-600">
          {{ ai.streamError }}
        </p>
      </div>

      <!-- Chat input area (shown after first response or on error) -->
      <div
        v-if="!ai.isStreaming && (ai.chatHistory.length > 0 || ai.streamError)"
        class="border-t border-gray-100 px-4 py-3"
      >
        <textarea
          v-model="chatInput"
          :placeholder="t('ai.chat_input_placeholder')"
          rows="2"
          class="w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800 focus:border-indigo-400 focus:outline-none"
          @keydown="onChatKeydown"
        />
        <div class="mt-2 flex items-center justify-between">
          <span class="text-xs text-gray-400">⌘↵ {{ t("ai.send") }}</span>
          <button
            :disabled="!chatInput.trim()"
            class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
            @click="sendChatMessage"
          >
            {{ t("ai.send") }}
          </button>
        </div>
      </div>
    </template>

    <!-- ── Single-shot mode (default) ── -->
    <template v-else>
      <div
        :class="sidebar
          ? 'min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800'
          : 'min-h-32 flex-1 overflow-y-auto whitespace-pre-wrap px-4 py-3 font-mono text-sm text-gray-800'"
        :style="sidebar ? undefined : 'max-height: 380px;'"
      >
        <span v-if="!ai.response && ai.isStreaming" class="animate-pulse text-gray-400">
          {{ t("ai.thinking") }}
        </span>
        <span v-else-if="ai.streamError" class="text-red-600">{{ ai.streamError }}</span>
        <span v-else>{{ ai.response }}</span>
      </div>
    </template>

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
        v-if="canApply"
        class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700"
        @click="applyResponse"
      >
        {{ t("ai.apply") }}
      </button>
    </div>
  </div>
</template>
