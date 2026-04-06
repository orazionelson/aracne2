<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useSettingStore } from "@/stores/settings";

const { t } = useI18n();
const store = useSettingStore();

const error = ref<string | null>(null);
// Map of key → draft value being edited (null = not editing)
const drafts = ref<Record<string, string>>({});
const saving = ref<Record<string, boolean>>({});
const saveError = ref<Record<string, string>>({});

async function load(): Promise<void> {
  error.value = null;
  try {
    await store.fetchSettings();
  } catch {
    error.value = t("common.error");
  }
}

function startEdit(key: string, currentValue: string): void {
  drafts.value[key] = currentValue;
  saveError.value[key] = "";
}

function cancelEdit(key: string): void {
  delete drafts.value[key];
  delete saveError.value[key];
}

async function save(key: string): Promise<void> {
  saving.value[key] = true;
  saveError.value[key] = "";
  try {
    await store.updateSetting(key, drafts.value[key]);
    delete drafts.value[key];
  } catch (err) {
    const msg = (err as { response?: { data?: { error?: { message?: string } } } })
      ?.response?.data?.error?.message;
    saveError.value[key] = msg ?? t("common.error");
  } finally {
    saving.value[key] = false;
  }
}

function isEditing(key: string): boolean {
  return key in drafts.value;
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-4xl p-6">
    <h1 class="mb-6 text-2xl font-bold">{{ t("settings.title") }}</h1>

    <p v-if="error" class="mb-4 text-red-600">{{ error }}</p>
    <p v-if="store.isLoading" class="text-gray-500">{{ t("common.loading") }}</p>

    <div v-else-if="store.settings.length > 0" class="overflow-x-auto">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="bg-gray-100 text-left">
            <th class="px-4 py-2 font-semibold w-56">{{ t("settings.key") }}</th>
            <th class="px-4 py-2 font-semibold">{{ t("settings.value") }}</th>
            <th class="px-4 py-2 font-semibold w-16">{{ t("settings.type") }}</th>
            <th class="px-4 py-2 font-semibold"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in store.settings"
            :key="s.key"
            class="border-b hover:bg-gray-50 align-top"
          >
            <td class="px-4 py-3">
              <code class="text-xs text-gray-700">{{ s.key }}</code>
              <p v-if="s.description" class="mt-0.5 text-xs text-gray-400">
                {{ s.description }}
              </p>
            </td>
            <td class="px-4 py-3">
              <template v-if="isEditing(s.key)">
                <div class="flex flex-col gap-1">
                  <template v-if="s.type === 'bool'">
                    <select
                      v-model="drafts[s.key]"
                      class="rounded border px-2 py-1 text-sm"
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  </template>
                  <template v-else>
                    <input
                      v-model="drafts[s.key]"
                      :type="s.type === 'int' ? 'number' : 'text'"
                      class="rounded border px-2 py-1 text-sm"
                    />
                  </template>
                  <p v-if="saveError[s.key]" class="text-xs text-red-600">
                    {{ saveError[s.key] }}
                  </p>
                </div>
              </template>
              <span v-else class="font-mono text-sm">{{ s.value }}</span>
            </td>
            <td class="px-4 py-3 text-gray-400 text-xs">{{ s.type }}</td>
            <td class="px-4 py-3">
              <template v-if="isEditing(s.key)">
                <div class="flex gap-2">
                  <button
                    :disabled="saving[s.key]"
                    class="rounded bg-gray-900 px-3 py-1 text-xs text-white hover:bg-gray-700 disabled:opacity-40"
                    @click="save(s.key)"
                  >
                    {{ t("common.save") }}
                  </button>
                  <button
                    class="rounded border px-3 py-1 text-xs hover:bg-gray-50"
                    @click="cancelEdit(s.key)"
                  >
                    {{ t("common.cancel") }}
                  </button>
                </div>
              </template>
              <button
                v-else
                class="text-xs text-blue-600 hover:underline"
                @click="startEdit(s.key, s.value)"
              >
                {{ t("settings.edit") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else class="mt-4 text-gray-500">{{ t("settings.empty") }}</p>
  </div>
</template>
