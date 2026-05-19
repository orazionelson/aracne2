import { ref } from "vue";
import { defineStore } from "pinia";
import { useAuthStore } from "@/stores/auth";
import { makeUuidV4 } from "@/utils/uuid";

/**
 * Allowed values for ``AiPrompt.scope``. Each value corresponds to a
 * specific UI surface that auto-renders the prompt as a button or
 * picker entry. ``null`` means orphan — visible only in Settings →
 * AI, never offered to a workflow.
 */
export type AiPromptScope =
  | "editor.selection"
  | "editor.document"
  | "editor.validation"
  | "editor.discuss"
  | "xslt.debug"
  | "xslt.discuss"
  | "bibliobuilder";

export interface AiPrompt {
  id: string;
  slug: string;
  label: string;
  description: string | null;
  template: string;
  context_vars: string[];
  scope: AiPromptScope | null;
  is_native: boolean;
  created_at: string;
  updated_at: string;
}

export interface AiConfig {
  provider: string;
  model: string;
  rate_limit: number;
  privacy_warning: boolean;
}

export interface AiChatMessage {
  role: "user" | "assistant";
  content: string;
}

export const useAiStore = defineStore("ai", () => {
  const prompts = ref<AiPrompt[]>([]);
  const config = ref<AiConfig | null>(null);
  const isStreaming = ref(false);
  const response = ref("");
  const streamError = ref<string | null>(null);
  const chatHistory = ref<AiChatMessage[]>([]);

  let _abortController: AbortController | null = null;

  // ── Prompt library ──────────────────────────────────────────────────────────

  async function fetchPrompts(scope?: AiPromptScope): Promise<void> {
    const params = scope ? `?scope=${encodeURIComponent(scope)}` : "";
    const res = await _authFetch(`/api/v1/ai/prompts${params}`);
    const json = await res.json();
    prompts.value = json.data ?? [];
  }

  async function fetchConfig(): Promise<void> {
    const res = await _authFetch("/api/v1/ai/config");
    const json = await res.json();
    config.value = json.data ?? null;
  }

  async function createPrompt(data: {
    slug: string;
    label: string;
    description?: string;
    template: string;
    context_vars?: string[];
    scope?: AiPromptScope | null;
  }): Promise<AiPrompt> {
    const res = await _authFetch("/api/v1/ai/prompts", {
      method: "POST",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err?.error?.message ?? "Error creating prompt");
    }
    const json = await res.json();
    const created: AiPrompt = json.data;
    prompts.value.push(created);
    return created;
  }

  async function updatePrompt(
    slug: string,
    data: Partial<Pick<AiPrompt, "label" | "description" | "template" | "context_vars" | "scope">>,
  ): Promise<AiPrompt> {
    const res = await _authFetch(`/api/v1/ai/prompts/${slug}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err?.error?.message ?? "Error updating prompt");
    }
    const json = await res.json();
    const updated: AiPrompt = json.data;
    const idx = prompts.value.findIndex((p) => p.slug === slug);
    if (idx !== -1) prompts.value[idx] = updated;
    return updated;
  }

  async function deletePrompt(slug: string): Promise<void> {
    const res = await _authFetch(`/api/v1/ai/prompts/${slug}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err?.error?.message ?? "Error deleting prompt");
    }
    prompts.value = prompts.value.filter((p) => p.slug !== slug);
  }

  // ── Streaming completion ────────────────────────────────────────────────────

  async function startStream(
    promptSlug: string,
    context: Record<string, string>,
  ): Promise<void> {
    if (isStreaming.value) stopStream();

    // Reset everything — each new preset prompt starts a fresh conversation.
    response.value = "";
    streamError.value = null;
    chatHistory.value = [];
    isStreaming.value = true;
    _abortController = new AbortController();

    try {
      const auth = useAuthStore();
      const res = await fetch("/api/v1/ai/complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(auth.accessToken
            ? { Authorization: `Bearer ${auth.accessToken}` }
            : {}),
          "X-Request-ID": makeUuidV4(),
        },
        body: JSON.stringify({ prompt_slug: promptSlug, context, history: [] }),
        signal: _abortController.signal,
        credentials: "include",
      });

      if (!res.ok || !res.body) {
        streamError.value = `HTTP ${res.status}`;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") return;
          try {
            const obj = JSON.parse(data) as { chunk?: string; error?: string };
            if (obj.error) {
              streamError.value = obj.error;
              return;
            }
            if (obj.chunk) response.value += obj.chunk;
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      streamError.value = err instanceof Error ? err.message : String(err);
    } finally {
      isStreaming.value = false;
      _abortController = null;
      // Archive the completed response into chat history.
      if (response.value && !streamError.value) {
        chatHistory.value.push({ role: "assistant", content: response.value });
      }
    }
  }

  /**
   * Send a follow-up user message using the existing conversation context.
   * The full history (including the new user message) is sent to the backend
   * so it can prepend the resolved template and reconstruct the full turn list.
   */
  async function continueChat(
    promptSlug: string,
    context: Record<string, string>,
    userMessage: string,
  ): Promise<void> {
    if (isStreaming.value) return;

    // Append the user turn before the request so the backend receives
    // the full history including this new message.
    chatHistory.value.push({ role: "user", content: userMessage });

    response.value = "";
    streamError.value = null;
    isStreaming.value = true;
    _abortController = new AbortController();

    try {
      const auth = useAuthStore();
      const res = await fetch("/api/v1/ai/complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(auth.accessToken
            ? { Authorization: `Bearer ${auth.accessToken}` }
            : {}),
          "X-Request-ID": makeUuidV4(),
        },
        body: JSON.stringify({
          prompt_slug: promptSlug,
          context,
          history: chatHistory.value,
        }),
        signal: _abortController.signal,
        credentials: "include",
      });

      if (!res.ok || !res.body) {
        streamError.value = `HTTP ${res.status}`;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") return;
          try {
            const obj = JSON.parse(data) as { chunk?: string; error?: string };
            if (obj.error) {
              streamError.value = obj.error;
              return;
            }
            if (obj.chunk) response.value += obj.chunk;
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      streamError.value = err instanceof Error ? err.message : String(err);
    } finally {
      isStreaming.value = false;
      _abortController = null;
      // Archive the completed response into chat history.
      if (response.value && !streamError.value) {
        chatHistory.value.push({ role: "assistant", content: response.value });
      }
    }
  }

  function stopStream(): void {
    _abortController?.abort();
    _abortController = null;
    isStreaming.value = false;
  }

  function clearResponse(): void {
    response.value = "";
    streamError.value = null;
    isStreaming.value = false;
  }

  function resetChat(): void {
    stopStream();
    response.value = "";
    streamError.value = null;
    chatHistory.value = [];
  }

  // ── Internal fetch helper (adds Bearer token) ───────────────────────────────

  function _authFetch(url: string, init: RequestInit = {}): Promise<Response> {
    const auth = useAuthStore();
    return fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(auth.accessToken
          ? { Authorization: `Bearer ${auth.accessToken}` }
          : {}),
        "X-Request-ID": makeUuidV4(),
        ...((init.headers as Record<string, string>) ?? {}),
      },
      credentials: "include",
    });
  }

  return {
    prompts,
    config,
    isStreaming,
    response,
    streamError,
    chatHistory,
    fetchPrompts,
    fetchConfig,
    createPrompt,
    updatePrompt,
    deletePrompt,
    startStream,
    continueChat,
    stopStream,
    clearResponse,
    resetChat,
  };
});
