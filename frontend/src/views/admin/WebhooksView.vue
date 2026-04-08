<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";

const { t } = useI18n();

// ── Types ────────────────────────────────────────────────────────────────────

interface WebhookEndpoint {
  id: string;
  label: string;
  url: string;
  events: string[];
  secret_set: boolean;
  active: boolean;
  last_triggered_at: string | null;
  last_status_code: number | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

// ── State ────────────────────────────────────────────────────────────────────

const webhooks = ref<WebhookEndpoint[]>([]);
const supportedEvents = ref<string[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);

// Create form
const showForm = ref(false);
const formLabel = ref("");
const formUrl = ref("");
const formSecret = ref("");
const formEvents = ref<string[]>([]);
const formActive = ref(true);
const formError = ref<string | null>(null);
const isSaving = ref(false);

// Edit state
const editingId = ref<string | null>(null);

// Test state
const testingId = ref<string | null>(null);

// ── Data loading ─────────────────────────────────────────────────────────────

async function fetchAll(): Promise<void> {
  isLoading.value = true;
  error.value = null;
  try {
    const [wh, ev] = await Promise.all([
      apiClient.get<WebhookEndpoint[]>("/webhooks"),
      apiClient.get<string[]>("/webhooks/events"),
    ]);
    webhooks.value = wh;
    supportedEvents.value = ev;
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
}

onMounted(fetchAll);

// ── Create / Edit ─────────────────────────────────────────────────────────────

function openCreate(): void {
  editingId.value = null;
  formLabel.value = "";
  formUrl.value = "";
  formSecret.value = "";
  formEvents.value = [];
  formActive.value = true;
  formError.value = null;
  showForm.value = true;
}

function openEdit(wh: WebhookEndpoint): void {
  editingId.value = wh.id;
  formLabel.value = wh.label;
  formUrl.value = wh.url;
  formSecret.value = "";  // never pre-fill the secret
  formEvents.value = [...wh.events];
  formActive.value = wh.active;
  formError.value = null;
  showForm.value = true;
}

function cancelForm(): void {
  showForm.value = false;
  editingId.value = null;
}

function toggleEvent(ev: string): void {
  const idx = formEvents.value.indexOf(ev);
  if (idx === -1) formEvents.value.push(ev);
  else formEvents.value.splice(idx, 1);
}

async function submitForm(): Promise<void> {
  formError.value = null;
  if (!formLabel.value.trim()) { formError.value = t("webhooks.error_label_required"); return; }
  if (!formUrl.value.trim()) { formError.value = t("webhooks.error_url_required"); return; }
  if (formEvents.value.length === 0) { formError.value = t("webhooks.error_events_required"); return; }

  isSaving.value = true;
  try {
    const payload: Record<string, unknown> = {
      label: formLabel.value.trim(),
      url: formUrl.value.trim(),
      events: formEvents.value,
      active: formActive.value,
    };
    if (formSecret.value.trim()) payload.secret = formSecret.value.trim();

    if (editingId.value) {
      await apiClient.put(`/webhooks/${editingId.value}`, payload);
    } else {
      await apiClient.post("/webhooks", payload);
    }
    showForm.value = false;
    editingId.value = null;
    await fetchAll();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    formError.value = msg ?? t("common.error");
  } finally {
    isSaving.value = false;
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function deleteWebhook(id: string): Promise<void> {
  if (!confirm(t("webhooks.confirm_delete"))) return;
  try {
    await apiClient.delete(`/webhooks/${id}`);
    await fetchAll();
  } catch {
    error.value = t("common.error");
  }
}

// ── Test ping ─────────────────────────────────────────────────────────────────

async function testWebhook(id: string): Promise<void> {
  testingId.value = id;
  try {
    await apiClient.post(`/webhooks/${id}/test`, {});
    await fetchAll();
  } catch {
    error.value = t("common.error");
  } finally {
    testingId.value = null;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusColor(wh: WebhookEndpoint): string {
  if (!wh.last_triggered_at) return "text-gray-400";
  if (wh.last_error) return "text-red-500";
  return "text-green-600";
}

function statusLabel(wh: WebhookEndpoint): string {
  if (!wh.last_triggered_at) return t("webhooks.never_triggered");
  if (wh.last_error) return `${wh.last_status_code ?? "—"} · ${wh.last_error}`;
  return `${wh.last_status_code}`;
}
</script>

<template>
  <div class="p-6">
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">{{ t("webhooks.title") }}</h1>
        <p class="mt-1 text-sm text-gray-500">{{ t("webhooks.subtitle") }}</p>
      </div>
      <button
        class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="openCreate"
      >
        {{ t("webhooks.add") }}
      </button>
    </div>

    <p v-if="error" class="mb-4 text-sm text-red-600">{{ error }}</p>
    <p v-if="isLoading" class="text-sm text-gray-400">{{ t("common.loading") }}</p>

    <!-- Webhook list -->
    <div v-if="!isLoading" class="space-y-3">
      <p v-if="webhooks.length === 0" class="text-sm text-gray-500">
        {{ t("webhooks.empty") }}
      </p>

      <div
        v-for="wh in webhooks"
        :key="wh.id"
        class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900">{{ wh.label }}</span>
              <span
                class="rounded px-1.5 py-0.5 text-xs font-medium"
                :class="wh.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
              >
                {{ wh.active ? t("webhooks.active") : t("webhooks.inactive") }}
              </span>
            </div>
            <p class="mt-0.5 truncate font-mono text-xs text-gray-500">{{ wh.url }}</p>
            <div class="mt-1.5 flex flex-wrap gap-1">
              <span
                v-for="ev in wh.events"
                :key="ev"
                class="rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-700"
              >
                {{ ev }}
              </span>
            </div>
            <div class="mt-1.5 flex items-center gap-1 text-xs" :class="statusColor(wh)">
              <span>{{ t("webhooks.last_delivery") }}:</span>
              <span>{{ statusLabel(wh) }}</span>
              <span v-if="wh.last_triggered_at" class="text-gray-400">
                · {{ new Date(wh.last_triggered_at).toLocaleString() }}
              </span>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <button
              :disabled="testingId === wh.id"
              class="rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              @click="testWebhook(wh.id)"
            >
              {{ testingId === wh.id ? t("common.loading") : t("webhooks.test") }}
            </button>
            <button
              class="rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50"
              @click="openEdit(wh)"
            >
              {{ t("common.edit") }}
            </button>
            <button
              class="rounded border border-red-200 px-2.5 py-1 text-xs text-red-600 hover:bg-red-50"
              @click="deleteWebhook(wh.id)"
            >
              {{ t("common.delete") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create / Edit form -->
    <div
      v-if="showForm"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="cancelForm"
    >
      <div class="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-4 text-base font-semibold text-gray-900">
          {{ editingId ? t("webhooks.edit_title") : t("webhooks.create_title") }}
        </h2>

        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("webhooks.field_label") }}
            </label>
            <input
              v-model="formLabel"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("webhooks.field_url") }}
            </label>
            <input
              v-model="formUrl"
              type="url"
              placeholder="https://example.com/hook"
              class="w-full rounded border border-gray-300 px-3 py-1.5 font-mono text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-gray-600">
              {{ t("webhooks.field_secret") }}
              <span class="font-normal text-gray-400">({{ t("webhooks.field_secret_hint") }})</span>
            </label>
            <input
              v-model="formSecret"
              type="password"
              :placeholder="editingId ? t('webhooks.secret_placeholder_edit') : ''"
              class="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-xs font-medium text-gray-600">
              {{ t("webhooks.field_events") }}
            </label>
            <div class="flex flex-wrap gap-2">
              <label
                v-for="ev in supportedEvents"
                :key="ev"
                class="flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1 text-xs"
                :class="formEvents.includes(ev)
                  ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'"
              >
                <input
                  type="checkbox"
                  :checked="formEvents.includes(ev)"
                  class="sr-only"
                  @change="toggleEvent(ev)"
                />
                {{ ev }}
              </label>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <input id="form-active" v-model="formActive" type="checkbox" />
            <label for="form-active" class="text-sm text-gray-700">
              {{ t("webhooks.field_active") }}
            </label>
          </div>
        </div>

        <p v-if="formError" class="mt-3 text-xs text-red-600">{{ formError }}</p>

        <div class="mt-5 flex justify-end gap-2">
          <button
            class="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            @click="cancelForm"
          >
            {{ t("common.cancel") }}
          </button>
          <button
            :disabled="isSaving"
            class="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            @click="submitForm"
          >
            {{ isSaving ? t("common.loading") : t("common.save") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
