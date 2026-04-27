/**
 * Collection-deposit component registry.
 *
 * Each entry maps a *component name* (the string a plugin's
 * ``ui_descriptor.collection_deposit.component`` field carries) to an
 * async import of the matching Vue component. Vite needs the path
 * literal at build time to do code-splitting, so the indirection
 * goes through this static map — but adding a new deposit plugin is
 * still a single line here, no further edits to CollectionDetailView.
 *
 * Components are loaded lazily: a plugin that the admin never
 * activates never ships its tab body into the user's browser.
 */
import type { Component } from "vue";
import { defineAsyncComponent } from "vue";

export const DEPOSIT_COMPONENTS: Record<string, Component> = {
  ZenodoCollectionDepositPanel:          defineAsyncComponent(() => import("@/components/deposit/ZenodoCollectionDepositPanel.vue")),
  InternetArchiveCollectionDepositPanel: defineAsyncComponent(() => import("@/components/deposit/InternetArchiveCollectionDepositPanel.vue")),
  CodebergCollectionDepositPanel:        defineAsyncComponent(() => import("@/components/deposit/CodebergCollectionDepositPanel.vue")),
  GithubCollectionDepositPanel:          defineAsyncComponent(() => import("@/components/deposit/GithubCollectionDepositPanel.vue")),
  GitlabCollectionDepositPanel:          defineAsyncComponent(() => import("@/components/deposit/GitlabCollectionDepositPanel.vue")),
  DataverseCollectionDepositPanel:       defineAsyncComponent(() => import("@/components/deposit/DataverseCollectionDepositPanel.vue")),
};
