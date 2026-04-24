<script setup lang="ts">
/**
 * "Deposit to Github" section for a website.
 *
 * Mounted inside WebsiteEditView's ``deposit`` tab when the
 * ``github_integration`` plugin is active. Manages the per-website
 * Github link (repo owner/name, branch, optional PAT override)
 * and invokes the push action that sends the rendered static-site
 * tree to the forge in a single commit.
 *
 * Refuses push on DYNAMIC sites and on sites that have not been
 * built (the backend is the source of truth; this component only
 * surfaces the resulting error). No Initialize flow here — websites
 * are always derived from a collection; a forge can never be the
 * source of truth for a website.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  useGithubStore,
  type GithubWebsiteLink,
  type GithubWebsitePushResponse,
} from "@/stores/github";
import type { Website } from "@/stores/websites";

const props = defineProps<{ website: Website }>();

const { t } = useI18n();
const store = useGithubStore();

const link = ref<GithubWebsiteLink | null>(null);
const pushResult = ref<GithubWebsitePushResponse | null>(null);
const error = ref<string | null>(null);

const editing = ref(false);
const draft = ref({
  base_url: "https://github.com",
  repo_owner: "",
  repo_name: "",
  branch: "main",
  pat_override: "",
  use_override: false,
});

const canPush = computed(
  () => link.value !== null
    && props.website.rendering_mode !== "DYNAMIC"
    && props.website.build_status === "done",
);

const whyCannotPush = computed<string | null>(() => {
  if (!link.value) return null;
  if (props.website.rendering_mode === "DYNAMIC") {
    return t("github.website_cannot_push_dynamic");
  }
  if (props.website.build_status !== "done") {
    return t("github.website_cannot_push_not_built");
  }
  return null;
});

onMounted(async () => {
  await refresh();
});

async function refresh(): Promise<void> {
  try {
    link.value = await store.getWebsiteLink(props.website.slug);
  } catch {
    link.value = null;
  }
}

function openEdit(): void {
  editing.value = true;
  error.value = null;
  pushResult.value = null;
  if (link.value) {
    draft.value = {
      base_url: link.value.base_url,
      repo_owner: link.value.repo_owner,
      repo_name: link.value.repo_name,
      branch: link.value.branch,
      pat_override: "",
      use_override: link.value.pat_override_set,
    };
  } else {
    draft.value = {
      base_url: "https://github.com",
      repo_owner: "",
      repo_name: "",
      branch: "main",
      pat_override: "",
      use_override: false,
    };
  }
}

async function save(): Promise<void> {
  error.value = null;
  const d = draft.value;
  let patOverride: string | null | undefined;
  if (!d.use_override) {
    patOverride = "";
  } else if (d.pat_override.trim()) {
    patOverride = d.pat_override.trim();
  } else {
    patOverride = undefined;
  }
  try {
    link.value = await store.writeWebsiteLink(props.website.slug, {
      base_url: d.base_url.trim(),
      repo_owner: d.repo_owner.trim(),
      repo_name: d.repo_name.trim(),
      branch: d.branch.trim() || "main",
      pat_override: patOverride,
    });
    editing.value = false;
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function disconnect(): Promise<void> {
  error.value = null;
  try {
    await store.deleteWebsiteLink(props.website.slug);
    link.value = null;
    pushResult.value = null;
    editing.value = false;
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}

async function push(): Promise<void> {
  error.value = null;
  pushResult.value = null;
  try {
    pushResult.value = await store.pushWebsite(props.website.slug);
    link.value = await store.getWebsiteLink(props.website.slug);
  } catch (err) {
    error.value =
      (err as { response?: { data?: { error?: { message?: string } } } })
        ?.response?.data?.error?.message ?? t("common.error");
  }
}
</script>

<template>
  <section class="rounded border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
    <div class="mb-3 flex items-start justify-between">
      <div>
        <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {{ t("github.website_section_title") }}
        </h2>
        <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {{ t("github.website_section_hint") }}
        </p>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </p>

    <!-- Not linked: show connect button -->
    <div v-if="!link && !editing">
      <button
        type="button"
        class="rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm text-amber-800 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200"
        @click="openEdit"
      >
        {{ t("github.connect_btn") }}
      </button>
    </div>

    <!-- Edit form (also used for the initial connect) -->
    <div v-else-if="editing" class="space-y-3">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ t("github.field_base_url") }}</span>
          <input v-model="draft.base_url" type="url" class="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ t("github.field_branch") }}</span>
          <input v-model="draft.branch" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ t("github.field_owner") }}</span>
          <input v-model="draft.repo_owner" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
        <label class="flex flex-col gap-1 text-xs">
          <span class="text-gray-600 dark:text-gray-300">{{ t("github.field_repo") }}</span>
          <input v-model="draft.repo_name" type="text" class="rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
        </label>
      </div>
      <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
        <input v-model="draft.use_override" type="checkbox" />
        <span>{{ t("github.use_per_link_pat") }}</span>
      </label>
      <input
        v-if="draft.use_override"
        v-model="draft.pat_override"
        type="password"
        autocomplete="off"
        class="w-full rounded border border-gray-300 px-2 py-1 text-sm font-mono dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        :placeholder="link?.pat_override_set ? t('github.override_replace_hint') : t('github.field_pat_placeholder')"
      />
      <div class="flex gap-2 pt-2">
        <button
          type="button"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          @click="save"
        >
          {{ t("common.save") }}
        </button>
        <button
          type="button"
          class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
          @click="editing = false"
        >
          {{ t("common.cancel") }}
        </button>
      </div>
    </div>

    <!-- Linked: summary + push / disconnect -->
    <div v-else-if="link" class="space-y-3 text-sm">
      <p class="font-mono text-gray-700 dark:text-gray-200">
        <a :href="link.html_url" target="_blank" rel="noopener" class="hover:underline">
          {{ link.repo_owner }}/{{ link.repo_name }}
        </a>
        <span class="text-xs text-gray-500 dark:text-gray-400">
          · {{ link.branch }} · {{ link.base_url }}
        </span>
      </p>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        <span v-if="link.last_push_sha">
          {{ t("github.last_push") }}:
          <code class="font-mono">{{ link.last_push_sha.slice(0, 10) }}</code>
          <span v-if="link.last_push_at"> ({{ new Date(link.last_push_at).toLocaleString() }})</span>
          <span v-if="link.last_push_file_count"> · {{ t("github.file_count", { n: link.last_push_file_count }) }}</span>
        </span>
        <span v-else>{{ t("github.never_pushed") }}</span>
        <span v-if="link.pat_override_set" class="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
          {{ t("github.pat_override_badge") }}
        </span>
      </p>

      <p v-if="pushResult" class="text-xs text-green-700 dark:text-green-400">
        {{ t("github.push_success", {
          n: pushResult.file_count,
          sha: pushResult.sha.slice(0, 10),
        }) }}
        <a v-if="pushResult.html_url" :href="pushResult.html_url" target="_blank" rel="noopener" class="underline">
          {{ t("github.view_commit") }}
        </a>
      </p>

      <p v-if="whyCannotPush" class="text-xs text-amber-700 dark:text-amber-300">
        {{ whyCannotPush }}
      </p>

      <div class="flex gap-2">
        <button
          type="button"
          :disabled="!canPush || store.isPushingWebsite"
          class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          @click="push"
        >
          {{ store.isPushingWebsite ? t("common.loading") : t("github.push_website_btn") }}
        </button>
        <button
          type="button"
          class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
          @click="openEdit"
        >
          {{ t("github.edit_btn") }}
        </button>
        <button
          type="button"
          class="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/40"
          @click="disconnect"
        >
          {{ t("github.disconnect_btn") }}
        </button>
      </div>
    </div>
  </section>
</template>
