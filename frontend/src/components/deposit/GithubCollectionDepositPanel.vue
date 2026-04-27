<script setup lang="ts">
/**
 * "Deposita" → GitHub tab body. Thin wrapper around ForgeCollectionSection.
 */
import { computed } from "vue";
import { useGithubStore } from "@/stores/github";
import { usePluginStore } from "@/stores/plugins";
import { useCollectionStore } from "@/stores/collections";
import ForgeCollectionSection from "@/components/ui/ForgeCollectionSection.vue";

defineProps<{ slug: string }>();
const emit = defineEmits<{ (e: "initialized"): void }>();

const store = useGithubStore();
const collectionStore = useCollectionStore();
const pluginStore = usePluginStore();

const isPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "github_integration" && p.status === "active"),
);
</script>

<template>
  <ForgeCollectionSection
    :slug="slug"
    :document-count="collectionStore.documents.length"
    :is-plugin-active="isPluginActive"
    :store="store"
    i18n-prefix="github"
    default-base-url="https://github.com"
    bare
    @initialized="emit('initialized')"
  />
</template>
