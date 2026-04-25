<script setup lang="ts">
/**
 * Generic user avatar — uploaded image when ``avatarUrl`` is set,
 * otherwise a deterministic monogram (initials in a coloured circle,
 * colour derived from a username hash so the same user always lands
 * on the same hue).
 *
 * Used in the Profile page, the navbar user dropdown, the workflow
 * timeline popovers, and any future @mention surface.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    /** Username — used both for the API URL and the monogram seed. */
    username: string;
    /** Display name — preferred over username for the monogram letters. */
    displayName?: string | null;
    /** Extension stored on the user (e.g. ``"png"``). When non-null
     * the avatar is fetched from ``/api/v1/users/<username>/avatar``;
     * when null the component renders a monogram. */
    avatarUrl?: string | null;
    /** Diameter in pixels. */
    size?: number;
    /** Adds a subtle border ring (used in the Profile preview). */
    ring?: boolean;
  }>(),
  { displayName: null, avatarUrl: null, size: 40, ring: false },
);

// Fixed palette — bright but desaturated so white initials read on top.
const PALETTE: string[] = [
  "#1e40af", "#0e7490", "#0369a1", "#3730a3", "#5b21b6",
  "#7c2d12", "#9d174d", "#831843", "#166534", "#365314",
  "#854d0e", "#9f1239", "#1e3a8a", "#075985", "#134e4a",
];

function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) & 0xffffffff;
  return Math.abs(h);
}

const initials = computed(() => {
  const source = (props.displayName || props.username || "?").trim();
  if (!source) return "?";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
});

const bgColor = computed(() => PALETTE[djb2(props.username || "") % PALETTE.length]);

const dimensionStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.max(10, Math.round(props.size * 0.4))}px`,
}));

const imgSrc = computed<string | null>(() => {
  if (!props.avatarUrl) return null;
  return `/api/v1/users/${encodeURIComponent(props.username)}/avatar`;
});
</script>

<template>
  <div
    class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold text-white"
    :class="ring ? 'ring-2 ring-white shadow-md dark:ring-gray-800' : ''"
    :style="{ ...dimensionStyle, backgroundColor: imgSrc ? '#e5e7eb' : bgColor }"
    :aria-label="username"
    :title="username"
  >
    <img
      v-if="imgSrc"
      :src="imgSrc"
      :alt="username"
      class="h-full w-full object-cover"
      loading="lazy"
    />
    <span v-else class="select-none uppercase tracking-tight">{{ initials }}</span>
  </div>
</template>
