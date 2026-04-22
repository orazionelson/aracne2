<script setup lang="ts">
/**
 * Generic host page for per-plugin configuration panels.
 *
 * Route: /admin/plugins/:slug/config
 *
 * The slug is looked up in the frontend plugin-config registry
 * (components/plugins/registry.ts). Known slugs render the matching
 * panel component; unknown slugs show a "no configuration available"
 * message.
 */

import { computed, defineAsyncComponent } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { usePluginStore } from "@/stores/plugins";
import { getPluginConfigEntry } from "@/components/plugins/registry";

const props = defineProps<{ slug: string }>();

const { t, te } = useI18n();
const router = useRouter();
const pluginStore = usePluginStore();

// Registry lookup — a known slug yields both the panel component and
// (optionally) the i18n title key. An unknown slug renders a fallback.
const entry = computed(() => getPluginConfigEntry(props.slug));

const PanelComponent = computed(() =>
  entry.value
    ? defineAsyncComponent(entry.value.component)
    : null,
);

const plugin = computed(() =>
  pluginStore.plugins.find((p) => p.name === props.slug),
);

const title = computed(() => {
  if (entry.value?.titleKey && te(entry.value.titleKey)) {
    return t(entry.value.titleKey);
  }
  return plugin.value?.display_name ?? props.slug;
});

async function ensurePlugins(): Promise<void> {
  // Fetch the plugin list if the user deep-linked here directly.
  if (pluginStore.plugins.length === 0) {
    try {
      await pluginStore.fetchPlugins();
    } catch {
      /* non-fatal — registry lookup still works, UI just shows raw slug */
    }
  }
}

ensurePlugins();
</script>

<template>
  <div class="p-6">
    <button
      class="mb-4 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
      @click="router.push({ name: 'admin-plugins' })"
    >
      ← {{ t("plugins.title") }}
    </button>

    <h1 class="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{{ title }}</h1>

    <!-- Unknown slug -->
    <p
      v-if="!entry"
      class="mt-6 rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200"
    >
      {{ t("plugins.no_config_available") }}
    </p>

    <!-- Known slug but plugin row is missing (deactivated after activation? fresh install?) -->
    <p
      v-else-if="plugin && plugin.status !== 'active'"
      class="mt-6 rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200"
    >
      {{ t("plugins.activate_first") }}
    </p>

    <component :is="PanelComponent" v-else-if="PanelComponent" class="mt-6" />
  </div>
</template>
