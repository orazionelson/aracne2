import { computed, type ComputedRef } from "vue";
import { useUiConfigStore } from "@/stores/ui_config";
import { contrastingTextColor } from "@/utils/color";

/**
 * Bind the public navbar's background colour (admin-configured via
 * `navbar_bg_color`) together with an automatically-picked readable
 * foreground colour (WCAG contrast-optimised — see utils/color.ts).
 *
 * Consumers apply `:style="{ backgroundColor: bg, color: text }"` on
 * their header/root element and can drop any hard-coded `text-white`
 * classes. A custom brand colour can still be forced through the
 * public pages CSS override (see docs/reference/PUBLIC_PAGES.md).
 */
export function useNavbarColors(): {
  bg: ComputedRef<string>;
  text: ComputedRef<string>;
} {
  const uiConfig = useUiConfigStore();
  const bg = computed(() => uiConfig.config.navbar_bg_color);
  const text = computed(() => contrastingTextColor(bg.value));
  return { bg, text };
}
