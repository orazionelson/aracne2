<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import {
  ArrowDownTrayIcon,
  TrashIcon,
  ArrowPathIcon,
} from "@heroicons/vue/24/outline";
import { useBackupStore, type BackupScope, type BackupJobStatus } from "@/stores/backup";

const { t } = useI18n();
const backupStore = useBackupStore();

const error = ref<string | null>(null);
const createError = ref<string | null>(null);
const isCreating = ref(false);
const confirmDeleteId = ref<string | null>(null);

const selectedScopes = ref<BackupScope[]>(["database", "collections", "media"]);
const label = ref("");

// Polling: refresh running/pending jobs every 3 seconds.
let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPolling(): void {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const active = backupStore.jobs.filter(
      (j) => j.status === "pending" || j.status === "running",
    );
    if (active.length === 0) {
      stopPolling();
      return;
    }
    for (const job of active) {
      await backupStore.refreshJob(job.id).catch(() => undefined);
    }
  }, 3000);
}

function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(async () => {
  error.value = null;
  try {
    await backupStore.fetchJobs();
    if (backupStore.jobs.some((j) => j.status === "pending" || j.status === "running")) {
      startPolling();
    }
  } catch {
    error.value = t("common.error");
  }
});

async function createBackup(): Promise<void> {
  if (selectedScopes.value.length === 0) return;
  createError.value = null;
  isCreating.value = true;
  try {
    await backupStore.createBackup(selectedScopes.value, label.value.trim());
    label.value = "";
    startPolling();
  } catch {
    createError.value = t("backup.error_create");
  } finally {
    isCreating.value = false;
  }
}

function askDelete(jobId: string): void {
  confirmDeleteId.value = jobId;
}

async function confirmDelete(): Promise<void> {
  if (!confirmDeleteId.value) return;
  await backupStore.deleteJob(confirmDeleteId.value).catch(() => undefined);
  confirmDeleteId.value = null;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function statusClass(status: BackupJobStatus): string {
  return {
    pending: "bg-yellow-100 text-yellow-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  }[status] ?? "";
}

function statusLabel(status: BackupJobStatus): string {
  return t(`backup.status_${status}`);
}

function scopeLabel(scope: BackupScope): string {
  return t(`backup.scope_${scope}`);
}
</script>

<template>
  <div class="p-6">
    <h1 class="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ t("backup.title") }}</h1>
    <p class="mb-6 text-sm text-gray-500 dark:text-gray-400">{{ t("backup.subtitle") }}</p>

    <!-- Create backup panel -->
    <div class="mb-8 rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div class="mb-4 flex flex-wrap gap-4">
        <label
          v-for="scope in (['database', 'collections', 'media'] as BackupScope[])"
          :key="scope"
          class="flex cursor-pointer items-center gap-2 text-sm text-gray-700 dark:text-gray-200"
        >
          <input
            v-model="selectedScopes"
            type="checkbox"
            :value="scope"
            class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-900"
          />
          {{ scopeLabel(scope) }}
        </label>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <input
          v-model="label"
          type="text"
          :placeholder="t('backup.label_placeholder')"
          class="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
        />
        <button
          :disabled="isCreating || selectedScopes.length === 0"
          class="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="createBackup"
        >
          {{ isCreating ? t("backup.creating") : t("backup.create") }}
        </button>
      </div>

      <p v-if="createError" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ createError }}</p>
    </div>

    <!-- Error loading list -->
    <p v-if="error" class="mb-4 text-sm text-red-600 dark:text-red-400">{{ error }}</p>

    <!-- Jobs table -->
    <div v-if="backupStore.jobs.length === 0 && !backupStore.isLoading" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t("backup.empty") }}
    </div>

    <div v-else class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <table class="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-900">
          <tr>
            <th class="px-4 py-3 text-left font-medium text-gray-500 dark:text-gray-400">{{ t("backup.col_label") }}</th>
            <th class="hidden px-4 py-3 text-left font-medium text-gray-500 md:table-cell dark:text-gray-400">{{ t("backup.col_scopes") }}</th>
            <th class="px-4 py-3 text-left font-medium text-gray-500 dark:text-gray-400">{{ t("backup.col_status") }}</th>
            <th class="hidden px-4 py-3 text-left font-medium text-gray-500 lg:table-cell dark:text-gray-400">{{ t("backup.col_started") }}</th>
            <th class="hidden px-4 py-3 text-left font-medium text-gray-500 lg:table-cell dark:text-gray-400">{{ t("backup.col_size") }}</th>
            <th class="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-400">{{ t("backup.col_actions") }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 dark:divide-gray-700">
          <tr
            v-for="job in backupStore.jobs"
            :key="job.id"
            class="hover:bg-gray-50 dark:hover:bg-gray-700/60"
          >
            <!-- Label -->
            <td class="px-4 py-3 text-gray-900 dark:text-gray-100">
              <span v-if="job.label" class="font-medium">{{ job.label }}</span>
              <span v-else class="text-gray-400 dark:text-gray-500">—</span>
              <p v-if="job.error" class="mt-0.5 text-xs text-red-600 dark:text-red-400">{{ job.error }}</p>
            </td>

            <!-- Scopes -->
            <td class="hidden px-4 py-3 text-gray-600 md:table-cell dark:text-gray-300">
              <span
                v-for="scope in job.scopes"
                :key="scope"
                class="mr-1 inline-block rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-gray-700 dark:text-gray-200"
              >
                {{ scopeLabel(scope as BackupScope) }}
              </span>
            </td>

            <!-- Status -->
            <td class="px-4 py-3">
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                :class="statusClass(job.status)"
              >
                <ArrowPathIcon
                  v-if="job.status === 'pending' || job.status === 'running'"
                  class="h-3 w-3 animate-spin"
                />
                {{ statusLabel(job.status) }}
              </span>
            </td>

            <!-- Started -->
            <td class="hidden px-4 py-3 text-gray-600 lg:table-cell dark:text-gray-300">
              {{ new Date(job.started_at).toLocaleString() }}
            </td>

            <!-- Size -->
            <td class="hidden px-4 py-3 text-gray-600 lg:table-cell dark:text-gray-300">
              {{ formatBytes(job.size_bytes) }}
            </td>

            <!-- Actions -->
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-2">
                <a
                  v-if="job.status === 'done'"
                  :href="backupStore.downloadUrl(job.id)"
                  class="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-900/30"
                  download
                >
                  <ArrowDownTrayIcon class="h-4 w-4" />
                  {{ t("backup.download") }}
                </a>
                <button
                  class="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30"
                  @click="askDelete(job.id)"
                >
                  <TrashIcon class="h-4 w-4" />
                  {{ t("backup.delete") }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Confirm delete modal -->
    <div
      v-if="confirmDeleteId"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <p class="mb-4 text-sm text-gray-700">{{ t("backup.confirm_delete") }}</p>
        <div class="flex justify-end gap-3">
          <button
            class="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            @click="confirmDeleteId = null"
          >
            {{ t("common.cancel") }}
          </button>
          <button
            class="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            @click="confirmDelete"
          >
            {{ t("common.delete") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
