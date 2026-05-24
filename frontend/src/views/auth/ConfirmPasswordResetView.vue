<script setup lang="ts">
/**
 * Public reset-completion form. Reads the plaintext token from the URL
 * (``/reset-password/{token}``), asks for a new password + confirmation,
 * posts to the backend and on success redirects to /login with a
 * one-shot success banner. Every failure mode collapses to the same
 * "link invalid or expired" message — the backend already returns a
 * single error code for that reason.
 */
import { ref } from "vue";
import axios from "axios";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const token = (route.params.token as string | undefined) ?? "";
const password = ref("");
const passwordConfirm = ref("");
const errorMessage = ref<string | null>(null);
const isSubmitting = ref(false);

async function onSubmit(): Promise<void> {
  errorMessage.value = null;
  if (password.value.length < 8) {
    errorMessage.value = t("auth.reset.password_too_short");
    return;
  }
  if (password.value !== passwordConfirm.value) {
    errorMessage.value = t("auth.reset.passwords_mismatch");
    return;
  }
  isSubmitting.value = true;
  try {
    await auth.confirmPasswordReset(token, password.value);
    router.push({
      name: "login",
      query: { reset: "ok" },
    });
  } catch (err) {
    // The backend collapses every legitimate failure (bad token, expired
    // token, already-used token, password too weak) into a single 401, so
    // a 401 maps cleanly to the "invalid or expired" message. Anything
    // else (network, 5xx, JS error from an interceptor) is an operational
    // problem the user can't fix by re-requesting a reset, and hiding it
    // as "invalid or expired" would make such bugs invisible to the
    // developer too.
    if (axios.isAxiosError(err) && err.response?.status === 401) {
      errorMessage.value = t("auth.reset.invalid_or_expired");
    } else {
      console.error("[confirm-reset] unexpected error:", err);
      errorMessage.value = t("common.unexpected_error");
    }
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div class="mx-auto mt-12 w-full max-w-md px-4">
    <h1 class="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
      {{ t("auth.reset.title") }}
    </h1>
    <p class="mb-6 text-sm text-gray-600 dark:text-gray-400">
      {{ t("auth.reset.intro") }}
    </p>

    <form class="space-y-4" @submit.prevent="onSubmit">
      <div>
        <label
          for="new-password"
          class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          {{ t("auth.reset.new_password_label") }}
        </label>
        <input
          id="new-password"
          v-model="password"
          type="password"
          required
          autocomplete="new-password"
          minlength="8"
          class="w-full rounded border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      <div>
        <label
          for="new-password-confirm"
          class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          {{ t("auth.reset.confirm_label") }}
        </label>
        <input
          id="new-password-confirm"
          v-model="passwordConfirm"
          type="password"
          required
          autocomplete="new-password"
          minlength="8"
          class="w-full rounded border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      <p
        v-if="errorMessage"
        class="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-200"
      >
        {{ errorMessage }}
        <span v-if="errorMessage === t('auth.reset.invalid_or_expired')">
          <button
            type="button"
            class="ml-1 underline"
            @click="router.push({ name: 'forgot-password' })"
          >
            {{ t("auth.reset.request_a_new_one") }}
          </button>
        </span>
      </p>

      <button
        type="submit"
        class="w-full rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        :disabled="isSubmitting || !password || !passwordConfirm"
      >
        {{ t("auth.reset.submit") }}
      </button>
    </form>
  </div>
</template>
