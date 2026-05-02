<script setup lang="ts">
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import UserAvatar from "@/components/ui/UserAvatar.vue";

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

// ── Email notifications toggle ────────────────────────────────────────────
const emailNotifSaving = ref(false);
const emailNotifError = ref<string | null>(null);

async function toggleEmailNotifications(next: boolean): Promise<void> {
  emailNotifError.value = null;
  emailNotifSaving.value = true;
  try {
    await auth.updateMe({ email_notifications_enabled: next });
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    emailNotifError.value = msg ?? t("common.error");
  } finally {
    emailNotifSaving.value = false;
  }
}

// ── Avatar upload + delete ────────────────────────────────────────────────
const avatarError = ref<string | null>(null);
const isUploadingAvatar = ref(false);
const avatarFileInput = ref<HTMLInputElement | null>(null);

function triggerAvatarUpload(): void {
  avatarFileInput.value?.click();
}

async function onAvatarChosen(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  avatarError.value = null;
  isUploadingAvatar.value = true;
  try {
    await auth.uploadAvatar(file);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    avatarError.value = msg ?? t("common.error");
  } finally {
    isUploadingAvatar.value = false;
  }
}

async function removeAvatar(): Promise<void> {
  avatarError.value = null;
  try {
    await auth.deleteAvatar();
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    avatarError.value = msg ?? t("common.error");
  }
}

// ── Bio editor (tiny Markdown subset) ─────────────────────────────────────
// Strategy: a textarea + an inline preview, plus three toolbar buttons that
// wrap the current selection in **…**, *…*, or __…__. No full Markdown
// parser — only the three idioms we render below in ``renderedBio``.
const editingBio = ref(false);
const bioDraft = ref("");
const bioError = ref<string | null>(null);
const bioSaved = ref(false);
const bioTextareaRef = ref<HTMLTextAreaElement | null>(null);

const BIO_MAX = 500;

const bioCharCount = computed(() => bioDraft.value.length);
const bioOverLimit = computed(() => bioCharCount.value > BIO_MAX);

function startBioEdit(): void {
  bioDraft.value = auth.user?.bio ?? "";
  bioError.value = null;
  bioSaved.value = false;
  editingBio.value = true;
}

function cancelBioEdit(): void {
  editingBio.value = false;
  bioError.value = null;
}

async function saveBio(): Promise<void> {
  if (bioOverLimit.value) {
    bioError.value = t("profile.bio_over_limit", { max: BIO_MAX });
    return;
  }
  bioError.value = null;
  bioSaved.value = false;
  try {
    await auth.updateMe({ bio: bioDraft.value.trim() || null });
    editingBio.value = false;
    bioSaved.value = true;
    setTimeout(() => {
      bioSaved.value = false;
    }, 3000);
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    bioError.value = msg ?? t("common.error");
  }
}

function wrapSelection(prefix: string, suffix: string = prefix): void {
  const ta = bioTextareaRef.value;
  if (!ta) return;
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const before = bioDraft.value.slice(0, start);
  const middle = bioDraft.value.slice(start, end) || t("profile.bio_placeholder_short");
  const after = bioDraft.value.slice(end);
  bioDraft.value = `${before}${prefix}${middle}${suffix}${after}`;
  // Restore caret around the inserted text on the next tick so the
  // user can type over the placeholder if no selection was made.
  requestAnimationFrame(() => {
    ta.focus();
    const newStart = before.length + prefix.length;
    ta.selectionStart = newStart;
    ta.selectionEnd = newStart + middle.length;
  });
}

/**
 * Render the tiny Markdown subset we accept. Order of operations
 * matters — bold (``**``) before italic (``*``) so ``**foo**`` is
 * parsed as bold rather than italic-italic.
 */
function renderBio(raw: string | null | undefined): string {
  if (!raw) return "";
  // Escape HTML first so user content can't smuggle tags.
  const escape = (s: string): string =>
    s.replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" } as Record<string, string>
    )[c]);
  return escape(raw)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<u>$1</u>")
    .replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/\n/g, "<br>");
}

