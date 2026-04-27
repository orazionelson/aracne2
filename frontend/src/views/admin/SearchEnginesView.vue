<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ t("search_engines.title") }}</h1>
      <button
        class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        @click="openCreate"
      >
        + {{ t("search_engines.new") }}
      </button>
    </div>

    <!-- Filter toolbar -->
    <div class="mb-4 flex items-center gap-3">
      <input
        v-model="filterName"
        type="search"
        :placeholder="t('search_engines.filter_placeholder')"
        class="w-64 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
      />
      <span class="text-xs text-gray-400">
        {{ filteredEngines.length }} / {{ store.engines.length }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="py-12 text-center text-sm text-gray-400">
      {{ t("common.loading") }}
    </div>

    <!-- Empty state — no engines at all -->
    <div
      v-else-if="store.engines.length === 0"
      class="rounded border border-dashed border-gray-300 py-16 text-center text-sm text-gray-400"
    >
      {{ t("search_engines.empty") }}
    </div>

    <!-- Empty state — filter no match -->
    <div
      v-else-if="filteredEngines.length === 0"
      class="rounded border border-dashed border-gray-300 py-12 text-center text-sm text-gray-400"
    >
      {{ t("search_engines.no_results") }}
    </div>

    <!-- Engine list -->
    <div v-else class="divide-y divide-gray-200 rounded border border-gray-200 bg-white">
      <div
        v-for="engine in filteredEngines"
        :key="engine.slug"
        class="flex items-center gap-4 px-4 py-3"
      >
        <!-- Info -->
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="font-medium text-gray-900">{{ engine.title }}</span>
            <code class="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              {{ engine.slug }}
            </code>
            <!-- Build status badge -->
            <span
              v-if="engine.build_status !== 'idle'"
              :class="buildBadgeClass(engine.build_status)"
              class="rounded-full px-2 py-0.5 text-xs font-medium"
            >
              {{ t(`search_engines.build_status_${engine.build_status}`) }}
            </span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
            <span>
              {{
                engine.collections.length === 0
                  ? t("search_engines.no_collections_assigned")
                  : t("search_engines.collections_count", { n: engine.collections.length })
              }}
            </span>
            <span v-if="engine.xslt_template_id" class="italic">
              {{ t("search_engines.xslt_assigned") }}
            </span>
            <span v-if="engine.last_build_at" class="text-gray-400">
              {{ t("search_engines.built_at") }}: {{ formatDate(engine.last_build_at) }}
            </span>
            <span v-if="engine.build_error" class="text-red-500" :title="engine.build_error">
              {{ t("search_engines.build_error_short") }}
            </span>
          </div>
        </div>

        <!-- Build -->
        <button
          :disabled="engine.build_status === 'building' || engine.build_status === 'pending'"
          class="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="triggerBuild(engine.slug)"
        >
          {{ t("search_engines.build") }}
        </button>

        <!-- Open built page -->
        <a
          v-if="engine.build_status === 'done'"
          :href="`/api/v1/search-pages/${engine.slug}/`"
          target="_blank"
          rel="noopener"
          class="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          {{ t("search_engines.open") }}
        </a>

        <!-- Clear cache -->
        <button
          v-if="engine.cache_ttl_minutes > 0"
          class="rounded bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-200"
          @click="handleClearCache(engine.slug)"
        >
          {{ t("search_engines.clear_cache") }}
        </button>

        <!-- Incorpora -->
        <button
          class="rounded bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700"
          @click="openEmbed(engine.slug)"
        >
          {{ t("search_engines.embed") }}
        </button>

        <!-- Edit -->
        <button
          class="rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800"
          @click="openEdit(engine.slug)"
        >
          {{ t("search_engines.edit") }}
        </button>

        <!-- Delete -->
        <button
          class="rounded bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200"
          @click="confirmDelete(engine.slug, engine.title)"
        >
          {{ t("search_engines.delete") }}
        </button>
      </div>
    </div>
  </div>

  <!-- ── Full-screen modal ──────────────────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="modalOpen"
      class="fixed inset-0 z-50 flex flex-col bg-white"
      role="dialog"
      aria-modal="true"
    >
      <!-- Modal header -->
      <div class="flex shrink-0 items-center justify-between border-b border-gray-200 px-6 py-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">
            {{ isCreating ? t("search_engines.modal_create_title") : t("search_engines.modal_edit_title") }}
          </h2>
          <p v-if="!isCreating" class="mt-0.5 text-xs text-gray-400">
            {{ editingSlug }}
          </p>
        </div>
        <button
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          @click="closeModal"
        >
          <span class="sr-only">Close</span>
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fill-rule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clip-rule="evenodd"
            />
          </svg>
        </button>
      </div>

      <!-- Tab bar -->
      <div class="flex shrink-0 border-b border-gray-200 px-6">
        <button
          v-for="tab in modalTabs"
          :key="tab.key"
          type="button"
          :class="[
            'mr-1 border-b-2 px-4 py-3 text-sm font-medium transition-colors',
            activeTab === tab.key
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700',
          ]"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <!-- Dot badge: CSS/JS tab when content present, Advanced tab when enabled -->
          <span
            v-if="(tab.key === 'cssjs' && (form.custom_css || form.custom_js)) ||
                  (tab.key === 'advanced' && form.advanced_search_enabled)"
            class="ml-1.5 inline-flex h-2 w-2 rounded-full bg-indigo-500"
          />
        </button>
      </div>

      <!-- Modal content -->
      <div class="flex-1 overflow-y-auto px-6 py-6">
        <form class="mx-auto max-w-xl space-y-5" @submit.prevent="saveForm">

          <!-- ── Tab: General ──────────────────────────────────────────────── -->
          <template v-if="activeTab === 'general'">
            <!-- Slug (create only) -->
            <div v-if="isCreating">
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.slug_label") }}
              </label>
              <input
                v-model="form.slug"
                type="text"
                required
                pattern="^[a-z0-9_-]+$"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                :placeholder="t('search_engines.slug_placeholder')"
              />
              <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.slug_hint") }}</p>
            </div>

            <!-- Title -->
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.title_label") }}
              </label>
              <input
                v-model="form.title"
                type="text"
                required
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
              />
            </div>

            <!-- XSLT template -->
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.xslt_label") }}
              </label>
              <select
                v-model="form.xslt_template_id"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
              >
                <option :value="null">{{ t("search_engines.xslt_none") }}</option>
                <option
                  v-for="tpl in xsltStore.templates"
                  :key="tpl.id"
                  :value="tpl.id"
                >
                  {{ tpl.name }}
                </option>
              </select>
              <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.xslt_hint") }}</p>
            </div>

            <!-- Collections multiselect -->
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.collections_label") }}
              </label>
              <div
                v-if="store.publicCollections.length === 0"
                class="rounded border border-dashed border-gray-300 py-6 text-center text-xs text-gray-400"
              >
                {{ t("search_engines.no_public_collections") }}
              </div>
              <div
                v-else
                class="max-h-56 overflow-y-auto rounded border border-gray-200"
              >
                <label
                  v-for="col in store.publicCollections"
                  :key="col.id"
                  class="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    :value="col.id"
                    v-model="form.collection_ids"
                    class="h-4 w-4 rounded border-gray-300 text-indigo-600"
                  />
                  <span class="text-sm text-gray-800">{{ col.title }}</span>
                  <code class="ml-auto text-xs text-gray-400">{{ col.slug }}</code>
                </label>
              </div>
              <p class="mt-1 text-xs text-gray-400">
                {{ t("search_engines.collections_hint") }}
              </p>
            </div>

            <!-- Cache TTL -->
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.cache_ttl_label") }}
              </label>
              <input
                v-model.number="form.cache_ttl_minutes"
                type="number"
                min="0"
                max="10080"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
              />
              <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.cache_ttl_hint") }}</p>
            </div>

            <!-- Page appearance -->
            <div class="space-y-3 rounded border border-gray-200 px-4 py-3">
              <p class="text-xs font-semibold text-gray-700">{{ t("search_engines.appearance_label") }}</p>

              <!-- Page background color -->
              <div class="flex items-center gap-3">
                <label class="w-40 shrink-0 text-xs text-gray-600">
                  {{ t("search_engines.page_bg_color_label") }}
                </label>
                <input
                  v-model="form.page_bg_color"
                  type="color"
                  class="h-8 w-12 cursor-pointer rounded border border-gray-300 p-0.5"
                />
                <button
                  type="button"
                  class="text-xs text-gray-400 hover:text-gray-600"
                  @click="form.page_bg_color = PAGE_BG_DEFAULT"
                >
                  {{ t("search_engines.color_reset") }}
                </button>
              </div>

              <!-- Header background color -->
              <div class="flex items-center gap-3">
                <label class="w-40 shrink-0 text-xs text-gray-600">
                  {{ t("search_engines.header_bg_color_label") }}
                </label>
                <input
                  v-model="form.header_bg_color"
                  type="color"
                  :disabled="form.header_hidden"
                  class="h-8 w-12 cursor-pointer rounded border border-gray-300 p-0.5 disabled:opacity-40"
                />
                <button
                  type="button"
                  :disabled="form.header_hidden"
                  class="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-40"
                  @click="form.header_bg_color = HEADER_BG_DEFAULT"
                >
                  {{ t("search_engines.color_reset") }}
                </button>
              </div>

              <!-- Hide header -->
              <label class="flex cursor-pointer items-center gap-2">
                <input
                  v-model="form.header_hidden"
                  type="checkbox"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                <span class="text-xs text-gray-700">{{ t("search_engines.header_hidden_label") }}</span>
              </label>
            </div>

            <!-- Footer -->
            <div class="space-y-2">
              <label class="mb-1 block text-xs font-medium text-gray-700">
                {{ t("search_engines.footer_text_label") }}
              </label>
              <textarea
                v-model="form.footer_text"
                rows="3"
                :disabled="form.footer_hidden"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none disabled:opacity-40"
                :placeholder="t('search_engines.footer_text_placeholder')"
              />
              <label class="flex cursor-pointer items-center gap-2">
                <input
                  v-model="form.footer_hidden"
                  type="checkbox"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                <span class="text-xs text-gray-700">{{ t("search_engines.footer_hidden_label") }}</span>
              </label>
              <p class="text-xs text-gray-400">{{ t("search_engines.footer_text_hint") }}</p>
            </div>
          </template>

          <!-- ── Tab: CSS/JS ──────────────────────────────────────────────── -->
          <template v-if="activeTab === 'cssjs'">
            <!-- Custom CSS -->
            <div>
              <label class="mb-1 block text-xs font-semibold text-gray-700">
                {{ t("search_engines.cssjs_custom_css") }}
              </label>
              <p class="mb-1 text-xs text-gray-500">{{ t("search_engines.cssjs_css_hint") }}</p>
              <textarea
                v-model="form.custom_css"
                rows="12"
                spellcheck="false"
                class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none"
              />
            </div>

            <!-- Custom JS -->
            <div>
              <label class="mb-1 block text-xs font-semibold text-gray-700">
                {{ t("search_engines.cssjs_custom_js") }}
              </label>
              <p class="mb-1 text-xs text-gray-500">{{ t("search_engines.cssjs_js_hint") }}</p>
              <label class="mb-3 flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  v-model="form.include_jquery"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span class="text-xs text-gray-700">{{ t("search_engines.cssjs_include_jquery") }}</span>
              </label>
              <textarea
                v-model="form.custom_js"
                rows="12"
                spellcheck="false"
                class="w-full rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:outline-none"
              />
            </div>
          </template>

          <!-- ── Tab: Advanced Search ──────────────────────────────────────── -->
          <template v-if="activeTab === 'advanced'">
            <!-- Enable toggle -->
            <div>
              <label class="flex cursor-pointer items-center gap-2">
                <input
                  v-model="form.advanced_search_enabled"
                  type="checkbox"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                <span class="text-sm font-medium text-gray-700">
                  {{ t("search_engines.advanced_search_toggle") }}
                </span>
              </label>
              <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.advanced_search_hint") }}</p>
            </div>

            <!-- Config panel (visible only when enabled) -->
            <template v-if="form.advanced_search_enabled">
              <!-- Datalists for autocomplete -->
              <datalist id="dl-elements">
                <option v-for="name in availableElementNames" :key="name" :value="name" />
              </datalist>
              <datalist id="dl-attrs">
                <option v-for="attr in availableAttrNames" :key="attr" :value="attr" />
              </datalist>

              <!-- Tags refresh bar -->
              <div class="flex items-center gap-2 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
                <span v-if="tagsLoading">{{ t("search_engines.advanced_tags_loading") }}</span>
                <span v-else-if="availableElementNames.length > 0">
                  {{ t("search_engines.advanced_tags_loaded", { n: availableElementNames.length }) }}
                </span>
                <span v-else>{{ t("search_engines.advanced_tags_empty") }}</span>
                <button
                  type="button"
                  :disabled="tagsLoading"
                  class="ml-auto rounded bg-white px-2 py-1 text-xs text-indigo-600 border border-indigo-200 hover:bg-indigo-50 disabled:opacity-50"
                  @click="loadAvailableTags"
                >
                  {{ t("search_engines.advanced_tags_refresh") }}
                </button>
              </div>

              <!-- Named entity tags -->
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-sm font-medium text-gray-700">
                    {{ t("search_engines.advanced_named_tags_label") }}
                  </span>
                  <button
                    type="button"
                    class="text-xs text-indigo-600 hover:underline"
                    @click="addTag"
                  >
                    + {{ t("search_engines.advanced_add_tag") }}
                  </button>
                </div>
                <p class="text-xs text-gray-400">{{ t("search_engines.advanced_named_tags_hint") }}</p>

                <div
                  v-for="(tag, idx) in form.advanced_search_config.named_tags"
                  :key="idx"
                  class="flex items-center gap-2"
                >
                  <input
                    v-model="tag.label"
                    type="text"
                    :placeholder="t('search_engines.advanced_tag_label_placeholder')"
                    class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                  />
                  <input
                    v-model="tag.element"
                    type="text"
                    list="dl-elements"
                    :placeholder="t('search_engines.advanced_tag_element_placeholder')"
                    class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                  />
                  <button
                    type="button"
                    class="shrink-0 text-xs text-red-500 hover:text-red-700"
                    @click="removeTag(idx)"
                  >
                    {{ t("search_engines.advanced_remove") }}
                  </button>
                </div>

                <p
                  v-if="form.advanced_search_config.named_tags.length === 0"
                  class="text-xs italic text-gray-400"
                >
                  {{ t("search_engines.advanced_named_tags_hint") }}
                </p>
              </div>

              <!-- Separator -->
              <hr class="border-gray-200" />

              <!-- Attribute filters -->
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-sm font-medium text-gray-700">
                    {{ t("search_engines.advanced_attr_filters_label") }}
                  </span>
                  <button
                    type="button"
                    class="text-xs text-indigo-600 hover:underline"
                    @click="addAttrFilter"
                  >
                    + {{ t("search_engines.advanced_add_filter") }}
                  </button>
                </div>
                <p class="text-xs text-gray-400">{{ t("search_engines.advanced_attr_filters_hint") }}</p>

                <div
                  v-for="(filter, idx) in form.advanced_search_config.attribute_filters"
                  :key="idx"
                  class="flex items-center gap-2"
                >
                  <input
                    v-model="filter.label"
                    type="text"
                    :placeholder="t('search_engines.advanced_attr_label_placeholder')"
                    class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                  />
                  <input
                    v-model="filter.attribute"
                    type="text"
                    list="dl-attrs"
                    :placeholder="t('search_engines.advanced_attr_attribute_placeholder')"
                    class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-indigo-400 focus:outline-none"
                  />
                  <button
                    type="button"
                    class="shrink-0 text-xs text-red-500 hover:text-red-700"
                    @click="removeAttrFilter(idx)"
                  >
                    {{ t("search_engines.advanced_remove") }}
                  </button>
                </div>
              </div>
            </template>

            <!-- Disabled state hint -->
            <div
              v-else
              class="rounded border border-dashed border-gray-200 py-10 text-center text-sm text-gray-400"
            >
              {{ t("search_engines.advanced_disabled_hint") }}
            </div>
          </template>

          <!-- Error (always visible regardless of active tab) -->
          <div v-if="formError" class="rounded bg-red-50 px-3 py-2 text-xs text-red-700">
            {{ formError }}
          </div>
        </form>
      </div>

      <!-- Modal action bar -->
      <div class="flex shrink-0 items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
        <button
          type="button"
          class="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          @click="closeModal"
        >
          {{ t("search_engines.cancel") }}
        </button>
        <button
          type="button"
          :disabled="saving"
          class="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          @click="saveForm"
        >
          {{ saving ? t("common.saving") : t("search_engines.save") }}
        </button>
      </div>
    </div>
  </Teleport>

  <!-- ── Embed modal ─────────────────────────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="embedModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
      role="dialog"
      aria-modal="true"
      @click.self="closeEmbedModal"
    >
      <div class="flex w-full max-w-2xl flex-col rounded-lg bg-white shadow-xl" style="max-height:90vh">
        <!-- Header -->
        <div class="flex shrink-0 items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ t("search_engines.embed_modal_title") }}</h2>
            <p class="mt-0.5 text-xs text-gray-400">{{ embedSlug }}</p>
          </div>
          <button class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600" @click="closeEmbedModal">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>

        <!-- Tabs -->
        <div class="flex shrink-0 border-b border-gray-200 px-6">
          <button
            v-for="tab in embedTabs"
            :key="tab.key"
            type="button"
            :class="['mr-1 border-b-2 px-4 py-3 text-sm font-medium transition-colors', embedActiveTab === tab.key ? 'border-teal-600 text-teal-600' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700']"
            @click="embedActiveTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto px-6 py-6">

          <!-- Tab: Configura -->
          <template v-if="embedActiveTab === 'config'">
            <div class="space-y-5">
              <!-- Enable toggle -->
              <div>
                <label class="flex cursor-pointer items-center gap-2">
                  <input v-model="embedForm.embed_enabled" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600" />
                  <span class="text-sm font-medium text-gray-700">{{ t("search_engines.embed_enabled_label") }}</span>
                </label>
                <p class="mt-1 text-xs text-gray-400">{{ t("search_engines.embed_enabled_hint") }}</p>
              </div>

              <template v-if="embedForm.embed_enabled">
                <!-- Mode -->
                <div>
                  <p class="mb-2 text-xs font-medium text-gray-700">{{ t("search_engines.embed_mode_label") }}</p>
                  <div class="flex flex-col gap-2">
                    <label v-for="opt in embedModeOptions" :key="opt.value" class="flex cursor-pointer items-center gap-2">
                      <input v-model="embedForm.embed_config.mode" type="radio" :value="opt.value" class="h-4 w-4 border-gray-300 text-teal-600" />
                      <span class="text-sm text-gray-700">{{ opt.label }}</span>
                    </label>
                  </div>
                </div>

                <!-- Allowed origins -->
                <div>
                  <p class="mb-1 text-xs font-medium text-gray-700">{{ t("search_engines.embed_origins_label") }}</p>
                  <p class="mb-2 text-xs text-gray-400">{{ t("search_engines.embed_origins_hint") }}</p>
                  <div
                    v-for="(origin, idx) in embedForm.embed_config.allowed_origins"
                    :key="idx"
                    class="mb-1.5 flex items-center gap-2"
                  >
                    <input
                      :value="origin"
                      @input="embedForm.embed_config.allowed_origins[idx] = ($event.target as HTMLInputElement).value"
                      type="url"
                      :placeholder="t('search_engines.embed_origins_placeholder')"
                      class="flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-teal-400 focus:outline-none"
                    />
                    <button type="button" class="shrink-0 text-xs text-red-500 hover:text-red-700" @click="removeOrigin(idx)">
                      {{ t("search_engines.embed_origins_remove") }}
                    </button>
                  </div>
                  <button
                    type="button"
                    class="mt-1 text-xs text-teal-600 hover:underline"
                    @click="addOrigin"
                  >
                    + {{ t("search_engines.embed_origins_add") }}
                  </button>
                  <p v-if="embedForm.embed_config.allowed_origins.length === 0" class="mt-1 text-xs italic text-amber-600">
                    {{ t("search_engines.embed_origins_open_warning") }}
                  </p>
                </div>
              </template>
            </div>
          </template>

          <!-- Tab: Snippet -->
          <template v-if="embedActiveTab === 'snippet'">
            <div v-if="!embedForm.embed_enabled" class="rounded border border-dashed border-gray-200 py-10 text-center text-sm text-gray-400">
              {{ t("search_engines.embed_snippet_disabled") }}
            </div>
            <div v-else class="space-y-4">
              <!-- Sub-tab bar -->
              <div class="flex gap-1 border-b border-gray-200">
                <button
                  v-for="st in snippetSubTabs"
                  :key="st.key"
                  type="button"
                  :class="['border-b-2 px-3 py-2 text-xs font-medium transition-colors', snippetTab === st.key ? 'border-teal-600 text-teal-600' : 'border-transparent text-gray-500 hover:text-gray-700']"
                  @click="snippetTab = st.key"
                >
                  {{ st.label }}
                </button>
              </div>

              <!-- widget.js snippet -->
              <div v-if="snippetTab === 'widgetjs'">
                <p class="mb-2 text-xs text-gray-500">{{ t("search_engines.embed_snippet_widgetjs_hint") }}</p>
                <div class="relative">
                  <textarea
                    :value="widgetJsSnippet"
                    readonly
                    rows="5"
                    class="w-full rounded border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-xs"
                  />
                  <button
                    type="button"
                    class="absolute right-2 top-2 rounded bg-teal-600 px-2 py-1 text-xs text-white hover:bg-teal-700"
                    @click="copySnippet(widgetJsSnippet)"
                  >
                    {{ copied ? t("search_engines.embed_snippet_copied") : t("search_engines.embed_snippet_copy") }}
                  </button>
                </div>
              </div>

              <!-- Inline snippet -->
              <div v-if="snippetTab === 'inline'">
                <p class="mb-2 text-xs text-gray-500">{{ t("search_engines.embed_snippet_inline_hint") }}</p>
                <div class="relative">
                  <textarea
                    :value="inlineSnippet"
                    readonly
                    rows="12"
                    class="w-full rounded border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-xs"
                  />
                  <button
                    type="button"
                    class="absolute right-2 top-2 rounded bg-teal-600 px-2 py-1 text-xs text-white hover:bg-teal-700"
                    @click="copySnippet(inlineSnippet)"
                  >
                    {{ copied ? t("search_engines.embed_snippet_copied") : t("search_engines.embed_snippet_copy") }}
                  </button>
                </div>
              </div>
            </div>
          </template>

          <!-- Tab: Statistiche -->
          <template v-if="embedActiveTab === 'stats'">
            <div v-if="embedLogsLoading" class="py-8 text-center text-sm text-gray-400">{{ t("common.loading") }}</div>
            <div v-else-if="embedLogs.length === 0" class="rounded border border-dashed border-gray-200 py-10 text-center text-sm text-gray-400">
              {{ t("search_engines.embed_log_empty") }}
            </div>
            <div v-else>
              <table class="w-full text-xs">
                <thead>
                  <tr class="border-b border-gray-200 text-left text-gray-500">
                    <th class="pb-2 pr-3 font-medium">{{ t("search_engines.embed_log_origin") }}</th>
                    <th class="pb-2 pr-3 font-medium">{{ t("search_engines.embed_log_query") }}</th>
                    <th class="pb-2 pr-3 font-medium">{{ t("search_engines.embed_log_mode") }}</th>
                    <th class="pb-2 pr-3 font-medium">{{ t("search_engines.embed_log_status") }}</th>
                    <th class="pb-2 font-medium">{{ t("search_engines.embed_log_date") }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  <tr v-for="log in embedLogs" :key="log.id">
                    <td class="py-1.5 pr-3 text-gray-700 font-mono max-w-[14rem] truncate" :title="log.origin ?? ''">
                      {{ log.origin ?? '—' }}
                    </td>
                    <td class="py-1.5 pr-3 text-gray-700 max-w-[10rem] truncate" :title="log.query">{{ log.query }}</td>
                    <td class="py-1.5 pr-3 text-gray-500">{{ log.mode }}</td>
                    <td class="py-1.5 pr-3">
                      <span :class="log.allowed ? 'text-green-600' : 'text-red-600'" class="font-medium">
                        {{ log.allowed ? t("search_engines.embed_log_allowed") : t("search_engines.embed_log_blocked") }}
                      </span>
                    </td>
                    <td class="py-1.5 text-gray-400">{{ formatDate(log.requested_at) }}</td>
                  </tr>
                </tbody>
              </table>
              <!-- Pagination -->
              <div class="mt-4 flex items-center justify-between text-xs text-gray-500">
                <span>{{ t("search_engines.embed_log_total", { n: embedLogTotal }) }}</span>
                <div class="flex gap-2">
                  <button :disabled="embedLogPage <= 1" class="rounded border border-gray-200 px-2 py-1 disabled:opacity-40" @click="loadEmbedLogs(embedLogPage - 1)">‹</button>
                  <span>{{ embedLogPage }} / {{ embedLogTotalPages }}</span>
                  <button :disabled="embedLogPage >= embedLogTotalPages" class="rounded border border-gray-200 px-2 py-1 disabled:opacity-40" @click="loadEmbedLogs(embedLogPage + 1)">›</button>
                </div>
              </div>
            </div>
          </template>

        </div>

        <!-- Footer -->
        <div class="flex shrink-0 items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
          <button type="button" class="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100" @click="closeEmbedModal">
            {{ t("search_engines.cancel") }}
          </button>
          <button
            type="button"
            :disabled="embedSaving"
            class="rounded bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50"
            @click="saveEmbedConfig"
          >
            {{ embedSaving ? t("common.saving") : t("search_engines.embed_save") }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  useSearchEngineStore,
  type AdvancedSearchConfig,
  type EmbedConfig,
  type EmbedLogEntry,
  type SearchEngineBuildStatus,
} from "@/stores/search_engines";
import { useXsltTemplateStore } from "@/stores/xslt_templates";

const { t } = useI18n();
const store = useSearchEngineStore();
const xsltStore = useXsltTemplateStore();

// ── Filter ────────────────────────────────────────────────────────────────────

const filterName = ref("");

const filteredEngines = computed(() => {
  if (!filterName.value) return store.engines;
  const q = filterName.value.toLowerCase();
  return store.engines.filter(
    (e) =>
      e.title.toLowerCase().includes(q) || e.slug.toLowerCase().includes(q),
  );
});

// ── Modal state ───────────────────────────────────────────────────────────────

type ModalTab = "general" | "cssjs" | "advanced";

const activeTab = ref<ModalTab>("general");

const modalTabs = computed(() => [
  { key: "general" as ModalTab,  label: t("search_engines.tab_general") },
  { key: "cssjs"   as ModalTab,  label: t("search_engines.tab_cssjs") },
  { key: "advanced" as ModalTab, label: t("search_engines.tab_advanced") },
]);

const modalOpen = ref(false);
const isCreating = ref(false);
const editingSlug = ref<string | null>(null);
const saving = ref(false);
const formError = ref<string | null>(null);

interface FormState {
  slug: string;
  title: string;
  xslt_template_id: string | null;
  collection_ids: string[];
  cache_ttl_minutes: number;
  footer_text: string;
  footer_hidden: boolean;
  page_bg_color: string;
  header_bg_color: string;
  header_hidden: boolean;
  custom_css: string;
  custom_js: string;
  include_jquery: boolean;
  advanced_search_enabled: boolean;
  advanced_search_config: AdvancedSearchConfig;
}

const PAGE_BG_DEFAULT   = "#f9fafb";
const HEADER_BG_DEFAULT = "#1e3a5f";

const defaultForm = (): FormState => ({
  slug: "",
  title: "",
  xslt_template_id: null,
  collection_ids: [],
  cache_ttl_minutes: 60,
  footer_text: "",
  footer_hidden: false,
  page_bg_color: PAGE_BG_DEFAULT,
  header_bg_color: HEADER_BG_DEFAULT,
  header_hidden: false,
  custom_css: "",
  custom_js: "",
  include_jquery: false,
  advanced_search_enabled: false,
  advanced_search_config: { named_tags: [], attribute_filters: [] },
});

const form = ref<FormState>(defaultForm());

function openCreate(): void {
  isCreating.value = true;
  editingSlug.value = null;
  form.value = defaultForm();
  formError.value = null;
  availableTags.value = {};
  activeTab.value = "general";
  modalOpen.value = true;
}

function openEdit(slug: string): void {
  const engine = store.engines.find((e) => e.slug === slug);
  if (!engine) return;
  isCreating.value = false;
  editingSlug.value = slug;
  availableTags.value = {};
  activeTab.value = "general";
  form.value = {
    slug: engine.slug,
    title: engine.title,
    xslt_template_id: engine.xslt_template_id,
    collection_ids: engine.collections.map((c) => c.id),
    cache_ttl_minutes: engine.cache_ttl_minutes,
    footer_text: engine.footer_text ?? "",
    footer_hidden: engine.footer_hidden,
    page_bg_color: engine.page_bg_color ?? PAGE_BG_DEFAULT,
    header_bg_color: engine.header_bg_color ?? HEADER_BG_DEFAULT,
    header_hidden: engine.header_hidden,
    custom_css: engine.custom_css ?? "",
    custom_js: engine.custom_js ?? "",
    include_jquery: engine.include_jquery,
    advanced_search_enabled: engine.advanced_search_enabled,
    advanced_search_config: {
      named_tags: engine.advanced_search_config.named_tags.map((t) => ({ ...t })),
      attribute_filters: engine.advanced_search_config.attribute_filters.map((f) => ({ ...f })),
    },
  };
  formError.value = null;
  modalOpen.value = true;
}

function closeModal(): void {
  modalOpen.value = false;
}

function _cleanedAdvancedConfig(): AdvancedSearchConfig {
  // Drop rows with any empty field — the backend enforces min_length=1
  // on every label/element/attribute, so half-filled placeholders that
  // ``addTag`` / ``addAttrFilter`` insert as scratch rows would 422.
  return {
    named_tags: form.value.advanced_search_config.named_tags
      .map((t) => ({ label: t.label.trim(), element: t.element.trim() }))
      .filter((t) => t.label && t.element),
    attribute_filters: form.value.advanced_search_config.attribute_filters
      .map((f) => ({ label: f.label.trim(), attribute: f.attribute.trim() }))
      .filter((f) => f.label && f.attribute),
  };
}

async function saveForm(): Promise<void> {
  formError.value = null;
  if (!form.value.title.trim()) {
    formError.value = t("search_engines.error_title_required");
    return;
  }
  if (isCreating.value && !form.value.slug.trim()) {
    formError.value = t("search_engines.error_slug_required");
    return;
  }
  saving.value = true;
  try {
    const cleanedAdvanced = _cleanedAdvancedConfig();
    if (isCreating.value) {
      await store.create({
        slug: form.value.slug,
        title: form.value.title,
        xslt_template_id: form.value.xslt_template_id,
        collection_ids: form.value.collection_ids,
        cache_ttl_minutes: form.value.cache_ttl_minutes,
        footer_text: form.value.footer_text || null,
        footer_hidden: form.value.footer_hidden,
        page_bg_color: form.value.page_bg_color !== PAGE_BG_DEFAULT ? form.value.page_bg_color : null,
        header_bg_color: form.value.header_bg_color !== HEADER_BG_DEFAULT ? form.value.header_bg_color : null,
        header_hidden: form.value.header_hidden,
        custom_css: form.value.custom_css || null,
        custom_js: form.value.custom_js || null,
        include_jquery: form.value.include_jquery,
        advanced_search_enabled: form.value.advanced_search_enabled,
        advanced_search_config: cleanedAdvanced,
      });
    } else {
      await store.update(editingSlug.value!, {
        title: form.value.title,
        xslt_template_id: form.value.xslt_template_id,
        collection_ids: form.value.collection_ids,
        cache_ttl_minutes: form.value.cache_ttl_minutes,
        footer_text: form.value.footer_text || null,
        footer_hidden: form.value.footer_hidden,
        page_bg_color: form.value.page_bg_color !== PAGE_BG_DEFAULT ? form.value.page_bg_color : null,
        header_bg_color: form.value.header_bg_color !== HEADER_BG_DEFAULT ? form.value.header_bg_color : null,
        header_hidden: form.value.header_hidden,
        custom_css: form.value.custom_css || null,
        custom_js: form.value.custom_js || null,
        include_jquery: form.value.include_jquery,
        advanced_search_enabled: form.value.advanced_search_enabled,
        advanced_search_config: cleanedAdvanced,
      });
    }
    // Persist the cleanup so the form state matches what we just sent.
    form.value.advanced_search_config = {
      named_tags: cleanedAdvanced.named_tags.map((t) => ({ ...t })),
      attribute_filters: cleanedAdvanced.attribute_filters.map((f) => ({ ...f })),
    };
    closeModal();
  } catch (err: unknown) {
    // Surface FastAPI 422 details when present so the user sees the real
    // reason (e.g. "advanced_search_config.named_tags.0.label: too short")
    // instead of just "Request failed with status code 422".
    type AxiosLikeError = {
      response?: {
        data?: {
          error?: { message?: string };
          detail?: unknown;
        };
      };
      message?: string;
    };
    const e = err as AxiosLikeError;
    const apiMsg = e?.response?.data?.error?.message;
    let detailMsg: string | null = null;
    const detail = e?.response?.data?.detail;
    if (Array.isArray(detail)) {
      detailMsg = detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const path = (d.loc ?? []).join(".");
          return `${path}: ${d.msg ?? ""}`;
        })
        .join("; ");
    }
    formError.value =
      apiMsg ?? detailMsg ?? e.message ?? t("search_engines.error_save");
  } finally {
    saving.value = false;
  }
}

