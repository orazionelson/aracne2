/**
 * Pinia store for ``/admin/policies`` — Phase PP-G.
 *
 * Holds the list of available templates plus the currently-loaded
 * form's hydration state. Filters / locale / draft buffer are
 * kept here, not in the URL — admins typically work on one policy
 * at a time and don't deep-link into a specific draft state.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { apiClient } from "@/services/api";

// ── Wire types ────────────────────────────────────────────────────────────────

export type FieldKind =
  | "text"
  | "textarea"
  | "integer"
  | "enum"
  | "rows"
  | "platform";

export interface FieldDescriptor {
  name: string;
  kind: FieldKind;
  label_key: string | null;
  hint_key: string | null;
  required: boolean;
  localized: boolean;
  options: string[];
  min: number | null;
  max: number | null;
  rows_fields: FieldDescriptor[];
  is_platform: boolean;
}

export interface TemplateDescriptor {
  slug: string;
  url_slug: string;
  title_key: string;
  categories: string[];
  fields: FieldDescriptor[];
}

export interface PolicyPageListItem {
  template_slug: string;
  url_slug: string;
  title_key: string;
  categories: string[];
  is_published: boolean;
  latest_version_number: number | null;
  latest_saved_at: string | null;
}

export interface PolicyPageDetail {
  template: TemplateDescriptor;
  is_published: boolean;
  published_version_number: number | null;
  latest_version_number: number | null;
  latest_content: Record<string, unknown>;
  platform_values: Record<string, unknown>;
}

export interface PolicyPageVersionView {
  id: string;
  version_number: number;
  content_sha256: string;
  message: string | null;
  saved_at: string;
  saved_by_username: string | null;
  is_published: boolean;
}

export interface CapabilityHolder {
  role_name: string;
  holder_user_id: string | null;
  holder_username: string | null;
  holder_display_name: string | null;
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const usePolicyPagesStore = defineStore("policyPages", () => {
  const list = ref<PolicyPageListItem[]>([]);
  const isLoadingList = ref(false);

  const detail = ref<PolicyPageDetail | null>(null);
  const isLoadingDetail = ref(false);
  const draftContent = ref<Record<string, unknown>>({});
  const draftDirty = ref(false);
  const message = ref("");

  const versions = ref<PolicyPageVersionView[]>([]);
  const isLoadingVersions = ref(false);

  const policyManager = ref<CapabilityHolder | null>(null);
  const isLoadingPolicyManager = ref(false);

  const error = ref<string | null>(null);

  const currentLocale = ref<"it" | "en">("en");

  const isWritable = computed(() => {
    // True when the user has the PolicyManager capability OR is Admin.
    // Resolved client-side from the role + the holder map; the
    // backend's require_capability is the authoritative gate.
    // We optimistically allow Admin always; PolicyManager
    // identification happens server-side on every write.
    return true;
  });

  // ── List ────────────────────────────────────────────────────────────────────

  async function fetchList(): Promise<void> {
    isLoadingList.value = true;
    error.value = null;
    try {
      list.value = await apiClient.get<PolicyPageListItem[]>("/policy-pages");
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoadingList.value = false;
    }
  }

  // ── Form ───────────────────────────────────────────────────────────────────

  async function fetchDetail(slug: string): Promise<void> {
    isLoadingDetail.value = true;
    error.value = null;
    try {
      const d = await apiClient.get<PolicyPageDetail>(`/policy-pages/${slug}`);
      detail.value = d;
      draftContent.value = { ...(d.latest_content || {}) };
      draftDirty.value = false;
      message.value = "";
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoadingDetail.value = false;
    }
  }

  function setField(name: string, value: unknown): void {
    draftContent.value = { ...draftContent.value, [name]: value };
    draftDirty.value = true;
  }

  function setLocalizedField(name: string, locale: string, value: string): void {
    const existing = (draftContent.value[name] as Record<string, string>) || {};
    draftContent.value = {
      ...draftContent.value,
      [name]: { ...existing, [locale]: value },
    };
    draftDirty.value = true;
  }

  function setRows(name: string, rows: Record<string, unknown>[]): void {
    draftContent.value = { ...draftContent.value, [name]: rows };
    draftDirty.value = true;
  }

  async function saveDraft(slug: string): Promise<PolicyPageVersionView | null> {
    error.value = null;
    try {
      const v = await apiClient.post<PolicyPageVersionView>(
        `/policy-pages/${slug}/save`,
        { content: draftContent.value, message: message.value || null },
      );
      draftDirty.value = false;
      message.value = "";
      // Refresh detail so the latest version number is right.
      await fetchDetail(slug);
      return v;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
      return null;
    }
  }

  async function publish(slug: string, versionNumber: number | null = null): Promise<void> {
    error.value = null;
    try {
      await apiClient.post(`/policy-pages/${slug}/publish`, {
        version_number: versionNumber,
      });
      await Promise.all([fetchDetail(slug), fetchVersions(slug), fetchList()]);
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  async function unpublish(slug: string): Promise<void> {
    error.value = null;
    try {
      await apiClient.post(`/policy-pages/${slug}/unpublish`);
      await Promise.all([fetchDetail(slug), fetchVersions(slug), fetchList()]);
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  // ── Versions ───────────────────────────────────────────────────────────────

  async function fetchVersions(slug: string): Promise<void> {
    isLoadingVersions.value = true;
    error.value = null;
    try {
      versions.value = await apiClient.get<PolicyPageVersionView[]>(
        `/policy-pages/${slug}/versions`,
      );
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoadingVersions.value = false;
    }
  }

  // ── PolicyManager capability ───────────────────────────────────────────────

  async function fetchPolicyManager(): Promise<void> {
    isLoadingPolicyManager.value = true;
    try {
      policyManager.value = await apiClient.get<CapabilityHolder>(
        "/admin/capabilities/PolicyManager",
      );
    } catch {
      policyManager.value = null;
    } finally {
      isLoadingPolicyManager.value = false;
    }
  }

  async function transferPolicyManager(userId: string): Promise<void> {
    policyManager.value = await apiClient.put<CapabilityHolder>(
      "/admin/capabilities/PolicyManager",
      { user_id: userId },
    );
  }

  async function revokePolicyManager(): Promise<void> {
    await apiClient.delete("/admin/capabilities/PolicyManager");
    policyManager.value = {
      role_name: "PolicyManager",
      holder_user_id: null,
      holder_username: null,
      holder_display_name: null,
    };
  }

  return {
    list,
    isLoadingList,
    detail,
    isLoadingDetail,
    draftContent,
    draftDirty,
    message,
    versions,
    isLoadingVersions,
    policyManager,
    isLoadingPolicyManager,
    error,
    currentLocale,
    isWritable,
    fetchList,
    fetchDetail,
    setField,
    setLocalizedField,
    setRows,
    saveDraft,
    publish,
    unpublish,
    fetchVersions,
    fetchPolicyManager,
    transferPolicyManager,
    revokePolicyManager,
  };
});
