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
  <div class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">{{ t("users.title") }}</h1>
    </div>

    <!-- Filters -->
    <div class="flex gap-3 mb-4">
      <input
        v-model="search"
        type="text"
        :placeholder="t('users.search_placeholder')"
        class="flex-1 border rounded px-3 py-2 text-sm"
      />
      <select v-model="isActiveFilter" class="border rounded px-3 py-2 text-sm">
        <option value="">{{ t("users.all_roles") }}</option>
        <option value="true">{{ t("users.filter_active") }}</option>
        <option value="false">{{ t("users.filter_inactive") }}</option>
      </select>
    </div>

    <!-- Error -->
    <p v-if="error" class="text-red-600 mb-4">{{ error }}</p>

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
              <span
                :class="user.is_active ? 'text-green-600' : 'text-gray-400'"
              >
                {{ user.is_active ? t("users.active") : t("users.inactive") }}
              </span>
            </td>
            <td class="px-4 py-2 text-gray-500">
              {{ formatDate(user.last_login_at) }}
            </td>
            <td v-if="auth.hasMinRole('Admin')" class="px-4 py-2">
              <button
                class="text-blue-600 hover:underline text-sm"
                @click="goToDetail(user.id)"
              >
                {{ t("users.edit") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else class="text-gray-500 mt-4">{{ t("users.no_users") }}</p>

    <!-- Pagination -->
    <div v-if="pagination && pagination.total_pages > 1" class="flex gap-2 mt-4">
      <button
        :disabled="page === 1"
        class="px-3 py-1 border rounded text-sm disabled:opacity-40"
        @click="page--; fetchUsers()"
      >
        ←
      </button>
      <span class="px-3 py-1 text-sm">{{ page }} / {{ pagination.total_pages }}</span>
      <button
        :disabled="page === pagination.total_pages"
        class="px-3 py-1 border rounded text-sm disabled:opacity-40"
        @click="page++; fetchUsers()"
      >
        →
      </button>
    </div>
  </div>
</template>
