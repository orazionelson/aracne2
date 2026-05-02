/**
 * Shared helpers for the ``public_navigation`` capability.
 *
 * Three layout components iterate the same array
 * (``uiConfig.config.public_nav``) — PublicHeader, PublicHomeSection,
 * PublicFooter. Centralising the section-filter and label-resolution
 * logic keeps the three iterators in sync.
 */
import { computed, type ComputedRef } from "vue";
import { useI18n } from "vue-i18n";
import { useUiConfigStore, type PublicNavEntry } from "@/stores/ui_config";

export type PublicNavSection = PublicNavEntry["section"];

/**
 * Reactive, priority-sorted list of entries for *section*. The backend
 * already sorts by priority + plugin_name, but sort defensively so a
 * future change on the wire does not break the layout.
 */
export function usePublicNav(
  section: PublicNavSection,
): ComputedRef<PublicNavEntry[]> {
  const uiConfig = useUiConfigStore();
  return computed(() =>
    uiConfig.config.public_nav
      .filter((e) => e.section === section)
      .sort((a, b) => a.priority - b.priority || a.plugin_name.localeCompare(b.plugin_name)),
  );
}

/**
 * Resolve an entry's user-visible label.
 *
 * Preference order:
 * 1. ``label_key`` via vue-i18n when the key is registered;
 * 2. ``label_<active locale>`` (e.g. ``label_it`` when locale is ``it``);
 * 3. ``label_en`` as the universal fallback;
 * 4. ``plugin_name`` — last resort, shouldn't happen in practice.
 */
export function publicNavLabel(
  entry: PublicNavEntry,
  resolveKey: (key: string) => string | null,
  activeLocale: string,
): string {
  if (entry.label_key) {
    const resolved = resolveKey(entry.label_key);
    if (resolved) return resolved;
  }
  const lang = activeLocale.split("-")[0].toLowerCase();
  if (lang === "it" && entry.label_it) return entry.label_it;
  if (lang === "en" && entry.label_en) return entry.label_en;
  if (entry.label_en) return entry.label_en;
  if (entry.label_it) return entry.label_it;
  return entry.plugin_name;
}

/**
 * Bound version of :func:`publicNavLabel` — wires up vue-i18n for the
 * caller. Use inside a component ``setup()`` only.
 */
export function usePublicNavLabel() {
  const { t, te, locale } = useI18n();
  function resolveKey(key: string): string | null {
    return te(key) ? t(key) : null;
  }
  return (entry: PublicNavEntry) =>
    publicNavLabel(entry, resolveKey, locale.value);
}
