<script setup lang="ts">
import { computed } from "vue";
import { useRoute, RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import AppNavbar from "@/components/layout/AppNavbar.vue";

const auth = useAuthStore();
const route = useRoute();

// Show navbar on all authenticated pages; hide on login and 404
const showNav = computed(() => auth.isAuthenticated && route.name !== "not-found");
</script>

<template>
  <AppNavbar v-if="showNav" />
  <main :class="showNav ? 'pt-14' : ''">
    <RouterView />
  </main>
</template>
