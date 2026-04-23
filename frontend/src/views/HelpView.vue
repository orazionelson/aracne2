<script setup lang="ts">
/**
 * Help — in-app documentation browser.
 *
 * Two-column layout: a search bar + navigation tree on the left, the
 * rendered page on the right. Clicking an internal link of the form
 * ``/help/page?path=...`` is intercepted and resolved in-app via the
 * store, so page-to-page navigation does not round-trip through the
 * router.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import {
  MagnifyingGlassIcon,
  HomeIcon,
  ArrowPathIcon,
} from "@heroicons/vue/24/outline";
import { useAuthStore } from "@/stores/auth";
import { useHelpStore } from "@/stores/help";
import HelpTreeItem from "@/components/help/HelpTreeItem.vue";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const help = useHelpStore();

const query = ref("");
const expanded = ref<Record<string, boolean>>({});
const refreshedMessage = ref("");

const currentPath = computed<string>(() => {
  const raw = route.query.path;
  return typeof raw === "string" ? raw : "";
});

onMounted(async () => {
  await help.fetchTree();
  // Expand the section containing the current page, if any.
  autoExpandForPath(currentPath.value);
  await help.fetchPage(currentPath.value);
});

watch(
  () => currentPath.value,
  async (path) => {
    autoExpandForPath(path);
    await help.fetchPage(path);
  },
);

function autoExpandForPath(path: string): void {
  if (!path) return;
  const segments = path.split("/");
  let acc = "";
  for (let i = 0; i < segments.length - 1; i += 1) {
    acc = acc ? `${acc}/${segments[i]}` : segments[i];
    expanded.value[acc] = true;
  }
}

function goTo(path: string): void {
  router.push({ name: "help", query: { path } });
}

async function onSearch(): Promise<void> {
  await help.search(query.value);
}

function clearSearch(): void {
  query.value = "";
  help.clearSearch();
}

function toggleSection(path: string): void {
  expanded.value[path] = !expanded.value[path];
}

async function refreshCache(): Promise<void> {
  await help.refreshCache();
  await help.fetchTree();
  await help.fetchPage(currentPath.value);
  refreshedMessage.value = t("help.refresh_done");
  setTimeout(() => (refreshedMessage.value = ""), 3500);
}

// Intercept clicks inside the rendered HTML so internal /help/page links
// stay in-app without forcing a full navigation.
function onContentClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null;
  if (!target) return;
  const anchor = target.closest("a") as HTMLAnchorElement | null;
  if (!anchor) return;
  const href = anchor.getAttribute("href") ?? "";
  if (!href.startsWith("/help/page")) return;
  event.preventDefault();
  const url = new URL(anchor.href, window.location.origin);
  const path = url.searchParams.get("path") ?? "";
  goTo(path);
}

</script>

<template>
  <div class="flex h-[calc(100vh-0px)] flex-col">
    <header class="border-b border-gray-200 px-6 py-4 dark:border-gray-700">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold">{{ t("help.title") }}</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400">{{ t("help.subtitle") }}</p>
        </div>
        <button
          v-if="auth.hasMinRole('Admin')"
          class="inline-flex items-center gap-1.5 rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
          :title="t('help.refresh')"
          @click="refreshCache"
        >
          <ArrowPathIcon class="h-4 w-4" />
          {{ t("help.refresh") }}
        </button>
      </div>
      <p v-if="refreshedMessage" class="mt-2 text-xs text-green-600 dark:text-green-400">
        {{ refreshedMessage }}
      </p>
    </header>

    <div class="flex min-h-0 flex-1">
      <!-- Sidebar: search + tree -->
      <aside class="w-72 shrink-0 border-r border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900">
        <div class="border-b border-gray-200 p-3 dark:border-gray-700">
          <form class="relative" @submit.prevent="onSearch">
            <MagnifyingGlassIcon class="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
            <input
              v-model="query"
              type="search"
              :placeholder="t('help.search_placeholder')"
              class="w-full rounded border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              @input="query.trim().length < 2 && clearSearch()"
            />
          </form>
          <p v-if="query && query.trim().length < 2" class="mt-1 text-[11px] text-gray-400">
            {{ t("help.search_hint") }}
          </p>
        </div>

        <div class="overflow-y-auto" style="max-height: calc(100vh - 150px);">
          <!-- Search results take over the sidebar when active -->
          <div v-if="help.searchResults.length > 0" class="p-2">
            <button
              v-for="hit in help.searchResults"
              :key="hit.path"
              class="mb-1 block w-full rounded border border-gray-200 bg-white p-2 text-left text-xs hover:border-indigo-300 hover:bg-indigo-50 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/40"
              @click="goTo(hit.path)"
            >
              <div class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">
                {{ hit.title }}
              </div>
              <div class="mt-1 text-gray-500 dark:text-gray-400" v-html="hit.snippet" />
            </button>
          </div>
          <p
            v-else-if="help.isSearching"
            class="p-4 text-center text-sm text-gray-400"
          >
            {{ t("help.loading") }}
          </p>
          <p
            v-else-if="query.trim().length >= 2"
            class="p-4 text-center text-sm text-gray-400"
          >
            {{ t("help.search_no_results") }}
          </p>

          <!-- Default: navigation tree -->
          <nav v-else class="p-2">
            <button
              class="mb-1 flex w-full items-center gap-2 rounded px-2 py-1 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
              :class="currentPath === '' ? 'bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300' : ''"
              @click="goTo('')"
            >
              <HomeIcon class="h-4 w-4 shrink-0" />
              <span class="truncate">{{ t("help.home") }}</span>
            </button>

            <p v-if="help.tree.length === 0 && !help.isLoadingTree" class="p-2 text-sm text-gray-400">
              {{ t("help.empty_tree") }}
            </p>

            <template v-for="node in help.tree" :key="node.path">
              <HelpTreeItem
                :node="node"
                :current-path="currentPath"
                :expanded="expanded"
                @navigate="goTo"
                @toggle="toggleSection"
              />
            </template>
          </nav>
        </div>
      </aside>

      <!-- Page content -->
      <main class="flex-1 overflow-y-auto bg-white p-6 dark:bg-gray-950">
        <div v-if="help.isLoadingPage" class="text-gray-400">{{ t("help.loading") }}</div>
        <div v-else-if="!help.currentPage" class="text-gray-500">
          {{ t("help.not_found") }}
        </div>
        <article v-else class="mx-auto max-w-3xl">
          <!-- Breadcrumb -->
          <nav class="mb-4 flex flex-wrap gap-x-1.5 text-xs text-gray-500 dark:text-gray-400">
            <template v-for="(crumb, idx) in help.currentPage.breadcrumb" :key="crumb[0] + idx">
              <button
                v-if="idx < help.currentPage.breadcrumb.length - 1"
                class="hover:text-indigo-600 dark:hover:text-indigo-300"
                @click="goTo(crumb[0])"
              >
                {{ crumb[1] }}
              </button>
              <span v-else class="text-gray-700 dark:text-gray-200">{{ crumb[1] }}</span>
              <span v-if="idx < help.currentPage.breadcrumb.length - 1">/</span>
            </template>
          </nav>

          <!-- Rendered HTML — sanitised by the backend with bleach -->
          <div
            class="prose prose-sm max-w-none dark:prose-invert"
            @click="onContentClick"
            v-html="help.currentPage.html"
          />
        </article>
      </main>
    </div>
  </div>
</template>

<style scoped>
:deep(mark) {
  background-color: rgb(254 240 138);
  color: rgb(113 63 18);
  padding: 0 2px;
  border-radius: 2px;
}
:deep(.dark mark),
.dark :deep(mark) {
  background-color: rgb(133 77 14);
  color: rgb(254 243 199);
}
</style>
