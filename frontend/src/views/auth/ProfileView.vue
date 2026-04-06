<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();

function formatDate(iso: string | null): string {
  if (!iso) return t("profile.never");
  return new Date(iso).toLocaleString();
}
</script>

<template>
  <div class="p-6 max-w-xl mx-auto">
    <h1 class="text-2xl font-bold mb-6">{{ t("profile.title") }}</h1>

    <div v-if="auth.user" class="space-y-4">
      <div class="border rounded p-4 space-y-3 text-sm">
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.username") }}</span>
          <span>{{ auth.user.username }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.email") }}</span>
          <span>{{ auth.user.email }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.display_name") }}</span>
          <span>{{ auth.user.display_name ?? "—" }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.role") }}</span>
          <span>{{ auth.user.role }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.preferred_lang") }}</span>
          <span>{{ auth.user.preferred_lang }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.last_login") }}</span>
          <span>{{ formatDate(auth.user.last_login_at) }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700">{{ t("profile.member_since") }}</span>
          <span>{{ formatDate(auth.user.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
