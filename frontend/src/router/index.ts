import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useUiConfigStore } from "@/stores/ui_config";

// Augment RouteMeta
declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    requiresMinRole?: string;  // numeric guard: user level >= role level
    requiresRole?: string;     // exact guard: for lateral-role-exclusive routes
    layout?: "admin" | "public" | "auth";
    forceCollapsedSidebar?: boolean;
    clipsOwnScroll?: boolean;
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ── Public landing ─────────────────────────────────────────────────────
    {
      path: "/",
      name: "home",
      component: () => import("@/views/PublicHomeView.vue"),
      meta: { layout: "public" },
    },
    // ── Public browsing (no auth required) ────────────────────────────────
    {
      path: "/browse/:slug",
      name: "public-collection",
      component: () => import("@/views/PublicCollectionView.vue"),
      meta: { layout: "public" },
    },
    {
      path: "/browse/:slug/bibliography",
      name: "public-bibliography",
      component: () => import("@/views/PublicBibliographyView.vue"),
      meta: { layout: "public" },
    },
    {
      path: "/browse/:slug/entities",
      name: "public-entities",
      component: () => import("@/views/PublicEntitiesView.vue"),
      meta: { layout: "public" },
    },
    {
      path: "/browse/:slug/:filename",
      name: "public-document",
      component: () => import("@/views/PublicDocumentView.vue"),
      meta: { layout: "public" },
    },
    // ── Public search (embed of the admin-chosen search engine) ───────────
    {
      path: "/search",
      name: "public-search",
      component: () => import("@/views/PublicSearchView.vue"),
      meta: { layout: "public" },
    },
    // ── EVT public viewer ──────────────────────────────────────────────────
    {
      path: "/collections/:slug/read",
      name: "collection-read",
      component: () => import("@/views/CollectionReadView.vue"),
      meta: { layout: "public" },
    },
    // ── Login ──────────────────────────────────────────────────────────────
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/auth/LoginView.vue"),
      meta: { layout: "auth" },
    },
    // ── Authenticated (admin layout with sidebar) ─────────────────────────
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("@/views/DashboardView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/auth/ProfileView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/users",
      name: "users",
      component: () => import("@/views/UsersView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "EditorInChief", layout: "admin" },
    },
    {
      path: "/users/:username",
      name: "user-detail",
      component: () => import("@/views/UserDetailView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/collections",
      name: "collections",
      component: () => import("@/views/CollectionsView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/collections/:slug",
      name: "collection-detail",
      component: () => import("@/views/CollectionDetailView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/collections/:slug/edit",
      name: "collection-edit",
      component: () => import("@/views/CollectionEditView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "EditorInChief", layout: "admin" },
    },
    {
      path: "/collections/:slug/bibliobuilder",
      name: "collection-bibliobuilder",
      component: () => import("@/views/CollectionBibliobuilderview.vue"),
      meta: { requiresAuth: true, requiresMinRole: "EditorInChief", layout: "admin" },
    },
    {
      path: "/collections/:slug/document/:filename/view",
      name: "document-view",
      component: () => import("@/views/DocumentView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/collections/:slug/document/:filename/edit",
      name: "document-edit",
      component: () => import("@/views/DocumentEditView.vue"),
      meta: {
        requiresAuth: true,
        layout: "admin",
        forceCollapsedSidebar: true,
        clipsOwnScroll: true,
      },
    },
    {
      path: "/notifications",
      name: "notifications",
      component: () => import("@/views/NotificationsView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/help",
      name: "help",
      component: () => import("@/views/HelpView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/admin/plugins",
      name: "admin-plugins",
      component: () => import("@/views/admin/PluginsView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/admin/plugins/:slug/config",
      name: "admin-plugin-config",
      component: () => import("@/views/admin/PluginConfigView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
      props: true,
    },
    {
      path: "/admin/settings",
      name: "admin-settings",
      component: () => import("@/views/admin/SettingsView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/admin/webhooks",
      name: "admin-webhooks",
      component: () => import("@/views/admin/WebhooksView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/admin/backup",
      name: "admin-backup",
      component: () => import("@/views/admin/BackupView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/admin/entities",
      name: "admin-entities",
      component: () => import("@/views/admin/NamedEntitiesView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/admin/websites",
      name: "admin-websites",
      component: () => import("@/views/admin/WebsitesView.vue"),
      // [D+]: Designer, EditorInChief, Admin.
      // Router enforces auth only; role check is in the view and backend.
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/admin/websites/:slug/edit",
      name: "admin-website-edit",
      component: () => import("@/views/admin/WebsiteEditView.vue"),
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/admin/search-engines",
      name: "admin-search-engines",
      component: () => import("@/views/admin/SearchEnginesView.vue"),
      // [D+]: Designer, EditorInChief, Admin.
      meta: { requiresAuth: true, layout: "admin" },
    },
    {
      path: "/admin/public-pages",
      name: "admin-public-pages",
      component: () => import("@/views/admin/PublicPagesView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin", layout: "admin" },
    },
    {
      path: "/entities",
      name: "entities",
      component: () => import("@/views/EntitiesView.vue"),
      // Layout derived from auth state: authenticated users see the sidebar.
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
      // Layout derived from auth state.
    },
  ],
});

let authHydrated = false;
let configFetched = false;

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  const uiConfig = useUiConfigStore();

  // Hydrate auth once (silent token refresh from cookie).
  if (!authHydrated) {
    await auth.hydrate();
    authHydrated = true;
  }

  // Fetch public UI config once (needed to decide whether / is public).
  if (!configFetched) {
    await uiConfig.fetchConfig();
    configFetched = true;
  }

  // Root (/): authenticated users jump to the dashboard; unauthenticated
  // users see the public home only if the admin enabled it.
  if (to.name === "home") {
    if (auth.isAuthenticated) return { name: "dashboard" };
    if (!uiConfig.config.public_home_enabled) return { name: "login" };
    return;
  }

  // Standard auth guard for protected routes.
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  // Redirect authenticated users away from login.
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "dashboard" };
  }

  if (to.meta.requiresMinRole && !auth.hasMinRole(to.meta.requiresMinRole)) {
    return { name: "dashboard" };
  }
  if (to.meta.requiresRole && !auth.hasRole(to.meta.requiresRole)) {
    return { name: "dashboard" };
  }
});

export default router;
