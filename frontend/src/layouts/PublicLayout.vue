<script setup lang="ts">
import { RouterView } from "vue-router";
import PublicHeader from "@/components/layout/PublicHeader.vue";
import PublicFooter from "@/components/layout/PublicFooter.vue";
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <PublicHeader />
    <main class="flex-1 bg-gray-50">
      <RouterView />
    </main>
    <PublicFooter />
  </div>
</template>
