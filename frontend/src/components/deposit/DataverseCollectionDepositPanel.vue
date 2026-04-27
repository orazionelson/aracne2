<script setup lang="ts">
/**
 * "Deposita" → Dataverse tab body. Thin wrapper around the existing
 * DataverseCollectionSection so the deposit-registry pattern stays
 * 1:1 (one plugin → one Vue component name).
 */
import DataverseCollectionSection from "@/components/ui/DataverseCollectionSection.vue";

defineProps<{ slug: string }>();
</script>

<template>
  <DataverseCollectionSection :slug="slug" bare />
</template>
