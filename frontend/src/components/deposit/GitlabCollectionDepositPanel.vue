<script setup lang="ts">
/**
 * "Deposita" → GitLab tab body. Thin wrapper around ForgeCollectionSection.
 */
import { computed } from "vue";
import { useGitlabStore } from "@/stores/gitlab";
import { usePluginStore } from "@/stores/plugins";
import { useCollectionStore } from "@/stores/collections";
import ForgeCollectionSection from "@/components/ui/ForgeCollectionSection.vue";

defineProps<{ slug: string }>();
const emit = defineEmits<{ (e: "initialized"): void }>();

const store = useGitlabStore();
const collectionStore = useCollectionStore();
const pluginStore = usePluginStore();

const isPluginActive = computed(() =>
  pluginStore.plugins.some((p) => p.name === "gitlab_integration" && p.status === "active"),
);
</script>

<template>
  <ForgeCollectionSection
    :slug="slug"
    :document-count="collectionStore.documents.length"
    :is-plugin-active="isPluginActive"
    :store="store"
    i18n-prefix="gitlab"
    default-base-url="https://gitlab.com"
    bare
    @initialized="emit('initialized')"
  />
</template>
