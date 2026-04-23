<script setup lang="ts">
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();

function formatDate(iso: string | null): string {
  if (!iso) return t("profile.never");
  return new Date(iso).toLocaleString();
}

// ── ORCID inline edit ─────────────────────────────────────────────────────
const editingOrcid = ref(false);
const orcidDraft = ref("");
const orcidError = ref<string | null>(null);
const orcidSaved = ref(false);

const orcidLink = computed(() =>
  auth.user?.orcid ? `https://orcid.org/${auth.user.orcid}` : null,
);

function startOrcidEdit(): void {
  orcidDraft.value = auth.user?.orcid ?? "";
  orcidError.value = null;
  orcidSaved.value = false;
  editingOrcid.value = true;
}

function cancelOrcidEdit(): void {
  editingOrcid.value = false;
  orcidError.value = null;
}

async function saveOrcid(): Promise<void> {
  orcidError.value = null;
  orcidSaved.value = false;
  try {
    // An empty string clears the stored ORCID; the backend validates
    // format + Mod 11-2 checksum on any non-empty value.
    await auth.updateMe({ orcid: orcidDraft.value.trim() || null });
    editingOrcid.value = false;
    orcidSaved.value = true;
    setTimeout(() => {
      orcidSaved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    orcidError.value = msg ?? t("common.error");
  }
}
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-6 text-gray-900 dark:text-gray-100">{{ t("profile.title") }}</h1>

    <div v-if="auth.user" class="max-w-xl space-y-4">
      <div class="rounded border border-gray-200 bg-white p-4 space-y-3 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100">
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.username") }}</span>
          <span>{{ auth.user.username }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.email") }}</span>
          <span>{{ auth.user.email }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.display_name") }}</span>
          <span>{{ auth.user.display_name ?? "—" }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.role") }}</span>
          <span>{{ auth.user.role }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.preferred_lang") }}</span>
          <span>{{ auth.user.preferred_lang }}</span>
        </div>

        <!-- ORCID — inline editable field. Empty submit clears it. -->
        <div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.orcid") }}</span>
            <template v-if="!editingOrcid">
              <div class="flex items-center gap-2">
                <a
                  v-if="orcidLink"
                  :href="orcidLink"
                  target="_blank"
                  rel="noopener"
                  class="font-mono text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  {{ auth.user.orcid }}
                </a>
                <span v-else class="text-gray-400 dark:text-gray-500">—</span>
                <button
                  class="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                  @click="startOrcidEdit"
                >
                  {{ auth.user.orcid ? t("profile.orcid_edit") : t("profile.orcid_add") }}
                </button>
              </div>
            </template>
            <template v-else>
              <div class="flex items-center gap-2">
                <input
                  v-model="orcidDraft"
                  type="text"
                  :placeholder="t('profile.orcid_placeholder')"
                  class="w-56 rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                />
                <button
                  class="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
                  @click="saveOrcid"
                >
                  {{ t("common.save") }}
                </button>
                <button
                  class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                  @click="cancelOrcidEdit"
                >
                  {{ t("common.cancel") }}
                </button>
              </div>
            </template>
          </div>
          <p v-if="orcidError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ orcidError }}
          </p>
          <p v-if="orcidSaved" class="mt-1 text-xs text-green-600 dark:text-green-400">
            {{ t("profile.orcid_saved") }}
          </p>
          <p v-else-if="editingOrcid" class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ t("profile.orcid_hint") }}
          </p>
        </div>

        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.last_login") }}</span>
          <span>{{ formatDate(auth.user.last_login_at) }}</span>
        </div>
        <div class="flex justify-between">
          <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.member_since") }}</span>
          <span>{{ formatDate(auth.user.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
