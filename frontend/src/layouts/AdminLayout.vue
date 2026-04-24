<script setup lang="ts">
import { computed, watch } from "vue";
import { useRoute, RouterView } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import AppSidebar from "@/components/layout/AppSidebar.vue";
import AppFooter from "@/components/layout/AppFooter.vue";

const { t } = useI18n();
const route = useRoute();
const auth = useAuthStore();
const ui = useUiStore();

// Full-bleed views manage their own scroll (e.g. document editor).
const clipsOwnScroll = computed(() => route.meta.clipsOwnScroll === true);

// Routes that force the sidebar into icon-strip mode (e.g. document editor).
const forceCollapsed = computed(() => route.meta.forceCollapsedSidebar === true);

watch(
  forceCollapsed,
  (value) => {
    ui.setSidebarForceCollapsed(value);
  },
  { immediate: true },
);

// Show footer everywhere in admin except on full-bleed views.
const showFooter = computed(() => !clipsOwnScroll.value);
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-gray-50 text-gray-800 dark:bg-gray-900 dark:text-gray-100">
    <AppSidebar />

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Impersonation banner above main content -->
      <div
        v-if="auth.impersonating"
        class="flex h-10 shrink-0 items-center justify-between bg-amber-400 px-4 text-sm font-medium text-amber-900"
      >
        <span>
          ⚠ {{ t("auth.impersonating", { username: auth.impersonating.username, role: auth.impersonating.role }) }}
        </span>
        <button
          class="rounded border border-amber-700 px-3 py-0.5 text-xs hover:bg-amber-500"
          @click="auth.exitImpersonation()"
        >
          {{ t("auth.exit_impersonation") }}
        </button>
      </div>

      <main
        :class="[
          'min-h-0 flex-1',
          clipsOwnScroll ? 'overflow-hidden' : 'overflow-y-auto',
        ]"
      >
        <template v-if="showFooter">
          <!-- Sticky-footer pattern: short pages push the footer to the
               viewport bottom; long pages scroll past content and the
               footer appears naturally at the end. -->
          <div class="flex min-h-full flex-col">
            <div class="flex-1">
              <RouterView />
            </div>
            <AppFooter />
          </div>
        </template>
        <RouterView v-else />
      </main>
    </div>
  </div>
</template>
