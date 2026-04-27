/**
 * Authority-lookup component registry.
 *
 * Each entry maps a *component name* (the string a plugin's
 * ``ui_descriptor.inline_authority.component`` field carries) to an
 * async import of the matching Vue component. Vite needs the path
 * literal at build time to do code-splitting, so the indirection
 * goes through this static map — but adding a new lookup plugin is
 * still a single line here, no further edits to DocumentEditView.
 *
 * Components are loaded lazily: a plugin that the admin never
 * activates never ships its panel into the user's browser.
 */
import type { Component } from "vue";
import { defineAsyncComponent } from "vue";

export const LOOKUP_COMPONENTS: Record<string, Component> = {
  WikidataLinkPanel:    defineAsyncComponent(() => import("@/components/ui/WikidataLinkPanel.vue")),
  OrcidLinkPanel:       defineAsyncComponent(() => import("@/components/ui/OrcidLinkPanel.vue")),
  RorLinkPanel:         defineAsyncComponent(() => import("@/components/ui/RorLinkPanel.vue")),
  ViafLinkPanel:        defineAsyncComponent(() => import("@/components/ui/ViafLinkPanel.vue")),
  GeonamesLinkPanel:    defineAsyncComponent(() => import("@/components/ui/GeonamesLinkPanel.vue")),
  GndLinkPanel:         defineAsyncComponent(() => import("@/components/ui/GndLinkPanel.vue")),
  CerlLinkPanel:        defineAsyncComponent(() => import("@/components/ui/CerlLinkPanel.vue")),
  PeripleoLinkPanel:    defineAsyncComponent(() => import("@/components/ui/PeripleoLinkPanel.vue")),
  GettyAatLinkPanel:    defineAsyncComponent(() => import("@/components/ui/GettyAatLinkPanel.vue")),
  OpenAlexPanel:        defineAsyncComponent(() => import("@/components/ui/OpenAlexPanel.vue")),
  TrismegistosLinkPanel: defineAsyncComponent(() => import("@/components/ui/TrismegistosLinkPanel.vue")),
  CrossrefPanel:        defineAsyncComponent(() => import("@/components/ui/CrossrefPanel.vue")),
};
