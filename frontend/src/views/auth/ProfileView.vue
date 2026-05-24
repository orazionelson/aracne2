<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import {
  usePersonalAccessTokensStore,
  type PersonalAccessTokenCreated,
} from "@/stores/personalAccessTokens";
import UserAvatar from "@/components/ui/UserAvatar.vue";
import { apiClient } from "@/services/api";

const { t, locale } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const patStore = usePersonalAccessTokensStore();

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

// ── Change password ───────────────────────────────────────────────────────
// Self-service form that hits POST /auth/password/change. No SMTP needed:
// it requires the current password and writes the new one directly. Backend
// revokes every active session on success, so we redirect to /login.
const showPasswordForm = ref(false);
const passwordCurrent = ref("");
const passwordNew = ref("");
const passwordConfirm = ref("");
const passwordError = ref<string | null>(null);
const passwordSaving = ref(false);

function openPasswordForm(): void {
  passwordCurrent.value = "";
  passwordNew.value = "";
  passwordConfirm.value = "";
  passwordError.value = null;
  showPasswordForm.value = true;
}

function cancelPasswordChange(): void {
  showPasswordForm.value = false;
  passwordError.value = null;
}

async function submitPasswordChange(): Promise<void> {
  passwordError.value = null;
  if (passwordNew.value.length < 8) {
    passwordError.value = t("profile.password.too_short");
    return;
  }
  if (passwordNew.value !== passwordConfirm.value) {
    passwordError.value = t("profile.password.mismatch");
    return;
  }
  passwordSaving.value = true;
  try {
    await auth.changePassword(passwordCurrent.value, passwordNew.value);
    await router.push({ path: "/login", query: { reason: "password_changed" } });
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    passwordError.value = msg ?? t("common.error");
  } finally {
    passwordSaving.value = false;
  }
}

// ── Personal Access Tokens (CLI-B) ────────────────────────────────────────
//
// Editor+ self-service: list / issue / revoke long-lived bearer tokens
// that authenticate the standalone ``aracne-cli`` against the REST API.
// Hidden for level-1 Users — the backend already gates POST with 403,
// but we hide the card to keep the surface tidy.
const showApiTokens = computed(() => auth.hasMinRole("Editor"));

const showIssueModal = ref(false);
const issueLabel = ref("");
const issueError = ref<string | null>(null);
const issuedToken = ref<PersonalAccessTokenCreated | null>(null);
const copyFeedback = ref<string | null>(null);

