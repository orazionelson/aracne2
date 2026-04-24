<script setup lang="ts">
/**
 * Deterministic monogram avatar for a plugin row.
 *
 * The slug is hashed into a fixed colour palette so a given plugin
 * always shows up with the same tint; the initials come from the
 * display name (first letter of the first two word-tokens, or the
 * first two characters of a single-word name).
 *
 * Pure presentation — no network, no assets.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    name: string;
    displayName: string;
    size?: "sm" | "md" | "lg";
  }>(),
  { size: "md" },
);

const PALETTE = [
  "bg-indigo-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-fuchsia-500",
  "bg-lime-600",
  "bg-cyan-600",
  "bg-red-500",
];

function hashSlug(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

const bgClass = computed(
  () => PALETTE[hashSlug(props.name) % PALETTE.length],
);

const initials = computed(() => {
  const label = (props.displayName || props.name).trim();
  const words = label.split(/[\s_\-]+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  return label.slice(0, 2).toUpperCase();
});

const sizeClass = computed(() => {
  switch (props.size) {
    case "sm":
      return "h-7 w-7 text-[11px]";
    case "lg":
      return "h-10 w-10 text-sm";
    default:
      return "h-8 w-8 text-xs";
  }
});
</script>

<template>
  <span
    :class="[
      'inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white',
      bgClass,
      sizeClass,
    ]"
    :title="displayName"
    aria-hidden="true"
  >
    {{ initials }}
  </span>
</template>
