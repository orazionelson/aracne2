<script setup lang="ts">
/**
 * Public "Forgot password?" form. Submitting always shows the same
 * confirmation message regardless of whether the account exists — the
 * backend mirrors that contract by always replying 204, so account
 * enumeration is closed at every layer.
 */
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

const emailOrUsername = ref("");
const isSubmitting = ref(false);
const submitted = ref(false);

async function onSubmit(): Promise<void> {
  const value = emailOrUsername.value.trim();
  if (!value) return;
  isSubmitting.value = true;
  try {
    await auth.requestPasswordReset(value);
  } catch {
    // Even on a transport error we display the generic confirmation —
    // exposing failure modes here would partially leak account state.
  } finally {
    isSubmitting.value = false;
    submitted.value = true;
  }
}
</script>

<template>
  <div class="mx-auto mt-12 w-full max-w-md px-4">
    <h1 class="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
      {{ t("auth.forgot.title") }}
    </h1>
    <p class="mb-6 text-sm text-gray-600 dark:text-gray-400">
      {{ t("auth.forgot.intro") }}
    </p>

    <div
      v-if="submitted"
      class="rounded border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200"
    >
      <p>{{ t("auth.forgot.confirmation") }}</p>
      <button
        class="mt-3 text-sm font-medium text-emerald-700 underline hover:text-emerald-900 dark:text-emerald-300"
        @click="router.push({ name: 'login' })"
      >
        {{ t("auth.forgot.back_to_login") }}
      </button>
    </div>

    <form v-else class="space-y-4" @submit.prevent="onSubmit">
      <div>
        <label
          for="reset-email"
          class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          {{ t("auth.forgot.field_label") }}
        </label>
        <input
          id="reset-email"
          v-model="emailOrUsername"
          type="text"
          required
          autocomplete="username"
          class="w-full rounded border border-gray-300 px-3 py-2 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          :placeholder="t('auth.forgot.field_placeholder')"
        />
      </div>

      <button
        type="submit"
        class="w-full rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        :disabled="isSubmitting || !emailOrUsername.trim()"
      >
        {{ t("auth.forgot.submit") }}
      </button>

      <p class="text-center text-sm">
        <button
          type="button"
          class="text-indigo-600 hover:underline dark:text-indigo-400"
          @click="router.push({ name: 'login' })"
        >
          {{ t("auth.forgot.back_to_login") }}
        </button>
      </p>
    </form>
  </div>
</template>
