/**
 * Inject and keep in sync a single ``<script type="application/ld+json">``
 * element in ``<head>`` that exposes schema.org structured data for the
 * current public page.
 *
 * Why just one script tag: at any time the browser is on exactly one
 * page, and search crawlers expect one structured-data object per page
 * (multiple are allowed but require array-of-objects wrapping). Using a
 * shared ``id`` means route navigations overwrite the previous payload
 * cleanly — no stacking, no stale blocks after `<RouterView />` swaps.
 *
 * Caller passes a Ref / ComputedRef that returns ``null`` when the page
 * has no structured data yet (e.g. data is still loading). The composable
 * removes the script tag while the source is ``null`` and re-installs it
 * when data arrives.
 */

import { onMounted, onUnmounted, watch, type Ref, type ComputedRef } from "vue";

const SCRIPT_ID = "aracne-jsonld";

export type JsonLdSource = Ref<object | null> | ComputedRef<object | null>;

function ensureScript(): HTMLScriptElement {
  const existing = document.getElementById(SCRIPT_ID);
  if (existing instanceof HTMLScriptElement) return existing;
  const el = document.createElement("script");
  el.type = "application/ld+json";
  el.id = SCRIPT_ID;
  document.head.appendChild(el);
  return el;
}

function removeScript(): void {
  const el = document.getElementById(SCRIPT_ID);
  if (el) el.remove();
}

function render(value: object | null): void {
  if (typeof document === "undefined") return; // SSR safety (future-proof)
  if (value === null) {
    removeScript();
    return;
  }
  ensureScript().textContent = JSON.stringify(value);
}

export function useJsonLd(source: JsonLdSource): void {
  onMounted(() => {
    render(source.value);
  });

  watch(source, (v) => render(v), { deep: true });

  onUnmounted(() => {
    removeScript();
  });
}
