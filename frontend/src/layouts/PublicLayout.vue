<script setup lang="ts">
import { RouterView } from "vue-router";
import PublicHeader from "@/components/layout/PublicHeader.vue";
import AppFooter from "@/components/layout/AppFooter.vue";
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <PublicHeader />
    <main class="flex-1 bg-gray-50">
      <RouterView />
    </main>
    <AppFooter />
  </div>
</template>
