<script setup lang="ts">
/**
 * Public natural-language search — `nl_search` plugin.
 *
 * Consumes the SSE stream emitted by ``POST /api/v1/nl-search/query``.
 * Each event has an ``event:`` name and a JSON ``data:`` body:
 *
 * - ``status`` — phase / tool-call activity (``thinking``,
 *   ``tool_call``, ``tool_done``).
 * - ``chunk``  — incremental answer text. Concatenate as it arrives.
 * - ``citations`` — final list of ``{slug, filename, excerpt}`` pairs
 *   the orchestrator validated against the tool-call history.
 * - ``error``  — ``{code, message}`` for any pre-stream failure that
 *   was surfaced inside the stream rather than as an HTTP status.
 * - ``done``   — terminal marker; close the reader.
 *
 * The answer is rendered as plain text — markdown is not parsed
 * client-side (no markdown dep in the frontend tree). The system
 * prompt instructs the LLM to keep paragraphs short and end with a
 * ``## Citations`` block, which we strip from the visible answer
 * once the structured citations event arrives.
 */
import { computed, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { makeUuidV4 } from "@/utils/uuid";

interface Citation {
  slug: string;
  filename: string;
  excerpt: string;
}

const { t } = useI18n();
const auth = useAuthStore();

const queryDraft = ref("");
const submittedQuery = ref("");
const answer = ref("");
const visibleAnswer = computed(() => stripCitationsBlock(answer.value));
const status = ref<string>("");
const citations = ref<Citation[]>([]);
const errorCode = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
const streaming = ref(false);

let abortController: AbortController | null = null;

function stripCitationsBlock(s: string): string {
  // Hide the LLM's citations heading + JSON lines from the visible
  // answer — the structured citations strip below renders the cleaned
  // version. Match either the English or the Italian heading.
  const cut = Math.max(
    s.toLowerCase().lastIndexOf("## citations"),
    s.toLowerCase().lastIndexOf("## citazioni"),
  );
  if (cut < 0) return s;
  return s.slice(0, cut).trimEnd();
}

async function submit(): Promise<void> {
  if (streaming.value) return;
  const q = queryDraft.value.trim();
  if (!q) return;

  submittedQuery.value = q;
  answer.value = "";
  status.value = "";
  citations.value = [];
  errorCode.value = null;
  errorMessage.value = null;
  streaming.value = true;
  abortController = new AbortController();

  try {
    const res = await fetch("/api/v1/nl-search/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth.accessToken
          ? { Authorization: `Bearer ${auth.accessToken}` }
          : {}),
        "X-Request-ID": makeUuidV4(),
      },
      body: JSON.stringify({ query: q }),
      signal: abortController.signal,
      credentials: "include",
    });

    if (!res.ok || !res.body) {
      errorCode.value = `HTTP_${res.status}`;
      errorMessage.value = await safeReadText(res);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let pendingEvent = "message";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE message boundary is a blank line; consume frame-by-frame.
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd >= 0) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        let dataLine = "";
        pendingEvent = "message";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) {
            pendingEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLine = line.slice(6);
          }
        }
        if (dataLine) handleEvent(pendingEvent, dataLine);
        frameEnd = buffer.indexOf("\n\n");
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    errorCode.value = "NETWORK_ERROR";
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    streaming.value = false;
    abortController = null;
    status.value = "";
  }
}

function handleEvent(name: string, dataJson: string): void {
  let data: unknown;
  try {
    data = JSON.parse(dataJson);
  } catch {
    return;
  }
  if (typeof data !== "object" || data === null) return;

  if (name === "chunk") {
    const text = (data as { text?: string }).text;
    if (typeof text === "string") answer.value += text;
    return;
  }
  if (name === "status") {
    const phase = (data as { phase?: string; name?: string }).phase;
    const toolName = (data as { name?: string }).name;
    if (phase === "thinking") status.value = t("nl_search.status_thinking");
    else if (phase === "tool_call" && toolName) {
      status.value = t("nl_search.status_tool_call", { name: toolName });
    } else if (phase === "tool_done") status.value = "";
    return;
  }
  if (name === "citations") {
    const items = (data as { items?: unknown }).items;
    if (Array.isArray(items)) {
      citations.value = items.filter(
        (i): i is Citation =>
          typeof i === "object"
          && i !== null
          && typeof (i as Citation).slug === "string"
          && typeof (i as Citation).filename === "string",
      );
    }
    return;
  }
  if (name === "error") {
    errorCode.value = String((data as { code?: string }).code ?? "UNKNOWN");
    errorMessage.value = String((data as { message?: string }).message ?? "");
    return;
  }
}

