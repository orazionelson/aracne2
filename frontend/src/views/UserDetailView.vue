<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { apiClient } from "@/services/api";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

interface RoleInfo {
  role_name: string;
  assigned_at: string;
}

interface UserResponse {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  preferred_lang: string;
  role: string;
  roles: RoleInfo[];
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  deleted_at: string | null;
}

const user = ref<UserResponse | null>(null);
const isLoading = ref(false);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMsg = ref<string | null>(null);

// Form fields
const formEmail = ref("");
const formDisplayName = ref("");
const formPreferredLang = ref("it");
const formIsActive = ref(true);
const formIsVerified = ref(false);

// Role assignment
const roleToAssign = ref("");
const VALID_ROLES = ["Admin", "EditorInChief", "Designer", "Editor", "User"];

async function fetchUser(): Promise<void> {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await apiClient.get<UserResponse>(`/users/${route.params.username}`);
    user.value = data;
    formEmail.value = data.email;
    formDisplayName.value = data.display_name ?? "";
    formPreferredLang.value = data.preferred_lang;
    formIsActive.value = data.is_active;
    formIsVerified.value = data.is_verified;
  } catch {
    error.value = t("users.not_found");
  } finally {
    isLoading.value = false;
  }
}

async function saveUser(): Promise<void> {
  if (!user.value) return;
  isSaving.value = true;
  error.value = null;
  successMsg.value = null;
  try {
    const updated = await apiClient.patch<UserResponse>(`/users/${user.value.id}`, {
      email: formEmail.value || undefined,
      display_name: formDisplayName.value || null,
      preferred_lang: formPreferredLang.value,
      is_active: formIsActive.value,
      is_verified: formIsVerified.value,
    });
    user.value = updated;
    successMsg.value = t("users.save");
  } catch {
    error.value = t("common.error");
  } finally {
    isSaving.value = false;
  }
}

async function assignRole(): Promise<void> {
  if (!user.value || !roleToAssign.value) return;
  error.value = null;
  successMsg.value = null;
  try {
    const updated = await apiClient.post<UserResponse>(
      `/users/${user.value.id}/roles`,
      { role_name: roleToAssign.value }
    );
    user.value = updated;
    roleToAssign.value = "";
  } catch {
    error.value = t("common.error");
  }
}

async function revokeRole(roleName: string): Promise<void> {
  if (!user.value) return;
  error.value = null;
  try {
    const updated = await apiClient.delete<UserResponse>(
      `/users/${user.value.id}/roles/${roleName}`
    );
    user.value = updated;
  } catch {
    error.value = t("common.error");
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return t("users.never");
  return new Date(iso).toLocaleString();
}

onMounted(fetchUser);
</script>

<template>
  <div class="p-6 max-w-2xl mx-auto">
    <button
      class="text-sm text-blue-600 hover:underline mb-4"
      @click="router.back()"
    >
      ← {{ t("users.title") }}
    </button>

    <p v-if="isLoading" class="text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="error && !user" class="text-red-600">{{ error }}</p>

    <template v-else-if="user">
      <h1 class="text-2xl font-bold mb-6">{{ user.username }}</h1>

      <!-- Feedback -->
      <p v-if="error" class="text-red-600 mb-3 text-sm">{{ error }}</p>
      <p v-if="successMsg" class="text-green-600 mb-3 text-sm">{{ successMsg }}</p>

      <!-- Edit form -->
      <section class="border rounded p-4 mb-6">
        <div class="grid gap-4">
          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.email") }}</span>
            <input
              v-model="formEmail"
              type="email"
              class="mt-1 w-full border rounded px-3 py-2 text-sm"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.display_name") }}</span>
            <input
              v-model="formDisplayName"
              type="text"
              class="mt-1 w-full border rounded px-3 py-2 text-sm"
            />
          </label>

          <label class="block">
            <span class="text-sm font-medium text-gray-700">{{ t("users.preferred_lang") }}</span>
            <select
              v-model="formPreferredLang"
              class="mt-1 w-full border rounded px-3 py-2 text-sm"
            >
              <option value="it">Italiano</option>
              <option value="en">English</option>
            </select>
          </label>

          <div class="flex gap-6">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="formIsActive" type="checkbox" />
              {{ t("users.active") }}
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="formIsVerified" type="checkbox" />
              {{ t("users.verified") }}
            </label>
          </div>
        </div>

        <button
          :disabled="isSaving"
          class="mt-4 bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          @click="saveUser"
        >
          {{ isSaving ? t("common.loading") : t("users.save") }}
        </button>
      </section>

      <!-- Roles -->
      <section class="border rounded p-4 mb-6">
        <h2 class="font-semibold mb-3">{{ t("users.roles_title") }}</h2>
        <ul class="space-y-2 mb-4">
          <li
            v-for="r in user.roles"
            :key="r.role_name"
            class="flex items-center justify-between text-sm"
          >
            <span>{{ r.role_name }}
              <span class="text-gray-400 text-xs ml-2">{{ formatDate(r.assigned_at) }}</span>
            </span>
            <button
              class="text-red-500 hover:underline text-xs"
              @click="revokeRole(r.role_name)"
            >
              {{ t("users.revoke") }}
            </button>
          </li>
        </ul>

        <div class="flex gap-2">
          <select v-model="roleToAssign" class="border rounded px-3 py-1 text-sm flex-1">
            <option value="">{{ t("users.assign_role") }}</option>
            <option v-for="r in VALID_ROLES" :key="r" :value="r">{{ r }}</option>
          </select>
          <button
            :disabled="!roleToAssign"
            class="bg-gray-800 text-white px-3 py-1 rounded text-sm disabled:opacity-40 hover:bg-gray-700"
            @click="assignRole"
          >
            {{ t("users.assign_role") }}
          </button>
        </div>
      </section>

      <!-- Metadata -->
      <section class="text-xs text-gray-400 space-y-1">
        <p>ID: {{ user.id }}</p>
        <p>{{ t("users.created_at") }}: {{ formatDate(user.created_at) }}</p>
        <p>{{ t("users.last_login") }}: {{ formatDate(user.last_login_at) }}</p>
        <p v-if="user.deleted_at" class="text-red-400">
          Deleted: {{ formatDate(user.deleted_at) }}
        </p>
      </section>
    </template>
  </div>
</template>
