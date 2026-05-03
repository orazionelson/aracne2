<script setup lang="ts">
/**
 * /admin/policies — list every built-in template + an editor pane.
 *
 * Layout: master / detail. The left rail lists the 12 templates,
 * grouped by category; clicking one loads its form in the right
 * pane. Save / Publish / Unpublish live at the top of the form
 * pane. Save = creates a new draft version. Publish = points the
 * page's published_version_id at the latest draft. Unpublish =
 * clears the pointer.
 *
 * Read access for Editor+ (the form is rendered read-only); write
 * for PolicyManager + Admin (the buttons enable). The actual
 * gate sits server-side via require_capability("PolicyManager") —
 * the disabled-buttons hint is a UX convenience.
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  CheckCircleIcon,
  PencilSquareIcon,
  XCircleIcon,
} from "@heroicons/vue/24/outline";
import FieldRenderer from "@/components/policy-pages/FieldRenderer.vue";
import { useAuthStore } from "@/stores/auth";
import { usePolicyPagesStore } from "@/stores/policyPages";

const { t, te } = useI18n();
const auth = useAuthStore();
const store = usePolicyPagesStore();

const activeSlug = ref<string | null>(null);

onMounted(async () => {
  await Promise.all([store.fetchList(), store.fetchPolicyManager()]);
});

const groupedList = computed(() => {
  const groups: Record<string, typeof store.list> = {};
  for (const item of store.list) {
    const cat = item.categories[0] ?? "core";
    (groups[cat] ??= []).push(item);
  }
  return groups;
});

async function selectPolicy(slug: string): Promise<void> {
  if (store.draftDirty && !confirm(t("policy_pages.unsaved_warning"))) return;
  activeSlug.value = slug;
  await Promise.all([store.fetchDetail(slug), store.fetchVersions(slug)]);
}

const activeDetail = computed(() => store.detail);

function fieldLabel(slug: string): string {
  // slug is a key like "policy.mission.title" — fall back to the
  // raw key when no translation is registered.
  return te(slug) ? t(slug) : slug;
}

const isAdmin = computed(() => auth.userRole === "Admin");
const isPolicyManager = computed(
  () => store.policyManager?.holder_user_id === auth.user?.id,
);
const canWrite = computed(() => isAdmin.value || isPolicyManager.value);

async function handleSave(): Promise<void> {
  if (!activeSlug.value) return;
  await store.saveDraft(activeSlug.value);
  if (activeSlug.value) await store.fetchVersions(activeSlug.value);
}

async function handlePublishLatest(): Promise<void> {
  if (!activeSlug.value) return;
  if (!confirm(t("policy_pages.publish_confirm"))) return;
  await store.publish(activeSlug.value, null);
}

async function handleUnpublish(): Promise<void> {
  if (!activeSlug.value) return;
  if (!confirm(t("policy_pages.unpublish_confirm"))) return;
  await store.unpublish(activeSlug.value);
}

async function handlePublishVersion(versionNumber: number): Promise<void> {
  if (!activeSlug.value) return;
  if (!confirm(t("policy_pages.publish_version_confirm", { n: versionNumber }))) return;
  await store.publish(activeSlug.value, versionNumber);
}
</script>

<template>
  <div class="px-6 py-6">
    <div class="mb-4">
      <h1 class="text-2xl font-bold text-gray-900">{{ t("policy_pages.title") }}</h1>
      <p class="mt-1 text-sm text-gray-500">{{ t("policy_pages.subtitle") }}</p>
    </div>

    <!-- PolicyManager card -->
    <section class="mb-4 rounded-xl border border-indigo-200 bg-white p-4 shadow-sm">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm font-semibold text-gray-800">
            {{ t("policy_pages.manager_card_title") }}
          </p>
          <p class="text-xs text-gray-500">
            {{ t("policy_pages.manager_card_hint") }}
          </p>
        </div>
        <div class="text-sm">
          <template v-if="store.policyManager?.holder_username">
            <span class="font-medium text-gray-800">{{ store.policyManager.holder_username }}</span>
            <span v-if="store.policyManager.holder_display_name" class="text-gray-500">
              ({{ store.policyManager.holder_display_name }})
            </span>
          </template>
          <span v-else class="italic text-gray-400">{{ t("policy_pages.no_manager") }}</span>
        </div>
      </div>
    </section>

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      <!-- ── Left rail ────────────────────────────────────────────────── -->
      <aside class="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
        <p v-if="store.isLoadingList" class="text-xs text-gray-500">{{ t("common.loading") }}</p>
        <div v-else>
          <div v-for="(items, cat) in groupedList" :key="cat" class="mb-3">
            <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
              {{ cat }}
            </p>
            <ul class="space-y-1">
              <li
                v-for="item in items"
                :key="item.template_slug"
                class="flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-sm transition"
                :class="activeSlug === item.template_slug ? 'bg-indigo-50 text-indigo-800 font-medium' : 'hover:bg-gray-50'"
                @click="selectPolicy(item.template_slug)"
              >
                <span>{{ fieldLabel(item.title_key) }}</span>
                <CheckCircleIcon
                  v-if="item.is_published"
                  class="h-4 w-4 text-emerald-500"
                  :title="t('policy_pages.is_published')"
                />
              </li>
            </ul>
          </div>
        </div>
      </aside>

      <!-- ── Form pane ────────────────────────────────────────────────── -->
      <section class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <p v-if="!activeSlug" class="text-sm text-gray-500">
          {{ t("policy_pages.select_template_hint") }}
        </p>

        <template v-else-if="activeDetail">
          <!-- Header + buttons -->
          <div class="mb-4 flex items-center justify-between border-b border-gray-100 pb-3">
            <div>
              <h2 class="text-lg font-bold text-gray-900">
                {{ fieldLabel(activeDetail.template.title_key) }}
              </h2>
              <p class="mt-0.5 text-xs text-gray-500">
                <template v-if="activeDetail.is_published">
                  {{ t("policy_pages.is_published_v", { n: activeDetail.published_version_number }) }}
                </template>
                <template v-else-if="activeDetail.latest_version_number">
                  {{ t("policy_pages.draft_only", { n: activeDetail.latest_version_number }) }}
                </template>
                <template v-else>
                  {{ t("policy_pages.no_drafts_yet") }}
                </template>
              </p>
            </div>
            <div class="flex items-center gap-2">
              <button
                type="button"
                :disabled="!canWrite || !store.draftDirty"
                class="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                @click="handleSave"
              >
                <PencilSquareIcon class="h-4 w-4" />
                {{ t("policy_pages.save_draft") }}
              </button>
              <button
                type="button"
                :disabled="!canWrite || !activeDetail.latest_version_number"
                class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                @click="handlePublishLatest"
              >
                <CheckCircleIcon class="h-4 w-4" />
                {{ t("policy_pages.publish_latest") }}
              </button>
              <button
                v-if="activeDetail.is_published"
                type="button"
                :disabled="!canWrite"
                class="inline-flex items-center gap-1.5 rounded-lg border border-rose-300 px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                @click="handleUnpublish"
              >
                <XCircleIcon class="h-4 w-4" />
                {{ t("policy_pages.unpublish") }}
              </button>
            </div>
          </div>

          <!-- Optional message -->
          <div v-if="canWrite" class="mb-4">
            <label class="block text-xs font-medium text-gray-600">
              {{ t("policy_pages.commit_message") }}
            </label>
            <input
              v-model="store.message"
              type="text"
              :placeholder="t('policy_pages.commit_message_placeholder')"
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <!-- Field list -->
          <div class="space-y-3">
            <FieldRenderer
              v-for="field in activeDetail.template.fields"
              :key="field.name"
              :field="field"
              :value="store.draftContent[field.name]"
              :platform-value="activeDetail.platform_values[field.name]"
              :readonly="!canWrite"
              @update="(name, value) => store.setField(name, value)"
              @update-localized="(name, loc, value) => store.setLocalizedField(name, loc, value)"
              @update-rows="(name, rows) => store.setRows(name, rows)"
            />
          </div>

          <!-- Version history -->
          <section class="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p class="mb-2 text-xs font-semibold uppercase text-gray-500">
              {{ t("policy_pages.versions") }}
            </p>
            <p v-if="store.versions.length === 0" class="text-xs italic text-gray-400">
              {{ t("policy_pages.no_versions") }}
            </p>
            <ul v-else class="space-y-1">
              <li
                v-for="v in store.versions"
                :key="v.id"
                class="flex items-center justify-between rounded bg-white px-3 py-1.5 text-xs"
              >
                <span>
                  <span class="font-mono">v{{ v.version_number }}</span>
                  <span class="ml-2 text-gray-500">
                    {{ new Date(v.saved_at).toLocaleString() }}
                  </span>
                  <span v-if="v.saved_by_username" class="ml-2 text-gray-400">
                    — {{ v.saved_by_username }}
                  </span>
                  <span v-if="v.message" class="ml-2 italic text-gray-500">{{ v.message }}</span>
                  <span
                    v-if="v.is_published"
                    class="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] uppercase text-emerald-700"
                  >
                    {{ t("policy_pages.is_published") }}
                  </span>
                </span>
                <button
                  v-if="canWrite && !v.is_published"
                  type="button"
                  class="text-xs text-indigo-600 hover:underline"
                  @click="handlePublishVersion(v.version_number)"
                >
                  {{ t("policy_pages.publish_this") }}
                </button>
              </li>
            </ul>
          </section>
        </template>

        <p v-if="store.error" class="mt-3 text-xs text-rose-600">
          {{ store.error }}
        </p>
      </section>
    </div>
  </div>
</template>
