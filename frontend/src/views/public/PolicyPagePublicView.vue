<script setup lang="ts">
/**
 * /policies/<url_slug> — render a single published policy.
 *
 * Calls the anonymous backend route which returns the
 * server-rendered Markdown → HTML body, plus the version metadata
 * the page footer displays. The HTML comes from a controlled
 * Markdown pipeline (markdown-it on the backend, html: false), so
 * we render it as-is via v-html.
 *
 * The "Print" button uses the browser's native ``window.print()``;
 * a small @media print stylesheet (in the global app CSS) hides
 * navbar / footer / sidebar so the printed PDF carries only the
 * policy body and its version footer. No server-side PDF
 * dependency in this milestone — see FUTURE_IDEAS §29 for the
 * sidecar option.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { PrinterIcon } from "@heroicons/vue/24/outline";
import { apiClient } from "@/services/api";

interface PolicyRenderResponse {
  title: string;
  locale: string;
  html: string;
  version_number: number;
  saved_at: string;
  saved_by: string | null;
}

const { t, te, locale } = useI18n();
const route = useRoute();

const data = ref<PolicyRenderResponse | null>(null);
const error = ref<string | null>(null);
const isLoading = ref(false);

const urlSlug = computed(() => String(route.params.url_slug ?? ""));

async function load(): Promise<void> {
  if (!urlSlug.value) return;
  isLoading.value = true;
  error.value = null;
  data.value = null;
  try {
    data.value = await apiClient.get<PolicyRenderResponse>(
      `/policies/${urlSlug.value}?lang=${locale.value}`,
    );
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    isLoading.value = false;
  }
}

onMounted(load);
watch([urlSlug, locale], load);

function pageTitle(): string {
  if (!data.value) return "";
  return te(data.value.title) ? t(data.value.title) : data.value.title;
}

function handlePrint(): void {
  window.print();
}
</script>

<template>
  <main class="mx-auto max-w-3xl px-4 py-10 policy-page">
    <p v-if="isLoading" class="text-sm text-gray-500">{{ t("common.loading") }}</p>
    <p v-else-if="error" class="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {{ error }}
    </p>

    <template v-else-if="data">
      <header class="mb-4 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-gray-900">{{ pageTitle() }}</h1>
        <button
          type="button"
          class="no-print inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          @click="handlePrint"
        >
          <PrinterIcon class="h-4 w-4" />
          {{ t("policy_pages.print_button") }}
        </button>
      </header>

      <article
        class="prose prose-sm max-w-none text-gray-800"
        v-html="data.html"
      />
    </template>
  </main>
</template>

<style>
@media print {
  .no-print {
    display: none !important;
  }
  /* Hide application chrome on print so the PDF only carries the
     policy body. PublicHeader / PublicFooter come from the layout;
     the global @media print rule below catches them by class. */
  header.aracne-public-header,
  footer.aracne-public-footer {
    display: none !important;
  }
}
</style>
