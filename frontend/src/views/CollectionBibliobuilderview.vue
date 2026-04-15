<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useCollectionStore } from "@/stores/collections";
import { useAiStore } from "@/stores/ai";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const collectionsStore = useCollectionStore();
const aiStore = useAiStore();

const slug = route.params.slug as string;

// ── Page load ─────────────────────────────────────────────────────────────────

const isLoading = ref(true);
const loadError = ref<string | null>(null);

onMounted(async () => {
  try {
    await Promise.all([
      collectionsStore.fetchCollection(slug),
      aiStore.fetchConfig(),
    ]);
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isLoading.value = false;
  }
});

const collection = computed(() => collectionsStore.current);

// ── Step 1 — Extract ──────────────────────────────────────────────────────────

const isExtracting = ref(false);
const extractError = ref<string | null>(null);
const rawEntries = ref("");
const entryCount = ref(0);
const showRaw = ref(false);

async function doExtract(): Promise<void> {
  if (!collection.value) return;
  isExtracting.value = true;
  extractError.value = null;
  try {
    const xml = await collectionsStore.extractBibl(collection.value.id);
    rawEntries.value = xml;
    entryCount.value = (xml.match(/<(bibl|biblStruct)[\s>]/g) ?? []).length;
    // Auto-show the raw XML so users can inspect it before running the AI.
    showRaw.value = true;
    // Reset any previous AI session when new data is extracted.
    aiStore.resetChat();
  } catch (err) {
    extractError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isExtracting.value = false;
  }
}

// ── Step 2 — AI ───────────────────────────────────────────────────────────────

const responseContainer = ref<HTMLElement | null>(null);

async function runAi(): Promise<void> {
  if (!rawEntries.value || aiStore.isStreaming) return;
  await aiStore.continueChat("bibliobuilder", {}, rawEntries.value);
}

// Auto-scroll response area as chunks arrive.
watch(
  () => aiStore.response,
  () => {
    nextTick(() => {
      if (responseContainer.value) {
        responseContainer.value.scrollTop = responseContainer.value.scrollHeight;
      }
    });
  },
);

// ── Step 3 — Follow-up ────────────────────────────────────────────────────────

const chatInput = ref("");

async function sendFollowUp(): Promise<void> {
  const msg = chatInput.value.trim();
  if (!msg || aiStore.isStreaming) return;
  chatInput.value = "";
  await aiStore.continueChat("bibliobuilder", {}, msg);
}

