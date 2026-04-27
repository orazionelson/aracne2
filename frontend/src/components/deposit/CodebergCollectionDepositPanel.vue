<script setup lang="ts">
/**
 * "Deposita" → Codeberg tab body. Thin wrapper around the generic
 * ForgeCollectionSection, parametrised with the Codeberg store + i18n
 * prefix so the registry-dispatched panel doesn't need to know about
 * forge plumbing.
 */
import { computed } from "vue";
import { useCodebergStore } from "@/stores/codeberg";
import { usePluginStore } from "@/stores/plugins";
import { useCollectionStore } from "@/stores/collections";
import ForgeCollectionSection from "@/components/ui/ForgeCollectionSection.vue";

defineProps<{ slug: string }>();
const emit = defineEmits<{ (e: "initialized"): void }>();

const store = useCodebergStore();
const collectionStore = useCollectionStore();
const pluginStore = usePluginStore();

const isPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "codeberg_integration" && p.status === "active"),
);
</script>

<template>
  <ForgeCollectionSection
    :slug="slug"
    :document-count="collectionStore.documents.length"
    :is-plugin-active="isPluginActive"
    :store="store"
    i18n-prefix="codeberg"
    default-base-url="https://codeberg.org"
    bare
    @initialized="emit('initialized')"
  />
</template>