function fmtDate(iso: string | null): string {
  if (!iso) return t("profile.api_tokens.never_used");
  try {
    return new Date(iso).toLocaleString(locale.value, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function openIssueModal(): void {
  issueLabel.value = "";
  issueError.value = null;
  issuedToken.value = null;
  copyFeedback.value = null;
  showIssueModal.value = true;
}

function closeIssueModal(): void {
  showIssueModal.value = false;
  issueLabel.value = "";
  issuedToken.value = null;
  copyFeedback.value = null;
}

async function submitIssue(): Promise<void> {
  const label = issueLabel.value.trim();
  if (!label) {
    issueError.value = t("profile.api_tokens.label_required");
    return;
  }
  issueError.value = null;
  const created = await patStore.issue(label);
  if (created === null) {
    issueError.value = patStore.error ?? t("common.error");
    return;
  }
  issuedToken.value = created;
}

async function copyTokenToClipboard(): Promise<void> {
  if (!issuedToken.value) return;
  try {
    await navigator.clipboard.writeText(issuedToken.value.token);
    copyFeedback.value = t("profile.api_tokens.copied");
    setTimeout(() => {
      copyFeedback.value = null;
    }, 2500);
  } catch {
    copyFeedback.value = t("profile.api_tokens.copy_failed");
  }
}

async function revokeToken(tokenId: string, label: string): Promise<void> {
  if (
    !window.confirm(
      t("profile.api_tokens.revoke_confirm", { label }),
    )
  ) {
    return;
  }
  await patStore.revoke(tokenId);
}

onMounted(async () => {
  if (showApiTokens.value) {
    await patStore.loadList();
  }
});

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

// ── Privacy / GDPR ────────────────────────────────────────────────────────
const isExporting = ref(false);
const exportError = ref<string | null>(null);

async function handleExportData(): Promise<void> {
  isExporting.value = true;
  exportError.value = null;
  try {
    const data = await apiClient.get<Record<string, unknown>>(
      "/users/me/export",
    );
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().slice(0, 10);
    a.download = `aracne2-personal-data-${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err: unknown) {
    exportError.value = err instanceof Error ? err.message : String(err);
  } finally {
    isExporting.value = false;
  }
}

const showAnonymiseDialog = ref(false);
const anonymiseReason = ref("");
const anonymiseConfirm = ref("");
const isSubmittingAnonymise = ref(false);
const anonymiseError = ref<string | null>(null);
const anonymiseDone = ref(false);

const ANONYMISE_CONFIRM_PHRASE = "ANONYMISE";

const canSubmitAnonymise = computed(
  () => anonymiseConfirm.value.trim() === ANONYMISE_CONFIRM_PHRASE,
);

function openAnonymiseDialog(): void {
  anonymiseReason.value = "";
  anonymiseConfirm.value = "";
  anonymiseError.value = null;
  anonymiseDone.value = false;
  showAnonymiseDialog.value = true;
}

function closeAnonymiseDialog(): void {
  if (isSubmittingAnonymise.value) return;
  showAnonymiseDialog.value = false;
}

async function handleSubmitAnonymise(): Promise<void> {
  if (!canSubmitAnonymise.value) return;
  isSubmittingAnonymise.value = true;
  anonymiseError.value = null;
  try {
    await apiClient.post("/users/me/anonymise-request", {
      reason: anonymiseReason.value.trim() || null,
    });
    anonymiseDone.value = true;
  } catch (err: unknown) {
    anonymiseError.value = err instanceof Error ? err.message : String(err);
  } finally {
    isSubmittingAnonymise.value = false;
  }
}
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

      <!-- Password card ─────────────────────────────────────────────── -->
      <div class="rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div class="mb-3 flex items-center justify-between">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("profile.password.title") }}
          </p>
          <button
            v-if="!showPasswordForm"
            type="button"
            class="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            @click="openPasswordForm"
          >
            {{ t("profile.password.change_button") }}
          </button>
        </div>

        <p v-if="!showPasswordForm" class="text-xs text-gray-500 dark:text-gray-400">
          {{ t("profile.password.intro") }}
        </p>

        <form v-else class="space-y-3" @submit.prevent="submitPasswordChange">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            {{ t("profile.password.note_signout") }}
          </p>

          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              {{ t("profile.password.current_label") }}
            </label>
            <input
              v-model="passwordCurrent"
              type="password"
              autocomplete="current-password"
              required
              :disabled="passwordSaving"
              class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              {{ t("profile.password.new_label") }}
            </label>
            <input
              v-model="passwordNew"
              type="password"
              autocomplete="new-password"
              required
              minlength="8"
              :disabled="passwordSaving"
              class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
            <p class="mt-1 text-[0.7rem] text-gray-500 dark:text-gray-400">
              {{ t("profile.password.min_length_hint") }}
            </p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
              {{ t("profile.password.confirm_label") }}
            </label>
            <input
              v-model="passwordConfirm"
              type="password"
              autocomplete="new-password"
              required
              :disabled="passwordSaving"
              class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>

          <p
            v-if="passwordError"
            class="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-200"
          >
            {{ passwordError }}
          </p>

          <div class="flex gap-2">
            <button
              type="submit"
              :disabled="passwordSaving"
              class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {{ passwordSaving ? t("profile.password.saving") : t("profile.password.submit") }}
            </button>
            <button
              type="button"
              :disabled="passwordSaving"
              class="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
              @click="cancelPasswordChange"
            >
              {{ t("common.cancel") }}
            </button>
          </div>
        </form>
      </div>

      <!-- API Tokens card (Phase CLI-B) — Editor+ only -->
      <div
        v-if="showApiTokens"
        class="rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800"
      >
        <div class="mb-3 flex items-center justify-between">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("profile.api_tokens.title") }}
          </p>
          <button
            class="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            @click="openIssueModal"
          >
            {{ t("profile.api_tokens.issue_button") }}
          </button>
        </div>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          {{ t("profile.api_tokens.intro") }}
        </p>

        <p
          v-if="patStore.error && !showIssueModal"
          class="mb-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-200"
        >
          {{ patStore.error }}
        </p>

        <p
          v-if="!patStore.isLoading && patStore.tokens.length === 0"
          class="text-sm text-gray-500 dark:text-gray-400"
        >
          {{ t("profile.api_tokens.empty") }}
        </p>

        <table v-else class="w-full text-left text-sm">
          <thead class="text-xs uppercase text-gray-500 dark:text-gray-400">
            <tr>
              <th class="pb-2">{{ t("profile.api_tokens.column_label") }}</th>
              <th class="pb-2">{{ t("profile.api_tokens.column_created") }}</th>
              <th class="pb-2">{{ t("profile.api_tokens.column_last_used") }}</th>
              <th class="pb-2 text-right">{{ t("profile.api_tokens.column_actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in patStore.tokens"
              :key="row.id"
              class="border-t border-gray-100 dark:border-gray-700"
            >
              <td class="py-2 font-medium text-gray-900 dark:text-gray-100">
                {{ row.label }}
              </td>
              <td class="py-2 text-gray-700 dark:text-gray-300">
                {{ fmtDate(row.created_at) }}
              </td>
              <td class="py-2 text-gray-700 dark:text-gray-300">
                {{ fmtDate(row.last_used_at) }}
              </td>
              <td class="py-2 text-right">
                <button
                  class="text-xs text-red-700 hover:underline dark:text-red-400"
                  @click="revokeToken(row.id, row.label)"
                >
                  {{ t("profile.api_tokens.revoke_button") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Privacy / GDPR card ─────────────────────────────────────────── -->
      <div class="rounded border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ t("profile.privacy.title") }}
          </p>
        </div>
        <p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
          {{ t("profile.privacy.intro") }}
        </p>

        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            :disabled="isExporting"
            class="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
            @click="handleExportData"
          >
            {{ isExporting ? t("profile.privacy.exporting") : t("profile.privacy.export_button") }}
          </button>
          <button
            type="button"
            class="rounded border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-900/30"
            @click="openAnonymiseDialog"
          >
            {{ t("profile.privacy.anonymise_button") }}
          </button>
        </div>

        <p v-if="exportError" class="mt-2 text-xs text-rose-600 dark:text-rose-400">
          {{ exportError }}
        </p>
      </div>
    </div>

    <!-- Anonymise-request dialog ───────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="showAnonymiseDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="closeAnonymiseDialog"
      >
        <div class="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl dark:bg-gray-800">
          <template v-if="!anonymiseDone">
            <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {{ t("profile.privacy.anonymise_modal_title") }}
            </h3>
            <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {{ t("profile.privacy.anonymise_modal_intro") }}
            </p>
            <ul class="mt-2 list-disc pl-5 text-xs text-gray-600 dark:text-gray-400">
              <li>{{ t("profile.privacy.anonymise_modal_bullet_mediated") }}</li>
              <li>{{ t("profile.privacy.anonymise_modal_bullet_record_survives") }}</li>
              <li>{{ t("profile.privacy.anonymise_modal_bullet_no_login") }}</li>
            </ul>

            <label class="mt-4 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("profile.privacy.anonymise_reason_label") }}
            </label>
            <textarea
              v-model="anonymiseReason"
              rows="3"
              :placeholder="t('profile.privacy.anonymise_reason_placeholder')"
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />

            <label class="mt-4 block text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t("profile.privacy.anonymise_confirm_label") }}
            </label>
            <input
              v-model="anonymiseConfirm"
              type="text"
              :placeholder="ANONYMISE_CONFIRM_PHRASE"
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />

            <p v-if="anonymiseError" class="mt-2 text-xs text-rose-600 dark:text-rose-400">
              {{ anonymiseError }}
            </p>

            <div class="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                class="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700"
                :disabled="isSubmittingAnonymise"
                @click="closeAnonymiseDialog"
              >
                {{ t("common.cancel") }}
              </button>
              <button
                type="button"
                class="rounded bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
                :disabled="!canSubmitAnonymise || isSubmittingAnonymise"
                @click="handleSubmitAnonymise"
              >
                {{ t("profile.privacy.anonymise_submit") }}
              </button>
            </div>
          </template>

          <template v-else>
            <h3 class="text-lg font-semibold text-emerald-700 dark:text-emerald-400">
              {{ t("profile.privacy.anonymise_done_title") }}
            </h3>
            <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {{ t("profile.privacy.anonymise_done_body") }}
            </p>
            <div class="mt-4 flex justify-end">
              <button
                type="button"
                class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                @click="closeAnonymiseDialog"
              >
                {{ t("common.close") }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Issue modal — captures the label, then flips to "copy this once" -->
    <Teleport to="body">
      <div
        v-if="showIssueModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="closeIssueModal"
      >
        <div class="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl dark:bg-gray-900">
          <!-- Step 1: ask for the label -->
          <template v-if="!issuedToken">
            <h2 class="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
              {{ t("profile.api_tokens.issue_modal_title") }}
            </h2>
            <p class="mb-4 text-sm text-gray-600 dark:text-gray-400">
              {{ t("profile.api_tokens.issue_modal_intro") }}
            </p>
            <label
              for="pat-label"
              class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              {{ t("profile.api_tokens.label_field") }}
            </label>
            <input
              id="pat-label"
              v-model="issueLabel"
              type="text"
              maxlength="128"
              :placeholder="t('profile.api_tokens.label_placeholder')"
              class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
              @keydown.enter="submitIssue"
            />
            <p
              v-if="issueError"
              class="mt-2 text-sm text-red-700 dark:text-red-400"
            >
              {{ issueError }}
            </p>
            <div class="mt-4 flex justify-end gap-2">
              <button
                class="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                @click="closeIssueModal"
              >
                {{ t("common.cancel") }}
              </button>
              <button
                class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                :disabled="!issueLabel.trim()"
                @click="submitIssue"
              >
                {{ t("profile.api_tokens.issue_submit") }}
              </button>
            </div>
          </template>

          <!-- Step 2: copy this once -->
          <template v-else>
            <h2 class="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
              {{ t("profile.api_tokens.created_title") }}
            </h2>
            <p
              class="mb-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
            >
              {{ t("profile.api_tokens.copy_once_warning") }}
            </p>
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t("profile.api_tokens.token_field") }}
            </label>
            <input
              :value="issuedToken.token"
              readonly
              class="w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
              @focus="($event.target as HTMLInputElement).select()"
            />
            <p
              v-if="copyFeedback"
              class="mt-2 text-xs text-emerald-700 dark:text-emerald-400"
            >
              {{ copyFeedback }}
            </p>
            <div class="mt-4 flex justify-end gap-2">
              <button
                class="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                @click="copyTokenToClipboard"
              >
                {{ t("profile.api_tokens.copy_button") }}
              </button>
              <button
                class="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                @click="closeIssueModal"
              >
                {{ t("profile.api_tokens.done_button") }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </Teleport>
  </div>
</template>
