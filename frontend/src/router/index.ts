import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

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
    {
      path: "/",
      name: "home",
      component: () => import("@/views/HomeView.vue"),
      meta: { requiresAuth: true },
    },
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
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
    },
  ],
});

let hydrated = false;
router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!hydrated) {
    await auth.hydrate();
    hydrated = true;
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
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
