<script setup lang="ts">
/**
 * /admin/gdpr — review queue for GDPR anonymisation requests.
 *
 * Layout: a card per open request showing requester, submission
 * timestamp, and the optional reason. The Admin types review
 * notes (institutional/legal basis), then either Approve+Execute
 * (runs the anonymise action and marks the request completed) or
 * Reject (leaves the user untouched, marks the request rejected).
 *
 * No detail side panel: each request is small enough to fit a
 * card; the full payload (audit trail, post-anonymisation legal
 * trail) lives in /admin/audit-log filtered on
 * action="user.anonymise_requested" or "user.anonymised".
 */
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
} from "@heroicons/vue/24/outline";
import { useGdprStore } from "@/stores/gdpr";

const { t } = useI18n();
const store = useGdprStore();

onMounted(() => {
  store.fetchRequests();
});

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

async function handleAnonymise(id: string): Promise<void> {
  const notes = store.getNotes(id).trim();
  if (!notes) {
    if (!confirm(t("admin_gdpr.no_notes_warning"))) return;
  }
  if (!confirm(t("admin_gdpr.anonymise_confirm"))) return;
  await store.executeAnonymise(id);
}

async function handleReject(id: string): Promise<void> {
  const notes = store.getNotes(id).trim();
  if (!notes) {
    alert(t("admin_gdpr.reject_needs_notes"));
    return;
  }
  await store.rejectRequest(id);
}
</script>

<template>
  <div class="px-6 py-6">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">
          {{ t("admin_gdpr.title") }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t("admin_gdpr.subtitle") }}
        </p>
      </div>
      <button
        type="button"
        :disabled="store.isLoading"
        class="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60"
        @click="store.fetchRequests"
      >
        <ArrowPathIcon
          class="h-4 w-4"
          :class="{ 'animate-spin': store.isLoading }"
        />
        {{ t("admin_gdpr.refresh") }}
      </button>
    </div>

    <p
      v-if="store.error"
      class="mb-3 rounded border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700"
    >
      {{ store.error }}
    </p>

    <p v-if="store.isLoading && store.requests.length === 0" class="text-sm text-gray-500">
      {{ t("common.loading") }}
    </p>

    <p
      v-else-if="store.requests.length === 0"
      class="rounded-xl border border-gray-200 bg-white px-4 py-6 text-center text-sm italic text-gray-500"
    >
      {{ t("admin_gdpr.empty") }}
    </p>

    <ul v-else class="space-y-3">
      <li
        v-for="r in store.requests"
        :key="r.id"
        class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
      >
        <header class="flex items-start justify-between">
          <div>
            <p class="text-sm font-semibold text-gray-800">
              {{ r.user_username || r.user_id }}
              <span class="ml-2 rounded bg-indigo-50 px-2 py-0.5 text-xs font-mono text-indigo-700">
                {{ r.kind }}
              </span>
              <span
                class="ml-1 rounded px-2 py-0.5 text-xs font-medium"
                :class="r.status === 'submitted' ? 'bg-amber-50 text-amber-700' : 'bg-gray-100 text-gray-600'"
              >
                {{ r.status }}
              </span>
            </p>
            <p class="mt-0.5 text-xs text-gray-500">
              {{ t("admin_gdpr.submitted_at") }} {{ formatTime(r.submitted_at) }}
            </p>
          </div>
        </header>

        <section v-if="r.reason" class="mt-3 rounded border border-amber-100 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span class="text-xs font-medium uppercase">{{ t("admin_gdpr.requester_reason") }}</span>
          <p class="mt-1 italic">{{ r.reason }}</p>
        </section>
        <p v-else class="mt-3 text-xs italic text-gray-400">
          {{ t("admin_gdpr.no_reason") }}
        </p>

        <label class="mt-3 block text-xs font-medium text-gray-600">
          {{ t("admin_gdpr.review_notes_label") }}
        </label>
        <textarea
          rows="3"
          :placeholder="t('admin_gdpr.review_notes_placeholder')"
          :value="store.getNotes(r.id)"
          class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          @input="store.setNotes(r.id, ($event.target as HTMLTextAreaElement).value)"
        />

        <div class="mt-3 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            :disabled="store.actingId === r.id"
            class="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            @click="handleReject(r.id)"
          >
            <XCircleIcon class="h-4 w-4" />
            {{ t("admin_gdpr.reject") }}
          </button>
          <button
            type="button"
            :disabled="store.actingId === r.id"
            class="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-60"
            @click="handleAnonymise(r.id)"
          >
            <CheckCircleIcon class="h-4 w-4" />
            {{ t("admin_gdpr.anonymise_now") }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>
