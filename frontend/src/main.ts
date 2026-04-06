import { createApp } from "vue";
import { createPinia } from "pinia";
import { createI18n } from "vue-i18n";

import App from "./App.vue";
import router from "./router";
import en from "./locales/en.json";
import it from "./locales/it.json";
import "./assets/main.css";

const i18n = createI18n({
  legacy: false,
  locale: "it",
  fallbackLocale: "en",
  messages: { en, it },
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(i18n);
app.mount("#app");
