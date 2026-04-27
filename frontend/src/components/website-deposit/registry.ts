/**
 * Website-deposit component registry.
 *
 * Mirrors the collection-side registry: each entry maps a *component
 * name* (the string a plugin's
 * ``ui_descriptor.website_deposit.component`` field carries) to an
 * async import of the matching Vue component.
 *
 * The components themselves already lived under ``components/ui/``
 * (one per backend, predating the capability refactor) so the
 * registry just points at them — no extraction or rename needed.
 *
 * Lazy-loaded: a plugin that the admin never activates never ships
 * its panel into the user's browser.
 */
import type { Component } from "vue";
import { defineAsyncComponent } from "vue";

export const WEBSITE_DEPOSIT_COMPONENTS: Record<string, Component> = {
  ZenodoWebsiteSection:          defineAsyncComponent(() => import("@/components/ui/ZenodoWebsiteSection.vue")),
  InternetArchiveWebsiteSection: defineAsyncComponent(() => import("@/components/ui/InternetArchiveWebsiteSection.vue")),
  CodebergWebsiteSection:        defineAsyncComponent(() => import("@/components/ui/CodebergWebsiteSection.vue")),
  GithubWebsiteSection:          defineAsyncComponent(() => import("@/components/ui/GithubWebsiteSection.vue")),
  GitlabWebsiteSection:          defineAsyncComponent(() => import("@/components/ui/GitlabWebsiteSection.vue")),
  DataverseWebsiteSection:       defineAsyncComponent(() => import("@/components/ui/DataverseWebsiteSection.vue")),
};