function onChatKeydown(event: KeyboardEvent): void {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    sendFollowUp();
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const lastAssistantResponse = computed(() => {
  const msgs = aiStore.chatHistory.filter((m) => m.role === "assistant");
  return msgs.length > 0 ? msgs[msgs.length - 1].content : "";
});

const hasExchange = computed(() => aiStore.chatHistory.length >= 2);

async function copyResult(): Promise<void> {
  if (!lastAssistantResponse.value) return;
  await navigator.clipboard.writeText(lastAssistantResponse.value);
}

// ── Save ─────────────────────────────────────────────────────────────────────

const isSaving = ref(false);
const saveError = ref<string | null>(null);
const savedVersion = ref<number | null>(null);

async function saveResult(): Promise<void> {
  if (!collection.value || !lastAssistantResponse.value || isSaving.value) return;
  isSaving.value = true;
  saveError.value = null;
  savedVersion.value = null;
  try {
    const entry = await collectionsStore.saveBibliography(
      collection.value.id,
      lastAssistantResponse.value,
    );
    savedVersion.value = entry.version;
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : t("common.error");
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Loading / error overlay -->
    <div v-if="isLoading" class="flex items-center justify-center py-24 text-sm text-gray-400">
      {{ t("common.loading") }}
    </div>
    <div v-else-if="loadError" class="mx-auto max-w-3xl px-4 py-12">
      <p class="text-sm text-red-600">{{ loadError }}</p>
    </div>

    <template v-else-if="collection">
      <!-- Header -->
      <div class="border-b border-gray-200 bg-white px-6 py-4">
        <div class="mx-auto max-w-3xl">
          <button
            class="mb-1 flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
            @click="router.push({ name: 'collection-detail', params: { slug } })"
          >
            ← {{ collection.title }}
          </button>
          <h1 class="text-lg font-semibold text-gray-800">{{ t("bibliobuilder.title") }}</h1>
        </div>
      </div>

      <div class="mx-auto max-w-3xl space-y-6 px-4 py-6">

        <!-- ── Step 1: Extract ──────────────────────────────────────────────── -->
        <section class="rounded-lg border border-gray-200 bg-white p-5">
          <h2 class="mb-3 text-sm font-semibold text-gray-700">
            1. {{ t("bibliobuilder.extract_btn") }}
          </h2>

          <div class="flex flex-wrap items-center gap-3">
            <button
              :disabled="isExtracting"
              class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              @click="doExtract"
            >
              <span v-if="isExtracting">{{ t("bibliobuilder.extracting") }}</span>
              <span v-else>{{ t("bibliobuilder.extract_btn") }}</span>
            </button>

            <template v-if="rawEntries">
              <span
                v-if="entryCount > 0"
                class="rounded-full bg-indigo-50 px-3 py-0.5 text-xs font-medium text-indigo-700"
              >
                {{ t("bibliobuilder.entries_found", { count: entryCount }) }}
              </span>
              <span
                v-else
                class="text-xs text-amber-600"
              >
                {{ t("bibliobuilder.no_entries") }}
              </span>

              <button
                class="text-xs text-gray-400 hover:text-gray-700"
                @click="showRaw = !showRaw"
              >
                {{ showRaw ? t("bibliobuilder.hide_raw") : t("bibliobuilder.show_raw") }}
              </button>
            </template>
          </div>

          <!-- Raw XML preview -->
          <textarea
            v-show="showRaw && rawEntries"
            :value="rawEntries"
            readonly
            rows="8"
            class="mt-3 w-full rounded border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-xs text-gray-700"
          />

          <!-- Extract error -->
          <p v-if="extractError" class="mt-2 text-sm text-red-600">
            {{ t("bibliobuilder.extract_error") }}: {{ extractError }}
          </p>
        </section>

        <!-- ── Step 2: AI ───────────────────────────────────────────────────── -->
        <section
          class="rounded-lg border border-gray-200 bg-white p-5"
          :class="{ 'opacity-50 pointer-events-none': !rawEntries || entryCount === 0 }"
        >
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-gray-700">
              2. {{ t("bibliobuilder.run_btn") }}
            </h2>
            <span class="text-xs text-gray-400">{{ aiStore.config?.provider ?? "" }}</span>
          </div>

          <div class="mb-3 flex gap-2">
            <button
              v-if="!aiStore.isStreaming"
              :disabled="!rawEntries || entryCount === 0"
              class="rounded bg-violet-600 px-4 py-1.5 text-sm text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              @click="runAi"
            >
              {{ t("bibliobuilder.run_btn") }}
            </button>
            <button
              v-else
              class="rounded border border-red-200 px-4 py-1.5 text-sm text-red-600 hover:bg-red-50"
              @click="aiStore.stopStream()"
            >
              {{ t("ai.stop") }}
            </button>
          </div>

          <!-- Response area -->
          <div
            ref="responseContainer"
            class="min-h-48 overflow-y-auto rounded border border-gray-200 bg-gray-50 px-4 py-3 font-mono text-sm text-gray-800"
            style="max-height: 480px;"
          >
            <span
              v-if="!aiStore.response && !aiStore.streamError && !aiStore.isStreaming && !hasExchange"
              class="text-xs text-gray-400"
            >
              {{ t("ai.idle_hint") }}
            </span>
            <span
              v-else-if="!aiStore.response && aiStore.isStreaming && !hasExchange"
              class="animate-pulse text-gray-400"
            >
              {{ t("ai.thinking") }}
            </span>
            <span v-else-if="aiStore.streamError" class="text-red-600">
              {{ aiStore.streamError }}
            </span>
            <template v-else>
              <!-- Finalized exchanges -->
              <div
                v-for="(msg, idx) in aiStore.chatHistory"
                :key="idx"
                class="mb-3"
              >
                <span
                  v-if="msg.role === 'assistant'"
                  class="block whitespace-pre-wrap"
                >{{ msg.content }}</span>
              </div>
              <!-- Live streaming chunk -->
              <span v-if="aiStore.response" class="whitespace-pre-wrap">{{ aiStore.response }}</span>
            </template>
          </div>

          <!-- Copy + Save result -->
          <div v-if="lastAssistantResponse && !aiStore.isStreaming" class="mt-2 flex items-center justify-end gap-3">
            <p v-if="saveError" class="text-xs text-red-600">{{ saveError }}</p>
            <span
              v-if="savedVersion !== null"
              class="rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700"
            >
              {{ t("bibliobuilder.saved_version", { version: savedVersion }) }}
            </span>
            <button
              class="text-xs text-gray-400 hover:text-indigo-600"
              @click="copyResult"
            >
              {{ t("bibliobuilder.copy_btn") }}
            </button>
            <button
              :disabled="isSaving"
              class="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
              @click="saveResult"
            >
              {{ isSaving ? t("common.saving") : t("bibliobuilder.save_btn") }}
            </button>
          </div>
        </section>

        <!-- ── Step 3: Follow-up ────────────────────────────────────────────── -->
        <section
          v-if="hasExchange"
          class="rounded-lg border border-gray-200 bg-white p-5"
        >
          <h2 class="mb-3 text-sm font-semibold text-gray-700">3. Follow-up</h2>
          <textarea
            v-model="chatInput"
            :placeholder="t('bibliobuilder.chat_placeholder')"
            rows="3"
            class="w-full resize-none rounded border border-gray-200 px-3 py-2 text-sm text-gray-800 focus:border-indigo-400 focus:outline-none"
            @keydown="onChatKeydown"
          />
          <div class="mt-2 flex items-center justify-between">
            <span class="text-xs text-gray-400">⌘↵ {{ t("ai.send") }}</span>
            <button
              :disabled="!chatInput.trim() || aiStore.isStreaming"
              class="rounded bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              @click="sendFollowUp"
            >
              {{ t("ai.send") }}
            </button>
          </div>
        </section>

      </div>
    </template>
  </div>
</template>
