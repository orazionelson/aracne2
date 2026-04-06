<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();

interface RoleInfo {
  role_name: string;
  assigned_at: string;
}

interface UserResponse {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  role: string;
  roles: RoleInfo[];
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login_at: string | null;
  deleted_at: string | null;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

const users = ref<UserResponse[]>([]);
const pagination = ref<Pagination | null>(null);
const search = ref("");
const isActiveFilter = ref<string>("");
const page = ref(1);
const isLoading = ref(false);
const error = ref<string | null>(null);

// ── Create modal ───────────────────────────────────────────────────────────────

const showModal = ref(false);
const isCreating = ref(false);
const createError = ref<string | null>(null);

const form = ref({
  username: "",
  email: "",
  password: "",
  display_name: "",
  preferred_lang: "it",
  role: "User",
});

const VALID_ROLES = ["Admin", "EditorInChief", "Designer", "Editor", "User"];

function openModal(): void {
  form.value = { username: "", email: "", password: "", display_name: "", preferred_lang: "it", role: "User" };
  createError.value = null;
  showModal.value = true;
}

function closeModal(): void {
  showModal.value = false;
}

async function createUser(): Promise<void> {
  isCreating.value = true;
  createError.value = null;
  try {
    await apiClient.post<UserResponse>("/users", {
      username: form.value.username,
      email: form.value.email,
      password: form.value.password,
      display_name: form.value.display_name || null,
      preferred_lang: form.value.preferred_lang,
      role: form.value.role,
    });
    closeModal();
    page.value = 1;
    await fetchUsers();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    createError.value = msg ?? t("common.error");
  } finally {
    isCreating.value = false;
  }
}

// ── List ───────────────────────────────────────────────────────────────────────

async function fetchUsers(): Promise<void> {
  isLoading.value = true;
  error.value = null;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      per_page: 20,
    };
    if (search.value) params.search = search.value;
    if (isActiveFilter.value !== "") params.is_active = isActiveFilter.value === "true";

    const res = await apiClient.getPaginated<UserResponse>("/users", { params });
    users.value = res.data as UserResponse[];
    pagination.value = res.pagination as Pagination;
  } catch {
    error.value = t("common.error");
  } finally {
    isLoading.value = false;
  }
}

function goToDetail(id: string): void {
  router.push({ name: "user-detail", params: { id } });
}

function formatDate(iso: string | null): string {
  if (!iso) return t("users.never");
  return new Date(iso).toLocaleDateString();
}

watch([search, isActiveFilter], () => {
  page.value = 1;
  fetchUsers();
});

onMounted(fetchUsers);
</script>

<template>
  <div class="mx-auto max-w-6xl p-6">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-bold">{{ t("users.title") }}</h1>
      <button
        v-if="auth.hasMinRole('EditorInChief')"
        class="rounded bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700"
        @click="openModal"
      >
        + {{ t("users.create") }}
      </button>
    </div>

    <!-- Filters -->
    <div class="mb-4 flex gap-3">
      <input
        v-model="search"
        type="text"
        :placeholder="t('users.search_placeholder')"
        class="flex-1 rounded border px-3 py-2 text-sm"
      />
      <select v-model="isActiveFilter" class="rounded border px-3 py-2 text-sm">
        <option value="">{{ t("users.all_roles") }}</option>
        <option value="true">{{ t("users.filter_active") }}</option>
        <option value="false">{{ t("users.filter_inactive") }}</option>
      </select>
    </div>

    <!-- Error -->
    <p v-if="error" class="mb-4 text-red-600">{{ error }}</p>

    <!-- Loading -->
    <p v-if="isLoading" class="text-gray-500">{{ t("common.loading") }}</p>

    <!-- Table -->
    <div v-else-if="users.length > 0" class="overflow-x-auto">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-gray-100 text-left">
            <th class="px-4 py-2 font-semibold">{{ t("users.username") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("users.email") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("users.role") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("users.status") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("users.last_login") }}</th>
            <th v-if="auth.hasMinRole('Admin')" class="px-4 py-2 font-semibold"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="user in users"
            :key="user.id"
            class="border-b hover:bg-gray-50"
          >
            <td class="px-4 py-2 font-medium">{{ user.username }}</td>
            <td class="px-4 py-2 text-gray-600">{{ user.email }}</td>
            <td class="px-4 py-2">{{ user.role }}</td>
            <td class="px-4 py-2">
              <span :class="user.is_active ? 'text-green-600' : 'text-gray-400'">
                {{ user.is_active ? t("users.active") : t("users.inactive") }}
              </span>
            </td>
            <td class="px-4 py-2 text-gray-500">{{ formatDate(user.last_login_at) }}</td>
            <td v-if="auth.hasMinRole('Admin')" class="px-4 py-2">
              <button
                class="text-sm text-blue-600 hover:underline"
                @click="goToDetail(user.id)"
              >
                {{ t("users.edit") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else class="mt-4 text-gray-500">{{ t("users.no_users") }}</p>

    <!-- Pagination -->
    <div v-if="pagination && pagination.total_pages > 1" class="mt-4 flex gap-2">
      <button
        :disabled="page === 1"
        class="rounded border px-3 py-1 text-sm disabled:opacity-40"
        @click="page--; fetchUsers()"
      >
        ←
      </button>
      <span class="px-3 py-1 text-sm">{{ page }} / {{ pagination.total_pages }}</span>
      <button
        :disabled="page === pagination.total_pages"
        class="rounded border px-3 py-1 text-sm disabled:opacity-40"
        @click="page++; fetchUsers()"
      >
        →
      </button>
    </div>
  </div>

  <!-- Create user modal -->
  <Teleport to="body">
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="closeModal"
    >
      <div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 class="mb-5 text-lg font-semibold">{{ t("users.create") }}</h2>

        <div class="space-y-4">
          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.username") }}</span>
            <input
              v-model="form.username"
              type="text"
              class="mt-1 w-full rounded border px-3 py-2 text-sm"
              autocomplete="off"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.email") }}</span>
            <input
              v-model="form.email"
              type="email"
              class="mt-1 w-full rounded border px-3 py-2 text-sm"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.password") }}</span>
            <input
              v-model="form.password"
              type="password"
              class="mt-1 w-full rounded border px-3 py-2 text-sm"
              autocomplete="new-password"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.display_name") }}</span>
            <input
              v-model="form.display_name"
              type="text"
              class="mt-1 w-full rounded border px-3 py-2 text-sm"
            />
          </label>

          <div class="flex gap-4">
            <label class="block flex-1">
              <span class="text-sm font-medium text-gray-700">{{ t("users.role") }}</span>
              <select v-model="form.role" class="mt-1 w-full rounded border px-3 py-2 text-sm">
                <option v-for="r in VALID_ROLES" :key="r" :value="r">{{ r }}</option>
              </select>
            </label>

            <label class="block flex-1">
              <span class="text-sm font-medium text-gray-700">{{ t("users.preferred_lang") }}</span>
              <select v-model="form.preferred_lang" class="mt-1 w-full rounded border px-3 py-2 text-sm">
                <option value="it">Italiano</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
        </div>

        <p v-if="createError" class="mt-3 text-sm text-red-600">{{ createError }}</p>

        <div class="mt-6 flex justify-end gap-3">
          <button
            class="rounded border px-4 py-2 text-sm hover:bg-gray-50"
            @click="closeModal"
          >
            {{ t("common.cancel") }}
          </button>
          <button
            :disabled="isCreating || !form.username || !form.email || !form.password"
            class="rounded bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700 disabled:opacity-40"
            @click="createUser"
          >
            {{ isCreating ? t("common.loading") : t("users.create") }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
