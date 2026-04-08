import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useUiConfigStore } from "@/stores/ui_config";

// Augment RouteMeta to allow requiresAuth and requiresRole
declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    requiresMinRole?: string;  // numeric guard: user level >= role level
    requiresRole?: string;     // exact guard: for lateral-role-exclusive routes
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ── Home (smart: auth home or public home) ─────────────────────────────
    {
      path: "/",
      name: "home",
      component: () => import("@/views/HomeView.vue"),
      // No requiresAuth — the guard handles conditional access below.
    },
    // ── Public browsing (no auth required) ────────────────────────────────
    {
      path: "/browse/:slug",
      name: "public-collection",
      component: () => import("@/views/PublicCollectionView.vue"),
    },
    {
      path: "/browse/:slug/:filename",
      name: "public-document",
      component: () => import("@/views/PublicDocumentView.vue"),
    },
    // ── EVT public viewer ──────────────────────────────────────────────────
    {
      path: "/collections/:slug/read",
      name: "collection-read",
      component: () => import("@/views/CollectionReadView.vue"),
      // No requiresAuth — EVT view is public
    },
    // ── Authenticated routes ───────────────────────────────────────────────
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/auth/LoginView.vue"),
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/auth/ProfileView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/users",
      name: "users",
      component: () => import("@/views/UsersView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "EditorInChief" },
    },
    {
      path: "/users/:username",
      name: "user-detail",
      component: () => import("@/views/UserDetailView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin" },
    },
    {
      path: "/collections",
      name: "collections",
      component: () => import("@/views/CollectionsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/collections/:slug",
      name: "collection-detail",
      component: () => import("@/views/CollectionDetailView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/collections/:slug/document/:filename/view",
      name: "document-view",
      component: () => import("@/views/DocumentView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/collections/:slug/document/:filename/edit",
      name: "document-edit",
      component: () => import("@/views/DocumentEditView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/notifications",
      name: "notifications",
      component: () => import("@/views/NotificationsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/admin/plugins",
      name: "admin-plugins",
      component: () => import("@/views/admin/PluginsView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin" },
    },
    {
      path: "/admin/settings",
      name: "admin-settings",
      component: () => import("@/views/admin/SettingsView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin" },
    },
    {
      path: "/admin/webhooks",
      name: "admin-webhooks",
      component: () => import("@/views/admin/WebhooksView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin" },
    },
    {
      path: "/admin/entities",
      name: "admin-entities",
      component: () => import("@/views/admin/NamedEntitiesView.vue"),
      meta: { requiresAuth: true, requiresMinRole: "Admin" },
    },
    {
      path: "/entities",
      name: "entities",
      component: () => import("@/views/EntitiesView.vue"),
      // Public — no requiresAuth
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
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

  // Home: allowed for authenticated users always; for unauthenticated users
  // only if public_home_enabled is on.
  if (to.name === "home" && !auth.isAuthenticated) {
    if (!uiConfig.config.public_home_enabled) {
      return { name: "login" };
    }
    return; // public home — allow through
  }

  // Standard auth guard for all other protected routes.
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  // Redirect authenticated users away from login.
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "home" };
  }

  if (to.meta.requiresMinRole && !auth.hasMinRole(to.meta.requiresMinRole)) {
    return { name: "home" };
  }
  if (to.meta.requiresRole && !auth.hasRole(to.meta.requiresRole)) {
    return { name: "home" };
  }
});

export default router;
