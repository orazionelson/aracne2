import { config } from "@vue/test-utils";
import { createI18n } from "vue-i18n";
import en from "@/locales/en.json";
import it from "@/locales/it.json";

// Global i18n instance for all component tests.
const i18n = createI18n({
  locale: "en",
  fallbackLocale: "en",
  messages: { en, it },
  legacy: false,
});

config.global.plugins = [i18n];
