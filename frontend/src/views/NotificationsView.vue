<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useNotificationStore } from "@/stores/notifications";

const { t } = useI18n();
const store = useNotificationStore();

const error = ref<string | null>(null);
const page = ref(1);
const unreadOnly = ref(false);

async function load(): Promise<void> {
  error.value = null;
  try {
    await store.fetchNotifications(page.value, unreadOnly.value);
  } catch {
    error.value = t("common.error");
  }
}

async function handleMarkRead(id: number): Promise<void> {
  try {
    await store.markRead(id);
  } catch {
    error.value = t("common.error");
  }
}

async function handleMarkAllRead(): Promise<void> {
  error.value = null;
  try {
    await store.markAllRead();
  } catch {
    error.value = t("common.error");
  }
}

async function handleDelete(id: number): Promise<void> {
  try {
    await store.removeNotification(id);
  } catch {
    error.value = t("common.error");
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-3xl p-6">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-bold">{{ t("notifications.title") }}</h1>
      <button
        v-if="store.notifications.some((n) => !n.is_read)"
        class="rounded border px-3 py-1.5 text-sm hover:bg-gray-50"
        @click="handleMarkAllRead"
      >
        {{ t("notifications.mark_all_read") }}
      </button>
    </div>

    <!-- Filter -->
    <div class="mb-4 flex items-center gap-3">
      <label class="flex items-center gap-2 text-sm text-gray-600">
        <input v-model="unreadOnly" type="checkbox" class="rounded" @change="page = 1; load()" />
        {{ t("notifications.unread_only") }}
      </label>
    </div>

    <!-- Error -->
    <p v-if="error" class="mb-4 text-red-600">{{ error }}</p>

    <!-- Loading -->
    <p v-if="store.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>

    <!-- List -->
    <div v-else-if="store.notifications.length > 0" class="space-y-2">
      <div
        v-for="n in store.notifications"
        :key="n.id"
        :class="[
          'rounded-lg border p-4',
          n.is_read ? 'bg-white' : 'border-blue-200 bg-blue-50',
        ]"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1">
            <p :class="['text-sm font-medium', !n.is_read && 'text-blue-900']">
              {{ n.title }}
            </p>
            <p v-if="n.body" class="mt-0.5 text-sm text-gray-600">{{ n.body }}</p>
            <p class="mt-1 text-xs text-gray-400">{{ formatDate(n.created_at) }}</p>
          </div>
          <div class="flex shrink-0 gap-3">
            <button
              v-if="!n.is_read"
              class="text-xs text-blue-600 hover:underline"
              @click="handleMarkRead(n.id)"
            >
              {{ t("notifications.mark_read") }}
            </button>
            <button
              class="text-xs text-red-500 hover:underline"
              @click="handleDelete(n.id)"
            >
              {{ t("common.delete") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <p v-else class="mt-4 text-gray-500">{{ t("notifications.empty") }}</p>

    <!-- Pagination -->
    <div
      v-if="store.pagination && store.pagination.total_pages > 1"
      class="mt-4 flex gap-2"
    >
      <button
        :disabled="page === 1"
        class="rounded border px-3 py-1 text-sm disabled:opacity-40"
        @click="page--; load()"
      >
        ←
      </button>
      <span class="px-3 py-1 text-sm">{{ page }} / {{ store.pagination.total_pages }}</span>
      <button
        :disabled="page === store.pagination.total_pages"
        class="rounded border px-3 py-1 text-sm disabled:opacity-40"
        @click="page++; load()"
      >
        →
      </button>
    </div>
  </div>
</template>
