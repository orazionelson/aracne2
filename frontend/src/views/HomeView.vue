<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import PublicHomeSection from "@/components/PublicHomeSection.vue";

const { t } = useI18n();
const auth = useAuthStore();
</script>

<template>
  <!-- Authenticated users see the standard welcome page. -->
  <div v-if="auth.isAuthenticated" class="p-6">
    <h1 class="mb-1 text-2xl font-bold">{{ t("home.title") }}</h1>
    <p class="text-gray-500">
      {{ t("home.welcome", { name: auth.user?.display_name || auth.user?.username }) }}
    </p>
  </div>

  <!-- Unauthenticated visitors see the public home (enabled by Admin). -->
  <PublicHomeSection v-else />
</template>