const renderedBio = computed(() => renderBio(auth.user?.bio));
const renderedBioPreview = computed(() => renderBio(bioDraft.value));
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-6 text-gray-900 dark:text-gray-100">{{ t("profile.title") }}</h1>

    <div v-if="auth.user" class="max-w-xl space-y-4">
      <!-- Avatar card ─────────────────────────────────────────────── -->
      <div class="rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <p class="mb-3 text-sm font-medium text-gray-700 dark:text-gray-200">
          {{ t("profile.avatar_title") }}
        </p>
        <div class="flex items-center gap-4">
          <UserAvatar
            :username="auth.user.username"
            :display-name="auth.user.display_name"
            :avatar-url="auth.user.avatar_url"
            :size="80"
            ring
          />
          <div class="flex-1 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                :disabled="isUploadingAvatar"
                @click="triggerAvatarUpload"
              >
                {{ isUploadingAvatar ? t("profile.avatar_uploading") : t("profile.avatar_upload") }}
              </button>
              <button
                v-if="auth.user.avatar_url"
                type="button"
                class="rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
                @click="removeAvatar"
              >
                {{ t("profile.avatar_remove") }}
              </button>
            </div>
            <p class="text-xs text-gray-400 dark:text-gray-500">
              {{ t("profile.avatar_hint") }}
            </p>
            <p v-if="avatarError" class="text-xs text-red-600 dark:text-red-400">
              {{ avatarError }}
            </p>
            <input
              ref="avatarFileInput"
              type="file"
              accept=".jpg,.jpeg,.png,.gif,.webp,.avif"
              class="hidden"
              @change="onAvatarChosen"
            />
          </div>
        </div>
      </div>

      <!-- Bio card ────────────────────────────────────────────────── -->
      <div class="rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("profile.bio_title") }}
          </p>
          <button
            v-if="!editingBio"
            class="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
            @click="startBioEdit"
          >
            {{ auth.user.bio ? t("profile.bio_edit") : t("profile.bio_add") }}
          </button>
        </div>
        <template v-if="!editingBio">
          <div
            v-if="auth.user.bio"
            class="prose prose-sm max-w-none text-sm text-gray-700 dark:text-gray-200"
            v-html="renderedBio"
          />
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">
            {{ t("profile.bio_empty") }}
          </p>
        </template>
        <template v-else>
          <div class="mb-2 flex items-center gap-1">
            <button
              type="button"
              class="rounded border border-gray-300 px-2 py-1 text-xs font-bold text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              :title="t('profile.bio_tool_bold')"
              @click="wrapSelection('**')"
            >
              B
            </button>
            <button
              type="button"
              class="rounded border border-gray-300 px-2 py-1 text-xs italic text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              :title="t('profile.bio_tool_italic')"
              @click="wrapSelection('*')"
            >
              I
            </button>
            <button
              type="button"
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 underline hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              :title="t('profile.bio_tool_underline')"
              @click="wrapSelection('__')"
            >
              U
            </button>
          </div>
          <textarea
            ref="bioTextareaRef"
            v-model="bioDraft"
            rows="4"
            :placeholder="t('profile.bio_placeholder')"
            class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
          <div class="mt-1 flex items-center justify-between text-xs">
            <span :class="bioOverLimit ? 'text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'">
              {{ bioCharCount }} / {{ BIO_MAX }}
            </span>
            <span class="text-gray-400 dark:text-gray-500">
              {{ t("profile.bio_markdown_hint") }}
            </span>
          </div>
          <div
            v-if="bioDraft.trim()"
            class="mt-3 rounded border border-dashed border-gray-200 bg-gray-50 p-2 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
          >
            <p class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
              {{ t("profile.bio_preview") }}
            </p>
            <div v-html="renderedBioPreview" />
          </div>
          <p v-if="bioError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ bioError }}
          </p>
          <div class="mt-2 flex items-center gap-2">
            <button
              type="button"
              :disabled="bioOverLimit"
              class="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
              @click="saveBio"
            >
              {{ t("common.save") }}
            </button>
            <button
              type="button"
              class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
              @click="cancelBioEdit"
            >
              {{ t("common.cancel") }}
            </button>
          </div>
        </template>
        <p v-if="bioSaved && !editingBio" class="mt-2 text-xs text-green-600 dark:text-green-400">
          {{ t("profile.bio_saved") }}
        </p>
      </div>

      <!-- Account fields card ─────────────────────────────────────── -->
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

        <!-- Email notifications toggle (workflow emails only — password
             reset bypasses this flag). Inline checkbox, no edit state:
             changes are persisted as soon as the user toggles. -->
        <div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-gray-700 dark:text-gray-300">{{ t("profile.email_notifications") }}</span>
            <label class="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                :checked="auth.user.email_notifications_enabled"
                :disabled="emailNotifSaving"
                @change="toggleEmailNotifications(($event.target as HTMLInputElement).checked)"
                class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span class="text-sm text-gray-700 dark:text-gray-300">
                {{ auth.user.email_notifications_enabled ? t("profile.email_notifications_on") : t("profile.email_notifications_off") }}
              </span>
            </label>
          </div>
          <p v-if="emailNotifError" class="mt-1 text-xs text-red-600 dark:text-red-400">
            {{ emailNotifError }}
          </p>
          <p v-else class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ t("profile.email_notifications_hint") }}
          </p>
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
