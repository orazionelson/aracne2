<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();

async function handleLogout(): Promise<void> {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <nav class="fixed inset-x-0 top-0 z-50 flex h-14 items-center gap-6 bg-gray-900 px-6 text-white">
    <!-- Brand -->
    <router-link
      to="/"
      class="text-lg font-bold tracking-tight hover:text-gray-300"
    >
      Aracne2
    </router-link>

    <!-- Primary links -->
    <div class="flex flex-1 gap-4 text-sm">
      <router-link
        to="/"
        class="text-gray-400 transition-colors hover:text-white"
        exact-active-class="!text-white font-medium"
      >
        {{ t("nav.home") }}
      </router-link>
      <router-link
        v-if="auth.hasMinRole('EditorInChief')"
        to="/users"
        class="text-gray-400 transition-colors hover:text-white"
        active-class="!text-white font-medium"
      >
        {{ t("nav.users") }}
      </router-link>
    </div>

    <!-- Right side -->
    <div class="flex items-center gap-5 text-sm">
      <span class="hidden text-xs text-gray-500 sm:inline">
        {{ auth.user?.username }} &middot; {{ auth.user?.role }}
      </span>
      <router-link
        to="/profile"
        class="text-gray-400 transition-colors hover:text-white"
        active-class="!text-white font-medium"
      >
        {{ t("nav.profile") }}
      </router-link>
      <button
        class="text-gray-400 transition-colors hover:text-white"
        @click="handleLogout"
      >
        {{ t("auth.sign_out") }}
      </button>
    </div>
  </nav>
</template>
