<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";

// Aracne lockup — vertical wordmark "Aracne" under the chevron marchio.
// Light variant on white background, inverse variant on dark background.
// Asset tree documented in frontend/public/aracne-icons/README.md.
const LOGO_LIGHT = "/aracne-icons/lockup/aracne-lockup-vertical-1024.png";
const LOGO_DARK = "/aracne-icons/lockup/aracne-lockup-vertical-1024-inverse.png";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const ui = useUiStore();

const usernameOrEmail = ref("");
const password = ref("");
const showPassword = ref(false);
const errorMessage = ref("");
const isLoading = ref(false);

const isDark = computed(() => ui.theme === "dark");
const currentYear = new Date().getFullYear();

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
  <div class="flex min-h-screen flex-col bg-white dark:bg-gray-900">
    <main class="flex flex-1 flex-col items-center justify-center px-4 py-10">
      <router-link to="/" class="mb-8 block" :title="t('auth.sign_in')">
        <img
          :src="isDark ? LOGO_DARK : LOGO_LIGHT"
          alt="Aracne2"
          class="h-40 w-auto object-contain sm:h-48"
        />
      </router-link>

      <div class="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:shadow-black/40">
        <h1 class="sr-only">{{ t("auth.sign_in") }}</h1>
        <form @submit.prevent="handleLogin" novalidate>
          <div class="mb-4">
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t("auth.username_or_email") }}
            </label>
            <input
              v-model="usernameOrEmail"
              type="text"
              required
              autocomplete="username"
              class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>
          <div class="relative mb-6">
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t("auth.password") }}
            </label>
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              required
              autocomplete="current-password"
              class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 pr-16 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
            <button
              type="button"
              class="absolute right-3 top-8 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? t("auth.hide_password") : t("auth.show_password") }}
            </button>
          </div>
          <p v-if="errorMessage" class="mb-4 text-sm text-red-600 dark:text-red-400">
            {{ errorMessage }}
          </p>
          <button
            type="submit"
            :disabled="isLoading"
            class="w-full rounded-lg bg-indigo-600 py-2 font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {{ isLoading ? t("auth.sign_in_loading") : t("auth.sign_in") }}
          </button>
        </form>
      </div>
    </main>

    <footer class="border-t border-gray-100 py-4 text-center text-xs text-gray-400 dark:border-gray-800 dark:text-gray-500">
      © {{ currentYear }} Aracne2 · Powered by Aracne2
    </footer>
  </div>
</template>