// ── Advanced search: available tags from linked collections ──────────────────

const availableTags = ref<Record<string, string[]>>({});
const tagsLoading = ref(false);

/** Sorted element names from the linked collections. */
const availableElementNames = computed(() => Object.keys(availableTags.value).sort());

/** All distinct attribute names across all elements. */
const availableAttrNames = computed(() =>
  [...new Set(Object.values(availableTags.value).flat())].sort(),
);

async function loadAvailableTags(): Promise<void> {
  const slug = editingSlug.value;
  if (!slug) return;
  tagsLoading.value = true;
  try {
    availableTags.value = await store.fetchAvailableTags(slug);
  } catch {
    availableTags.value = {};
  } finally {
    tagsLoading.value = false;
  }
}

// Auto-fetch when the advanced search panel is first opened during an edit.
watch(
  () => form.value.advanced_search_enabled,
  (enabled) => {
    if (enabled && editingSlug.value && Object.keys(availableTags.value).length === 0) {
      void loadAvailableTags();
    }
  },
);

// ── Advanced search config helpers ───────────────────────────────────────────

function addTag(): void {
  form.value.advanced_search_config.named_tags.push({ label: "", element: "" });
}

function removeTag(idx: number): void {
  form.value.advanced_search_config.named_tags.splice(idx, 1);
}

