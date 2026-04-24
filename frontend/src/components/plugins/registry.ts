/**
 * Frontend registry of plugins that expose an admin configuration page.
 *
 * The route ``/admin/plugins/:slug/config`` looks up the slug here to pick
 * which Vue component to mount. When a new plugin ships a config panel,
 * extend the registry with a new entry — do not hardcode slugs elsewhere.
 */

import type { Component } from "vue";

export interface PluginConfigEntry {
  /** Plugin slug — must match ``Plugin.name`` in the backend DB. */
  slug: string;
  /**
   * i18n key whose value is the human-readable page title.
   * Falls back to the plugin's display name when missing.
   */
  titleKey?: string;
  /** Async-imported component rendered inside the config page shell. */
  component: () => Promise<Component>;
}

export const PLUGIN_CONFIG_REGISTRY: PluginConfigEntry[] = [
  {
    slug: "zenodo_deposit",
    titleKey: "zenodo.panel_title",
    component: () => import("@/components/plugins/ZenodoDepositConfig.vue"),
  },
  {
    slug: "internet_archive",
    titleKey: "internet_archive.panel_title",
    component: () =>
      import("@/components/plugins/InternetArchiveConfig.vue"),
  },
  {
    slug: "zotero_import",
    titleKey: "zotero_import.panel_title",
    component: () =>
      import("@/components/plugins/ZoteroImportConfig.vue"),
  },
  {
    slug: "wikidata",
    titleKey: "wikidata.panel_title",
    component: () => import("@/components/plugins/WikidataConfig.vue"),
  },
  {
    slug: "gnd",
    titleKey: "gnd.panel_title",
    component: () => import("@/components/plugins/GndConfig.vue"),
  },
  {
    slug: "cerl",
    titleKey: "cerl.panel_title",
    component: () => import("@/components/plugins/CerlConfig.vue"),
  },
  {
    slug: "peripleo",
    titleKey: "peripleo.panel_title",
    component: () => import("@/components/plugins/PeripleoConfig.vue"),
  },
  {
    slug: "getty_aat",
    titleKey: "getty_aat.panel_title",
    component: () => import("@/components/plugins/GettyAatConfig.vue"),
  },
  {
    slug: "openalex",
    titleKey: "openalex.panel_title",
    component: () => import("@/components/plugins/OpenAlexConfig.vue"),
  },
  {
    slug: "trismegistos",
    titleKey: "trismegistos.panel_title",
    component: () => import("@/components/plugins/TrismegistosConfig.vue"),
  },
  {
    slug: "orcid",
    titleKey: "orcid.panel_title",
    component: () => import("@/components/plugins/OrcidConfig.vue"),
  },
  {
    slug: "ror",
    titleKey: "ror.panel_title",
    component: () => import("@/components/plugins/RorConfig.vue"),
  },
  {
    slug: "viaf",
    titleKey: "viaf.panel_title",
    component: () => import("@/components/plugins/ViafConfig.vue"),
  },
  {
    slug: "geonames",
    titleKey: "geonames.panel_title",
    component: () => import("@/components/plugins/GeonamesConfig.vue"),
  },
  {
    slug: "crossref_lookup",
    titleKey: "crossref.panel_title",
    component: () =>
      import("@/components/plugins/CrossrefLookupConfig.vue"),
  },
  {
    slug: "help",
    titleKey: "help.panel_title",
    component: () => import("@/components/plugins/HelpConfig.vue"),
  },
  {
    slug: "evt",
    titleKey: "evt.panel_title",
    component: () => import("@/components/plugins/EvtConfig.vue"),
  },
  {
    slug: "codeberg_integration",
    titleKey: "codeberg.panel_title",
    component: () => import("@/components/plugins/CodebergConfig.vue"),
  },
  {
    slug: "github_integration",
    titleKey: "github.panel_title",
    component: () => import("@/components/plugins/GithubConfig.vue"),
  },
  {
    slug: "gitlab_integration",
    titleKey: "gitlab.panel_title",
    component: () => import("@/components/plugins/GitlabConfig.vue"),
  },
];

export function getPluginConfigEntry(
  slug: string,
): PluginConfigEntry | undefined {
  return PLUGIN_CONFIG_REGISTRY.find((e) => e.slug === slug);
}

export function hasPluginConfig(slug: string): boolean {
  return PLUGIN_CONFIG_REGISTRY.some((e) => e.slug === slug);
}