async function safeReadText(res: Response): Promise<string> {
  try {
    const j = await res.json();
    return JSON.stringify(j);
  } catch {
    try {
      return await res.text();
    } catch {
      return "";
    }
  }
}

function cancel(): void {
  if (abortController) abortController.abort();
}

onBeforeUnmount(() => cancel());

const errorLabel = computed(() => {
  switch (errorCode.value) {
    case "BUDGET_EXCEEDED":
      return t("nl_search.error_budget_exceeded");
    case "OVER_CAPACITY":
      return t("nl_search.error_over_capacity");
    case "PROVIDER_MISCONFIGURED":
    case "PROVIDER_ERROR":
      return t("nl_search.error_provider");
    case "CORPUS_NOT_CONFIGURED":
      return t("nl_search.error_no_corpus");
    case "HTTP_401":
      return t("nl_search.error_login_required");
    case "HTTP_413":
      return t("nl_search.error_too_long");
    case "HTTP_429":
      return t("nl_search.error_rate_limited");
    default:
      return errorMessage.value || t("nl_search.error_generic");
  }
});
</script>

<template>
  <div class="ph-page">
    <main class="mx-auto max-w-3xl px-4 py-10">
      <h1 class="mb-2 text-2xl font-bold text-gray-900">
        {{ t("nl_search.title") }}
      </h1>
      <p class="mb-6 text-sm text-gray-500">
        {{ t("nl_search.subtitle") }}
      </p>

      <form
        class="mb-6 flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
        @submit.prevent="submit"
      >
        <textarea
          v-model="queryDraft"
          rows="3"
          maxlength="500"
          :placeholder="t('nl_search.placeholder')"
          :disabled="streaming"
          class="resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:opacity-50"
        />
        <div class="flex items-center gap-3">
          <button
            type="submit"
            :disabled="streaming || queryDraft.trim().length === 0"
            class="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {{ streaming ? t("nl_search.searching") : t("nl_search.ask") }}
          </button>
          <button
            v-if="streaming"
            type="button"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
            @click="cancel"
          >
            {{ t("common.cancel") }}
          </button>
          <span
            v-if="status"
            class="text-xs italic text-gray-500"
            aria-live="polite"
          >
            {{ status }}
          </span>
        </div>
      </form>

      <section v-if="errorCode" class="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        {{ errorLabel }}
      </section>

      <section v-if="submittedQuery" class="mb-3 text-xs text-gray-400">
        {{ t("nl_search.your_question") }}: <span class="italic">{{ submittedQuery }}</span>
      </section>

      <section
        v-if="visibleAnswer"
        class="mb-6 whitespace-pre-wrap rounded-xl border border-gray-200 bg-white px-5 py-4 text-sm leading-relaxed text-gray-800 shadow-sm"
      >
        {{ visibleAnswer }}
      </section>

      <section v-if="citations.length > 0" class="mb-6">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          {{ t("nl_search.citations_title") }}
        </h2>
        <ul class="space-y-2">
          <li
            v-for="c in citations"
            :key="`${c.slug}__${c.filename}`"
            class="rounded-lg border border-indigo-100 bg-white px-4 py-3 text-sm shadow-sm"
          >
            <router-link
              :to="{ name: 'public-document', params: { slug: c.slug, filename: c.filename } }"
              class="font-medium text-indigo-700 hover:underline"
            >
              {{ c.slug }} / {{ c.filename }}
            </router-link>
            <p v-if="c.excerpt" class="mt-1 text-xs italic text-gray-500 line-clamp-3">
              {{ c.excerpt }}
            </p>
          </li>
        </ul>
      </section>

      <p v-if="!streaming && !visibleAnswer && !errorCode" class="text-xs text-gray-400">
        {{ t("nl_search.empty_hint") }}
      </p>
    </main>
  </div>
</template>
