/**
 * Public-page component registry — `public_navigation` capability.
 *
 * Each entry maps a *component name* (the string a plugin's
 * ``ui_descriptor.public_navigation.component`` field carries) to an
 * async import of the matching Vue component. Mirrors the pattern used
 * by ``components/lookup/registry.ts`` (inline_authority),
 * ``components/deposit/registry.ts`` (collection_deposit), and
 * ``components/website-deposit/registry.ts`` (website_deposit).
 *
 * Vite needs the path literal at build time to do code-splitting, so
 * adding a new public-navigation plugin is a single line here. The
 * link is surfaced via PublicHeader / PublicHomeSection / PublicFooter
 * iterating ``uiConfig.config.public_nav`` filtered by section.
 *
 * Each plugin still owns its SPA route (declared in its own router
 * snippet under PublicLayout); this registry is consumed if a layout
 * component ever needs to render the page body inline (none does
 * today — the registry is here so future PRs don't need to re-derive
 * the convention).
 */
import type { Component } from "vue";
// import { defineAsyncComponent } from "vue";

export const PUBLIC_PAGE_COMPONENTS: Record<string, Component> = {
  // Future plugins land one line each. Example:
  // NlSearchPublicView: defineAsyncComponent(() => import("@/components/public-pages/NlSearchPublicView.vue")),
};