function addAttrFilter(): void {
  form.value.advanced_search_config.attribute_filters.push({ label: "", attribute: "" });
}

function removeAttrFilter(idx: number): void {
  form.value.advanced_search_config.attribute_filters.splice(idx, 1);
}

// ── Build ─────────────────────────────────────────────────────────────────────

function buildBadgeClass(status: SearchEngineBuildStatus): string {
  switch (status) {
    case "done":     return "bg-green-100 text-green-700";
    case "failed":   return "bg-red-100 text-red-700";
    case "building": return "bg-blue-100 text-blue-700";
    case "pending":  return "bg-yellow-100 text-yellow-700";
    default:         return "bg-gray-100 text-gray-500";
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

async function triggerBuild(slug: string): Promise<void> {
  try {
    await store.build(slug);
    // Poll until done or failed (max ~30 s at 2 s intervals).
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts++;
      await store.fetchAll();
      const engine = store.engines.find((e) => e.slug === slug);
      if (!engine || engine.build_status === "done" || engine.build_status === "failed" || attempts >= 15) {
        clearInterval(poll);
      }
    }, 2000);
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_build"));
  }
}

// ── Cache ─────────────────────────────────────────────────────────────────────

async function handleClearCache(slug: string): Promise<void> {
  try {
    const deleted = await store.clearCache(slug);
    window.alert(t("search_engines.cache_cleared", { n: deleted }));
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_clear_cache"));
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function confirmDelete(slug: string, title: string): Promise<void> {
  if (!window.confirm(t("search_engines.delete_confirm", { title }))) return;
  try {
    await store.remove(slug);
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_delete"));
  }
}

// ── Embed modal ───────────────────────────────────────────────────────────────

type EmbedTab = "config" | "snippet" | "stats";
type SnippetTab = "widgetjs" | "inline";

const embedModalOpen = ref(false);
const embedSlug = ref<string>("");
const embedSaving = ref(false);
const embedActiveTab = ref<EmbedTab>("config");
const snippetTab = ref<SnippetTab>("widgetjs");
const copied = ref(false);

interface EmbedFormState {
  embed_enabled: boolean;
  embed_config: EmbedConfig;
}

const embedForm = ref<EmbedFormState>({
  embed_enabled: false,
  embed_config: { mode: "simple", allowed_origins: [] },
});

const embedTabs = computed(() => [
  { key: "config" as EmbedTab,  label: t("search_engines.embed_tab_config") },
  { key: "snippet" as SnippetTab, label: t("search_engines.embed_tab_snippet") },
  { key: "stats" as EmbedTab,   label: t("search_engines.embed_tab_stats") },
]);

const snippetSubTabs = computed(() => [
  { key: "widgetjs" as SnippetTab, label: t("search_engines.embed_snippet_widgetjs") },
  { key: "inline"   as SnippetTab, label: t("search_engines.embed_snippet_inline") },
]);

const embedModeOptions = computed(() => [
  { value: "simple",   label: t("search_engines.embed_mode_simple") },
  { value: "advanced", label: t("search_engines.embed_mode_advanced") },
  { value: "both",     label: t("search_engines.embed_mode_both") },
]);

// Snippets are generated client-side using window.location.origin as API base.
const widgetJsSnippet = computed(() => {
  const base = window.location.origin;
  const slug = embedSlug.value;
  return `<div id="aracne2-${slug}"></div>\n<script\n  src="${base}/api/v1/embed/${slug}/widget.js"\n  data-target="aracne2-${slug}">\n<\/script>`;
});

const inlineSnippet = computed(() => {
  const base = window.location.origin;
  const slug = embedSlug.value;
  const mode = embedForm.value.embed_config.mode;
  return (
    `<div id="aracne2-${slug}"></div>\n` +
    `<script>\n` +
    `/* Aracne2 embed widget — mode: ${mode} */\n` +
    `(function(cfg){\n` +
    `  var s=document.createElement('script');\n` +
    `  s.src=cfg.api+'/api/v1/embed/'+cfg.slug+'/widget.js';\n` +
    `  s.setAttribute('data-target','aracne2-'+cfg.slug);\n` +
    `  document.currentScript.parentNode.insertBefore(s,document.currentScript.nextSibling);\n` +
    `})({\n` +
    `  slug: '${slug}',\n` +
    `  api: '${base}'\n` +
    `});\n` +
    `<\/script>`
  );
});

function openEmbed(slug: string): void {
  const engine = store.engines.find((e) => e.slug === slug);
  if (!engine) return;
  embedSlug.value = slug;
  embedForm.value = {
    embed_enabled: engine.embed_enabled,
    embed_config: {
      mode: engine.embed_config.mode,
      allowed_origins: [...engine.embed_config.allowed_origins],
    },
  };
  embedActiveTab.value = "config";
  snippetTab.value = "widgetjs";
  copied.value = false;
  embedLogs.value = [];
  embedLogPage.value = 1;
  embedLogTotal.value = 0;
  embedLogTotalPages.value = 1;
  embedModalOpen.value = true;
}

function closeEmbedModal(): void {
  embedModalOpen.value = false;
}

function addOrigin(): void {
  embedForm.value.embed_config.allowed_origins.push("");
}

function removeOrigin(idx: number): void {
  embedForm.value.embed_config.allowed_origins.splice(idx, 1);
}

async function copySnippet(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    // Fallback for browsers without clipboard API
  }
}

async function saveEmbedConfig(): Promise<void> {
  embedSaving.value = true;
  try {
    await store.update(embedSlug.value, {
      embed_enabled: embedForm.value.embed_enabled,
      embed_config: {
        mode: embedForm.value.embed_config.mode,
        allowed_origins: embedForm.value.embed_config.allowed_origins.filter((o) => o.trim()),
      },
    });
    closeEmbedModal();
  } catch (err: unknown) {
    window.alert(err instanceof Error ? err.message : t("search_engines.error_save"));
  } finally {
    embedSaving.value = false;
  }
}

// ── Embed stats ───────────────────────────────────────────────────────────────

const embedLogs = ref<EmbedLogEntry[]>([]);
const embedLogsLoading = ref(false);
const embedLogPage = ref(1);
const embedLogTotal = ref(0);
const embedLogTotalPages = ref(1);

async function loadEmbedLogs(page: number = 1): Promise<void> {
  embedLogsLoading.value = true;
  try {
    const res = await store.fetchEmbedLogs(embedSlug.value, page);
    embedLogs.value = res.data;
    embedLogPage.value = res.pagination.page;
    embedLogTotal.value = res.pagination.total;
    embedLogTotalPages.value = res.pagination.total_pages;
  } catch {
    embedLogs.value = [];
  } finally {
    embedLogsLoading.value = false;
  }
}

// Auto-load logs when the stats tab is opened.
watch(embedActiveTab, (tab) => {
  if (tab === "stats" && embedSlug.value) {
    void loadEmbedLogs(1);
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([
    store.fetchAll(),
    store.fetchPublicCollections(),
    xsltStore.fetchTemplates(),
  ]);
});
</script>
