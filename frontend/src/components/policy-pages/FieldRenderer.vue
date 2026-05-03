<script setup lang="ts">
/**
 * Per-field renderer for the policy form.
 *
 * Six kinds. Localized text / textarea show two side-by-side
 * tabs (IT / EN). Rows render as a small table with per-row
 * sub-fields. Platform fields render the resolved value
 * read-only.
 */
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FieldDescriptor } from "@/stores/policyPages";

const props = defineProps<{
  field: FieldDescriptor;
  value: unknown;
  platformValue?: unknown;
  readonly?: boolean;
}>();

const emit = defineEmits<{
  (e: "update", name: string, value: unknown): void;
  (e: "updateLocalized", name: string, locale: string, value: string): void;
  (e: "updateRows", name: string, rows: Record<string, unknown>[]): void;
}>();

const { t, te } = useI18n();
const activeLocale = ref<"it" | "en">("en");

const labelText = computed(() => {
  const k = props.field.label_key;
  return k && te(k) ? t(k) : props.field.name;
});

const hintText = computed(() => {
  const k = props.field.hint_key;
  return k && te(k) ? t(k) : "";
});

function asString(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function asLocalizedValue(locale: string): string {
  const o = (props.value as Record<string, string>) || {};
  return typeof o[locale] === "string" ? o[locale] : "";
}

function asInteger(): number | "" {
  return typeof props.value === "number" ? props.value : "";
}

function asEnum(): string {
  return typeof props.value === "string" ? props.value : "";
}

function asRows(): Record<string, unknown>[] {
  return Array.isArray(props.value) ? (props.value as Record<string, unknown>[]) : [];
}

function platformDisplay(): string {
  const v = props.platformValue;
  if (v == null) return "—";
  if (Array.isArray(v))
    return v
      .map((x) =>
        typeof x === "string"
          ? x
          : typeof x === "object" && x && "name" in x
            ? `${(x as { name: string }).name} (${(x as { version?: string }).version ?? ""})`
            : JSON.stringify(x),
      )
      .join(", ");
  if (typeof v === "object")
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${val}`)
      .join(", ");
  return String(v);
}

function addRow(): void {
  const empty: Record<string, unknown> = {};
  for (const sub of props.field.rows_fields) {
    empty[sub.name] = sub.localized ? { it: "", en: "" } : "";
  }
  emit("updateRows", props.field.name, [...asRows(), empty]);
}

function removeRow(idx: number): void {
  const cur = asRows();
  emit(
    "updateRows",
    props.field.name,
    cur.filter((_, i) => i !== idx),
  );
}

function setRowCell(idx: number, sub: FieldDescriptor, value: unknown): void {
  const cur = asRows().map((row, i) => (i === idx ? { ...row, [sub.name]: value } : row));
  emit("updateRows", props.field.name, cur);
}
</script>

<template>
  <div class="rounded border border-gray-200 bg-white p-3">
    <div class="flex items-center justify-between">
      <label class="text-sm font-medium text-gray-800">
        {{ labelText }}
        <span v-if="field.required" class="text-rose-500">*</span>
      </label>
      <span
        v-if="field.is_platform"
        class="rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
      >
        {{ t("policy_pages.platform_value") }}
      </span>
    </div>
    <p v-if="hintText" class="mt-1 text-xs text-gray-500">{{ hintText }}</p>

    <!-- text / textarea — non-localized -->
    <template v-if="(field.kind === 'text' || field.kind === 'textarea') && !field.localized && !field.is_platform">
      <input
        v-if="field.kind === 'text'"
        type="text"
        :value="asString(value)"
        :disabled="readonly"
        class="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @input="emit('update', field.name, ($event.target as HTMLInputElement).value)"
      />
      <textarea
        v-else
        rows="4"
        :value="asString(value)"
        :disabled="readonly"
        class="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @input="emit('update', field.name, ($event.target as HTMLTextAreaElement).value)"
      />
    </template>

    <!-- text / textarea — localized -->
    <template v-else-if="(field.kind === 'text' || field.kind === 'textarea') && field.localized && !field.is_platform">
      <div class="mt-2 flex gap-2 border-b border-gray-100 text-xs">
        <button
          v-for="loc in ['it', 'en']"
          :key="loc"
          type="button"
          class="px-2 py-1"
          :class="activeLocale === loc ? 'border-b-2 border-indigo-500 font-semibold text-indigo-700' : 'text-gray-500'"
          @click="activeLocale = loc as 'it' | 'en'"
        >
          {{ loc.toUpperCase() }}
        </button>
      </div>
      <input
        v-if="field.kind === 'text'"
        type="text"
        :value="asLocalizedValue(activeLocale)"
        :disabled="readonly"
        class="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @input="emit('updateLocalized', field.name, activeLocale, ($event.target as HTMLInputElement).value)"
      />
      <textarea
        v-else
        rows="4"
        :value="asLocalizedValue(activeLocale)"
        :disabled="readonly"
        class="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @input="emit('updateLocalized', field.name, activeLocale, ($event.target as HTMLTextAreaElement).value)"
      />
    </template>

    <!-- integer -->
    <template v-else-if="field.kind === 'integer' && !field.is_platform">
      <input
        type="number"
        :value="asInteger()"
        :min="field.min ?? undefined"
        :max="field.max ?? undefined"
        :disabled="readonly"
        class="mt-2 w-32 rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @input="emit('update', field.name, Number(($event.target as HTMLInputElement).value))"
      />
    </template>

    <!-- enum -->
    <template v-else-if="field.kind === 'enum' && !field.is_platform">
      <select
        :value="asEnum()"
        :disabled="readonly"
        class="mt-2 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-50 disabled:opacity-70"
        @change="emit('update', field.name, ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>—</option>
        <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
      </select>
    </template>

    <!-- rows -->
    <template v-else-if="field.kind === 'rows' && !field.is_platform">
      <div class="mt-2 space-y-2">
        <div
          v-for="(row, idx) in asRows()"
          :key="idx"
          class="rounded border border-gray-200 bg-gray-50 p-2"
        >
          <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
            <FieldRenderer
              v-for="sub in field.rows_fields"
              :key="sub.name"
              :field="sub"
              :value="row[sub.name]"
              :readonly="readonly"
              @update="(_n, v) => setRowCell(idx, sub, v)"
              @updateLocalized="(_n, l, v) => setRowCell(idx, sub, { ...((row[sub.name] as Record<string, string>) || {}), [l]: v })"
            />
          </div>
          <button
            v-if="!readonly"
            type="button"
            class="mt-2 rounded border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50"
            @click="removeRow(idx)"
          >
            {{ t("policy_pages.remove_row") }}
          </button>
        </div>
        <button
          v-if="!readonly"
          type="button"
          class="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50"
          @click="addRow"
        >
          {{ t("policy_pages.add_row") }}
        </button>
      </div>
    </template>

    <!-- platform -->
    <template v-else-if="field.is_platform">
      <p class="mt-2 break-all rounded bg-amber-50 px-3 py-2 font-mono text-xs text-amber-900">
        {{ platformDisplay() }}
      </p>
    </template>
  </div>
</template>
