<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const usernameOrEmail = ref("");
const password = ref("");
const showPassword = ref(false);
const errorMessage = ref("");
const isLoading = ref(false);

// Validates that the redirect target is a safe internal path (prevents open redirect)
function isSafeRedirect(url: string): boolean {
  return url.startsWith("/") && !url.startsWith("//") && !url.includes(":");
}

async function handleLogin(): Promise<void> {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    await auth.login(usernameOrEmail.value, password.value);
    const raw = route.query.redirect as string | undefined;
    const redirect = raw && isSafeRedirect(raw) ? raw : "/dashboard";
    await router.push(redirect);
  } catch {
    // Generic message — do not distinguish between wrong username and wrong password
    errorMessage.value = t("auth.invalid_credentials");
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-md bg-white rounded-xl shadow p-8">
      <h1 class="text-2xl font-bold text-center mb-6">{{ t("auth.sign_in") }}</h1>
      <form @submit.prevent="handleLogin" novalidate>
        <div class="mb-4">
          <label class="block text-sm font-medium mb-1">{{ t("auth.username_or_email") }}</label>
          <input
            v-model="usernameOrEmail"
            type="text"
            required
            autocomplete="username"
            class="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2"
          />
        </div>
        <div class="mb-6 relative">
          <label class="block text-sm font-medium mb-1">{{ t("auth.password") }}</label>
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            required
            autocomplete="current-password"
            class="w-full border rounded-lg px-3 py-2 pr-10 focus:outline-none focus:ring-2"
          />
          <button
            type="button"
            @click="showPassword = !showPassword"
            class="absolute right-3 top-8 text-gray-500 text-sm"
          >
            {{ showPassword ? t("auth.hide_password") : t("auth.show_password") }}
          </button>
        </div>
        <p v-if="errorMessage" class="text-red-600 text-sm mb-4">{{ errorMessage }}</p>
        <button
          type="submit"
          :disabled="isLoading"
          class="w-full bg-blue-600 text-white py-2 rounded-lg font-semibold
                 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ isLoading ? t("auth.sign_in_loading") : t("auth.sign_in") }}
        </button>
      </form>
    </div>
  </div>
</template>
